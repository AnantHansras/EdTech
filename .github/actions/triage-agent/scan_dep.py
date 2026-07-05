#!/usr/bin/env python3
"""
scan_dep.py

Reads repo_scan.json, computes dependency centrality for each component
(placeholder implementation for now), and writes dependency_scan.json.

Usage:
    python3 scan_dep.py <repo_scan.json> <repo_path> <dependency_scan.json>
"""

import json
import sys


def find_dependency_centrality(repo_path, ecosystem, component):
    """
    Placeholder implementation.

    Later this function can analyze the dependency graph of the repository
    and compute a centrality score for the given dependency.

    Examples of future implementations:
      - Number of packages depending on this component
      - PageRank over the dependency graph
      - Degree centrality
      - Betweenness centrality

    Returns:
        int: Dependency centrality score.
    """
    return 5


def load_repo_scan(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def enrich_components(components, repo_path):
    output = {}

    for component, details in components.items():
        entry = dict(details)
        entry["dependency_centrality"] = find_dependency_centrality(
            repo_path,
            details.get("ecosystem"),
            component,
        )
        output[component] = entry

    return output


def main():
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
