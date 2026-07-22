#!/usr/bin/env python3
"""Summarize complete source combinations and leave-one-source-out effects."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import mean
from typing import Any


def read_rows(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            output.setdefault(row["approach"], {})[row["instance_id"]] = row
    return output


def flag(row: dict[str, Any], metric: str) -> int:
    return int(float(row[metric]))


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(
            {key: 'NA' if value == '' else value for key, value in row.items()}
            for row in rows
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top20-instances", required=True, type=Path)
    parser.add_argument("--token4000-instances", required=True, type=Path)
    parser.add_argument("--prefix-instances", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def summarize(
    scenario: str,
    rows: dict[str, dict[str, dict[str, Any]]],
    full_label: str,
    ablations: dict[str, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for metric in ("file_hit", "hit", "complete"):
        for removed_source, ablated_label in ablations.items():
            ids = sorted(set(rows[full_label]) & set(rows[ablated_label]))
            full_values = [flag(rows[full_label][i], metric) for i in ids]
            ablated_values = [flag(rows[ablated_label][i], metric) for i in ids]
            full_only = sum(f and not a for f, a in zip(full_values, ablated_values))
            ablated_only = sum(a and not f for f, a in zip(full_values, ablated_values))
            output.append(
                {
                    "scenario": scenario,
                    "analysis": "leave_one_source_out",
                    "metric": metric,
                    "source": removed_source,
                    "comparison": f"{ablated_label}->{full_label}",
                    "N": len(ids),
                    "baseline_percent": f"{100 * mean(ablated_values):.6f}",
                    "full_percent": f"{100 * mean(full_values):.6f}",
                    "delta_points": f"{100 * (mean(full_values) - mean(ablated_values)):.6f}",
                    "full_only": full_only,
                    "ablated_only": ablated_only,
                }
            )
    return output


def exclusive_hits(
    scenario: str,
    rows: dict[str, dict[str, dict[str, Any]]],
    singles: dict[str, str],
) -> list[dict[str, Any]]:
    ids = sorted(set.intersection(*(set(rows[label]) for label in singles.values())))
    output: list[dict[str, Any]] = []
    for source, label in singles.items():
        others = [other for name, other in singles.items() if name != source]
        unique = sum(
            flag(rows[label][i], "hit")
            and all(not flag(rows[other][i], "hit") for other in others)
            for i in ids
        )
        output.append(
            {
                "scenario": scenario,
                "analysis": "single_source_exclusive",
                "metric": "hit",
                "source": source,
                "comparison": label,
                "N": len(ids),
                "baseline_percent": "",
                "full_percent": "",
                "delta_points": "",
                "full_only": unique,
                "ablated_only": "",
            }
        )
    return output


def main() -> int:
    args = parse_args()
    top20 = read_rows(args.top20_instances)
    token = read_rows(args.token4000_instances)
    prefix = read_rows(args.prefix_instances)
    output: list[dict[str, Any]] = []
    output.extend(
        summarize(
            "standalone_top20",
            top20,
            "MURAL",
            {
                "BM25": "Structural_Dense",
                "Structural": "BM25_Dense",
                "Dense": "BM25_Structural",
            },
        )
    )
    output.extend(
        exclusive_hits(
            "standalone_top20",
            top20,
            {"BM25": "BM25", "Structural": "Structural", "Dense": "Dense"},
        )
    )
    output.extend(
        summarize(
            "token4000",
            token,
            "MURAL_t4000",
            {
                "BM25": "Structural_Dense_t4000",
                "Structural": "BM25_Dense_t4000",
                "Dense": "BM25_Structural_t4000",
            },
        )
    )
    output.extend(
        summarize(
            "glm_prefix_top20",
            prefix,
            "GLM_MURAL",
            {
                "BM25": "GLM_Structural_Dense",
                "Structural": "GLM_BM25_Dense",
                "Dense": "GLM_BM25_Structural",
            },
        )
    )
    write_tsv(args.output, output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
