#!/usr/bin/env python3
"""Convert ranked entity retrieval output into source-labelled file seeds."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Iterable


def load_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            ids.append(json.loads(raw)["instance_id"] if raw.startswith("{") else raw)
    return ids


def normalize_file_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def ranked_methods(payload: dict) -> list[dict]:
    methods = (payload.get("related_entities") or {}).get("methods") or []
    return sorted(methods, key=lambda item: float(item.get("similarity") or 0.0), reverse=True)


def select_files(methods: Iterable[dict], max_files: int, scan_methods: int | None) -> list[dict]:
    pool = list(methods)
    scan_pool = pool[:scan_methods] if scan_methods else pool
    support = Counter(
        normalize_file_path(item.get("file_path") or "")
        for item in scan_pool
        if normalize_file_path(item.get("file_path") or "")
    )
    selected: list[dict] = []
    seen: set[str] = set()
    for method_rank, item in enumerate(scan_pool, start=1):
        file_path = normalize_file_path(item.get("file_path") or "")
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        selected.append(
            {
                "file_path": file_path,
                "file_rank": len(selected) + 1,
                "best_method_rank": method_rank,
                "best_method_score": float(item.get("similarity") or 0.0),
                "support": support[file_path],
            }
        )
        if len(selected) >= max_files:
            break
    return selected


def make_seed(instance_id: str, file_info: dict, support_mode: str, source_name: str) -> dict:
    file_path = file_info["file_path"]
    rank = int(file_info["file_rank"])
    support = int(file_info["support"]) if support_mode == "count" else 0
    source_upper = source_name.upper()
    source_display = "BM25" if source_name == "bm25" else source_name.capitalize()
    score_field = "best_bm25_score" if source_name == "bm25" else "best_method_score"
    return {
        "type": "method",
        "entity_type": "file_seed",
        "name": f"{source_name}_file_seed.{rank}",
        "signature": f"{source_name}_file_seed.{rank}({file_path})",
        "file_path": file_path,
        "source_code": "",
        "start_line": 0,
        "end_line": 0,
        "similarity": float(file_info["best_method_score"]),
        "evidence": {
            "support": support,
            "distance": int(file_info["best_method_rank"]),
            "anchor_match": False,
            "issue_exact_anchor_matches": [],
            "issue_token_matches": [],
            "issue_path_token_matches": [],
        },
        "path_details": [
            {
                "start_node": instance_id,
                "end_node": file_path,
                "start_labels": ["Issue"],
                "end_labels": ["File"],
                "start_type": "issue",
                "end_type": "file",
                "type": f"{source_upper}_FILE_SEED",
                "description": f"selected by {source_display} file ranking",
                "file_rank": rank,
                "best_method_rank": int(file_info["best_method_rank"]),
                score_field: float(file_info["best_method_score"]),
            }
        ],
    }


def convert_one(
    payload: dict,
    instance_id: str,
    max_files: int,
    scan_methods: int | None,
    support_mode: str,
    source_name: str = "bm25",
    uses_embeddings: bool = False,
) -> dict:
    files = select_files(ranked_methods(payload), max_files, scan_methods)
    output = deepcopy(payload)
    entities = payload.get("related_entities") or {}
    output["related_entities"] = {
        "methods": [make_seed(instance_id, file_info, support_mode, source_name) for file_info in files],
        "classes": [],
        "issues": entities.get("issues") or [],
    }
    output["kg_params"] = {
        "baseline": f"{source_name}_file_seed",
        "retrieval_mode": f"{source_name}_ranked_files_only",
        "score": (
            f"{source_name}_best_method_file_rank_with_candidate_count_support"
            if support_mode == "count"
            else f"{source_name}_best_method_file_rank"
        ),
        "uses_embeddings": uses_embeddings,
        "uses_edge_weights": False,
        "uses_discussion_comments": False,
        "tunable_retrieval_parameters": [],
    }
    output.setdefault("artifact_stats", {})[f"{source_name}_file_seed_count"] = len(files)
    output.setdefault("run_meta", {})["instance_id"] = instance_id
    output["run_meta"][f"{source_name}_file_seed"] = {
        "max_files": max_files,
        "scan_methods": scan_methods,
        "support_mode": support_mode,
    }
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--max-files", type=int, default=20)
    parser.add_argument("--scan-methods", type=int, default=0)
    parser.add_argument("--support-mode", choices=["count", "zero"], default="count")
    parser.add_argument(
        "--source-name",
        default="bm25",
        help="Stable lowercase source label used in evidence and metadata.",
    )
    parser.add_argument(
        "--uses-embeddings",
        action="store_true",
        help="Record that the ranked input source uses embeddings.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_files <= 0:
        raise ValueError("--max-files must be positive")
    source_name = args.source_name.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", source_name):
        raise ValueError("--source-name must match [a-z][a-z0-9_-]*")
    scan_methods = args.scan_methods if args.scan_methods > 0 else None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for instance_id in load_ids(args.ids_file):
        source = args.input_dir / f"{instance_id}.json"
        if not source.exists():
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        output = convert_one(
            payload,
            instance_id,
            args.max_files,
            scan_methods,
            args.support_mode,
            source_name,
            args.uses_embeddings,
        )
        destination = args.output_dir / source.name
        destination.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1
    print(f"wrote {written} ranked file-seed exports to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
