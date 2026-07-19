#!/usr/bin/env python3
"""Bind decoded human judgments to the audited paper-facing configurations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


METHOD_ALIASES = {
    "BM25-local": "BM25_projection",
    "BM25_projection": "BM25_projection",
    "MURAL": "MURAL_2src",
    "MURAL_2src": "MURAL_2src",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--strict-instances", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--output-items", type=Path, required=True)
    parser.add_argument("--output-annotations", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_method(value: str) -> str:
    try:
        return METHOD_ALIASES[value]
    except KeyError as exc:
        raise ValueError(f"unsupported audit method: {value}") from exc


def strict_stratum(bm25_hit: int, mural_hit: int) -> str:
    if mural_hit and not bm25_hit:
        return "MURAL_2src_only"
    if bm25_hit and not mural_hit:
        return "BM25_projection_only"
    return "both" if bm25_hit else "neither"


def main() -> int:
    args = parse_args()
    payload = json.loads(args.items.read_text(encoding="utf-8"))
    annotations = read_tsv(args.annotations)
    strict_rows = read_tsv(args.strict_instances)

    hits = {
        (row["instance_id"], row["approach"]): int(row["hit"])
        for row in strict_rows
        if row["approach"] in {"BM25_projection", "MURAL_2src"}
    }
    strata: dict[str, str] = {}
    for item in payload["items"]:
        instance_id = item["instance_id"]
        try:
            strata[instance_id] = strict_stratum(
                hits[(instance_id, "BM25_projection")],
                hits[(instance_id, "MURAL_2src")],
            )
        except KeyError as exc:
            raise ValueError(f"missing strict audit row for {instance_id}") from exc
        item["method_a"] = normalize_method(item["method_a"])
        item["method_b"] = normalize_method(item["method_b"])
        item["objective_outcome"] = strata[instance_id]

    protocol = payload.setdefault("protocol", {})
    protocol.update(
        {
            "version_date": "2026-07-19",
            "benchmark": "SWE-bench Verified",
            "benchmark_instances": 500,
            "ranking_file_sha256": sha256_file(args.rankings),
            "ranking_sources": {
                "BM25_projection": "BM25_projection",
                "MURAL_2src": "MURAL_2src",
            },
            "audited_configuration": (
                "BM25 projection versus equal-weight lexical+structural MURAL"
            ),
            "window_size_entities": 20,
            "binding_rule": "exact rendered Top-20 window",
        }
    )

    for row in annotations:
        instance_id = row["instance_id"]
        row["method_a"] = normalize_method(row["method_a"])
        row["method_b"] = normalize_method(row["method_b"])
        row["preferred_method"] = METHOD_ALIASES.get(
            row["preferred_method"], row["preferred_method"]
        )
        row["objective_outcome"] = strata[instance_id]

    manifest_fields = [
        "annotation_id",
        "instance_id",
        "repository",
        "assignment",
        "method_a",
        "method_b",
        "objective_outcome",
    ]
    manifest = [
        {
            "annotation_id": item["annotation_id"],
            "instance_id": item["instance_id"],
            "repository": item["repo"],
            "assignment": item["assignment"],
            "method_a": item["method_a"],
            "method_b": item["method_b"],
            "objective_outcome": item["objective_outcome"],
        }
        for item in payload["items"]
    ]

    args.output_items.parent.mkdir(parents=True, exist_ok=True)
    args.output_items.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_tsv(args.output_annotations, annotations, list(annotations[0]))
    write_tsv(args.output_manifest, manifest, manifest_fields)
    print(
        f"bound {len(payload['items'])} items and {len(annotations)} judgments "
        "to BM25_projection and MURAL_2src"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
