#!/usr/bin/env python3
"""
scan_repo.py

Reads components.json, scans the repository, and produces repo_scan.json by
adding a usage_count field to each component.

Usage:
    python3 scan_repo.py <components.json> <repo_path> <repo_scan.json>
"""

import json
import os
import re
import sys


EXCLUDED_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "dist", "build", "out", "target",
    "vendor", "venv", ".venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".tox",
    ".gradle", ".idea", ".vscode", ".next", "coverage",
}

MANIFEST_FILENAMES = {
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "npm-shrinkwrap.json",
    "requirements.txt", "requirements-dev.txt", "pipfile", "pipfile.lock",
    "pyproject.toml", "poetry.lock", "setup.py", "setup.cfg",
    "pom.xml",
    "build.gradle", "build.gradle.kts", "settings.gradle",
    "settings.gradle.kts", "gradle.lockfile", "versions.toml",
}


_FILE_CACHE = {}


def _iter_candidate_files(repo_path, extensions):
    """
    Walks repo_path and yields file paths that end with one of the given
    extensions, skipping excluded directories (node_modules, .git, build
    output, etc.) and manifest/lockfiles.

    Sample input:
        repo_path = "test_repo"
        extensions = (".js", ".ts")

    Sample output (generator yields):
        "test_repo/src/app.js"
        "test_repo/src/utils.ts"
    """
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [
            d for d in dirs
            if d not in EXCLUDED_DIRS and not d.startswith(".")
        ]
        for filename in files:
            if filename.lower() in MANIFEST_FILENAMES:
                continue
            if filename.lower().endswith(extensions):
                yield os.path.join(root, filename)


def _read_text(path):
    """
    Reads a file as UTF-8 text, ignoring undecodable bytes, and returns
    None instead of raising if the file can't be opened.

    Sample input:
        path = "test_repo/src/app.js"

    Sample output:
        "const _ = require('lodash');\\nimport debounce from 'lodash/debounce';\\n"
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return None


def _get_repo_files(repo_path, extensions):
    """
    Returns a list of (filepath, file_text) tuples for every candidate file
    under repo_path matching extensions. Results are cached per
    (repo_path, extensions) pair so repeated calls for different components
    in the same ecosystem don't re-walk and re-read the filesystem.

    Sample input:
        repo_path = "test_repo"
        extensions = (".py",)

    Sample output:
        [
            ("test_repo/pysrc/main.py", "import yaml\\nfrom yaml import safe_load\\n"),
            ("test_repo/pysrc/other.py", "print('no yaml here')\\n"),
        ]
    """
    cache_key = (os.path.abspath(repo_path), extensions)
    cached = _FILE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    files = []
    for filepath in _iter_candidate_files(repo_path, extensions):
        text = _read_text(filepath)
        if text is not None:
            files.append((filepath, text))

    _FILE_CACHE[cache_key] = files
    return files


def _count_matches(repo_path, extensions, pattern):
    """
    Counts how many candidate files under repo_path (matching extensions)
    contain at least one match for the given compiled regex pattern.

    Sample input:
        repo_path = "test_repo"
        extensions = (".js",)
        pattern = re.compile(r"require\\(\\s*['\\\"]lodash['\\\"]\\s*\\)")

    Sample output:
        1
    """
    count = 0
    for _filepath, text in _get_repo_files(repo_path, extensions):
        if pattern.search(text):
            count += 1
    return count


def _find_usage_npm(repo_path, component):
    """
    Counts files that import an npm package via require(...), ES module
    import statements, or dynamic import(...), including subpath imports.

    Sample input:
        repo_path = "test_repo"
        component = "lodash"

    Sample output:
        1
    """
    extensions = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue")
    pkg = re.escape(component)
    subpath = r"""(?:/[^'"]*)?"""

    pattern = re.compile(
        r"""require\(\s*['"]""" + pkg + subpath + r"""['"]\s*\)"""
        r"""|from\s+['"]""" + pkg + subpath + r"""['"]"""
        r"""|import\(\s*['"]""" + pkg + subpath + r"""['"]\s*\)"""
        r"""|import\s+['"]""" + pkg + subpath + r"""['"]"""
    )

    return _count_matches(repo_path, extensions, pattern)


def _find_usage_python(repo_path, component):
    """
    Counts .py files that import a pip package via `import x` or
    `from x import ...`, checking the declared name plus its
    hyphen/underscore variants. Packages whose import name differs
    entirely from their distribution name (e.g. PyYAML -> yaml) will not
    be detected.

    Sample input:
        repo_path = "test_repo"
        component = "requests"

    Sample output:
        1
    """
    extensions = (".py",)
    candidates = {
        component,
        component.replace("-", "_"),
        component.replace("_", "-"),
    }

    alternation = "|".join(re.escape(name) for name in candidates)
    pattern = re.compile(
        r"^\s*import\s+(?:" + alternation + r")(?:[.\s,]|$)"
        r"|^\s*from\s+(?:" + alternation + r")(?:\.\S*)?\s+import\s",
        re.MULTILINE,
    )

    return _count_matches(repo_path, extensions, pattern)


def _find_usage_jvm(repo_path, component):
    """
    Counts Java/Kotlin/Groovy/Scala files that appear to import a Maven or
    Gradle dependency, given as a "groupId:artifactId" coordinate. A file
    counts if it has an import statement starting with the groupId, or
    containing the artifactId (separators normalized to dots) as a
    substring. This is a best-effort heuristic since coordinates don't map
    deterministically to package names.

    Sample input:
        repo_path = "test_repo"
        component = "com.fasterxml.jackson.core:jackson-databind"

    Sample output:
        1
    """
    extensions = (".java", ".kt", ".kts", ".groovy", ".scala")

    group_id, _, artifact_id = component.partition(":")
    if not artifact_id:
        artifact_id = group_id
        group_id = ""

    normalized_artifact = re.sub(r"[-_]", ".", artifact_id).lower()

    import_line = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.MULTILINE)

    count = 0
    for _filepath, text in _get_repo_files(repo_path, extensions):
        for match in import_line.finditer(text):
            imported = match.group(1)
            imported_lower = imported.lower()
            if group_id and imported.startswith(group_id):
                count += 1
                break
            if normalized_artifact and normalized_artifact in imported_lower:
                count += 1
                break

    return count


ECOSYSTEM_SCANNERS = {
    "npm": _find_usage_npm,
    "pip": _find_usage_python,
    "maven": _find_usage_jvm,
    "gradle": _find_usage_jvm,
}


def find_usage(repo_path, ecosystem, component):
    """
    Looks up the scanner for the given ecosystem and uses it to count how
    many non-manifest files in repo_path import component. Returns 0 and
    logs a warning if the ecosystem has no scanner.

    Sample input:
        repo_path = "test_repo"
        ecosystem = "npm"
        component = "lodash"

    Sample output:
        1
    """
    ecosystem_key = (ecosystem or "").strip().lower()
    scanner = ECOSYSTEM_SCANNERS.get(ecosystem_key)

    if scanner is None:
        print(
            f"[scan_repo] Warning: no usage scanner for ecosystem "
            f"'{ecosystem}' (component '{component}'); usage_count=0",
            file=sys.stderr,
        )
        return 0

    return scanner(repo_path, component)


def load_components(path):
    """
    Loads and parses components.json into a dict.

    Sample input:
        path = "components.json"
        (file contents: {"lodash": {"ecosystem": "npm", "cve": [], "sev_count": {...}}})

    Sample output:
        {"lodash": {"ecosystem": "npm", "cve": [], "sev_count": {...}}}
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def enrich_components(components, repo_path):
    """
    Returns a copy of components with a usage_count field added to each
    entry, computed by scanning repo_path.

    Sample input:
        components = {"lodash": {"ecosystem": "npm", "cve": [], "sev_count": {...}}}
        repo_path = "test_repo"

    Sample output:
        {"lodash": {"ecosystem": "npm", "cve": [], "sev_count": {...}, "usage_count": 1}}
    """
    output = {}

    for component, details in components.items():
        entry = dict(details)
        entry["usage_count"] = find_usage(
            repo_path,
            details.get("ecosystem"),
            component,
        )
        output[component] = entry

    return output


def main():
    """
    Entry point: reads components.json, scans repo_path, and writes
    repo_scan.json with usage_count added to every component.

    Sample input (command line):
        python3 scan_repo.py components.json test_repo repo_scan.json

    Sample output (written to repo_scan.json):
        {
            "lodash": {
                "ecosystem": "npm",
                "cve": [],
                "sev_count": {"low": 0, "medium": 0, "high": 0, "critical": 0},
                "usage_count": 1
            }
        }
    """
    if len(sys.argv) != 4:
        print(
            "Usage: python3 scan_repo.py <components.json> <repo_path> <repo_scan.json>",
            file=sys.stderr,
        )
        sys.exit(1)

    components_path = sys.argv[1]
    repo_path = sys.argv[2]
    output_path = sys.argv[3]

    components = load_components(components_path)
    repo_scan = enrich_components(components, repo_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(repo_scan, f, indent=2, sort_keys=True)

    print(f"[scan_repo] Repository: {repo_path}")
    print(f"[scan_repo] Wrote {len(repo_scan)} component(s) to {output_path}")


if __name__ == "__main__":
    main()
