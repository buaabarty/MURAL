#!/usr/bin/env python3
"""Recompute the construct and support-role audit statistics."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "artifacts" / "results"


def read_tsv(name: str) -> list[dict[str, str]]:
    with (RESULTS / name).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def reliability(rows: list[dict[str, str]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["annotation_id"], []).append(row)
    pairs = [
        (items[0][field], items[1][field])
        for items in grouped.values()
        if len(items) == 2
    ]
    labels = sorted({label for pair in pairs for label in pair})
    matches = sum(left == right for left, right in pairs)
    observed = matches / len(pairs)
    expected = sum(
        sum(left == label for left, _ in pairs) / len(pairs)
        * sum(right == label for _, right in pairs) / len(pairs)
        for label in labels
    )
    return {
        "n": len(pairs),
        "agreement_count": matches,
        "agreement": observed,
        "kappa": (observed - expected) / (1 - expected),
    }


def analyze() -> dict[str, Any]:
    construct_raw = read_tsv("human_construct_annotations_raw_20260721.tsv")
    construct_final = read_tsv("human_construct_adjudicated_20260721.tsv")
    support_raw = read_tsv("human_support_annotations_raw_20260721.tsv")
    support_final = read_tsv("human_support_adjudicated_20260721.tsv")

    construct_exact_only = sum(
        row["final_coverage"] == "covered" and int(row["fallback_regions"]) == 0
        for row in construct_final
    )
    return {
        "task_a": {
            "unique_items": len({row["annotation_id"] for row in construct_raw}),
            "judgments": len(construct_raw),
            "shared_items": sum(
                count == 2 for count in Counter(
                    row["annotation_id"] for row in construct_raw
                ).values()
            ),
            "annotator_rows": dict(Counter(row["annotator"] for row in construct_raw)),
            "raw_mapping_reliability": reliability(construct_raw, "mapping_label"),
            "raw_extra_entity_reliability": reliability(construct_raw, "extra_entity"),
            "final_coverage": dict(Counter(row["final_coverage"] for row in construct_final)),
            "exact_entity_only_instances": construct_exact_only,
            "instances_using_file_fallback": sum(
                int(row["fallback_regions"]) > 0 for row in construct_final
            ),
            "unmatched_regions": sum(
                int(row["unmatched_regions"]) for row in construct_final
            ),
        },
        "task_b": {
            "unique_items": len({row["annotation_id"] for row in support_raw}),
            "judgments": len(support_raw),
            "shared_items": sum(
                count == 2 for count in Counter(
                    row["annotation_id"] for row in support_raw
                ).values()
            ),
            "annotator_rows": dict(Counter(row["annotator"] for row in support_raw)),
            "raw_role_reliability": reliability(support_raw, "support_role"),
            "raw_exact_receiver_reliability": reliability(support_raw, "exact_receiver"),
            "final_roles": dict(Counter(row["final_role"] for row in support_final)),
        },
    }


def verify(summary: dict[str, Any]) -> None:
    task_a = summary["task_a"]
    assert task_a["unique_items"] == 60
    assert task_a["judgments"] == 80
    assert task_a["shared_items"] == 20
    assert task_a["annotator_rows"] == {"A": 40, "B": 40}
    assert task_a["raw_mapping_reliability"]["agreement_count"] == 10
    assert task_a["raw_extra_entity_reliability"]["agreement_count"] == 16
    assert task_a["final_coverage"] == {"covered": 60}
    assert task_a["exact_entity_only_instances"] == 26
    assert task_a["instances_using_file_fallback"] == 34
    assert task_a["unmatched_regions"] == 0

    task_b = summary["task_b"]
    assert task_b["unique_items"] == 100
    assert task_b["judgments"] == 120
    assert task_b["shared_items"] == 20
    assert task_b["annotator_rows"] == {"A": 60, "B": 60}
    assert task_b["raw_role_reliability"]["agreement_count"] == 0
    assert task_b["raw_exact_receiver_reliability"]["agreement_count"] == 11
    assert task_b["final_roles"] == {
        "irrelevant": 68,
        "required": 2,
        "strong": 12,
        "weak": 18,
    }


def main() -> None:
    summary = analyze()
    verify(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
