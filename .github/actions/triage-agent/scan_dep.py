#!/usr/bin/env python3
"""
scan_dep.py

Reads repo_scan.json, computes dependency centrality for each component --
the number of other known components that directly depend on it, based on
each ecosystem's real dependency graph -- and writes dependency_scan.json.

Usage:
    python3 scan_dep.py <repo_scan.json> <repo_path> <dependency_scan.json>
"""

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request

try:
    import tomllib
except ImportError:
    tomllib = None


EXCLUDED_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "dist", "build", "out", "target",
    "vendor", "venv", ".venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".tox",
    ".gradle", ".idea", ".vscode", ".next", "coverage",
}

MAVEN_REPO_BASE_URL = os.environ.get("MAVEN_REPO_BASE_URL", "https://repo1.maven.org/maven2")
DOWNLOAD_TIMEOUT_SECONDS = 15
POM_DOWNLOAD_CACHE_DIR = os.path.join(tempfile.gettempdir(), "scan_dep_pom_cache")


_DEPENDENCY_GRAPH_CACHE = {}


def _normalize_pip_name(name):
    """
    Normalizes a pip distribution name per PEP 503 (lowercase, runs of
    -_. collapsed to a single -), so names from different sources
    (lockfiles, installed metadata, components.json) compare equal.

    Sample input:
        name = "PyYAML_extra.Thing"

    Sample output:
        "pyyaml-extra-thing"
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _find_file(repo_path, filename, max_depth=3):
    """
    Searches repo_path, up to max_depth directories deep, for a file named
    filename, skipping excluded directories. Returns the first match or
    None.

    Sample input:
        repo_path = "test_repo"
        filename = "package-lock.json"

    Sample output:
        "test_repo/package-lock.json"
    """
    repo_path = os.path.abspath(repo_path)
    base_depth = repo_path.rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(repo_path):
        depth = root.rstrip(os.sep).count(os.sep) - base_depth
        if depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        if filename in files:
            return os.path.join(root, filename)

    return None


def _load_npm_edges(repo_path):
    """
    Parses package-lock.json (v1 nested or v2/v3 flat format) into a
    direct-dependency graph: package name -> set of package names it
    directly depends on. Returns None if no lockfile is found, so callers
    can distinguish "we verified zero dependents" from "we had nothing to
    check against."

    Sample input:
        repo_path = "test_repo" (containing a package-lock.json where
        "express" depends on "lodash")

    Sample output:
        {"express": {"lodash"}, "lodash": set()}
    """
    lockfile_path = _find_file(repo_path, "package-lock.json")
    if lockfile_path is None:
        return None

    with open(lockfile_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return None

    edges = {}

    packages = data.get("packages")
    if isinstance(packages, dict):
        for path, info in packages.items():
            if path == "" or not isinstance(info, dict):
                continue
            name = path.rsplit("node_modules/", 1)[-1]
            deps = set(info.get("dependencies", {}).keys())
            edges.setdefault(name, set()).update(deps)
        return edges

    def _walk_v1(tree):
        for name, info in (tree or {}).items():
            if not isinstance(info, dict):
                continue
            deps = set(info.get("requires", {}).keys())
            edges.setdefault(name, set()).update(deps)
            nested = info.get("dependencies")
            if isinstance(nested, dict):
                _walk_v1(nested)

    _walk_v1(data.get("dependencies"))
    return edges


def _load_requirements_edges(repo_path):
    """
    Parses requirements.txt into a graph containing only top-level
    dependencies. Since requirements.txt does not record transitive
    dependencies, each package is mapped to an empty dependency set.
    """
    req_path = _find_file(repo_path, "requirements.txt")
    if req_path is None:
        return {}

    edges = {}

    with open(req_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            name = re.split(r"[<>=!~\[\s]", line, 1)[0].strip()
            if name:
                edges[_normalize_pip_name(name)] = set()

    return edges


def _load_poetry_lock_edges(repo_path):
    """
    Parses poetry.lock's [[package]]/[package.dependencies] sections into a
    direct-dependency graph. Returns {} if poetry.lock isn't found or
    tomllib isn't available (Python < 3.11).

    Sample output:
        {"requests": {"certifi", "charset-normalizer", "idna", "urllib3"}}
    """
    if tomllib is None:
        return {}

    lockfile_path = _find_file(repo_path, "poetry.lock")
    if lockfile_path is None:
        return {}

    with open(lockfile_path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            return {}

    edges = {}
    for pkg in data.get("package", []):
        name = _normalize_pip_name(pkg.get("name", ""))
        if not name:
            continue
        deps = {_normalize_pip_name(dep) for dep in pkg.get("dependencies", {}).keys()}
        edges[name] = deps

    return edges


def _load_pip_edges(repo_path):
    """
    Builds a pip dependency graph using repository files only.
    Prefers poetry.lock, then falls back to requirements.txt.
    Returns None if neither source is available.
    """
    edges = _load_poetry_lock_edges(repo_path)
    if edges:
        return edges

    edges = _load_requirements_edges(repo_path)
    if edges:
        return edges

    return None


def _iter_build_files(repo_path):
    """
    Walks repo_path and returns (filepath, text) for every pom.xml,
    build.gradle, and build.gradle.kts file found.

    Sample input:
        repo_path = "test_repo"

    Sample output:
        [("test_repo/pom.xml", "<project>...<version>2.15.2</version>...")]
    """
    build_filenames = {"pom.xml", "build.gradle", "build.gradle.kts"}
    results = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for filename in files:
            if filename.lower() not in build_filenames:
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            results.append((filepath, text))
    return results


def _resolve_version_from_repo(repo_path, group_id, artifact_id):
    """
    Scans pom.xml/build.gradle/build.gradle.kts files in repo_path for a
    literal version declared for group_id:artifact_id. Placeholder
    versions (Maven ${property}, Gradle variables) are skipped rather than
    guessed at.

    Sample input:
        repo_path = "test_repo"
        group_id = "com.fasterxml.jackson.core"
        artifact_id = "jackson-databind"

    Sample output:
        "2.15.2"
    """
    pom_dep = re.compile(
        r"<dependency>\s*"
        r"<groupId>\s*" + re.escape(group_id) + r"\s*</groupId>\s*"
        r"<artifactId>\s*" + re.escape(artifact_id) + r"\s*</artifactId>\s*"
        r"<version>\s*([^<$\s]+)\s*</version>",
        re.DOTALL,
    )
    pom_dep_reordered = re.compile(
        r"<dependency>\s*"
        r"<artifactId>\s*" + re.escape(artifact_id) + r"\s*</artifactId>\s*"
        r"<groupId>\s*" + re.escape(group_id) + r"\s*</groupId>\s*"
        r"<version>\s*([^<$\s]+)\s*</version>",
        re.DOTALL,
    )
    coordinate = re.escape(f"{group_id}:{artifact_id}")
    gradle_dep = re.compile(coordinate + r":([\w.\-]+)")

    for filepath, text in _iter_build_files(repo_path):
        if os.path.basename(filepath).lower() == "pom.xml":
            match = pom_dep.search(text) or pom_dep_reordered.search(text)
            if match:
                return match.group(1)
        else:
            match = gradle_dep.search(text)
            if match:
                return match.group(1)

    return None


def _download_pom(group_id, artifact_id, version):
    """
    Downloads the POM file for group_id:artifact_id:version from
    MAVEN_REPO_BASE_URL, caching it in a temp directory, and returns the
    local path. Returns None if the download fails.

    Sample input:
        group_id = "com.fasterxml.jackson.core"
        artifact_id = "jackson-databind"
        version = "2.15.2"

    Sample output:
        "/tmp/scan_dep_pom_cache/jackson-databind-2.15.2.pom"
    """
    os.makedirs(POM_DOWNLOAD_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(POM_DOWNLOAD_CACHE_DIR, f"{artifact_id}-{version}.pom")
    if os.path.isfile(cache_path):
        return cache_path

    group_path = "/".join(group_id.split("."))
    url = f"{MAVEN_REPO_BASE_URL}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"

    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            data = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        print(f"[scan_dep] Warning: failed to download POM {url} ({exc})", file=sys.stderr)
        return None

    tmp_path = cache_path + ".partial"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.replace(tmp_path, cache_path)

    return cache_path


def _parse_pom_dependencies(pom_path):
    """
    Parses a POM file's <dependencies> section into a set of
    "groupId:artifactId" strings, skipping test-scoped dependencies.

    Sample input:
        pom_path = ".../jackson-databind-2.15.2.pom"

    Sample output:
        {"com.fasterxml.jackson.core:jackson-core", "com.fasterxml.jackson.core:jackson-annotations"}
    """
    try:
        with open(pom_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return set()

    deps = set()
    for block in re.findall(r"<dependency>(.*?)</dependency>", text, re.DOTALL):
        group_match = re.search(r"<groupId>\s*([^<\s]+)\s*</groupId>", block)
        artifact_match = re.search(r"<artifactId>\s*([^<\s]+)\s*</artifactId>", block)
        scope_match = re.search(r"<scope>\s*([^<\s]+)\s*</scope>", block)
        if not group_match or not artifact_match:
            continue
        if scope_match and scope_match.group(1).strip().lower() == "test":
            continue
        deps.add(f"{group_match.group(1)}:{artifact_match.group(1)}")

    return deps


def _load_jvm_edges(repo_path, component_names):
    """
    Builds a direct-dependency graph for the given maven/gradle components
    by resolving each one's exact version from the repo's build files,
    downloading its POM from Maven Central, and reading its declared
    <dependencies>. A component whose version or POM can't be resolved
    simply contributes no outgoing edges of its own -- it can still be
    correctly counted as a dependent of others.

    Sample input:
        component_names = ["com.fasterxml.jackson.core:jackson-databind"]

    Sample output:
        {"com.fasterxml.jackson.core:jackson-databind": {"com.fasterxml.jackson.core:jackson-core"}}
    """
    edges = {}
    for component in component_names:
        group_id, _, artifact_id = component.partition(":")
        if not artifact_id:
            edges[component] = set()
            continue

        version = _resolve_version_from_repo(repo_path, group_id, artifact_id)
        if version is None:
            edges[component] = set()
            continue

        pom_path = _download_pom(group_id, artifact_id, version)
        if pom_path is None:
            edges[component] = set()
            continue

        edges[component] = _parse_pom_dependencies(pom_path)

    return edges


def _build_dependency_graph(repo_path, components):
    """
    Builds a direct-dependency graph (name -> set of direct dependency
    names) for each ecosystem present in components, scoped per ecosystem
    since cross-ecosystem edges aren't meaningful. Cached per repo_path so
    it's only built once even though centrality is looked up once per
    component.

    Sample input:
        repo_path = "test_repo"
        components = {"lodash": {"ecosystem": "npm"}, "express": {"ecosystem": "npm"}}

    Sample output:
        {"npm": {"express": {"lodash"}, "lodash": set()}}
    """
    if repo_path in _DEPENDENCY_GRAPH_CACHE:
        return _DEPENDENCY_GRAPH_CACHE[repo_path]

    names_by_ecosystem = {}
    for name, details in components.items():
        eco = (details.get("ecosystem") or "").strip().lower()
        names_by_ecosystem.setdefault(eco, []).append(name)

    graph = {}
    for eco, names in names_by_ecosystem.items():
        if eco == "npm":
            graph[eco] = _load_npm_edges(repo_path)
        elif eco == "pip":
            graph[eco] = _load_pip_edges(repo_path)
        elif eco in ("maven", "gradle"):
            graph[eco] = _load_jvm_edges(repo_path, names)
        else:
            graph[eco] = None

    _DEPENDENCY_GRAPH_CACHE[repo_path] = graph
    return graph


def find_dependency_centrality(repo_path, ecosystem, component, components):
    """
    Returns the number of other known components (within the same
    ecosystem) that directly depend on component, based on the real
    dependency graph built from lockfiles, installed package metadata, or
    downloaded POMs. Returns None if the ecosystem has no graph source
    available, so an unresolved count is never confused with a genuine
    zero.

    Note this takes the full components dict (not just this one
    component), because computing "who depends on me" requires knowing
    every other component's direct dependencies too.

    Sample input:
        repo_path = "test_repo"
        ecosystem = "npm"
        component = "lodash"
        components = {"lodash": {...}, "express": {...}}  # express depends on lodash

    Sample output:
        1
    """
    eco_key = (ecosystem or "").strip().lower()
    graph = _build_dependency_graph(repo_path, components)
    edges = graph.get(eco_key)

    if edges is None:
        print(
            f"[scan_dep] Warning: no dependency graph source for ecosystem "
            f"'{ecosystem}' (component '{component}'); dependency_centrality unresolved",
            file=sys.stderr,
        )
        return None

    target = component
    if eco_key == "pip":
        target = _normalize_pip_name(component)
        edges = {_normalize_pip_name(name): {_normalize_pip_name(d) for d in deps} for name, deps in edges.items()}

    dependents = 0
    for name, deps in edges.items():
        if name == target:
            continue
        if target in deps:
            dependents += 1

    return dependents


def load_repo_scan(path):
    """
    Loads and parses repo_scan.json into a dict.

    Sample input:
        path = "repo_scan.json"
        (file contents: {"lodash": {"ecosystem": "npm", "usage_count": 1}})

    Sample output:
        {"lodash": {"ecosystem": "npm", "usage_count": 1}}
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def enrich_components(components, repo_path):
    """
    Returns a copy of components with a dependency_centrality field added
    to each entry.

    Sample input:
        components = {"lodash": {"ecosystem": "npm"}, "express": {"ecosystem": "npm"}}
        repo_path = "test_repo"  # express depends on lodash

    Sample output:
        {
            "lodash": {"ecosystem": "npm", "dependency_centrality": 1},
            "express": {"ecosystem": "npm", "dependency_centrality": 0},
        }
    """
    output = {}

    for component, details in components.items():
        entry = dict(details)
        entry["dependency_centrality"] = find_dependency_centrality(
            repo_path,
            details.get("ecosystem"),
            component,
            components,
        )
        output[component] = entry

    return output


def main():
    """
    Entry point: reads repo_scan.json, computes dependency_centrality for
    every component, and writes dependency_scan.json.

    Sample input (command line):
        python3 scan_dep.py repo_scan.json test_repo dependency_scan.json

    Sample output (written to dependency_scan.json):
        {
            "lodash": {
                "ecosystem": "npm",
                "usage_count": 1,
                "dependency_centrality": 1
            }
        }
    """
    if len(sys.argv) != 4:
        print(
            "Usage: python3 scan_dep.py <repo_scan.json> <repo_path> <dependency_scan.json>",
            file=sys.stderr,
        )
        sys.exit(1)

    input_path = sys.argv[1]
    repo_path = sys.argv[2]
    output_path = sys.argv[3]

    components = load_repo_scan(input_path)
    dependency_scan = enrich_components(components, repo_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dependency_scan, f, indent=2, sort_keys=True)

    print(f"[scan_dep] Repository: {repo_path}")
    print(
        f"[scan_dep] Wrote {len(dependency_scan)} component(s) to {output_path}"
    )


if __name__ == "__main__":
    main()
