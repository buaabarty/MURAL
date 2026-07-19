#!/usr/bin/env python3
"""Merge exact audited configurations into the canonical localization ledgers."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


AUDITED_APPROACHES = {"BM25_projection", "MURAL_2src"}
EXACT_PAIRS = {
    ("BM25_entities", "BM25_projection"),
    ("BM25_projection", "MURAL_2src"),
    ("BM25_projection", "MURAL"),
    ("MURAL_2src", "MURAL"),
}
PAIR_ORDER = [
    ("BM25_entities", "BM25_projection"),
    ("Structural_entities", "Structural_adapter"),
    ("BM25_projection", "MURAL_2src"),
    ("BM25_projection", "MURAL"),
    ("Dense_projection", "MURAL"),
    ("MURAL_2src", "MURAL"),
    ("GLM5_BM25", "GLM5_MURAL"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--paired", type=Path, required=True)
    parser.add_argument("--exact-summary", type=Path, required=True)
    parser.add_argument("--exact-instances", type=Path, required=True)
    parser.add_argument("--exact-paired", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-instances", type=Path, required=True)
    parser.add_argument("--output-paired", type=Path, required=True)
    return parser.parse_args()


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def write_tsv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    summary_fields, summary = read_tsv(args.summary)
    _, exact_summary = read_tsv(args.exact_summary)
    exact_summary_by_approach = {
        row["approach"]: row
        for row in exact_summary
        if row["approach"] in AUDITED_APPROACHES
    }
    if set(exact_summary_by_approach) != AUDITED_APPROACHES:
        raise ValueError("exact summary is missing an audited approach")
    merged_summary = [
        exact_summary_by_approach.get(row["approach"], row) for row in summary
    ]

    instance_fields, instances = read_tsv(args.instances)
    _, exact_instances = read_tsv(args.exact_instances)
    exact_instance_rows = {
        (row["approach"], row["instance_id"]): row
        for row in exact_instances
        if row["approach"] in AUDITED_APPROACHES
    }
    expected_instance_rows = 500 * len(AUDITED_APPROACHES)
    if len(exact_instance_rows) != expected_instance_rows:
        raise ValueError(
            f"expected {expected_instance_rows} exact instance rows, "
            f"found {len(exact_instance_rows)}"
        )
    merged_instances = [
        exact_instance_rows.get((row["approach"], row["instance_id"]), row)
        for row in instances
    ]

    paired_fields, paired = read_tsv(args.paired)
    _, exact_paired = read_tsv(args.exact_paired)
    exact_pair_rows = {
        (row["baseline"], row["treatment"], row["metric"]): row
        for row in exact_paired
        if (row["baseline"], row["treatment"]) in EXACT_PAIRS
    }
    if len(exact_pair_rows) != 5 * len(EXACT_PAIRS):
        raise ValueError("exact paired ledger is missing audited comparisons")
    retained_pair_rows = {
        (row["baseline"], row["treatment"], row["metric"]): row
        for row in paired
        if (row["baseline"], row["treatment"]) not in EXACT_PAIRS
    }
    all_pair_rows = {**retained_pair_rows, **exact_pair_rows}
    metrics = ["file_hit", "target_coverage", "mrr", "hit", "complete"]
    merged_paired = [
        all_pair_rows[(baseline, treatment, metric)]
        for baseline, treatment in PAIR_ORDER
        for metric in metrics
    ]

    write_tsv(args.output_summary, summary_fields, merged_summary)
    write_tsv(args.output_instances, instance_fields, merged_instances)
    write_tsv(args.output_paired, paired_fields, merged_paired)
    print(
        "merged exact BM25_projection and MURAL_2src rows into canonical "
        "summary, instance, and paired ledgers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
