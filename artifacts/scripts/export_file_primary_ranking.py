#!/usr/bin/env python3
"""Reorder projected entities with source-file rank as the primary key.

The released Entity Projection ranks all entities in the retrieved file pool
with issue-conditioned entity signals before the source file rank. This
control preserves the same files and entities while making source file rank
primary and retaining the released entity order within each file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def normalized_path(value: object) -> str:
    return str(value or "").replace("\\", "/").lstrip("./")


def explicit_file_rank(item: dict[str, Any]) -> int | None:
    path_mining = (item.get("evidence") or {}).get("path_mining") or {}
    value = path_mining.get("file_best_rank")
    if isinstance(value, int) and value > 0:
        return value
    for detail in item.get("path_details") or []:
        value = detail.get("file_rank")
        if isinstance(value, int) and value > 0:
            return value
    return None


def reorder(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_seen: dict[str, int] = {}
    source_rank: dict[str, int] = {}
    for item in items:
        file_path = normalized_path(item.get("file_path"))
        if not file_path:
            continue
        first_seen.setdefault(file_path, len(first_seen) + 1)
        rank = explicit_file_rank(item)
        if rank is not None:
            source_rank[file_path] = min(source_rank.get(file_path, rank), rank)

    fallback_offset = max(source_rank.values(), default=0)
    indexed = list(enumerate(items))
    indexed.sort(
        key=lambda pair: (
            source_rank.get(
                normalized_path(pair[1].get("file_path")),
                fallback_offset
                + first_seen.get(normalized_path(pair[1].get("file_path")), 9999),
            ),
            pair[0],
        )
    )
    return [item for _, item in indexed]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for source_path in sorted(args.input_dir.glob("*.json")):
        destination = args.output_dir / source_path.name
        if destination.exists() and not args.force:
            continue
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        related = payload.setdefault("related_entities", {})
        related["methods"] = reorder(list(related.get("methods") or []))
        related["classes"] = reorder(list(related.get("classes") or []))
        payload["ordering_control"] = {
            "file_order": "source file rank",
            "within_file_order": "released issue-conditioned entity order",
        }
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        written += 1
    if not written and not any(args.output_dir.glob("*.json")):
        raise ValueError(f"No JSON rankings in {args.input_dir}")
    print(f"wrote {written} file-primary rankings to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
