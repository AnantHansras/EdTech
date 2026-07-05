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

# How much a component's usage/centrality can amplify its severity score.
# blast_radius_bonus is normalized to [0, 1], so the final multiplier ranges
# from 1x (no usage/centrality signal, or dead last among peers) to
# (1 + BLAST_RADIUS_MAX)x (the most used/central component in this run).
BLAST_RADIUS_MAX = 1.0

# Relative weight of "how widely used" vs "how structurally central" within
# the blast-radius bonus. Must sum to 1.0.
USAGE_WEIGHT = 0.5
CENTRALITY_WEIGHT = 0.5


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


def compute_scores(components):
    """
    Score components so that vulnerability severity determines the overall
    ranking tier, and usage/centrality only amplify the score within that
    tier (up to a capped bonus) rather than being able to outweigh it.

    Previous formula (severity + usage*20 + centrality*10) was unbounded
    additive: a handful of medium-severity CVEs in a widely-imported
    package could easily outscore a critical CVE in a rarely-used one,
    which inverts the priority a security triage report should convey.
    """
    raw = {}
    for name, details in components.items():
        usage_count = max(details.get("usage_count", 0), 0)
        centrality = max(details.get("dependency_centrality", 0), 0)
        raw[name] = {
            "severity_score": compute_severity_score(details),
            # log1p compresses large usage counts so e.g. 500 vs 510 imports
            # isn't treated as meaningfully "more used" than 1 vs 10 is.
            "log_usage": math.log1p(usage_count),
            "centrality": centrality,
        }

    # Normalize usage/centrality relative to the max seen in this run, so
    # the blast-radius bonus is always a bounded, comparable percentage
    # regardless of the raw scale scan_dep.py happens to produce.
    max_log_usage = max((r["log_usage"] for r in raw.values()), default=0)
    max_centrality = max((r["centrality"] for r in raw.values()), default=0)

    scores = {}
    for name, r in raw.items():
        usage_norm = (r["log_usage"] / max_log_usage) if max_log_usage > 0 else 0
        centrality_norm = (r["centrality"] / max_centrality) if max_centrality > 0 else 0

        blast_radius_bonus = (
            USAGE_WEIGHT * usage_norm + CENTRALITY_WEIGHT * centrality_norm
        )

        # Severity floor: with no severity data, don't rank a component as
        # urgent just because it's widely used/central.
        final = r["severity_score"] * (1 + BLAST_RADIUS_MAX * blast_radius_bonus)

        scores[name] = {
            "score": round(final, 1),
            "blast_radius_pct": round(blast_radius_bonus * 100),
        }

    return scores


def render_markdown(components):

    scores = compute_scores(components)

    ranked = []

    for name, details in components.items():
        ranked.append({
            "name": name,
            "score": scores[name]["score"],
            "blast_radius_pct": scores[name]["blast_radius_pct"],
            "details": details,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)

    lines = []

    lines.append("# 🚨 Dependency Risk Summary")
    lines.append("")
    lines.append(
        "| Rank | Component | Ecosystem | Critical | High | Medium | Low | Usage | Centrality | Blast Radius | Score |"
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
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | +{}% | **{}** |".format(
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
                d.get("usage_count", 0),
                d.get("dependency_centrality", 0),
                item["blast_radius_pct"],
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
