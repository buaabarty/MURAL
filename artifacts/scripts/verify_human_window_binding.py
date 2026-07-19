#!/usr/bin/env python3
"""Verify that every annotated A/B window matches its frozen audit ranking."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


METHOD_TO_CONFIGURATION = {
    "BM25-local": "BM25_projection",
    "MURAL": "MURAL_BM25_structural",
}
DISPLAY_WIDTH = 360


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--output-binding", type=Path, required=True)
    return parser.parse_args()


def compact_signature(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= DISPLAY_WIDTH else text[: DISPLAY_WIDTH - 3] + "..."


def render_window(candidates: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{rank:02d}. {candidate.get('file_path') or '（未知文件）'} :: "
        f"{compact_signature(candidate.get('signature') or candidate.get('name'))}"
        for rank, candidate in enumerate(candidates[:20], start=1)
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_rankings(path: Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            rankings[record["instance_id"]] = record["sources"]
    return rankings


def verify(payload: dict[str, Any], rankings: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        instance_id = item["instance_id"]
        if set((item["method_a"], item["method_b"])) != set(METHOD_TO_CONFIGURATION):
            raise ValueError(f"invalid method mapping for {item['annotation_id']}")
        row: dict[str, Any] = {
            "annotation_id": item["annotation_id"],
            "instance_id": instance_id,
            "assignment": item["assignment"],
        }
        for side in ("a", "b"):
            method = item[f"method_{side}"]
            observed = item[f"window_{side}"]
            expected = render_window(rankings[instance_id][method])
            if observed != expected:
                raise ValueError(
                    f"{item['annotation_id']} window {side.upper()} does not match {method}"
                )
            row[f"method_{side}"] = method
            row[f"configuration_{side}"] = METHOD_TO_CONFIGURATION[method]
            row[f"window_{side}_sha256"] = sha256_text(observed)
            row[f"exact_match_{side}"] = 1
        rows.append(row)
    return rows


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    payload = json.loads(args.items.read_text(encoding="utf-8"))
    rows = verify(payload, read_rankings(args.rankings))
    write_tsv(args.output_binding, rows)
    print(f"verified {len(rows)} exact human-audit A/B window pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
