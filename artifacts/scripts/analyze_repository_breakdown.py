#!/usr/bin/env python3
"""Aggregate localization and repair outcomes by repository."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_eval_module() -> Any:
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "scripts" / "eval_controls_v3.py"
    spec = importlib.util.spec_from_file_location("eval_controls_v3", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_named_path(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    name, value = (part.strip() for part in raw.split("=", 1))
    if not name or not value:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    return name, Path(value)


def repository_from_instance_id(instance_id: str) -> str:
    owner, repository_and_id = instance_id.split("__", 1)
    repository = re.sub(r"-\d+$", "", repository_and_id)
    return f"{owner}/{repository}"


def mean(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows)


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def localization_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    eval_module = load_eval_module()
    ids = eval_module.load_ids(args.ids_file)
    gt_map = eval_module.load_or_build_gt_cache(ids, args.gt_cache)
    groups = [parse_named_path(raw) for raw in args.localization]
    evaluated: dict[str, dict[str, dict[str, Any]]] = {}

    for name, directory in groups:
        per_instance: dict[str, dict[str, Any]] = {}
        for instance_id in ids:
            path = directory / f"{instance_id}.json"
            if not path.exists():
                raise FileNotFoundError(f"Missing {name} output: {path}")
            per_instance[instance_id] = eval_module.evaluate_one_instance(
                json.loads(path.read_text(encoding="utf-8")),
                gt_map[instance_id],
                args.top_k,
            )
        evaluated[name] = per_instance

    repositories = sorted({repository_from_instance_id(instance_id) for instance_id in ids})
    output: list[dict[str, Any]] = []
    for repository in [*repositories, "ALL"]:
        selected = [
            instance_id
            for instance_id in ids
            if repository == "ALL" or repository_from_instance_id(instance_id) == repository
        ]
        for name, _ in groups:
            rows = [evaluated[name][instance_id] for instance_id in selected]
            output.append(
                {
                    "repository": repository,
                    "N": len(rows),
                    "method": name,
                    "file_rate": mean(rows, "find_file"),
                    "entity_coverage": mean(rows, "ratio"),
                    "mrr": sum(
                        0.0 if row.get("best_rank") is None else 1.0 / float(row["best_rank"])
                        for row in rows
                    )
                    / len(rows),
                    "hit_rate": mean(rows, "hit"),
                }
            )
    return output


def repair_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle, delimiter="\t"))
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        grouped[(repository_from_instance_id(row["instance_id"]), row["variant"])].append(row)

    repositories = sorted({repository for repository, _ in grouped})
    variants = sorted({variant for _, variant in grouped})
    output: list[dict[str, Any]] = []
    for repository in [*repositories, "ALL"]:
        for variant in variants:
            rows = (
                [row for (repo, name), values in grouped.items() if name == variant for row in values]
                if repository == "ALL"
                else grouped[(repository, variant)]
            )
            if not rows:
                continue
            output.append(
                {
                    "repository": repository,
                    "N": len(rows),
                    "variant": variant,
                    "nonempty": sum(int(row["nonempty"]) for row in rows),
                    "applied": sum(int(row["applied"]) for row in rows),
                    "resolved": sum(int(row["resolved"]) for row in rows),
                    "resolved_rate": sum(int(row["resolved"]) for row in rows) / len(rows),
                }
            )
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-file", type=Path, default=Path("temp_run/SWE-bench_Verified_ids.jsonl"))
    parser.add_argument(
        "--gt-cache",
        type=Path,
        default=Path("temp_run/output/gt_eval_cache_verified_v3_entities.json"),
    )
    parser.add_argument("--localization", action="append", required=True, help="NAME=DIR")
    parser.add_argument("--repair-outcomes", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--output-localization", type=Path, required=True)
    parser.add_argument("--output-repair", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    write_tsv(
        args.output_localization,
        localization_rows(args),
        ["repository", "N", "method", "file_rate", "entity_coverage", "mrr", "hit_rate"],
    )
    write_tsv(
        args.output_repair,
        repair_rows(args.repair_outcomes),
        ["repository", "N", "variant", "nonempty", "applied", "resolved", "resolved_rate"],
    )
    print(f"wrote {args.output_localization}")
    print(f"wrote {args.output_repair}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
