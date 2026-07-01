#!/usr/bin/env python3
"""
Remediation Agent scoring engine.

Groups Dependabot alerts by dependency component, then for each component
ranks its available fixed versions using a severity-weighted score:

    score(version) = sum(SEVERITY_WEIGHT[severity] for each vuln fixed by that version)

The version with the highest score is listed first in `fixed_version`
(and its matching entry is listed first in `fix_summary`), separated by `|`.

Only alerts that are currently "open" AND have a known first_patched_version
are considered — an alert with no available fix cannot contribute to a
remediation recommendation.
"""

import json
import sys
from collections import defaultdict

SEVERITY_WEIGHT = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def severity_weight(severity: str) -> int:
    return SEVERITY_WEIGHT.get((severity or "").lower(), 0)


def load_alerts(path: str):
    with open(path) as f:
        return json.load(f)


def group_by_component(alerts):
    """component -> version -> list of (cve_id, severity)"""
    components = defaultdict(lambda: defaultdict(list))

    for alert in alerts:
        if alert.get("state") != "open":
            continue

        dependency = alert.get("dependency") or {}
        package = dependency.get("package") or {}
        component = package.get("name")
        if not component:
            continue

        vuln = alert.get("security_vulnerability") or {}
        patched = vuln.get("first_patched_version") or {}
        fixed_version = patched.get("identifier")
        if not fixed_version:
            # No fix currently available for this alert; nothing to recommend.
            continue

        severity = vuln.get("severity") or (alert.get("security_advisory") or {}).get("severity", "")

        advisory = alert.get("security_advisory") or {}
        cve_id = advisory.get("cve_id") or advisory.get("ghsa_id") or f"alert-{alert.get('number', 'unknown')}"

        components[component][fixed_version].append((cve_id, severity))

    return components


def score_version(cve_list):
    """Total severity-weighted score for a single fixed version."""
    return sum(severity_weight(sev) for _, sev in cve_list)


def build_plan(components):
    plan = []

    for component, versions in components.items():
        # Rank versions: highest score first, then most vulnerabilities fixed,
        # then version string ascending (deterministic tie-break).
        ranked_versions = sorted(
            versions.items(),
            key=lambda item: (-score_version(item[1]), -len(item[1]), item[0]),
        )

        version_strings = []
        summary_strings = []

        for version, cve_list in ranked_versions:
            # Within a version, list the most severe vulnerabilities first.
            ranked_cves = sorted(
                cve_list,
                key=lambda c: (-severity_weight(c[1]), c[0]),
            )

            cve_fragments = [f"{cve_id}({severity.lower()})" for cve_id, severity in ranked_cves]
            summary = "This pr fixes following vulnerabilities " + ", ".join(cve_fragments)

            version_strings.append(version)
            summary_strings.append(summary)

        plan.append(
            {
                "component": component,
                "fixed_version": "|".join(version_strings),
                "fix_summary": "|".join(summary_strings),
            }
        )

    # Deterministic top-level ordering by component name.
    plan.sort(key=lambda entry: entry["component"])
    return plan


def main():
    if len(sys.argv) != 3:
        print("Usage: build_remediation_plan.py <input_raw_json> <output_plan_json>", file=sys.stderr)
        sys.exit(1)

    src, dst = sys.argv[1], sys.argv[2]

    alerts = load_alerts(src)
    components = group_by_component(alerts)
    plan = build_plan(components)

    with open(dst, "w") as f:
        json.dump(plan, f, indent=2)

    print(f"Remediation plan written to {dst}: {len(plan)} component(s), {len(alerts)} alert(s) considered.")


if __name__ == "__main__":
    main()
