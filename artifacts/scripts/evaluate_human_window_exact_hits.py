#!/usr/bin/env python3
"""Evaluate the exact frozen human-audit windows against strict targets."""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import json
from pathlib import Path
from typing import Any


def load_evaluator():
    path = Path(__file__).with_name("evaluate_strict_reference_context.py")
    spec = importlib.util.spec_from_file_location("strict_context", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def read_rankings(path: Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    output: dict[str, dict[str, list[dict[str, Any]]]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            output[record["instance_id"]] = record["sources"]
    return output


def repository_id(instance_id: str) -> str:
    return instance_id.rsplit("-", 1)[0]


def main() -> int:
    args = parse_args()
    evaluator = load_evaluator()
    payload = json.loads(args.items.read_text(encoding="utf-8"))
    targets = json.loads(args.targets.read_text(encoding="utf-8"))["items"]
    rankings = read_rankings(args.rankings)
    rows: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        instance_id = item["instance_id"]
        for method in ("BM25-local", "MURAL"):
            result = evaluator.evaluate_instance(
                rankings[instance_id][method], targets[instance_id], top_k=20
            )
            rows.append(
                {
                    "approach": method,
                    "instance_id": instance_id,
                    "repository": repository_id(instance_id),
                    **result,
                }
            )
    fields = [
        "approach",
        "instance_id",
        "repository",
        "candidate_count",
        "target_count",
        "matched_target_count",
        "first_rank",
        "file_hit",
        "target_coverage",
        "hit",
        "mrr",
        "complete",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"evaluated {len(rows)} exact human-audit windows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
