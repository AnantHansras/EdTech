"""
Convert line-delimited Dependabot alerts into a JSON array.

This script reads a JSON Lines (.jsonl) file where each line contains a
single Dependabot alert as a JSON object. It combines all alerts into a
single JSON array and writes the result to an output file.

If the input file does not exist, an empty JSON array is written instead.
The script also prints the total number of alerts processed.

Usage:
    python alerts.py <input_jsonl> <output_json>
"""

import json, sys

src, dst = sys.argv[1], sys.argv[2]
alerts = []
try:
    with open(src) as f:
        for line in f:
            line = line.strip()
            if line:
                alerts.append(json.loads(line))
except FileNotFoundError:
    pass

json.dump(alerts, open(dst, "w"), indent=2)
print(f"Collected {len(alerts)} alert(s)")
