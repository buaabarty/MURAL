#!/usr/bin/env python3
"""Compute repository-clustered paired intervals for repair outcomes."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from statistics import mean


sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_strict_reference_context import (  # noqa: E402
    cluster_bootstrap_ci,
    exact_mcnemar,
    repository_id,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--baseline", default="bm25")
    parser.add_argument("--treatment", default="mural")
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    by_variant: dict[str, dict[str, dict]] = {}
    with args.outcomes.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            by_variant.setdefault(row["variant"], {})[row["instance_id"]] = row
    ids = sorted(set(by_variant[args.baseline]) & set(by_variant[args.treatment]))
    rows: list[dict] = []
    for metric in ("nonempty", "applied", "resolved"):
        triples = [
            (
                repository_id(instance_id),
                float(by_variant[args.baseline][instance_id][metric]),
                float(by_variant[args.treatment][instance_id][metric]),
            )
            for instance_id in ids
        ]
        differences = [treatment - baseline for _, baseline, treatment in triples]
        low, high = cluster_bootstrap_ci(triples, args.bootstrap, args.seed)
        wins = sum(baseline == 0 and treatment == 1 for _, baseline, treatment in triples)
        losses = sum(baseline == 1 and treatment == 0 for _, baseline, treatment in triples)
        rows.append(
            {
                "baseline": args.baseline,
                "treatment": args.treatment,
                "metric": metric,
                "N": len(ids),
                "delta": f"{100 * mean(differences):.6f}",
                "clustered_ci_low": f"{100 * low:.6f}",
                "clustered_ci_high": f"{100 * high:.6f}",
                "wins": wins,
                "losses": losses,
                "mcnemar_p": f"{exact_mcnemar(wins, losses):.12g}",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
