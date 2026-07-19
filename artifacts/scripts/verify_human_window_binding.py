#!/usr/bin/env python3
"""Verify that blinded audit windows are exact views of frozen rankings."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


METHOD_TO_SOURCE = {
    "BM25_projection": "BM25_projection",
    "MURAL_2src": "MURAL_2src",
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
    if len(text) > DISPLAY_WIDTH:
        return text[: DISPLAY_WIDTH - 3] + "..."
    return text


def render_window(candidates: list[dict[str, Any]], top_k: int = 20) -> str:
    if len(candidates) < top_k:
        raise ValueError(f"ranking has only {len(candidates)} candidates; expected {top_k}")
    return "\n".join(
        f"{rank:02d}. {candidate['file_path']} :: {compact_signature(candidate.get('signature'))}"
        for rank, candidate in enumerate(candidates[:top_k], start=1)
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_rankings(
    path: Path,
    instance_ids: set[str] | None = None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    opener = gzip.open if path.suffix == ".gz" else path.open
    rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            instance_id = record["instance_id"]
            if instance_ids is not None and instance_id not in instance_ids:
                continue
            if instance_id in rankings:
                raise ValueError(f"duplicate ranking instance: {instance_id}")
            rankings[instance_id] = record["sources"]
    return rankings


def verify(
    payload: dict[str, Any],
    rankings: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    items = payload.get("items", [])
    if not items:
        raise ValueError("audit payload contains no items")

    binding: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        annotation_id = item["annotation_id"]
        instance_id = item["instance_id"]
        if annotation_id in seen:
            raise ValueError(f"duplicate annotation id: {annotation_id}")
        seen.add(annotation_id)
        if instance_id not in rankings:
            raise ValueError(f"missing frozen ranking for {instance_id}")
        if {item["method_a"], item["method_b"]} != set(METHOD_TO_SOURCE):
            raise ValueError(f"invalid method pair for {annotation_id}")

        row: dict[str, Any] = {
            "annotation_id": annotation_id,
            "instance_id": instance_id,
            "assignment": item["assignment"],
        }
        for side in ("a", "b"):
            method = item[f"method_{side}"]
            source = METHOD_TO_SOURCE[method]
            try:
                expected = render_window(rankings[instance_id][source])
            except KeyError as exc:
                raise ValueError(
                    f"missing frozen source {source} for {instance_id}"
                ) from exc
            observed = item[f"window_{side}"]
            if observed != expected:
                raise ValueError(
                    f"{annotation_id} window {side.upper()} does not match "
                    f"{source} Top-20 for {instance_id}"
                )
            row[f"method_{side}"] = method
            row[f"source_{side}"] = source
            row[f"window_{side}_sha256"] = sha256_text(observed)
            row[f"exact_match_{side}"] = 1
        binding.append(row)
    return binding


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
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


def main() -> int:
    args = parse_args()
    payload = json.loads(args.items.read_text(encoding="utf-8"))
    instance_ids = {item["instance_id"] for item in payload.get("items", [])}
    binding = verify(
        payload, read_rankings(args.rankings, instance_ids=instance_ids)
    )
    write_tsv(args.output_binding, binding)
    print(
        f"verified {len(binding)} blinded items: every A/B window is an exact "
        "Top-20 view of BM25_projection or MURAL_2src"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
