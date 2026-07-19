#!/usr/bin/env python3
"""Rebuild blinded audit windows from the frozen paper-facing rankings."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


METHOD_TO_SOURCE = {
    "MURAL": "MURAL",
    "BM25-local": "BM25_projection",
}
DISPLAY_WIDTH = 360


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-items", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--output-items", type=Path, required=True)
    parser.add_argument("--output-alignment", type=Path, required=True)
    parser.add_argument("--version-date", default="2026-07-19")
    return parser.parse_args()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def canonical_window(candidates: list[dict[str, Any]], top_k: int = 20) -> list[list[Any]]:
    return [
        [
            candidate.get("file_path", ""),
            candidate.get("entity_type", ""),
            candidate.get("name", ""),
            candidate.get("start_line"),
            candidate.get("end_line"),
        ]
        for candidate in candidates[:top_k]
    ]


def window_sha256(candidates: list[dict[str, Any]], top_k: int = 20) -> str:
    payload = json.dumps(
        canonical_window(candidates, top_k),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def read_rankings(path: Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    opener = gzip.open if path.suffix == ".gz" else path.open
    rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            instance_id = record["instance_id"]
            if instance_id in rankings:
                raise ValueError(f"duplicate ranking instance: {instance_id}")
            rankings[instance_id] = record["sources"]
    return rankings


def rebuild(
    old_payload: dict[str, Any],
    rankings: dict[str, dict[str, list[dict[str, Any]]]],
    rankings_sha256: str,
    version_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    old_items = old_payload.get("items", [])
    if not old_items:
        raise ValueError("old audit payload contains no items")

    rebuilt_items: list[dict[str, Any]] = []
    alignment: list[dict[str, Any]] = []
    seen: set[str] = set()
    for old in old_items:
        annotation_id = old["annotation_id"]
        instance_id = old["instance_id"]
        if annotation_id in seen:
            raise ValueError(f"duplicate annotation id: {annotation_id}")
        seen.add(annotation_id)
        if instance_id not in rankings:
            raise ValueError(f"missing frozen ranking for {instance_id}")
        if {old["method_a"], old["method_b"]} != set(METHOD_TO_SOURCE):
            raise ValueError(f"invalid blinded method pair for {annotation_id}")

        current_windows: dict[str, str] = {}
        current_hashes: dict[str, str] = {}
        changed: dict[str, bool] = {}
        for side in ("a", "b"):
            method = old[f"method_{side}"]
            source = METHOD_TO_SOURCE[method]
            candidates = rankings[instance_id][source]
            current_windows[side] = render_window(candidates)
            current_hashes[side] = window_sha256(candidates)
            changed[side] = old[f"window_{side}"] != current_windows[side]

        rebuilt = dict(old)
        rebuilt.update(
            {
                "window_a": current_windows["a"],
                "window_b": current_windows["b"],
                "window_a_sha256": current_hashes["a"],
                "window_b_sha256": current_hashes["b"],
                "requires_reannotation": changed["a"] or changed["b"],
            }
        )
        rebuilt_items.append(rebuilt)
        alignment.append(
            {
                "annotation_id": annotation_id,
                "instance_id": instance_id,
                "assignment": old["assignment"],
                "window_a_changed": int(changed["a"]),
                "window_b_changed": int(changed["b"]),
                "requires_reannotation": int(changed["a"] or changed["b"]),
                "window_a_sha256": current_hashes["a"],
                "window_b_sha256": current_hashes["b"],
            }
        )

    protocol = dict(old_payload.get("protocol", {}))
    protocol.update(
        {
            "version_date": version_date,
            "ranking_file_sha256": rankings_sha256,
            "ranking_sources": METHOD_TO_SOURCE,
            "window_size_entities": 20,
            "alignment_rule": "exact rendered Top-20 window",
        }
    )
    return {"protocol": protocol, "items": rebuilt_items}, alignment


def write_tsv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(records[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    args = parse_args()
    old_payload = json.loads(args.old_items.read_text(encoding="utf-8"))
    rankings_sha256 = sha256_file(args.rankings)
    rebuilt, alignment = rebuild(
        old_payload,
        read_rankings(args.rankings),
        rankings_sha256,
        args.version_date,
    )
    args.output_items.parent.mkdir(parents=True, exist_ok=True)
    args.output_items.write_text(
        json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_tsv(args.output_alignment, alignment)
    changed = sum(int(row["requires_reannotation"]) for row in alignment)
    print(
        f"rebuilt {len(alignment)} blinded items from {args.rankings.name}; "
        f"{changed} require reannotation and {len(alignment) - changed} are unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
