#!/usr/bin/env python3
"""Summarize exact-file target evidence in the strict target ledger."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


FLAGS = {
    "added_or_outer_scope": "added_or_outer_scope_change",
    "base_scope": "base_scope_change",
    "patched_parse_failure": "patched_parse_failure",
    "new_or_missing_base_file": "new_or_missing_base_file",
    "non_python_change": "non_python_change",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-instances", required=True, type=Path)
    return parser.parse_args()


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def evidence_flags(evidence: str) -> dict[str, int]:
    tokens = set(evidence.split("+"))
    return {label: int(token in tokens) for label, token in FLAGS.items()}


def main() -> int:
    args = parse_args()
    payload = json.loads(args.targets.read_text(encoding="utf-8"))
    instance_rows: list[dict[str, object]] = []
    exact = Counter()
    for instance_id, item in sorted(payload["items"].items()):
        for target in item["targets"]:
            if target["target_type"] != "file":
                continue
            evidence = str(target["evidence"])
            exact[evidence] += 1
            instance_rows.append(
                {
                    "instance_id": instance_id,
                    "file_path": target["file_path"],
                    "evidence": evidence,
                    **evidence_flags(evidence),
                }
            )

    total = len(instance_rows)
    summary_rows: list[dict[str, object]] = [
        {
            "category": "all_file_targets",
            "count": total,
            "share": "1.000000",
            "counting": "exclusive_total",
        }
    ]
    for label in FLAGS:
        count = sum(int(row[label]) for row in instance_rows)
        summary_rows.append(
            {
                "category": label,
                "count": count,
                "share": f"{count / total:.6f}",
                "counting": "overlapping_evidence_flag",
            }
        )
    for evidence, count in sorted(exact.items()):
        summary_rows.append(
            {
                "category": f"exact:{evidence}",
                "count": count,
                "share": f"{count / total:.6f}",
                "counting": "exclusive_exact_evidence",
            }
        )

    write_tsv(args.output_summary, summary_rows)
    write_tsv(args.output_instances, instance_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
