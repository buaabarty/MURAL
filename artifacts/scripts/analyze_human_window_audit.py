#!/usr/bin/env python3
"""Summarize the anonymized blinded MURAL/BM25 window audit."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


PREFERENCE_ORDER = ("MURAL", "BM25-local", "Comparable", "Both insufficient")
NON_POSITIONAL_LABELS = {
    "基本相当": "Comparable",
    "两者都不足": "Both insufficient",
}
REQUIRED_COLUMNS = {
    "annotator",
    "annotation_id",
    "instance_id",
    "assignment",
    "method_a",
    "method_b",
    "objective_outcome",
    "window_preference_label",
    "preferred_method",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path} contains no annotation rows")
    return rows


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> tuple[int, float, float]:
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("Cohen's kappa requires two nonempty aligned label sequences")
    n = len(labels_a)
    agreements = sum(a == b for a, b in zip(labels_a, labels_b))
    observed = agreements / n
    counts_a = Counter(labels_a)
    counts_b = Counter(labels_b)
    expected = sum((counts_a[label] / n) * (counts_b[label] / n) for label in set(counts_a) | set(counts_b))
    kappa = (observed - expected) / (1.0 - expected) if expected < 1.0 else 1.0
    return agreements, observed, kappa


def validate(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    by_annotator: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["annotator"], row["annotation_id"])
        if key in seen:
            raise ValueError(f"duplicate annotator/item pair: {key}")
        seen.add(key)
        if row["preferred_method"] not in PREFERENCE_ORDER:
            raise ValueError(f"unsupported preference label: {row['preferred_method']}")
        if {row["method_a"], row["method_b"]} != {"MURAL", "BM25-local"}:
            raise ValueError(f"unblinding map is invalid for {row['annotation_id']}")
        label = row["window_preference_label"]
        if label == "窗口A":
            expected_preference = row["method_a"]
        elif label == "窗口B":
            expected_preference = row["method_b"]
        elif label in NON_POSITIONAL_LABELS:
            expected_preference = NON_POSITIONAL_LABELS[label]
        else:
            raise ValueError(f"unsupported blinded label: {label}")
        if row["preferred_method"] != expected_preference:
            raise ValueError(
                f"decoded preference is inconsistent for {row['annotation_id']}: "
                f"expected {expected_preference}, found {row['preferred_method']}"
            )
        by_annotator[row["annotator"]].append(row)
    if set(by_annotator) != {"A", "B"}:
        raise ValueError(f"expected annotators A and B, found {sorted(by_annotator)}")
    return by_annotator


def summarize(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    by_annotator = validate(rows)
    summary: list[dict[str, object]] = []

    def add_scope(scope: str, scoped_rows: list[dict[str, str]]) -> None:
        counts = Counter(row["preferred_method"] for row in scoped_rows)
        denominator = len(scoped_rows)
        for category in PREFERENCE_ORDER:
            count = counts[category]
            summary.append(
                {
                    "scope": scope,
                    "category": category,
                    "count": count,
                    "denominator": denominator,
                    "share": count / denominator,
                }
            )

    add_scope("all_judgments", rows)
    for annotator in ("A", "B"):
        add_scope(f"annotator_{annotator}", by_annotator[annotator])

    by_item: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_item[row["annotation_id"]].append(row)
    consensus_rows: list[dict[str, str]] = []
    for annotation_id, item_rows in sorted(by_item.items()):
        labels = {row["preferred_method"] for row in item_rows}
        label = next(iter(labels)) if len(labels) == 1 else "No consensus"
        consensus_rows.append({"preferred_method": label, "annotation_id": annotation_id})
    counts = Counter(row["preferred_method"] for row in consensus_rows)
    for category in (*PREFERENCE_ORDER, "No consensus"):
        count = counts[category]
        summary.append(
            {
                "scope": "unique_instances",
                "category": category,
                "count": count,
                "denominator": len(consensus_rows),
                "share": count / len(consensus_rows),
            }
        )

    indexed = {
        annotator: {row["annotation_id"]: row for row in annotator_rows}
        for annotator, annotator_rows in by_annotator.items()
    }
    overlap = sorted(set(indexed["A"]) & set(indexed["B"]))
    labels_a = [indexed["A"][item]["window_preference_label"] for item in overlap]
    labels_b = [indexed["B"][item]["window_preference_label"] for item in overlap]
    agreements, observed, kappa = cohen_kappa(labels_a, labels_b)
    agreement = [
        {
            "field": "window_preference_label",
            "overlap_n": len(overlap),
            "agreement_n": agreements,
            "observed_agreement": observed,
            "cohen_kappa": kappa,
        }
    ]
    return summary, agreement


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--agreement-output", type=Path, required=True)
    args = parser.parse_args()

    rows = read_tsv(args.annotations)
    summary, agreement = summarize(rows)
    write_tsv(
        args.summary_output,
        ["scope", "category", "count", "denominator", "share"],
        summary,
    )
    write_tsv(
        args.agreement_output,
        ["field", "overlap_n", "agreement_n", "observed_agreement", "cohen_kappa"],
        agreement,
    )
    all_counts = {row["category"]: row["count"] for row in summary if row["scope"] == "all_judgments"}
    print(
        "Blinded window audit: "
        f"MURAL={all_counts['MURAL']}, BM25-local={all_counts['BM25-local']}, "
        f"comparable={all_counts['Comparable']}, insufficient={all_counts['Both insufficient']}; "
        f"agreement={agreement[0]['observed_agreement']:.3f}, kappa={agreement[0]['cohen_kappa']:.3f}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
