#!/usr/bin/env python3
"""Compute paired uncertainty for edit-target recall and complete coverage."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from analyze_retrieve_localize_controls import bootstrap_ci, exact_mcnemar_p
from evaluate_patch_derived_context import candidates_from_dir, matched_edit_targets


METRICS = ("edit_recall", "complete_edit")


def parse_named_path(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    name, path = (part.strip() for part in raw.split("=", 1))
    if not name or not path:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    return name, Path(path)


def parse_comparison(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise ValueError(f"Expected BASELINE=TREATMENT, got {raw!r}")
    baseline, treatment = (part.strip() for part in raw.split("=", 1))
    if not baseline or not treatment:
        raise ValueError(f"Expected BASELINE=TREATMENT, got {raw!r}")
    return baseline, treatment


def load_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            ids.append(json.loads(line)["instance_id"] if line.startswith("{") else line)
    return ids


def score_instance(targets: dict[str, Any], candidates: list[dict], top_k: int) -> dict[str, float]:
    matched: set[str] = set()
    fallback_hit = 0
    for candidate in candidates[:top_k]:
        matched_delta, fallback_delta = matched_edit_targets(candidate, targets)
        matched.update(matched_delta)
        fallback_hit = max(fallback_hit, fallback_delta)

    denominator = max(1, int(targets["gt_entities_n"]))
    found = fallback_hit if targets["fallback_file_target"] else len(matched)
    return {
        "edit_recall": found / denominator,
        "complete_edit": float(found >= denominator),
    }


def load_group(
    ids: list[str],
    targets: dict[str, dict],
    directory: Path,
    top_k: int,
) -> dict[str, dict[str, float]]:
    candidates = candidates_from_dir(ids, directory, top_limit=top_k)
    return {
        instance_id: score_instance(targets[instance_id], candidates[instance_id], top_k)
        for instance_id in ids
    }


def paired_rows(
    baseline: str,
    treatment: str,
    ids: list[str],
    groups: dict[str, dict[str, dict[str, float]]],
    top_k: int,
    iterations: int,
    seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric_index, metric in enumerate(METRICS):
        values = [
            (groups[baseline][instance_id][metric], groups[treatment][instance_id][metric])
            for instance_id in ids
        ]
        baseline_mean = sum(old for old, _ in values) / len(values)
        treatment_mean = sum(new for _, new in values) / len(values)
        wins = sum(new > old + 1e-12 for old, new in values)
        losses = sum(new < old - 1e-12 for old, new in values)
        low, high = bootstrap_ci(values, iterations, seed + metric_index)
        rows.append(
            {
                "baseline": baseline,
                "treatment": treatment,
                "top_k": top_k,
                "metric": metric,
                "N": len(values),
                "baseline_value": baseline_mean,
                "treatment_value": treatment_mean,
                "delta": treatment_mean - baseline_mean,
                "ci95_low": low,
                "ci95_high": high,
                "wins": wins,
                "losses": losses,
                "ties": len(values) - wins - losses,
                "exact_mcnemar_p": exact_mcnemar_p(wins, losses) if metric == "complete_edit" else "NA",
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--target-cache", type=Path, required=True)
    parser.add_argument("--group", action="append", default=[], metavar="NAME=DIR")
    parser.add_argument("--compare", action="append", default=[], metavar="BASELINE=TREATMENT")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--bootstrap-iters", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.group or not args.compare:
        raise ValueError("At least one --group and --compare are required")

    ids = load_ids(args.ids_file)
    target_payload = json.loads(args.target_cache.read_text(encoding="utf-8"))
    targets = target_payload["items"]
    missing_targets = [instance_id for instance_id in ids if instance_id not in targets]
    if missing_targets:
        raise ValueError(f"Target cache is missing {len(missing_targets)} instances")

    group_paths = dict(parse_named_path(raw) for raw in args.group)
    groups = {
        name: load_group(ids, targets, directory, args.top_k)
        for name, directory in group_paths.items()
    }

    output: list[dict[str, Any]] = []
    for comparison_index, raw in enumerate(args.compare):
        baseline, treatment = parse_comparison(raw)
        if baseline not in groups or treatment not in groups:
            raise ValueError(f"Unknown comparison group: {raw}")
        output.extend(
            paired_rows(
                baseline,
                treatment,
                ids,
                groups,
                args.top_k,
                args.bootstrap_iters,
                args.seed + comparison_index * 10,
            )
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "baseline",
        "treatment",
        "top_k",
        "metric",
        "N",
        "baseline_value",
        "treatment_value",
        "delta",
        "ci95_low",
        "ci95_high",
        "wins",
        "losses",
        "ties",
        "exact_mcnemar_p",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
