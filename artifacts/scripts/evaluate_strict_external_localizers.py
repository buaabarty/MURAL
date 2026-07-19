#!/usr/bin/env python3
"""Evaluate released localizer prefixes with strict MURAL targets."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from build_strict_reference_targets import parse_entities, read_commit_file  # noqa: E402
from evaluate_external_localizer_fusion import (  # noqa: E402
    external_candidates,
    load_jsonl,
    mural_candidates,
)
from evaluate_strict_reference_context import (  # noqa: E402
    candidate_kind,
    candidate_local_name,
    candidate_matches_target,
    cluster_bootstrap_ci,
    exact_mcnemar,
    normalized_path,
    repository_id,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--mural-dir", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--primary-prefix", type=int, default=10)
    parser.add_argument("--secondary-pool", type=int, default=20)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-instances", type=Path, required=True)
    parser.add_argument("--output-paired", type=Path, required=True)
    return parser.parse_args()


def load_ids(path: Path) -> list[str]:
    result: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        result.append(str(json.loads(line)["instance_id"]) if line.startswith("{") else line)
    return result


def strict_candidate(candidate: dict) -> dict:
    return {
        "file_path": candidate.get("file_path") or "",
        "signature": candidate.get("signature") or candidate.get("label") or "",
        "source_code": candidate.get("source_code") or "",
    }


def canonical_identity(candidate: dict) -> tuple[str, str, str]:
    normalized = strict_candidate(candidate)
    return (
        normalized_path(normalized["file_path"]),
        candidate_kind(normalized),
        candidate_local_name(normalized),
    )


def fill_unique_exact(base: list[dict], extra: list[dict], limit: int) -> list[dict]:
    output: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in [*base, *extra]:
        identity = canonical_identity(candidate)
        if not all(identity) or identity in seen:
            continue
        seen.add(identity)
        output.append(candidate)
        if len(output) >= limit:
            break
    return output


def fuse_candidates_exact(
    primary: list[dict],
    secondary: list[dict],
    primary_prefix: int,
    secondary_pool: int,
    top_k: int,
) -> list[dict]:
    merged = fill_unique_exact(primary[:primary_prefix], secondary[:secondary_pool], top_k)
    if len(merged) < top_k:
        merged = fill_unique_exact(merged, primary[primary_prefix:], top_k)
    if len(merged) < top_k:
        merged = fill_unique_exact(merged, secondary[secondary_pool:], top_k)
    return merged[:top_k]


def canonical_external_label(candidate: dict) -> str:
    label = str(candidate.get("label") or "").replace("#", ".").strip(".")
    return candidate_local_name(
        {
            "file_path": candidate.get("file_path") or "",
            "signature": label,
            "source_code": "",
        }
    )


def resolve_external_candidates(
    row: dict | None,
    reference: dict,
    workspace_root: Path,
    limit: int,
    entity_cache: dict[tuple[str, str, str], list],
) -> list[dict]:
    output: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    repo = str(reference["repo"])
    base_commit = str(reference["base_commit"])
    for raw in external_candidates(row, 500):
        file_path = normalized_path(raw.get("file_path"))
        label = canonical_external_label(raw)
        if not file_path or not label:
            continue
        cache_key = (repo, base_commit, file_path)
        if cache_key not in entity_cache:
            source = read_commit_file(workspace_root, repo, base_commit, file_path)
            if source is None:
                entity_cache[cache_key] = []
            else:
                entities, error = parse_entities(source, file_path)
                entity_cache[cache_key] = [] if error else entities

        requested_kind = str(raw.get("kind") or "unknown")
        matches = [
            entity
            for entity in entity_cache[cache_key]
            if entity.qualified_name == label
            and (
                requested_kind == "unknown"
                or requested_kind == "function"
                and entity.kind == "function"
                or requested_kind == "variable"
                and entity.kind == "assignment"
            )
        ]
        if len(matches) != 1:
            continue
        entity = matches[0]
        signature = (
            f"{entity.qualified_name} = <assignment>"
            if entity.kind == "assignment"
            else f"{entity.qualified_name}()"
        )
        candidate = {
            "source": "external",
            "file_path": file_path,
            "kind": entity.kind,
            "label": entity.qualified_name,
            "signature": signature,
            "source_code": "",
        }
        identity = canonical_identity(candidate)
        if identity in seen:
            continue
        seen.add(identity)
        output.append(candidate)
        if len(output) >= limit:
            break
    return output


def matches_target(candidate: dict, target: dict) -> bool:
    return candidate_matches_target(strict_candidate(candidate), target)


def evaluate(candidates: list[dict], reference: dict, top_k: int) -> dict:
    targets = reference["targets"]
    patch_files = {normalized_path(path) for path in reference.get("patch_files") or []}
    matched: set[int] = set()
    first_rank: int | None = None
    file_hit = 0
    for rank, candidate in enumerate(candidates[:top_k], 1):
        if normalized_path(candidate.get("file_path")) in patch_files:
            file_hit = 1
        for target_index, target in enumerate(targets):
            if matches_target(candidate, target):
                matched.add(target_index)
                if first_rank is None:
                    first_rank = rank
    return {
        "candidate_count": min(len(candidates), top_k),
        "file_hit": file_hit,
        "target_coverage": len(matched) / len(targets),
        "hit": int(bool(matched)),
        "mrr": 0.0 if first_rank is None else 1.0 / first_rank,
        "complete": int(len(matched) == len(targets)),
    }


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    ids = load_ids(args.ids_file)
    targets = json.loads(args.targets.read_text(encoding="utf-8"))["items"]
    specs = {
        "CoSIL": args.external_root / "CoSIL" / "CoSIL_qwen_coder_32b_func.jsonl",
        "Agentless": args.external_root / "agentless" / "agentless_qwen_coder_32b_func.jsonl",
        "LocAgent": args.external_root / "locagent" / "locagent_qwen_coder_32b_func.jsonl",
        "OrcaLoca": args.external_root / "orcaloca" / "orcaloca_qwen_coder_32b_func.jsonl",
    }
    tail = {
        instance_id: mural_candidates(
            args.mural_dir / f"{instance_id}.json",
            max(args.top_k, args.secondary_pool),
        )
        for instance_id in ids
    }

    rows: list[dict] = []
    by_name: dict[str, dict[str, dict]] = defaultdict(dict)
    entity_cache: dict[tuple[str, str, str], list] = {}
    comparisons: list[tuple[str, str]] = []
    for name, source_path in specs.items():
        external = {row["instance_id"]: row for row in load_jsonl(source_path)}
        prefix = {
            instance_id: resolve_external_candidates(
                external.get(instance_id),
                targets[instance_id],
                args.workspace_root,
                args.primary_prefix,
                entity_cache,
            )
            for instance_id in ids
        }
        fused = {
            instance_id: fuse_candidates_exact(
                prefix[instance_id],
                tail[instance_id],
                args.primary_prefix,
                args.secondary_pool,
                args.top_k,
            )
            for instance_id in ids
        }
        for instance_id in ids:
            locked = prefix[instance_id][: args.primary_prefix]
            if [canonical_identity(item) for item in fused[instance_id][: len(locked)]] != [
                canonical_identity(item) for item in locked
            ]:
                raise AssertionError(f"{name} {instance_id}: fixed prefix changed")
        fused_name = f"{name}+MURAL"
        comparisons.append((name, fused_name))
        for label, rankings in ((name, prefix), (fused_name, fused)):
            for instance_id in ids:
                result = evaluate(rankings[instance_id], targets[instance_id], args.top_k)
                result.update(
                    {
                        "approach": label,
                        "instance_id": instance_id,
                        "repository": repository_id(instance_id),
                    }
                )
                rows.append(result)
                by_name[label][instance_id] = result

    summary: list[dict] = []
    for label in by_name:
        group = list(by_name[label].values())
        summary.append(
            {
                "approach": label,
                "N": len(group),
                "candidate_count_mean": f"{mean(row['candidate_count'] for row in group):.6f}",
                "file_hit": f"{100 * mean(row['file_hit'] for row in group):.6f}",
                "target_coverage": f"{100 * mean(row['target_coverage'] for row in group):.6f}",
                "mrr": f"{100 * mean(row['mrr'] for row in group):.6f}",
                "hit": f"{100 * mean(row['hit'] for row in group):.6f}",
                "complete": f"{100 * mean(row['complete'] for row in group):.6f}",
            }
        )

    paired: list[dict] = []
    for baseline, treatment in comparisons:
        for metric in ("target_coverage", "hit", "complete"):
            triples = [
                (
                    repository_id(instance_id),
                    float(by_name[baseline][instance_id][metric]),
                    float(by_name[treatment][instance_id][metric]),
                )
                for instance_id in ids
            ]
            delta = mean(treat - base for _, base, treat in triples)
            low, high = cluster_bootstrap_ci(triples, args.bootstrap, args.seed)
            item = {
                "baseline": baseline,
                "treatment": treatment,
                "metric": metric,
                "delta": f"{100 * delta:.6f}",
                "clustered_ci_low": f"{100 * low:.6f}",
                "clustered_ci_high": f"{100 * high:.6f}",
                "wins": "",
                "losses": "",
                "mcnemar_p": "",
            }
            if metric in {"hit", "complete"}:
                wins = sum(base == 0 and treat == 1 for _, base, treat in triples)
                losses = sum(base == 1 and treat == 0 for _, base, treat in triples)
                item.update(
                    {
                        "wins": wins,
                        "losses": losses,
                        "mcnemar_p": f"{exact_mcnemar(wins, losses):.12g}",
                    }
                )
            paired.append(item)

    instance_fields = [
        "approach",
        "instance_id",
        "repository",
        "candidate_count",
        "file_hit",
        "target_coverage",
        "mrr",
        "hit",
        "complete",
    ]
    write_tsv(args.output_instances, rows, instance_fields)
    write_tsv(args.output_summary, summary, list(summary[0]))
    write_tsv(args.output_paired, paired, list(paired[0]))
    print(f"wrote {args.output_summary}, {args.output_instances}, and {args.output_paired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
