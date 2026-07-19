#!/usr/bin/env python3
"""Recompute Java paired statistics from the frozen complete instance ledger."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_java_retrieve_localize import exact_mcnemar  # noqa: E402
from evaluate_strict_reference_context import cluster_bootstrap_ci  # noqa: E402


COMPARISONS = (
    ("Raw_BM25_entities", "BM25_projection"),
    ("BM25_projection", "Structural_projection"),
    ("BM25_projection", "Lexical_structural_fusion"),
    ("Structural_projection", "Lexical_structural_fusion"),
)
METRICS = ("file", "method", "mrr", "hit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = [
        json.loads(line)
        for line in args.instances.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("Java instance ledger is empty")

    output: list[dict] = []
    for baseline, treatment in COMPARISONS:
        for metric in METRICS:
            triples = [
                (
                    str(row["repo"]),
                    float(row["metrics"][baseline][metric]),
                    float(row["metrics"][treatment][metric]),
                )
                for row in rows
            ]
            differences = [new - old for _, old, new in triples]
            low, high = cluster_bootstrap_ci(triples, args.bootstrap, args.seed)
            wins = sum(delta > 0 for delta in differences)
            losses = sum(delta < 0 for delta in differences)
            output.append(
                {
                    "baseline": baseline,
                    "treatment": treatment,
                    "top_k": 20,
                    "metric": metric,
                    "N": len(rows),
                    "baseline_value": mean(old for _, old, _ in triples),
                    "treatment_value": mean(new for _, _, new in triples),
                    "delta": mean(differences),
                    "ci95_low": low,
                    "ci95_high": high,
                    "wins": wins,
                    "losses": losses,
                    "ties": len(rows) - wins - losses,
                    "exact_mcnemar_p": (
                        exact_mcnemar(wins, losses)
                        if metric in {"file", "hit"}
                        else "NA"
                    ),
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(output[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
