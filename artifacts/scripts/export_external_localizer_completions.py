#!/usr/bin/env python3
"""Export matched completion rankings for released localizer prefixes."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from build_strict_reference_targets import parse_entities, read_commit_file  # noqa: E402
from evaluate_external_localizer_fusion import load_jsonl  # noqa: E402
from evaluate_strict_external_localizers import (  # noqa: E402
    canonical_identity,
    fill_unique_exact,
    load_ids,
    resolve_external_candidates,
)


LOCALIZERS = {
    "CoSIL": ("CoSIL", "CoSIL_qwen_coder_32b_func.jsonl"),
    "Agentless": ("agentless", "agentless_qwen_coder_32b_func.jsonl"),
    "LocAgent": ("locagent", "locagent_qwen_coder_32b_func.jsonl"),
    "OrcaLoca": ("orcaloca", "orcaloca_qwen_coder_32b_func.jsonl"),
}
SOURCE_KEYS = {
    "BM25": "BM25_projection",
    "Structural": "Structural_adapter",
    "Dense": "Dense_projection",
    "MURAL": "MURAL",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--external-root", required=True, type=Path)
    parser.add_argument("--rankings-archive", required=True, type=Path)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output-resolution", type=Path)
    parser.add_argument("--primary-prefix", type=int, default=10)
    parser.add_argument("--max-candidates", type=int, default=50)
    return parser.parse_args()


def load_rankings(path: Path, limit: int) -> dict[str, dict[str, list[dict]]]:
    opener = gzip.open if path.suffix == ".gz" else open
    output: dict[str, dict[str, list[dict]]] = {}
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            sources = row.get("sources") or {}
            output[str(row["instance_id"])] = {
                label: list(sources.get(key) or [])[:limit]
                for label, key in SOURCE_KEYS.items()
            }
    return output


def round_robin(source_lists: list[list[dict]], limit: int) -> list[dict]:
    output: list[dict] = []
    depth = 0
    while len(output) < limit and any(depth < len(rows) for rows in source_lists):
        for rows in source_lists:
            if depth < len(rows):
                output = fill_unique_exact(output, [rows[depth]], limit)
        depth += 1
    return output


def hydrate_candidate(
    candidate: dict,
    reference: dict,
    workspace_root: Path,
    source_cache: dict[tuple[str, str, str], str | None],
    entity_cache: dict[tuple[str, str, str], list],
) -> dict:
    output = deepcopy(candidate)
    path, kind, name = canonical_identity(output)
    key = (str(reference["repo"]), str(reference["base_commit"]), path)
    if key not in source_cache:
        source_cache[key] = read_commit_file(workspace_root, key[0], key[1], path)
    source = source_cache[key]
    if source is None:
        return output
    if key not in entity_cache:
        entities, error = parse_entities(source, path)
        entity_cache[key] = [] if error else entities
    match = next(
        (
            entity
            for entity in entity_cache[key]
            if entity.kind == kind and entity.qualified_name == name
        ),
        None,
    )
    if match is None:
        return output
    lines = source.splitlines()
    output["kind"] = match.kind
    output["entity_type"] = "method"
    output["name"] = match.qualified_name
    output["label"] = match.qualified_name
    output["start_line"] = match.start_line
    output["end_line"] = match.end_line
    output["source_code"] = "\n".join(lines[match.start_line - 1 : match.end_line])
    return output


def write_tsv(path: Path, rows: list[dict]) -> None:
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
    if args.primary_prefix < 0 or args.max_candidates <= 0:
        raise ValueError("Require primary-prefix >= 0 and max-candidates > 0")
    ids = load_ids(args.ids_file)
    references = json.loads(args.targets.read_text(encoding="utf-8"))["items"]
    rankings = load_rankings(args.rankings_archive, args.max_candidates)
    missing = sorted(set(ids) - set(rankings))
    if missing:
        raise ValueError(f"Ranking archive misses {len(missing)} instances")

    args.output_root.mkdir(parents=True, exist_ok=True)
    resolution_rows: list[dict] = []
    parse_cache: dict[tuple[str, str, str], tuple[list, str]] = {}
    source_cache: dict[tuple[str, str, str], str | None] = {}
    entity_cache: dict[tuple[str, str, str], list] = {}

    for localizer, (directory, filename) in LOCALIZERS.items():
        external_path = args.external_root / directory / filename
        external = {row["instance_id"]: row for row in load_jsonl(external_path)}
        diagnostics: Counter = Counter()
        full_rankings: dict[str, list[dict]] = {}
        for instance_id in ids:
            resolved = resolve_external_candidates(
                external.get(instance_id),
                references[instance_id],
                args.workspace_root,
                500,
                parse_cache,
                diagnostics,
            )
            full_rankings[instance_id] = [
                hydrate_candidate(
                    item,
                    references[instance_id],
                    args.workspace_root,
                    source_cache,
                    entity_cache,
                )
                for item in resolved
            ]

        for instance_id in ids:
            prefix = full_rankings[instance_id][: args.primary_prefix]
            source_rows = rankings[instance_id]
            tails = {
                "Remainder": full_rankings[instance_id][args.primary_prefix :],
                "BM25": source_rows["BM25"],
                "Structural": source_rows["Structural"],
                "Dense": source_rows["Dense"],
                "EqualRR": round_robin(
                    [source_rows["BM25"], source_rows["Structural"], source_rows["Dense"]],
                    args.max_candidates,
                ),
                "MURAL": source_rows["MURAL"],
            }
            for tail_name, tail in tails.items():
                completed = fill_unique_exact(prefix, tail, args.max_candidates)
                # The file order is the completed ranking. Remove source-specific
                # scores so downstream readers do not reorder the preserved prefix.
                completed = [deepcopy(item) for item in completed]
                for item in completed:
                    item.pop("similarity", None)
                output_dir = args.output_root / f"{localizer}__{tail_name}"
                output_dir.mkdir(parents=True, exist_ok=True)
                payload = {
                    "related_entities": {"methods": completed, "classes": [], "issues": []},
                    "completion_params": {
                        "localizer": localizer,
                        "tail": tail_name,
                        "primary_prefix": args.primary_prefix,
                        "max_candidates": args.max_candidates,
                        "strategy": "preserve_resolved_prefix_then_fill_selected_tail",
                    },
                }
                (output_dir / f"{instance_id}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )

        resolution_rows.append(
            {
                "localizer": localizer,
                "instances": len(ids),
                "raw_predictions": diagnostics["raw_predictions"],
                "resolved_unique_entities": diagnostics["resolved_unique_entities"],
                "unresolved_predictions": diagnostics["unresolved_predictions"],
                "missing_file_predictions": diagnostics["missing_file"],
                "parse_error_predictions": diagnostics["parse_error"],
                "nonempty_source_instances": sum(bool(rows) for rows in full_rankings.values()),
                "mean_resolved_entities": (
                    sum(len(rows) for rows in full_rankings.values()) / len(ids)
                ),
            }
        )

    if args.output_resolution:
        write_tsv(args.output_resolution, resolution_rows)
    print(f"wrote matched completion rankings to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
