#!/usr/bin/env python3
"""Fuse source-specific file rankings and emit projection-compatible seeds."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def normalized_path(value: object) -> str:
    return str(value or "").replace("\\", "/").lstrip("./")


def parse_named_path(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    name, directory = (part.strip() for part in raw.split("=", 1))
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name) or not directory:
        raise ValueError(f"Expected a stable source NAME and directory, got {raw!r}")
    return name, Path(directory)


def ranked_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    related = payload.get("related_entities") or {}
    items = list(related.get("methods") or []) + list(related.get("classes") or [])
    if any(isinstance(item.get("similarity"), (int, float)) for item in items):
        items.sort(
            key=lambda item: (
                float(item["similarity"])
                if isinstance(item.get("similarity"), (int, float))
                else float("-inf")
            ),
            reverse=True,
        )
    return items


def file_ranking(payload: dict[str, Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in ranked_items(payload):
        file_path = normalized_path(item.get("file_path"))
        if file_path and file_path not in seen:
            seen.add(file_path)
            output.append(file_path)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, help="NAME=DIR")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--max-files", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = [parse_named_path(raw) for raw in args.source]
    names = [name for name, _ in sources]
    if len(sources) < 2 or len(names) != len(set(names)):
        raise ValueError("Provide at least two uniquely named sources")
    if args.rrf_k < 0 or args.max_files <= 0:
        raise ValueError("Require rrf-k >= 0 and max-files > 0")

    id_sets = [{path.stem for path in directory.glob("*.json")} for _, directory in sources]
    instance_ids = sorted(set.intersection(*id_sets))
    if not instance_ids:
        raise ValueError("No shared JSON instances across source directories")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for instance_id in instance_ids:
        destination = args.output_dir / f"{instance_id}.json"
        if destination.exists() and not args.force:
            continue
        payloads = {
            name: json.loads((directory / destination.name).read_text(encoding="utf-8"))
            for name, directory in sources
        }
        rank_maps = {
            name: {file_path: rank for rank, file_path in enumerate(file_ranking(payload), 1)}
            for name, payload in payloads.items()
        }
        all_files = set().union(*(set(ranks) for ranks in rank_maps.values()))
        scored: list[tuple[tuple[Any, ...], str, dict[str, int | None], float]] = []
        for file_path in all_files:
            ranks = {name: rank_maps[name].get(file_path) for name in names}
            present = [rank for rank in ranks.values() if rank is not None]
            score = sum(1.0 / (args.rrf_k + rank) for rank in present)
            scored.append(((-score, -len(present), min(present), file_path), file_path, ranks, score))
        scored.sort(key=lambda row: row[0])

        methods: list[dict[str, Any]] = []
        for file_rank, (_, file_path, ranks, score) in enumerate(scored[: args.max_files], 1):
            methods.append(
                {
                    "type": "method",
                    "entity_type": "file_seed",
                    "name": f"file_rrf_seed.{file_rank}",
                    "signature": f"file_rrf_seed.{file_rank}({file_path})",
                    "file_path": file_path,
                    "source_code": "",
                    "start_line": 0,
                    "end_line": 0,
                    "similarity": score,
                    "evidence": {
                        "support": sum(rank is not None for rank in ranks.values()),
                        "distance": min(rank for rank in ranks.values() if rank is not None),
                        "anchor_match": False,
                        "source_file_ranks": ranks,
                    },
                    "path_details": [
                        {
                            "start_node": instance_id,
                            "end_node": file_path,
                            "start_labels": ["Issue"],
                            "end_labels": ["File"],
                            "start_type": "issue",
                            "end_type": "file",
                            "type": "FILE_RRF_SEED",
                            "description": "selected by equal-weight file-level RRF",
                            "file_rank": file_rank,
                            "source_file_ranks": ranks,
                        }
                    ],
                }
            )

        issues = next(
            (
                (payload.get("related_entities") or {}).get("issues")
                for payload in payloads.values()
                if (payload.get("related_entities") or {}).get("issues")
            ),
            [],
        )
        output = {
            "related_entities": {"methods": methods, "classes": [], "issues": issues},
            "file_fusion_params": {
                "strategy": "equal_weight_file_rank_rrf",
                "sources": names,
                "rrf_k": args.rrf_k,
                "max_files": args.max_files,
                "source_dirs": {name: str(directory) for name, directory in sources},
            },
            "artifact_stats": {"fused_file_count": len(methods)},
        }
        destination.write_text(
            json.dumps(output, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        written += 1
    print(f"wrote {written} file-level RRF seed rankings to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
