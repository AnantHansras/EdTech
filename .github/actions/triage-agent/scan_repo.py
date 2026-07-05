#!/usr/bin/env python3
"""
scan_repo.py

Reads components.json, scans the repository (placeholder for now), and
produces repo_scan.json by adding a usage_count field to each component.

Usage:
    python3 scan_repo.py <components.json> <repo_path> <repo_scan.json>
"""

import json
import sys


def find_usage(repo_path, ecosystem, component):
    """
    Placeholder implementation.

    Later this function can scan the repository located at repo_path and
    determine how many times the given dependency is used.
    """
    return 7


def load_components(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def enrich_components(components, repo_path):
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
