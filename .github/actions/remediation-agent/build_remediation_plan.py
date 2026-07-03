#!/usr/bin/env python3
"""
Remediation Agent scoring engine.

Groups Dependabot alerts by dependency component. Each component may have
several open CVEs, each tied to its own `first_patched_version` and
`vulnerable_version_range`. A component can therefore have multiple distinct
"fixed version" candidates (e.g. nodemailer 8.0.8 and 8.0.9).

Naively scoring each candidate version only by the CVEs whose own
first_patched_version equals it undercounts what upgrading actually buys you:
a higher version typically also resolves CVEs that were already patched at a
lower version. So instead, for every candidate fixed version V of a
component, we use `vulnerable_version_range` to determine how many of *all*
that component's CVEs V actually resolves (i.e. V falls outside the CVE's
vulnerable range), and score V on that cumulative set:

    score(V) = sum(SEVERITY_WEIGHT[severity] for each CVE V resolves)

Fixed versions are ordered in the response (highest first) by:
    (-score, -number_of_cves_resolved, version string ascending)

The `fixed_version` and `fix_summary` fields keep their original meaning —
each entry still only *lists* the CVEs whose own first_patched_version is
exactly that version — only the ORDER of the entries changes based on the
cumulative scoring above. No affected/vulnerable-range text is included in
the output.

Only alerts that are currently "open" AND have a known first_patched_version
are considered — an alert with no available fix cannot contribute to a
remediation recommendation.
"""

import json
import re
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


# ---------------------------------------------------------------------------
# Minimal version comparison + range parsing.
#
# Versions are dotted numeric strings ("8.0.8", "4.0.6"). Ranges look like
# "<= 8.0.8", "< 4.0.6", ">= 4.0.0, < 4.0.6". This is intentionally simple
# (no pre-release/build-metadata handling) since Dependabot's
# vulnerable_version_range strings for npm/most ecosystems fit this shape.
# ---------------------------------------------------------------------------

def parse_version(v: str):
    parts = []
    for chunk in re.split(r"[.\-+]", v.strip()):
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group()) if m else 0)
    return tuple(parts)


def compare_versions(v1: str, v2: str) -> int:
    p1, p2 = parse_version(v1), parse_version(v2)
    length = max(len(p1), len(p2))
    p1 = p1 + (0,) * (length - len(p1))
    p2 = p2 + (0,) * (length - len(p2))
    if p1 < p2:
        return -1
    if p1 > p2:
        return 1
    return 0


_OPS = (">=", "<=", ">", "<", "=")


def parse_constraints(range_str: str):
    constraints = []
    for part in (range_str or "").split(","):
        part = part.strip()
        if not part:
            continue
        for op in _OPS:
            if part.startswith(op):
                constraints.append((op, part[len(op):].strip()))
                break
    return constraints


def version_satisfies_range(version: str, range_str: str) -> bool:
    """True if `version` falls inside the vulnerable range (i.e. is still vulnerable)."""
    constraints = parse_constraints(range_str)
    if not constraints:
        return False
    for op, bound in constraints:
        cmp = compare_versions(version, bound)
        if op == ">=" and not (cmp >= 0):
            return False
        if op == "<=" and not (cmp <= 0):
            return False
        if op == ">" and not (cmp > 0):
            return False
        if op == "<" and not (cmp < 0):
            return False
        if op == "=" and not (cmp == 0):
            return False
    return True


def resolves_cve(candidate_version: str, cve_patched_version: str, cve_range: str):
    """
    Does upgrading to `candidate_version` resolve a CVE whose own fix is
    `cve_patched_version` / vulnerable range `cve_range`?

    Preferred check: candidate_version is outside the vulnerable range.
    Falls back to plain version comparison if the range is missing/unparseable.
    """
    if cve_range:
        constraints = parse_constraints(cve_range)
        if constraints:
            return not version_satisfies_range(candidate_version, cve_range)
    # Fallback: no usable range, just compare against the CVE's own fixed version.
    return compare_versions(candidate_version, cve_patched_version) >= 0


# ---------------------------------------------------------------------------
# Alert grouping
# ---------------------------------------------------------------------------

def group_by_component(alerts):
    """component -> list of (cve_id, severity, patched_version, affected_range)"""
    components = defaultdict(list)

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
        affected_range = vuln.get("vulnerable_version_range") or ""

        advisory = alert.get("security_advisory") or {}
        cve_id = advisory.get("cve_id") or advisory.get("ghsa_id") or f"alert-{alert.get('number', 'unknown')}"

        components[component].append((cve_id, severity, fixed_version, affected_range))

    return components


def build_plan(components):
    plan = []

    for component, cves in components.items():
        candidate_versions = sorted({v for (_, _, v, _) in cves})

        # For every candidate fixed version, work out the *cumulative* set of
        # CVEs it resolves (using affected_version_range), and score that set.
        version_stats = {}
        for candidate in candidate_versions:
            resolved = [
                (cve_id, severity)
                for (cve_id, severity, patched_version, affected_range) in cves
                if resolves_cve(candidate, patched_version, affected_range)
            ]
            version_stats[candidate] = {
                "score": sum(severity_weight(sev) for _, sev in resolved),
                "count": len(resolved),
            }

        # Order candidate versions: highest cumulative score first, then most
        # CVEs resolved, then version string ascending (deterministic tie-break).
        ranked_versions = sorted(
            candidate_versions,
            key=lambda v: (-version_stats[v]["score"], -version_stats[v]["count"], v),
        )

        # Direct mapping: which CVEs are *listed* under each version in the
        # response (only those whose own first_patched_version is that version).
        direct_cves_by_version = defaultdict(list)
        for (cve_id, severity, patched_version, _affected_range) in cves:
            direct_cves_by_version[patched_version].append((cve_id, severity))

        version_strings = []
        summary_strings = []

        for version in ranked_versions:
            direct = direct_cves_by_version.get(version, [])
            ranked_direct = sorted(direct, key=lambda c: (-severity_weight(c[1]), c[0]))
            cve_fragments = [f"{cve_id}({severity.lower()})" for cve_id, severity in ranked_direct]
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
