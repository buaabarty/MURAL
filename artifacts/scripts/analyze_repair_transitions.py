#!/usr/bin/env python3
"""Summarize paired repair transitions between two context variants."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


OUTCOMES = ("nonempty", "applied", "resolved")


def read_rows(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            output.setdefault(row["variant"], {})[row["instance_id"]] = row
    return output


def flag(row: dict[str, Any], outcome: str) -> int:
    return int(str(row.get(outcome) or "0"))


def transition(old: int, new: int, baseline: str, treatment: str) -> str:
    if old and new:
        return "both"
    if old:
        return f"{baseline}_only"
    if new:
        return f"{treatment}_only"
    return "neither"


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", required=True, type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--treatment", required=True)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-instances", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    variants = read_rows(args.outcomes)
    if args.baseline not in variants or args.treatment not in variants:
        raise ValueError("Requested variants are absent from the outcome ledger")
    baseline = variants[args.baseline]
    treatment = variants[args.treatment]
    instance_ids = sorted(set(baseline) & set(treatment))
    if not instance_ids:
        raise ValueError("No paired outcomes")

    instance_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for instance_id in instance_ids:
        row: dict[str, Any] = {"instance_id": instance_id}
        for outcome in OUTCOMES:
            old = flag(baseline[instance_id], outcome)
            new = flag(treatment[instance_id], outcome)
            row[f"{args.baseline}_{outcome}"] = old
            row[f"{args.treatment}_{outcome}"] = new
            row[f"{outcome}_transition"] = transition(
                old, new, args.baseline, args.treatment
            )
        instance_rows.append(row)

    for outcome in OUTCOMES:
        categories = [
            "both",
            f"{args.baseline}_only",
            f"{args.treatment}_only",
            "neither",
        ]
        counts = {
            category: sum(
                row[f"{outcome}_transition"] == category for row in instance_rows
            )
            for category in categories
        }
        summary_rows.append(
            {
                "outcome": outcome,
                "N": len(instance_rows),
                "both": counts["both"],
                "baseline_only": counts[f"{args.baseline}_only"],
                "treatment_only": counts[f"{args.treatment}_only"],
                "neither": counts["neither"],
                "baseline": args.baseline,
                "treatment": args.treatment,
            }
        )

    write_tsv(args.output_summary, summary_rows)
    write_tsv(args.output_instances, instance_rows)
    print(f"wrote {args.output_summary}")
    print(f"wrote {args.output_instances}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
