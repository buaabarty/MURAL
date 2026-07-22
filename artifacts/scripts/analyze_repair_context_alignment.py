#!/usr/bin/env python3
"""Relate paired repair transitions to changes in model-visible target coverage."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


def read_by(path: Path, group: str) -> dict[str, dict[str, dict[str, str]]]:
    output: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            output[row[group]][row["instance_id"]] = row
    return output


def transition(baseline: int, treatment: int) -> str:
    if baseline and treatment:
        return "both"
    if baseline:
        return "bm25_only"
    if treatment:
        return "mural_only"
    return "neither"


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-instances", required=True, type=Path)
    parser.add_argument("--line-instances", required=True, type=Path)
    parser.add_argument("--repair-outcomes", required=True, type=Path)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-instances", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contexts = read_by(args.context_instances, "approach")
    lines = read_by(args.line_instances, "source")
    repairs = read_by(args.repair_outcomes, "variant")
    bm25_context = contexts[f"BM25_t{args.budget}"]
    mural_context = contexts[f"MURAL_t{args.budget}"]
    ids = sorted(set(bm25_context) & set(mural_context) & set(repairs["bm25"]) & set(repairs["mural"]))
    instance_rows: list[dict[str, Any]] = []
    for instance_id in ids:
        bm25_resolved = int(repairs["bm25"][instance_id]["resolved"])
        mural_resolved = int(repairs["mural"][instance_id]["resolved"])
        bm25_line = lines["BM25"][instance_id]
        mural_line = lines["MURAL"][instance_id]
        row = {
            "instance_id": instance_id,
            "repair_transition": transition(bm25_resolved, mural_resolved),
            "bm25_resolved": bm25_resolved,
            "mural_resolved": mural_resolved,
            "hit_transition": transition(
                int(bm25_context[instance_id]["hit"]),
                int(mural_context[instance_id]["hit"]),
            ),
            "entity_complete_transition": transition(
                int(bm25_context[instance_id]["complete"]),
                int(mural_context[instance_id]["complete"]),
            ),
            "complete_line_transition": transition(
                int(bm25_line["complete_changed_lines"]),
                int(mural_line["complete_changed_lines"]),
            ),
        }
        instance_rows.append(row)

    summary_rows: list[dict[str, Any]] = []
    for metric in ("hit", "entity_complete", "complete_line"):
        field = f"{metric}_transition"
        for context_transition in ("mural_only", "bm25_only", "both", "neither"):
            subset = [row for row in instance_rows if row[field] == context_transition]
            repair_counts = {
                category: sum(row["repair_transition"] == category for row in subset)
                for category in ("mural_only", "bm25_only", "both", "neither")
            }
            summary_rows.append(
                {
                    "context_metric": metric,
                    "context_transition": context_transition,
                    "N": len(subset),
                    "bm25_resolved": sum(row["bm25_resolved"] for row in subset),
                    "mural_resolved": sum(row["mural_resolved"] for row in subset),
                    "repair_mural_only": repair_counts["mural_only"],
                    "repair_bm25_only": repair_counts["bm25_only"],
                    "repair_both": repair_counts["both"],
                    "repair_neither": repair_counts["neither"],
                }
            )
    write_tsv(args.output_summary, summary_rows)
    write_tsv(args.output_instances, instance_rows)
    print(f"wrote {args.output_summary} and {args.output_instances}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
