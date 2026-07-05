#!/usr/bin/env python3
"""
parse_alerts.py

Reads a raw Dependabot alerts JSON file (as returned by the GitHub REST API
`GET /repos/{owner}/{repo}/dependabot/alerts` endpoint -- normally a JSON
array of alert objects) and groups the alerts by package/component.

Usage:
    python3 parse_alerts.py <input_raw_alerts.json> <output_components.json>

Output shape (components.json):
{
  "<package-name>": {
    "ecosystem": "npm",
    "cve": ["CVE-xxxx-xxxx", , ...],
    "sev_count": {"low": 0, "medium": 0, "high": 1, "critical": 0}
  },
  ...
}
"""

import json
import sys
from collections import defaultdict

SEVERITY_LEVELS = ("low", "medium", "high", "critical")


def load_alerts(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        # GitHub API error responses look like {"message": ..., "documentation_url": ...}
        # rather than an alert object. Fail loudly instead of silently treating the
        # error payload as a single alert.
        if "message" in data and "documentation_url" in data:
            raise ValueError(
                f"Alerts file {path} looks like a GitHub API error response: "
                f"{data.get('message')!r}"
            )
        if "alerts" in data and isinstance(data["alerts"], list):
            return data["alerts"]
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unrecognized alerts JSON shape in {path}")


def extract_identifiers(alert):
    ids = set()

    advisory = alert.get("security_advisory") or {}

    cve_id = advisory.get("cve_id")
    if cve_id:
        ids.add(cve_id)

    for ident in advisory.get("identifiers", []) or []:
        if ident.get("type") == "CVE" and ident.get("value"):
            ids.add(ident["value"])

    return ids


def extract_alert_key(alert):
    """
    A stable, unique identifier for this alert, used for de-duplicating
    severity counts. Every Dependabot alert has a `number` that is unique
    within a repository, and a GHSA id, both of which exist even when no
    CVE has been assigned yet. Prefer the GHSA id (stable across repos,
    useful if input ever aggregates multiple repos); fall back to the
    alert number.
    """
    advisory = alert.get("security_advisory") or {}
    ghsa_id = advisory.get("ghsa_id")
    if ghsa_id:
        return ("ghsa", ghsa_id)

    number = alert.get("number")
    if number is not None:
        return ("number", number)

    return None


def extract_severity(alert):
    vuln = alert.get("security_vulnerability") or {}
    severity = vuln.get("severity")

    if not severity:
        advisory = alert.get("security_advisory") or {}
        severity = advisory.get("severity")

    if severity:
        severity = severity.lower()

    return severity if severity in SEVERITY_LEVELS else None


def extract_package(alert):
    dependency = alert.get("dependency") or {}
    package = dependency.get("package") or {}
    name = package.get("name")
    ecosystem = package.get("ecosystem")
    return name, ecosystem


def group_by_component(alerts):
    components = defaultdict(lambda: {
        "ecosystem": None,
        "cve": set(),
        "seen_alert_keys": set(),  # De-dup severity counts per alert, not per CVE
        "sev_count": {level: 0 for level in SEVERITY_LEVELS},
    })

    skipped = 0
    for alert in alerts:
        name, ecosystem = extract_package(alert)
        if not name:
            skipped += 1
            continue

        entry = components[name]
        if entry["ecosystem"] is None:
            entry["ecosystem"] = ecosystem

        cves = extract_identifiers(alert)
        entry["cve"].update(cves)

        # BUGFIX: severity used to only be counted when the alert also had a
        # CVE identifier, because the counting loop was nested inside
        # `for cve in cves`. Alerts for advisories that have not (yet) been
        # assigned a CVE -- which is common for GHSA-only advisories -- have
        # an empty `cves` set, so that loop silently never ran and those
        # alerts vanished from sev_count entirely. Severity is now counted
        # once per alert, keyed on a CVE-independent alert identifier, so
        # every alert is represented regardless of whether it has a CVE.
        severity = extract_severity(alert)
        if severity:
            alert_key = extract_alert_key(alert)
            if alert_key is None or alert_key not in entry["seen_alert_keys"]:
                if alert_key is not None:
                    entry["seen_alert_keys"].add(alert_key)
                entry["sev_count"][severity] += 1

    if skipped:
        print(
            f"[parse_alerts] Warning: skipped {skipped} alert(s) with no package name",
            file=sys.stderr,
        )

    # Convert sets to sorted lists for stable, JSON-serializable output.
    output = {}
    for name, entry in components.items():
        output[name] = {
            "ecosystem": entry["ecosystem"],
            "cve": sorted(entry["cve"]),
            "sev_count": entry["sev_count"],
        }
    return output


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: parse_alerts.py <input_raw_alerts.json> <output_components.json>",
            file=sys.stderr,
        )
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    alerts = load_alerts(input_path)
    components = group_by_component(alerts)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(components, f, indent=2, sort_keys=True)

    print(f"[parse_alerts] Wrote {len(components)} component(s) to {output_path}")


if __name__ == "__main__":
    main()
