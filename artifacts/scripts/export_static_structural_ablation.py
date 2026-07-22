#!/usr/bin/env python3
"""Replay MURAL after removing every issue/PR-derived structural candidate."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from audit_structural_temporal_provenance import historical_nodes  # noqa: E402
from entity_identity import canonical_entity_key  # noqa: E402
from export_multi_source_rrf_fusion import fuse_entities  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structural-dir", required=True, type=Path)
    parser.add_argument("--bm25-dir", required=True, type=Path)
    parser.add_argument("--dense-dir", required=True, type=Path)
    parser.add_argument("--mural-dir", required=True, type=Path)
    parser.add_argument("--output-structural-dir", required=True, type=Path)
    parser.add_argument("--output-mural-dir", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-instances", required=True, type=Path)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--top-k", type=int, default=50)
    return parser.parse_args()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def candidates(payload: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return list((payload.get("related_entities") or {}).get(kind) or [])


def identities(rows: list[dict[str, Any]], limit: int) -> list[str]:
    return [canonical_entity_key(row) for row in rows[:limit]]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


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
    instance_ids = sorted(path.stem for path in args.structural_dir.glob("*.json"))
    if not instance_ids:
        raise ValueError(f"No rankings found in {args.structural_dir}")

    instance_rows: list[dict[str, Any]] = []
    for instance_id in instance_ids:
        structural = load(args.structural_dir / f"{instance_id}.json")
        bm25 = load(args.bm25_dir / f"{instance_id}.json")
        dense = load(args.dense_dir / f"{instance_id}.json")
        current = load(args.mural_dir / f"{instance_id}.json")

        static_structural = deepcopy(structural)
        removed = 0
        removed_ids: list[str] = []
        for kind in ("methods", "classes"):
            kept: list[dict[str, Any]] = []
            for item in candidates(structural, kind):
                if historical_nodes(item):
                    removed += 1
                    removed_ids.append(canonical_entity_key(item))
                else:
                    kept.append(item)
            static_structural["related_entities"][kind] = kept
        static_structural["static_ablation"] = {
            "policy": "remove_candidates_with_issue_or_pull_request_path_nodes",
            "removed_candidates": removed,
        }

        fused: dict[str, list[dict[str, Any]]] = {}
        for kind in ("methods", "classes"):
            fused[kind] = fuse_entities(
                [
                    ("BM25", candidates(bm25, kind)),
                    ("Structural", candidates(static_structural, kind)),
                    ("Dense", candidates(dense, kind)),
                ],
                {"BM25": 1.0, "Structural": 1.0, "Dense": 1.0},
                args.rrf_k,
                args.top_k,
            )
        static_mural = {
            "related_entities": {
                "methods": fused["methods"],
                "classes": fused["classes"],
                "issues": [],
            },
            "fusion_params": {
                "sources": ["BM25", "StructuralStatic", "Dense"],
                "weights": {"BM25": 1.0, "StructuralStatic": 1.0, "Dense": 1.0},
                "rrf_k": args.rrf_k,
                "top_k": args.top_k,
            },
            "static_ablation": static_structural["static_ablation"],
        }
        write_json(args.output_structural_dir / f"{instance_id}.json", static_structural)
        write_json(args.output_mural_dir / f"{instance_id}.json", static_mural)

        current_methods = sorted(
            candidates(current, "methods"),
            key=lambda item: float(item.get("similarity", 0.0)),
            reverse=True,
        )
        top20_equal = identities(current_methods, 20) == identities(fused["methods"], 20)
        top50_equal = identities(current_methods, 50) == identities(fused["methods"], 50)
        instance_rows.append(
            {
                "instance_id": instance_id,
                "removed_historical_candidates": removed,
                "removed_identities": ";".join(removed_ids),
                "top20_equal": int(top20_equal),
                "top50_equal": int(top50_equal),
            }
        )

    summary = {
        "instances": len(instance_rows),
        "instances_with_history_candidates": sum(
            row["removed_historical_candidates"] > 0 for row in instance_rows
        ),
        "historical_candidates_removed": sum(
            row["removed_historical_candidates"] for row in instance_rows
        ),
        "top20_changed_instances": sum(not row["top20_equal"] for row in instance_rows),
        "top50_changed_instances": sum(not row["top50_equal"] for row in instance_rows),
        "rrf_k": args.rrf_k,
        "top_k": args.top_k,
    }
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_tsv(args.output_instances, instance_rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
