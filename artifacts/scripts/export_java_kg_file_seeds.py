#!/usr/bin/env python3
"""Export the Java KG source through MURAL's ranked-file contract.

The exporter intentionally retains only file paths, ranks, and support counts.
Entity source text and path-level records are not carried into the submission
artifact.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def normalize_path(value: object, repo_id: str) -> str:
    path = str(value or "").replace("\\", "/")
    for marker in (f"playground/{repo_id}/", f"{repo_id}/"):
        index = path.find(marker)
        if index >= 0:
            return path[index + len(marker) :]
    while path.startswith("./"):
        path = path[2:]
    if path.startswith("/") or path == ".." or path.startswith("../"):
        raise ValueError(f"Path is outside the repository: {value!r}")
    return path


def ranked_files(payload: dict[str, Any], repo_id: str, depth: int, max_files: int) -> list[dict[str, Any]]:
    file_evidence: dict[str, dict[str, Any]] = {}
    for item in (payload.get("related_entities") or {}).get("files") or []:
        file_path = normalize_path(item.get("file_path"), repo_id)
        if not file_path:
            continue
        distance = max(1, int(item.get("distance") or 1))
        current = file_evidence.setdefault(
            file_path,
            {"distance": distance, "support": 0, "direct_anchor": False},
        )
        current["distance"] = min(current["distance"], distance)
        current["support"] += max(1, int(item.get("support") or 1))
        current["direct_anchor"] = bool(
            current["direct_anchor"] or item.get("direct_anchor")
        )

    entities = [
        *((payload.get("related_entities") or {}).get("methods") or []),
        *((payload.get("related_entities") or {}).get("classes") or []),
    ]
    entities.sort(key=lambda item: -float(item.get("similarity") or 0.0))
    paths = [normalize_path(item.get("file_path"), repo_id) for item in entities[:depth]]
    paths = [path for path in paths if path]
    entity_support = Counter(paths)
    first_entity_rank: dict[str, int] = {}
    for entity_rank, file_path in enumerate(paths, start=1):
        first_entity_rank.setdefault(file_path, entity_rank)

    ordered_paths = sorted(
        file_evidence,
        key=lambda path: (
            0 if file_evidence[path]["direct_anchor"] else 1,
            file_evidence[path]["distance"],
            -file_evidence[path]["support"],
            path,
        ),
    )
    ordered_paths.extend(
        path
        for path, _ in sorted(first_entity_rank.items(), key=lambda item: item[1])
        if path not in file_evidence
    )

    output: list[dict[str, Any]] = []
    for file_path in ordered_paths:
        evidence = file_evidence.get(file_path) or {}
        entity_rank = first_entity_rank.get(file_path)
        output.append(
            {
                "file_path": file_path,
                "rank": len(output) + 1,
                "support": max(1, int(
                    evidence.get("support")
                    if evidence
                    else entity_support.get(file_path) or 0
                )),
                "first_entity_rank": entity_rank,
                "graph_distance": evidence.get("distance"),
                "direct_anchor": bool(evidence.get("direct_anchor")),
            }
        )
        if len(output) >= max_files:
            break
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--entity-depth", type=int, default=50)
    parser.add_argument("--max-files", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows: list[dict[str, Any]] = []
    for path in sorted(args.input_dir.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        repo_id = path.stem.rsplit("-", 1)[0]
        rows.append(
            {
                "instance_id": path.stem,
                "source": "typed_kg_ranked_files",
                "entity_depth": args.entity_depth,
                "max_files": args.max_files,
                "ranked_files": ranked_files(
                    payload,
                    repo_id,
                    args.entity_depth,
                    args.max_files,
                ),
            }
        )
    if not rows:
        raise ValueError(f"No structural result JSON files found under {args.input_dir}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    print(f"wrote {len(rows)} ranked-file rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
