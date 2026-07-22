#!/usr/bin/env python3
"""Stratify rendered changed-line coverage by patch-hunk operation type."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import pyarrow.ipc as ipc
from unidiff import PatchSet


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_strict_reference_context import (  # noqa: E402
    cluster_bootstrap_ci,
    exact_mcnemar,
    repository_id,
)


def dataset_patches(path: Path) -> dict[str, str]:
    if path.suffix == ".arrow":
        rows = ipc.open_stream(path).read_all().select(["instance_id", "patch"]).to_pylist()
    else:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {str(row["instance_id"]): str(row.get("patch") or "") for row in rows}


def patch_profile(instance_id: str, patch: str) -> dict[str, Any]:
    counts = {"insertion_only": 0, "deletion_only": 0, "mixed": 0}
    for patched_file in PatchSet(patch):
        for hunk in patched_file:
            added = sum(line.is_added for line in hunk)
            removed = sum(line.is_removed for line in hunk)
            if added and removed:
                counts["mixed"] += 1
            elif added:
                counts["insertion_only"] += 1
            elif removed:
                counts["deletion_only"] += 1
    hunk_count = sum(counts.values())
    if hunk_count and counts["insertion_only"] == hunk_count:
        stratum = "insertion_only"
    elif hunk_count and counts["deletion_only"] == hunk_count:
        stratum = "deletion_only"
    else:
        stratum = "mixed_or_combined"
    return {
        "instance_id": instance_id,
        "repository": repository_id(instance_id),
        "hunk_count": hunk_count,
        "insertion_only_hunks": counts["insertion_only"],
        "deletion_only_hunks": counts["deletion_only"],
        "mixed_hunks": counts["mixed"],
        "contains_insertion_only_hunk": int(counts["insertion_only"] > 0),
        "contains_deletion_only_hunk": int(counts["deletion_only"] > 0),
        "stratum": stratum,
    }


def read_line_rows(path: Path, budget: int) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if int(row["token_budget"]) != budget:
                continue
            total = int(row["changed_lines_total"])
            covered = int(row["changed_lines_covered"])
            if total <= 0:
                raise ValueError(f"{row['instance_id']} has no changed-line anchors")
            output[row["source"]][row["instance_id"]] = {
                "changed_lines_covered": covered,
                "changed_lines_total": total,
                "line_recall": covered / total,
                "complete_line": int(row["complete_changed_lines"]),
            }
    return output


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
    parser.add_argument("--dataset-file", required=True, type=Path)
    parser.add_argument("--line-instances", required=True, type=Path)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--baseline", default="BM25")
    parser.add_argument("--treatment", default="MURAL")
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-profile", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-paired", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profiles = {
        instance_id: patch_profile(instance_id, patch)
        for instance_id, patch in dataset_patches(args.dataset_file).items()
    }
    values = read_line_rows(args.line_instances, args.budget)
    instance_ids = sorted(set(values[args.baseline]) & set(values[args.treatment]))
    profile_rows = [profiles[instance_id] for instance_id in instance_ids]
    write_tsv(args.output_profile, profile_rows)

    strata = ["all", "insertion_only", "mixed_or_combined", "deletion_only"]
    summary_rows: list[dict[str, Any]] = []
    paired_rows: list[dict[str, Any]] = []
    for stratum in strata:
        ids = [
            instance_id
            for instance_id in instance_ids
            if stratum == "all" or profiles[instance_id]["stratum"] == stratum
        ]
        for source in (args.baseline, args.treatment):
            summary_rows.append(
                {
                    "stratum": stratum,
                    "source": source,
                    "N": len(ids),
                    "line_recall": f"{100 * sum(values[source][i]['changed_lines_covered'] for i in ids) / sum(values[source][i]['changed_lines_total'] for i in ids):.6f}",
                    "complete_line": f"{100 * mean(values[source][i]['complete_line'] for i in ids):.6f}",
                }
            )
        for metric, metric_label in (
            ("line_recall", "instance_mean_line_recall"),
            ("complete_line", "complete_line"),
        ):
            pairs = [
                (
                    profiles[i]["repository"],
                    values[args.baseline][i][metric],
                    values[args.treatment][i][metric],
                )
                for i in ids
            ]
            delta = mean(treatment - baseline for _, baseline, treatment in pairs)
            low, high = cluster_bootstrap_ci(pairs, args.bootstrap, args.seed)
            wins = sum(treatment > baseline for _, baseline, treatment in pairs)
            losses = sum(treatment < baseline for _, baseline, treatment in pairs)
            paired_rows.append(
                {
                    "stratum": stratum,
                    "metric": metric_label,
                    "N": len(ids),
                    "delta_points": f"{100 * delta:.6f}",
                    "clustered_ci_low": f"{100 * low:.6f}",
                    "clustered_ci_high": f"{100 * high:.6f}",
                    "wins": wins,
                    "losses": losses,
                    "mcnemar_p": (
                        f"{exact_mcnemar(wins, losses):.12g}"
                        if metric == "complete_line"
                        else ""
                    ),
                }
            )
    write_tsv(args.output_summary, summary_rows)
    write_tsv(args.output_paired, paired_rows)
    print(f"wrote {args.output_profile}, {args.output_summary}, and {args.output_paired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
