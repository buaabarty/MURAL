#!/usr/bin/env python3
"""Materialize a compact ranking ledger into evaluator-compatible JSON files."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output_root.resolve()
    seen: set[str] = set()
    source_labels: set[str] | None = None
    with gzip.open(args.input.resolve(), "rt", encoding="utf-8") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            instance_id = str(row.get("instance_id") or "")
            if not instance_id or instance_id in seen:
                raise ValueError(f"Missing or duplicate instance id: {instance_id!r}")
            seen.add(instance_id)
            sources = row.get("sources") or {}
            labels = set(sources)
            if source_labels is None:
                source_labels = labels
            elif labels != source_labels:
                raise ValueError(f"Inconsistent source labels for {instance_id}")
            for label, methods in sources.items():
                destination = output_root / label / f"{instance_id}.json"
                destination.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "related_entities": {"methods": methods},
                    "artifact_stats": {
                        "source": "compact_frozen_ranking",
                        "source_label": label,
                        "top_k": row.get("top_k"),
                    },
                }
                destination.write_text(
                    json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
    if not seen:
        raise ValueError(f"No rows in {args.input}")
    print(f"materialized {len(seen)} instances for {len(source_labels or ())} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
