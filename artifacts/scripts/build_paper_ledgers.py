#!/usr/bin/env python3
"""Build the canonical paper-facing MURAL result ledgers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "artifacts" / "results"
LOCALIZATION = RESULTS / "strict_localization_summary_20260719.tsv"
SOURCE_COMBINATIONS = RESULTS / "source_combinations_top20_summary_20260722.tsv"
TARGETS = RESULTS / "strict_reference_targets_20260719.json"
MAIN_OUTPUT = RESULTS / "paper_main_results_20260722.tsv"
PROFILE_OUTPUT = RESULTS / "paper_dataset_profile_20260722.tsv"

MAIN_ROWS = (
    ("Raw BM25 entities", "BM25_entities"),
    ("MURAL (BM25)", "BM25_projection"),
    ("MURAL (Dense)", "Dense_projection"),
    ("BLUiR", "BLUiR"),
    ("StaticGraph", "CodeGraph"),
    ("Raw structural entities", "Structural_entities"),
    ("MURAL (Structural)", "Structural_adapter"),
    ("MURAL (BM25 + Structural)", "MURAL_2src"),
    ("MURAL (BM25 + Dense)", "BM25_Dense"),
    ("MURAL (Structural + Dense)", "Structural_Dense"),
    ("MURAL", "MURAL"),
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_main_results() -> None:
    strict = {row["approach"]: row for row in read_tsv(LOCALIZATION)}
    combinations = {row["approach"]: row for row in read_tsv(SOURCE_COMBINATIONS)}
    source_rows = dict(strict)
    source_rows.update(
        {
            "BM25_Dense": combinations["BM25_Dense"],
            "Structural_Dense": combinations["Structural_Dense"],
        }
    )
    output: list[dict[str, object]] = []
    for paper_label, source_approach in MAIN_ROWS:
        row = source_rows[source_approach]
        source_ledger = (
            SOURCE_COMBINATIONS
            if source_approach in {"BM25_Dense", "Structural_Dense"}
            else LOCALIZATION
        )
        output.append(
            {
                "paper_label": paper_label,
                "source_approach": source_approach,
                "N": int(row["N"]),
                "top_k": int(row["top_k"]),
                "file_hit": f'{float(row["file_hit"]):.1f}',
                "target_coverage": f'{float(row["target_coverage"]):.1f}',
                "mrr": f'{float(row["mrr"]):.1f}',
                "hit_at_20": f'{float(row["hit"]):.1f}',
                "ref_complete": f'{float(row["complete"]):.1f}',
                "source_ledger": source_ledger.relative_to(ROOT).as_posix(),
            }
        )
    write_tsv(
        MAIN_OUTPUT,
        [
            "paper_label",
            "source_approach",
            "N",
            "top_k",
            "file_hit",
            "target_coverage",
            "mrr",
            "hit_at_20",
            "ref_complete",
            "source_ledger",
        ],
        output,
    )


def build_dataset_profile() -> None:
    payload = json.loads(TARGETS.read_text(encoding="utf-8"))
    items = list(payload["items"].values())
    targets = [target for item in items for target in item["targets"]]
    entity_only = sum(item["entity_target_count"] > 0 and item["file_target_count"] == 0 for item in items)
    mixed = sum(item["entity_target_count"] > 0 and item["file_target_count"] > 0 for item in items)
    file_only = sum(item["entity_target_count"] == 0 and item["file_target_count"] > 0 for item in items)
    counts = [
        ("population", "instances", len(items)),
        ("targets", "total", len(targets)),
        ("target_type", "function", sum(target["target_type"] == "function" for target in targets)),
        ("target_type", "assignment", sum(target["target_type"] == "assignment" for target in targets)),
        ("target_type", "file_fallback", sum(target["target_type"] == "file" for target in targets)),
        ("target_stratum", "entity_only", entity_only),
        ("target_stratum", "mixed", mixed),
        ("target_stratum", "file_only", file_only),
        ("target_multiplicity", "single", sum(item["target_count"] == 1 for item in items)),
        ("target_multiplicity", "multi", sum(item["target_count"] > 1 for item in items)),
        ("file_fallback", "instances_with_file_fallback", sum(item["file_target_count"] > 0 for item in items)),
    ]
    source = TARGETS.relative_to(ROOT).as_posix()
    write_tsv(
        PROFILE_OUTPUT,
        ["category", "item", "count", "source_ledger"],
        [
            {"category": category, "item": item, "count": count, "source_ledger": source}
            for category, item, count in counts
        ],
    )


def main() -> None:
    build_main_results()
    build_dataset_profile()
    print(f"Wrote {MAIN_OUTPUT.relative_to(ROOT)}")
    print(f"Wrote {PROFILE_OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
