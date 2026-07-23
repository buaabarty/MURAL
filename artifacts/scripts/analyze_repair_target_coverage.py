#!/usr/bin/env python3
"""Relate source-visible target coverage to official repair outcomes."""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot compute a percentile over an empty sample")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def join_rows(
    prompt_rows: list[dict[str, str]],
    outcome_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    prompts = {
        (row["instance_id"], row["variant"]): row for row in prompt_rows
    }
    outcomes = {
        (row["instance_id"], row["variant"]): row for row in outcome_rows
    }
    if set(prompts) != set(outcomes):
        missing_prompts = sorted(set(outcomes) - set(prompts))
        missing_outcomes = sorted(set(prompts) - set(outcomes))
        raise ValueError(
            "Prompt/outcome keys differ: "
            f"missing prompts={missing_prompts[:3]}, "
            f"missing outcomes={missing_outcomes[:3]}"
        )

    joined: list[dict[str, Any]] = []
    for key in sorted(prompts):
        prompt = prompts[key]
        outcome = outcomes[key]
        target_count = int(prompt["target_count"])
        if target_count <= 0:
            raise ValueError(f"{key[0]} has no reference targets")
        joined.append(
            {
                "instance_id": key[0],
                "repository": prompt["repository"],
                "variant": key[1],
                "target_count": target_count,
                "target_band": "single" if target_count == 1 else "multi",
                "target_coverage": float(prompt["source_target_coverage"]),
                "resolved": int(outcome["resolved"]),
            }
        )
    return joined


def clustered_outcome_gap(
    rows: list[dict[str, Any]],
    resamples: int,
    seed: int,
) -> tuple[float, float, int]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[str(row["repository"])].append(row)
    names = sorted(clusters)
    if not names:
        raise ValueError("No repository clusters")

    rng = random.Random(seed)
    gaps: list[float] = []
    for _ in range(resamples):
        sampled: list[dict[str, Any]] = []
        for _ in names:
            sampled.extend(clusters[rng.choice(names)])
        unresolved = [
            float(row["target_coverage"])
            for row in sampled
            if int(row["resolved"]) == 0
        ]
        resolved = [
            float(row["target_coverage"])
            for row in sampled
            if int(row["resolved"]) == 1
        ]
        if unresolved and resolved:
            gaps.append(mean(resolved) - mean(unresolved))
    if not gaps:
        raise ValueError("No bootstrap draw contains both repair outcomes")
    return percentile(gaps, 0.025), percentile(gaps, 0.975), len(gaps)


def summarize_outcomes(
    joined: list[dict[str, Any]],
    resamples: int,
    seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    variants = sorted({str(row["variant"]) for row in joined})
    for target_band in ("single", "multi"):
        for variant in variants:
            selected = [
                row
                for row in joined
                if row["target_band"] == target_band
                and row["variant"] == variant
            ]
            unresolved = [
                float(row["target_coverage"])
                for row in selected
                if int(row["resolved"]) == 0
            ]
            resolved = [
                float(row["target_coverage"])
                for row in selected
                if int(row["resolved"]) == 1
            ]
            if not unresolved or not resolved:
                raise ValueError(
                    f"{variant}/{target_band} lacks one repair-outcome group"
                )
            gap = mean(resolved) - mean(unresolved)
            low, high, valid = clustered_outcome_gap(
                selected, resamples, seed
            )
            rows.append(
                {
                    "target_band": target_band,
                    "variant": variant,
                    "N": len(selected),
                    "unresolved_N": len(unresolved),
                    "unresolved_target_coverage": f"{100 * mean(unresolved):.6f}",
                    "resolved_N": len(resolved),
                    "resolved_target_coverage": f"{100 * mean(resolved):.6f}",
                    "delta_points": f"{100 * gap:.6f}",
                    "clustered_ci_low": f"{100 * low:.6f}",
                    "clustered_ci_high": f"{100 * high:.6f}",
                    "bootstrap_valid_draws": valid,
                }
            )
    return rows


def summarize_two_target_bins(
    joined: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    variants = sorted({str(row["variant"]) for row in joined})
    for variant in variants:
        selected = [
            row
            for row in joined
            if row["target_count"] == 2 and row["variant"] == variant
        ]
        for coverage_bin in ("zero", "partial", "complete"):
            if coverage_bin == "zero":
                bucket = [
                    row for row in selected if float(row["target_coverage"]) == 0
                ]
            elif coverage_bin == "partial":
                bucket = [
                    row
                    for row in selected
                    if 0 < float(row["target_coverage"]) < 1
                ]
            else:
                bucket = [
                    row for row in selected if float(row["target_coverage"]) == 1
                ]
            resolved = sum(int(row["resolved"]) for row in bucket)
            rows.append(
                {
                    "target_count": 2,
                    "variant": variant,
                    "coverage_bin": coverage_bin,
                    "N": len(bucket),
                    "resolved": resolved,
                    "resolved_rate": (
                        f"{100 * resolved / len(bucket):.6f}"
                        if bucket
                        else "0.000000"
                    ),
                }
            )
    return rows


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
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
    parser.add_argument("--prompts", required=True, type=Path)
    parser.add_argument("--outcomes", required=True, type=Path)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-outcome", required=True, type=Path)
    parser.add_argument("--output-bins", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    joined = join_rows(read_tsv(args.prompts), read_tsv(args.outcomes))
    write_tsv(
        args.output_outcome,
        summarize_outcomes(joined, args.bootstrap, args.seed),
    )
    write_tsv(args.output_bins, summarize_two_target_bins(joined))
    print(f"wrote {args.output_outcome} and {args.output_bins}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
