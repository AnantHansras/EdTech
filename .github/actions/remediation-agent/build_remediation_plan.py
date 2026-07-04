import json
import re
import sys
from collections import defaultdict


SEVERITY_WEIGHT = {
    "critical": 2,
    "high": 1,
    "medium": 0,
    "low": 0,
}


def severity_weight(severity: str) -> int:
    return SEVERITY_WEIGHT.get((severity or "").lower(), 0)


def load_alerts(path: str):
    """
    Read the input JSON file containing Dependabot alerts.

    Example:
        alerts = load_alerts("alerts.json")

    Returns:
        A Python list of alert dictionaries.
    """
    with open(path) as f:
        return json.load(f)


def parse_version(v: str):
    """
    Convert a version string into a tuple of numbers.

    Example:
        "2.5.1" -> (2, 5, 1)
        "1.0-beta" -> (1, 0, 0)

    This makes version comparison easier.
    """
    parts = []
    for chunk in re.split(r"[-.+]", v.strip()):
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group()) if m else 0)
    return tuple(parts)


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version numbers.

    Returns:
        -1 if v1 < v2
         0 if equal
         1 if v1 > v2

    Example:
        compare_versions("1.2", "1.3") -> -1
    """
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
    """
    Split a vulnerable version range into individual conditions.

    Example:
        ">=1.0,<2.0"

    becomes:
        [('>=','1.0'),('<','2.0')]
    """
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
    """
    Check whether a version falls inside a vulnerable version range.

    Example:
        version="1.5"
        range=">=1.0,<2.0"

        Returns True.
    """
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


def resolves_cve(candidate_version: str,
                 cve_patched_version: str,
                 cve_range: str):
    """
    Check whether a candidate version fixes a CVE.

    A version fixes the CVE only if:
    1. It is outside the vulnerable version range.
    2. It is greater than or equal to the first patched version.

    Example:
        Candidate = 2.1
        Patched = 2.0
        Vulnerable range = >=1.0,<2.0

        Returns True.
    """ 

    not_vulnerable_by_range = True

    constraints = parse_constraints(cve_range) if cve_range else []

    if constraints:
        not_vulnerable_by_range = not version_satisfies_range(
            candidate_version,
            cve_range,
        )

    at_or_above_patched = (
        compare_versions(candidate_version, cve_patched_version) >= 0
    )

    return not_vulnerable_by_range and at_or_above_patched


def group_by_component(alerts):
    """
    Group all open alerts by dependency.

    Each dependency stores:
    - CVE id
    - Severity
    - First patched version
    - Vulnerable range
    - Ecosystem

    Example:
         "commons-io": [
                (
                    "CVE-2024-1111",
                    "critical",
                    "2.16.1",
                    "<2.16.1",
                    "maven"
                ),
                (
                    "CVE-2024-2222",
                    "high",
                    "2.17.0",
                    "<2.17.0",
                    "maven"
                )
            ],
    """
    components = defaultdict(list)

    for alert in alerts:
        if alert.get("state") != "open":
            continue

        dependency = alert.get("dependency") or {}
        package = dependency.get("package") or {}
        component = package.get("name")
        ecosystem = package.get("ecosystem")

        if not component:
            continue

        vuln = alert.get("security_vulnerability") or {}
        patched = vuln.get("first_patched_version") or {}
        fixed_version = patched.get("identifier")

        if not fixed_version:
            continue

        severity = (
            vuln.get("severity")
            or (alert.get("security_advisory") or {}).get("severity", "")
        )

        affected_range = vuln.get("vulnerable_version_range") or ""

        advisory = alert.get("security_advisory") or {}

        cve_id = (
            advisory.get("cve_id")
            or advisory.get("ghsa_id")
            or f"alert-{alert.get('number', 'unknown')}"
        )

        components[component].append(
            (
                cve_id,
                severity,
                fixed_version,
                affected_range,
                ecosystem,
            )
        )

    return components


def build_plan(components):
    """
    Build the remediation plan.

    Steps:
    1. Collect candidate fixed versions.
    2. Check which CVEs each version fixes.
    3. Calculate a score.
    4. Rank versions.
    5. Create the final JSON output.

    Example:
        If version 2.9 fixes more critical CVEs than 2.7,
        then 2.9 is ranked first.
    """
    plan = []

    for component, cves in components.items():
        candidate_versions = sorted({v for (_, _, v, _, _) in cves})
        version_stats = {}

        for candidate in candidate_versions:
            resolved = [
                (cve_id, severity)
                for (cve_id, severity, patched_version, affected_range, ecosystem) in cves
                if resolves_cve(candidate, patched_version, affected_range)
            ]

            version_stats[candidate] = {
                "score": sum(severity_weight(sev) for _, sev in resolved),
                "count": len(resolved),
                "resolved": resolved,
            }

        ranked_versions = sorted(
            candidate_versions,
            key=lambda v: (-version_stats[v]["score"], -version_stats[v]["count"], v),
        )

        version_strings = []
        summary_strings = []

        for version in ranked_versions:
            resolved = version_stats[version]["resolved"]

            ranked_resolved = sorted(
                resolved,
                key=lambda c: (-severity_weight(c[1]), c[0])
            )

            cve_fragments = [
                f"{cve_id}({severity.lower()})"
                for cve_id, severity in ranked_resolved
            ]

            summary = (
                "This pr fixes following vulnerabilities : "
                + ", ".join(cve_fragments)
            )

            version_strings.append(version)
            summary_strings.append(summary)

        plan.append(
            {
                "component": component,
                "fixed_version": "|".join(version_strings),
                "fix_summary": "|".join(summary_strings),
                "ecosystem": components[component][0][4],
            }
        )

    plan.sort(key=lambda entry: entry["component"])
    return plan

def main():
    """
    Run the complete remediation planning process.

    Steps:
    1. Read command-line arguments.
    2. Load alerts.
    3. Group alerts by dependency.
    4. Build the remediation plan.
    5. Save the output JSON.

    Example:
        python build_remediation_plan.py alerts.json plan.json
    """

    if len(sys.argv) != 3:
        print(
            "Usage: build_remediation_plan.py <input_raw_json> <output_plan_json>",
            file=sys.stderr,
        )
        sys.exit(1)

    src, dst = sys.argv[1], sys.argv[2]

    alerts = load_alerts(src)
    components = group_by_component(alerts)
    plan = build_plan(components)

    with open(dst, "w") as f:
        json.dump(plan, f, indent=2)

    print(
        f"Remediation plan written to {dst}: "
        f"{len(plan)} component(s), "
        f"{len(alerts)} alert(s) considered."
    )


if __name__ == "__main__":
    main()
