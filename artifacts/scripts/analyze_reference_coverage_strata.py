#!/usr/bin/env python3
"""Report entity and rendered changed-line coverage by target stratum."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_strict_reference_context import candidate_matches_target, ranked_methods


def parse_named_path(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    name, path = (part.strip() for part in raw.split("=", 1))
    if not name or not path:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    return name, Path(path)


def normalized_path(value: object) -> str:
    return str(value or "").replace("\\", "/").lstrip("./")


def target_stratum(reference: dict[str, Any]) -> str:
    entity_count = int(reference.get("entity_target_count") or 0)
    file_count = int(reference.get("file_target_count") or 0)
    if entity_count and file_count:
        return "mixed"
    if file_count:
        return "file-only"
    return "entity-only"


def load_packing(path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    if path is None:
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return {(row["source"], row["instance_id"]): row for row in rows}


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--row", action="append", required=True, help="NAME=DIR")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--budget-label", default="Top-20")
    parser.add_argument("--packing-instances", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = json.loads(args.targets.read_text(encoding="utf-8"))["items"]
    packing = load_packing(args.packing_instances)
    rows: list[dict[str, Any]] = []

    for approach, ranking_dir in map(parse_named_path, args.row):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for instance_id, reference in targets.items():
            candidates = ranked_methods(ranking_dir, instance_id)[: args.top_k]
            entity_targets = [
                target for target in reference["targets"] if target["target_type"] != "file"
            ]
            matched = {
                index
                for index, target in enumerate(entity_targets)
                if any(candidate_matches_target(candidate, target) for candidate in candidates)
            }
            patch_files = {normalized_path(path) for path in reference.get("patch_files") or []}
            file_hit = int(
                any(
                    normalized_path(candidate.get("file_path")) in patch_files
                    for candidate in candidates
                )
            )
            packing_row = packing.get((approach, instance_id))
            grouped[target_stratum(reference)].append(
                {
                    "entity_coverage": len(matched) / len(entity_targets)
                    if entity_targets
                    else None,
                    "entity_hit": int(bool(matched)) if entity_targets else None,
                    "complete_entity": int(len(matched) == len(entity_targets))
                    if entity_targets
                    else None,
                    "file_hit": file_hit,
                    "changed_lines_covered": int(packing_row["changed_lines_covered"])
                    if packing_row
                    else None,
                    "changed_lines_total": int(packing_row["changed_lines_total"])
                    if packing_row
                    else None,
                    "complete_changed_lines": int(packing_row["complete_changed_lines"])
                    if packing_row
                    else None,
                }
            )

        for stratum in ("entity-only", "mixed", "file-only"):
            values = grouped[stratum]
            entity_values = [row for row in values if row["entity_coverage"] is not None]
            covered_lines = sum(row["changed_lines_covered"] or 0 for row in values)
            total_lines = sum(row["changed_lines_total"] or 0 for row in values)
            complete_lines = [
                row["complete_changed_lines"]
                for row in values
                if row["complete_changed_lines"] is not None
            ]
            rows.append(
                {
                    "approach": approach,
                    "budget": args.budget_label,
                    "stratum": stratum,
                    "N": len(values),
                    "entity_target_coverage": (
                        100
                        * sum(row["entity_coverage"] for row in entity_values)
                        / len(entity_values)
                        if entity_values
                        else ""
                    ),
                    "entity_hit": (
                        100 * sum(row["entity_hit"] for row in entity_values) / len(entity_values)
                        if entity_values
                        else ""
                    ),
                    "complete_entity": (
                        100
                        * sum(row["complete_entity"] for row in entity_values)
                        / len(entity_values)
                        if entity_values
                        else ""
                    ),
                    "file_hit": 100 * sum(row["file_hit"] for row in values) / len(values),
                    "changed_line_recall": 100 * covered_lines / total_lines
                    if total_lines
                    else "",
                    "complete_changed_line": 100 * sum(complete_lines) / len(complete_lines)
                    if complete_lines
                    else "",
                }
            )
    write_tsv(args.output, rows)
    print(f"wrote {len(rows)} stratum rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
