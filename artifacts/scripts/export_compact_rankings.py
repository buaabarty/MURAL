#!/usr/bin/env python3
"""Export ranked entity contexts as a compact, deterministic gzip ledger."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


FIELDS = (
    "name",
    "signature",
    "file_path",
    "start_line",
    "end_line",
    "source_code",
    "doc_string",
    "entity_type",
    "similarity",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--source", action="append", required=True, metavar="LABEL=DIR")
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_ids(path: Path) -> list[str]:
    values: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        values.append(str(json.loads(line)["instance_id"]) if line.startswith("{") else line)
    if not values or len(values) != len(set(values)):
        raise ValueError(f"Empty or duplicate instance ids in {path}")
    return values


def parse_sources(values: list[str]) -> list[tuple[str, Path]]:
    parsed: list[tuple[str, Path]] = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"Expected LABEL=DIR, received {value!r}")
        label, raw_path = value.split("=", 1)
        label = label.strip()
        if not label or label in {name for name, _ in parsed}:
            raise ValueError(f"Invalid or duplicate source label: {label!r}")
        parsed.append((label, Path(raw_path).resolve()))
    return parsed


def ranked_methods(path: Path, instance_id: str) -> list[dict[str, object]]:
    payload = json.loads((path / f"{instance_id}.json").read_text(encoding="utf-8"))
    methods = list((payload.get("related_entities") or {}).get("methods") or [])
    if any(isinstance(item.get("similarity"), (int, float)) for item in methods):
        methods.sort(
            key=lambda item: (
                float(item["similarity"])
                if isinstance(item.get("similarity"), (int, float))
                else float("-inf")
            ),
            reverse=True,
        )
    return methods


def compact(candidate: dict[str, object]) -> dict[str, object]:
    return {field: candidate[field] for field in FIELDS if field in candidate}


def main() -> int:
    args = parse_args()
    if args.top_k <= 0:
        raise ValueError("--top-k must be positive")
    ids = load_ids(args.ids_file.resolve())
    sources = parse_sources(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8", newline="\n") as handle:
        for instance_id in ids:
            row = {
                "instance_id": instance_id,
                "top_k": args.top_k,
                "sources": {
                    label: [
                        compact(item)
                        for item in ranked_methods(source_dir, instance_id)[: args.top_k]
                    ]
                    for label, source_dir in sources
                },
            }
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    print(f"wrote {args.output} ({len(ids)} instances, {len(sources)} sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
