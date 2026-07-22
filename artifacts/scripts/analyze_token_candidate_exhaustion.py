#!/usr/bin/env python3
"""Summarize candidate-pool exhaustion before rendered-token packing."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packing-instances", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--candidate-cap", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.packing_instances.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    grouped: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["source"], int(row["token_budget"]))].append(row)

    summary: list[dict[str, object]] = []
    for (source, budget), selected in sorted(
        grouped.items(), key=lambda item: (item[0][1], item[0][0])
    ):
        candidates = [int(row["candidate_entities"]) for row in selected]
        retained = [int(row["selected_entities"]) for row in selected]
        summary.append(
            {
                "source": source,
                "token_budget": budget,
                "instances": len(selected),
                "candidate_cap": args.candidate_cap,
                "input_below_cap": sum(value < args.candidate_cap for value in candidates),
                "packing_exhausted_input": sum(
                    keep == available for keep, available in zip(retained, candidates)
                ),
                "selected_at_cap": sum(value == args.candidate_cap for value in retained),
                "max_selected": max(retained),
            }
        )

    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    with args.output_summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(summary[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
