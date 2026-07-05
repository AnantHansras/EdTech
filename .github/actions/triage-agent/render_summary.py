#!/usr/bin/env python3

"""
render_summary.py

Reads dependency_scan.json, computes a priority score for every component,
sorts the components by score, and writes a markdown summary to the GitHub
Actions Job Summary.

Usage:
    python3 render_summary.py <dependency_scan.json>
"""

import json
import math
import os
import sys


SEVERITY_WEIGHTS = {
    "critical": 100,
    "high": 50,
    "medium": 10,
    "low": 1,
}

# Usage/centrality are converted into simple Low/Medium/High/Very High
# levels (based on where a component falls relative to the others in this
# run), and each level adds a fixed, capped bonus on top of the severity
# score. This keeps the math easy to explain: severity always sets the
# base score, and how widely-used/central a component is can only nudge
# it up within a known range -- it can never flip the ranking on its own.
LEVEL_THRESHOLDS = {
    "Very High": 0.75,  # top 25%
    "High": 0.50,       # top 50%
    "Medium": 0.25,      # top 75%
    # anything below 0.25 -> "Low"
}

LEVEL_BONUS = {
    "Low": 0.0,
    "Medium": 0.15,
    "High": 0.30,
    "Very High": 0.50,
}


def load_components(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_severity_score(component):
    sev = component.get("sev_count", {})
    return (
        sev.get("critical", 0) * SEVERITY_WEIGHTS["critical"]
        + sev.get("high", 0) * SEVERITY_WEIGHTS["high"]
        + sev.get("medium", 0) * SEVERITY_WEIGHTS["medium"]
        + sev.get("low", 0) * SEVERITY_WEIGHTS["low"]
    )


def level_from_ratio(ratio):
    """Map a 0-1 normalized value to a Low/Medium/High/Very High label."""
    if ratio >= LEVEL_THRESHOLDS["Very High"]:
        return "Very High"
    if ratio >= LEVEL_THRESHOLDS["High"]:
        return "High"
    if ratio >= LEVEL_THRESHOLDS["Medium"]:
        return "Medium"
    return "Low"


def compute_scores(components):
    """
    Score components so that vulnerability severity determines the overall
    ranking tier, and usage/centrality only add a small, capped bonus on
    top of it -- expressed as plain Low/Medium/High/Very High levels
    rather than raw counts or percentages.

    For each component:
      1. severity_score = weighted count of critical/high/medium/low CVEs.
      2. usage_count and dependency_centrality are each normalized against
         the max seen in this run (log1p is used for usage so a jump from
         500 to 510 imports isn't treated as more significant than 1 to 10),
         then bucketed into a Low/Medium/High/Very High level.
      3. The higher of the two levels becomes the component's overall
         "Impact" level, which adds a fixed bonus (0% / 15% / 30% / 50%)
         to the severity score.

    This replaces an earlier unbounded additive formula (severity +
    usage*20 + centrality*10), where a handful of medium-severity CVEs in
    a widely-imported package could outscore a critical CVE in a
    rarely-used one -- inverting the priority a security triage report
    should convey.
    """
    raw = {}
    for name, details in components.items():
        usage_count = max(details.get("usage_count", 0), 0)
        centrality = max(details.get("dependency_centrality", 0), 0)
        raw[name] = {
            "severity_score": compute_severity_score(details),
            "log_usage": math.log1p(usage_count),
            "centrality": centrality,
        }

    max_log_usage = max((r["log_usage"] for r in raw.values()), default=0)
    max_centrality = max((r["centrality"] for r in raw.values()), default=0)

    LEVEL_RANK = {"Low": 0, "Medium": 1, "High": 2, "Very High": 3}

    scores = {}
    for name, r in raw.items():
        usage_ratio = (r["log_usage"] / max_log_usage) if max_log_usage > 0 else 0
        centrality_ratio = (r["centrality"] / max_centrality) if max_centrality > 0 else 0

        usage_level = level_from_ratio(usage_ratio)
        centrality_level = level_from_ratio(centrality_ratio)

        # Overall impact = whichever signal is stronger, so a component
        # that's very central but rarely imported directly (or vice versa)
        # still gets credited for it.
        impact_level = max(
            (usage_level, centrality_level), key=lambda lvl: LEVEL_RANK[lvl]
        )

        bonus = LEVEL_BONUS[impact_level]
        final = r["severity_score"] * (1 + bonus)

        scores[name] = {
            "score": round(final, 1),
            "usage_level": usage_level,
            "centrality_level": centrality_level,
            "impact_level": impact_level,
        }

    return scores


def render_markdown(components):

    scores = compute_scores(components)

    ranked = []

    for name, details in components.items():
        ranked.append({
            "name": name,
            "score": scores[name]["score"],
            "usage_level": scores[name]["usage_level"],
            "centrality_level": scores[name]["centrality_level"],
            "impact_level": scores[name]["impact_level"],
            "details": details,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)

    lines = []

    lines.append("# 🚨 Dependency Risk Summary")
    lines.append("")
    lines.append(
        "| Rank | Component | Ecosystem | Critical | High | Medium | Low | Usage | Centrality | Impact | Score |"
    )
    lines.append(
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    )

    for i, item in enumerate(ranked, start=1):
        d = item["details"]
        # BUGFIX: was `d["sev_count"]`, which raises KeyError if a component
        # ever lacks the key (e.g. malformed upstream data). Use .get() with
        # a default, consistent with how compute_severity_score() reads the
        # same field, so a single malformed component can't crash the whole
        # summary render.
        sev = d.get("sev_count", {})

        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | **{}** |".format(
                i,
                item["name"],
                # BUGFIX: ecosystem can be None (e.g. package.ecosystem was
                # missing upstream); str(None) -> "None" would render
                # literally in the table. Fall back to empty string.
                d.get("ecosystem") or "",
                sev.get("critical", 0),
                sev.get("high", 0),
                sev.get("medium", 0),
                sev.get("low", 0),
                item["usage_level"],
                item["centrality_level"],
                item["impact_level"],
                item["score"],
            )
        )

    return "\n".join(lines)


def main():

    if len(sys.argv) != 2:
        print(
            "Usage: python3 render_summary.py <dependency_scan.json>",
            file=sys.stderr,
        )
        sys.exit(1)

    components = load_components(sys.argv[1])

    markdown = render_markdown(components)

    summary_file = os.getenv("GITHUB_STEP_SUMMARY")

    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(markdown)
            f.write("\n")
        print("[render_summary] Wrote GitHub Job Summary.")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
