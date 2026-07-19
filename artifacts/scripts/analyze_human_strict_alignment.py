#!/usr/bin/env python3
"""Relabel blinded window judgments with strict objective-hit strata."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--strict-instances", type=Path, required=True)
    parser.add_argument("--output-judgments", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def strict_stratum(bm25_hit: int, mural_hit: int) -> str:
    if mural_hit and not bm25_hit:
        return "MURAL_only"
    if bm25_hit and not mural_hit:
        return "BM25_only"
    if bm25_hit:
        return "both"
    return "neither"


def directional_alignment(stratum: str, preference: str) -> str:
    expected = "MURAL" if stratum == "MURAL_only" else "BM25-local" if stratum == "BM25_only" else ""
    if not expected:
        return "not_exclusive"
    if preference == expected:
        return "aligned"
    if preference in {"MURAL", "BM25-local"}:
        return "opposed"
    return "neutral"


def main() -> int:
    args = parse_args()
    hits: dict[tuple[str, str], int] = {}
    for row in read_tsv(args.strict_instances):
        if row["approach"] in {"BM25_projection", "MURAL"}:
            hits[(row["instance_id"], row["approach"])] = int(row["hit"])

    judgments: list[dict] = []
    for row in read_tsv(args.annotations):
        instance_id = row["instance_id"]
        stratum = strict_stratum(
            hits[(instance_id, "BM25_projection")], hits[(instance_id, "MURAL")]
        )
        judgments.append(
            {
                "annotation_id": row["annotation_id"],
                "instance_id": instance_id,
                "annotator": row["annotator"],
                "strict_stratum": stratum,
                "preferred_method": row["preferred_method"],
                "directional_alignment": directional_alignment(
                    stratum, row["preferred_method"]
                ),
            }
        )

    unique_strata: dict[str, str] = {}
    for row in judgments:
        unique_strata[row["instance_id"]] = row["strict_stratum"]
    summary: list[dict] = []
    for stratum, count in sorted(Counter(unique_strata.values()).items()):
        summary.append(
            {
                "scope": "unique_instances",
                "strict_stratum": stratum,
                "decision": "instances",
                "count": count,
            }
        )
    for (stratum, decision), count in sorted(
        Counter((row["strict_stratum"], row["preferred_method"]) for row in judgments).items()
    ):
        summary.append(
            {
                "scope": "judgments",
                "strict_stratum": stratum,
                "decision": decision,
                "count": count,
            }
        )
    for decision, count in sorted(
        Counter(
            row["directional_alignment"]
            for row in judgments
            if row["directional_alignment"] != "not_exclusive"
        ).items()
    ):
        summary.append(
            {
                "scope": "exclusive_hit_judgments",
                "strict_stratum": "MURAL_only_or_BM25_only",
                "decision": decision,
                "count": count,
            }
        )

    write_tsv(args.output_judgments, judgments, list(judgments[0]))
    write_tsv(
        args.output_summary,
        summary,
        ["scope", "strict_stratum", "decision", "count"],
    )
    print(f"wrote {args.output_judgments} and {args.output_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
