#!/usr/bin/env python3
"""
Aggregate unique URLs from api_calls_summary.csv and collect their statuses and response files.

Input CSV expected columns (at minimum):
- url
- status
- response_json_file (may be empty)

Output CSV columns:
- url
- statuses (unique, pipe-separated, in ascending order)
- response_files (unique, pipe-separated)

Usage:
  python3 url_aggregate.py --input /path/to/api_calls_summary.csv --output /path/to/url_to_responses.csv
"""

import argparse
import csv
from collections import OrderedDict
from typing import Dict, Set


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate unique URLs to statuses and response files")
    parser.add_argument("--input", required=True, help="Path to api_calls_summary.csv")
    parser.add_argument("--output", required=True, help="Path to write aggregated CSV")
    parser.add_argument("--sep", default="|", help="Separator for multi-values (default: |)")
    args = parser.parse_args()

    url_map: "OrderedDict[str, Dict[str, Set[str]]]" = OrderedDict()

    with open(args.input, "r", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)
        for row in reader:
            url = (row.get("url") or "").strip()
            if not url:
                continue
            status = str(row.get("status") or "").strip()
            resp_file = (row.get("response_json_file") or "").strip()

            if url not in url_map:
                url_map[url] = {"statuses": set(), "files": set()}
            if status:
                url_map[url]["statuses"].add(status)
            if resp_file:
                url_map[url]["files"].add(resp_file)

    with open(args.output, "w", newline="", encoding="utf-8") as fout:
        fieldnames = ["url", "statuses", "response_files"]
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for url, data in url_map.items():
            statuses_sorted = sorted(data["statuses"], key=lambda s: (len(s), s))
            files_sorted = sorted(data["files"])  # keep deterministic
            writer.writerow(
                {
                    "url": url,
                    "statuses": args.sep.join(statuses_sorted),
                    "response_files": args.sep.join(files_sorted),
                }
            )

    print(f"Wrote {len(url_map)} unique URLs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


