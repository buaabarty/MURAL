#!/usr/bin/env python3
"""Build a deterministic same-file-neighbor tail for prefix controls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ranked_methods(payload: dict[str, Any]) -> list[dict[str, Any]]:
    methods = (payload.get("related_entities") or {}).get("methods") or []
    return sorted(
        methods,
        key=lambda item: float(item.get("similarity") or 0.0),
        reverse=True,
    )


def identity(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(item.get("file_path") or "").replace("\\", "/"),
        str(item.get("signature") or item.get("name") or ""),
        int(item.get("start_line") or 0),
        int(item.get("end_line") or 0),
    )


def line_distance(item: dict[str, Any], anchors: list[dict[str, Any]]) -> int:
    start = int(item.get("start_line") or 0)
    end = int(item.get("end_line") or start)
    distances = []
    for anchor in anchors:
        anchor_start = int(anchor.get("start_line") or 0)
        anchor_end = int(anchor.get("end_line") or anchor_start)
        if end < anchor_start:
            distances.append(anchor_start - end)
        elif anchor_end < start:
            distances.append(start - anchor_end)
        else:
            distances.append(0)
    return min(distances) if distances else 10**9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-dir", required=True, type=Path)
    parser.add_argument("--pool-dir", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prefix", type=int, default=10)
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    id_sets = [{path.stem for path in args.primary_dir.glob("*.json")}]
    id_sets.extend({path.stem for path in path.glob("*.json")} for path in args.pool_dir)
    instance_ids = sorted(set.intersection(*id_sets))
    if not instance_ids:
        raise ValueError("No shared instances across primary and pool directories")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for instance_id in instance_ids:
        filename = f"{instance_id}.json"
        primary_payload = json.loads(
            (args.primary_dir / filename).read_text(encoding="utf-8")
        )
        prefix = ranked_methods(primary_payload)[: args.prefix]
        anchors_by_file: dict[str, list[dict[str, Any]]] = {}
        file_order: dict[str, int] = {}
        for item in prefix:
            path = str(item.get("file_path") or "").replace("\\", "/")
            if not path:
                continue
            file_order.setdefault(path, len(file_order))
            anchors_by_file.setdefault(path, []).append(item)

        candidates: dict[tuple[Any, ...], dict[str, Any]] = {}
        for pool_dir in args.pool_dir:
            payload = json.loads((pool_dir / filename).read_text(encoding="utf-8"))
            for item in ranked_methods(payload):
                path = str(item.get("file_path") or "").replace("\\", "/")
                if path not in anchors_by_file:
                    continue
                candidates.setdefault(identity(item), item)

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                file_order[str(item.get("file_path") or "").replace("\\", "/")],
                line_distance(
                    item,
                    anchors_by_file[
                        str(item.get("file_path") or "").replace("\\", "/")
                    ],
                ),
                int(item.get("start_line") or 0),
                str(item.get("signature") or item.get("name") or ""),
            ),
        )
        output_methods = []
        for rank, item in enumerate(ranked[: args.limit], start=1):
            copied = dict(item)
            copied["similarity"] = 1.0 / rank
            copied.setdefault("evidence", {})["same_file_neighbor"] = {
                "rank": rank,
                "prefix": args.prefix,
                "line_distance": line_distance(
                    item,
                    anchors_by_file[
                        str(item.get("file_path") or "").replace("\\", "/")
                    ],
                ),
            }
            output_methods.append(copied)

        output = {
            "related_entities": {"methods": output_methods, "classes": [], "issues": []},
            "tail_params": {
                "strategy": "same_file_line_distance",
                "primary_dir": str(args.primary_dir),
                "pool_dirs": [str(path) for path in args.pool_dir],
                "prefix": args.prefix,
                "limit": args.limit,
            },
        }
        (args.output_dir / filename).write_text(
            json.dumps(output, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    print(f"wrote {len(instance_ids)} same-file tails to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
