#!/usr/bin/env python3
"""Freeze the exact ranked windows used to build the human-audit packets."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterable


DISPLAY_WIDTH = 360


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--source", action="append", required=True, metavar="METHOD=DIR")
    parser.add_argument("--output-rankings", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    return parser.parse_args()


def parse_specs(values: Iterable[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"invalid source specification: {raw!r}")
        method, directory = (part.strip() for part in raw.split("=", 1))
        if not method or not directory or method in result:
            raise ValueError(f"invalid source specification: {raw!r}")
        result[method] = Path(directory)
    return result


def compact_signature(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= DISPLAY_WIDTH else text[: DISPLAY_WIDTH - 3] + "..."


def ranked_methods(path: Path, instance_id: str, top_k: int = 20) -> list[dict[str, Any]]:
    data = json.loads((path / f"{instance_id}.json").read_text(encoding="utf-8"))
    methods = list((data.get("related_entities") or {}).get("methods") or [])
    if any(isinstance(item.get("similarity"), (int, float)) for item in methods):
        methods.sort(
            key=lambda item: (
                item.get("similarity")
                if isinstance(item.get("similarity"), (int, float))
                else float("-inf")
            ),
            reverse=True,
        )
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for method in methods:
        signature = str(method.get("signature") or method.get("name") or "")
        if not signature or signature in seen:
            continue
        seen.add(signature)
        output.append(method)
        if len(output) == top_k:
            break
    if len(output) < top_k:
        raise ValueError(f"{instance_id} in {path} has only {len(output)} ranked entities")
    return output


def render_window(candidates: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{rank:02d}. {candidate.get('file_path') or '（未知文件）'} :: "
        f"{compact_signature(candidate.get('signature') or candidate.get('name'))}"
        for rank, candidate in enumerate(candidates, start=1)
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_deterministic_gzip(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    args = parse_args()
    payload = json.loads(args.items.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    sources = parse_specs(args.source)
    if set(sources) != {"MURAL", "BM25-local"}:
        raise ValueError("the audit requires MURAL and BM25-local source directories")

    records: list[dict[str, Any]] = []
    for item in items:
        instance_id = item["instance_id"]
        source_rankings = {
            method: ranked_methods(directory, instance_id)
            for method, directory in sources.items()
        }
        for side in ("a", "b"):
            method = item[f"method_{side}"]
            if item[f"window_{side}"] != render_window(source_rankings[method]):
                raise ValueError(
                    f"{item['annotation_id']} window {side.upper()} does not match {method}"
                )
        records.append(
            {
                "annotation_id": item["annotation_id"],
                "instance_id": instance_id,
                "sources": source_rankings,
            }
        )

    write_deterministic_gzip(args.output_rankings, records)
    manifest = {
        "schema_version": 1,
        "packet_created_date": payload["protocol"]["created_date"],
        "random_seed": payload["protocol"]["random_seed"],
        "benchmark": "SWE-bench Verified",
        "benchmark_instances": payload["protocol"]["benchmark_instances"],
        "audited_instances": len(records),
        "top_k": payload["protocol"]["window_size_entities"],
        "main_experiment": {
            "paper_table": "RQ-1 source-composition comparison",
            "configurations": ["BM25_projection", "MURAL_2src"],
        },
        "method_mapping": {
            "BM25-local": "BM25_projection",
            "MURAL": "MURAL_2src (paper label: MURAL w/o Dense)",
        },
        "source_directories": {method: str(path) for method, path in sources.items()},
        "rankings": {
            "path": str(args.output_rankings),
            "sha256": sha256(args.output_rankings),
        },
        "binding_rule": "verbatim rendered Top-20 window",
    }
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"froze and verified {len(records)} human-audit ranking pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
