#!/usr/bin/env python3
"""Fuse two or more ranked code-entity sources with deterministic RRF."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_named_path(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    name, directory = (part.strip() for part in raw.split("=", 1))
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name) or not directory:
        raise ValueError(f"Expected a stable source NAME and directory, got {raw!r}")
    return name, Path(directory)


def parse_named_weight(raw: str) -> tuple[str, float]:
    if "=" not in raw:
        raise ValueError(f"Expected NAME=WEIGHT, got {raw!r}")
    name, value = (part.strip() for part in raw.split("=", 1))
    return name, float(value)


def ranked_entities(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    entities = (payload.get("related_entities") or {}).get(key) or []
    return sorted(entities, key=lambda item: -float(item.get("similarity") or 0.0))


def entity_id(item: dict[str, Any]) -> str:
    signature = item.get("signature") or item.get("name")
    if signature:
        return str(signature)
    return "|".join(
        [
            str(item.get("file_path") or ""),
            str(item.get("start_line") or ""),
            str(item.get("entity_type") or ""),
        ]
    )


def rank_map(entities: list[dict[str, Any]]) -> dict[str, tuple[int, dict[str, Any]]]:
    output: dict[str, tuple[int, dict[str, Any]]] = {}
    for rank, entity in enumerate(entities, start=1):
        identifier = entity_id(entity)
        if identifier and identifier not in output:
            output[identifier] = (rank, entity)
    return output


def fuse_entities(
    sources: list[tuple[str, list[dict[str, Any]]]],
    weights: dict[str, float],
    rrf_k: int,
    limit: int,
) -> list[dict[str, Any]]:
    source_maps = [(name, rank_map(entities)) for name, entities in sources]
    identifiers: set[str] = set()
    for _, source_map in source_maps:
        identifiers.update(source_map)

    rows: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for identifier in sorted(identifiers):
        ranks: dict[str, int | None] = {}
        score = 0.0
        base: dict[str, Any] | None = None
        first_source = len(source_maps)
        present_count = 0
        best_rank: int | None = None

        for source_index, (name, source_map) in enumerate(source_maps):
            entry = source_map.get(identifier)
            rank = entry[0] if entry else None
            ranks[name] = rank
            if rank is None:
                continue
            score += weights[name] / (rrf_k + rank)
            present_count += 1
            best_rank = rank if best_rank is None else min(best_rank, rank)
            if base is None:
                base = entry[1]
                first_source = source_index

        if base is None or best_rank is None:
            continue
        fused = dict(base)
        fused["similarity"] = score
        fused["fusion_evidence"] = {
            "source_ranks": ranks,
            "source_weights": weights,
            "rrf_score": score,
        }
        stable_key = (
            -score,
            -present_count,
            best_rank,
            first_source,
            str(fused.get("file_path") or ""),
            int(fused.get("start_line") or 0),
            identifier,
        )
        rows.append((stable_key, fused))

    rows.sort(key=lambda row: row[0])
    return [entity for _, entity in rows[:limit]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, help="NAME=DIR; repeat per source")
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        help="NAME=WEIGHT; omitted sources default to 1.0",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = [parse_named_path(raw) for raw in args.source]
    source_names = [name for name, _ in sources]
    if len(sources) < 2 or len(source_names) != len(set(source_names)):
        raise ValueError("Provide at least two uniquely named sources")
    if args.top_k <= 0 or args.rrf_k < 0:
        raise ValueError("Require top-k > 0 and rrf-k >= 0")

    weights = {name: 1.0 for name in source_names}
    for name, weight in map(parse_named_weight, args.weight):
        if name not in weights:
            raise ValueError(f"Weight names unknown source {name!r}")
        weights[name] = weight
    if any(weight < 0 for weight in weights.values()) or not any(weights.values()):
        raise ValueError("Source weights must be non-negative and at least one must be positive")

    id_sets = [{path.stem for path in directory.glob("*.json")} for _, directory in sources]
    instance_ids = sorted(set.intersection(*id_sets))
    if not instance_ids:
        raise ValueError("No shared JSON instances across the source directories")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for instance_id in instance_ids:
        destination = args.output_dir / f"{instance_id}.json"
        if destination.exists() and not args.force:
            continue
        payloads = [(name, load(directory / destination.name)) for name, directory in sources]
        output = {
            "related_entities": {
                key: fuse_entities(
                    [(name, ranked_entities(payload, key)) for name, payload in payloads],
                    weights,
                    args.rrf_k,
                    args.top_k,
                )
                for key in ("methods", "classes")
            },
            "artifact_stats": {
                "sources": {name: payload.get("artifact_stats") or {} for name, payload in payloads}
            },
            "fusion_params": {
                "strategy": "multi_source_reciprocal_rank_fusion",
                "sources": source_names,
                "weights": weights,
                "rrf_k": args.rrf_k,
                "top_k": args.top_k,
                "tie_break": "source_count,best_rank,source_order,file_path,start_line,entity_id",
                "source_dirs": {name: str(directory) for name, directory in sources},
            },
        }
        output["related_entities"]["issues"] = next(
            (
                (payload.get("related_entities") or {}).get("issues")
                for _, payload in payloads
                if (payload.get("related_entities") or {}).get("issues")
            ),
            [],
        )
        destination.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1

    print(
        f"wrote {written} {len(sources)}-source RRF fusions to {args.output_dir} "
        f"(k={args.rrf_k}, weights={weights})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
