#!/usr/bin/env python3
"""Measure strict target coverage in the exact source-bearing repair prompts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from statistics import mean


ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ARTIFACT_ROOT / "kgcompass"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_strict_reference_context import (  # noqa: E402
    candidate_matches_target,
    cluster_bootstrap_ci,
    exact_mcnemar,
    repository_id,
)
from repair_claude import CodeRepair, load_instance_from_dataset  # noqa: E402
import repair_claude as repair_module  # noqa: E402


METRICS = ("source_target_coverage", "source_hit", "source_complete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--shard-ids-root", type=Path, required=True)
    parser.add_argument("--playground-root", type=Path, required=True)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--dataset-file", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--reference-rendering", type=Path)
    parser.add_argument("--variant", action="append", required=True, metavar="LABEL=RUN_VARIANT")
    parser.add_argument("--preset", default="local_qwen3coder30b")
    parser.add_argument("--round-tag", default="_base")
    parser.add_argument("--prompt-token-limit", type=int, default=4000)
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


def parse_variants(values: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"Invalid --variant {raw!r}")
        label, run_variant = (part.strip() for part in raw.split("=", 1))
        if not label or not run_variant:
            raise ValueError(f"Invalid --variant {raw!r}")
        result.append((label, run_variant))
    return result


def load_shards(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.glob("*.jsonl")):
        shard = path.stem
        for instance_id in load_ids(path):
            if instance_id in result:
                raise ValueError(f"Instance appears in multiple shards: {instance_id}")
            result[instance_id] = shard
    return result


def load_reference_rendering(path: Path) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            key = (row["instance_id"], row["variant"])
            if key in result:
                raise ValueError(f"Duplicate reference-rendering row: {key}")
            result[key] = row
    return result


def parse_rendered_blocks(content: str) -> list[dict]:
    result: list[dict] = []
    for block in re.split(r"(?=^- signature : )", content, flags=re.MULTILINE):
        signature = re.search(r"^- signature : (.*)$", block, flags=re.MULTILINE)
        if not signature:
            continue
        start = re.search(r"^- start_line : (.*)$", block, flags=re.MULTILINE)
        end = re.search(r"^- end_line : (.*)$", block, flags=re.MULTILINE)
        result.append(
            {
                "signature": signature.group(1).strip(),
                "start_line": (start.group(1).strip() if start else ""),
                "end_line": (end.group(1).strip() if end else ""),
                "source_bearing": int("- source_authority :" in block),
            }
        )
    return result


def method_key(method: dict) -> tuple[str, str, str]:
    return (
        str(method.get("signature") or ""),
        str(method.get("start_line") or ""),
        str(method.get("end_line") or ""),
    )


def resolve_rendered_methods(blocks: list[dict], methods: list[dict]) -> list[tuple[dict, int]]:
    by_key: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    by_signature: dict[str, list[dict]] = defaultdict(list)
    by_span: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for method in methods:
        by_key[method_key(method)].append(method)
        by_signature[str(method.get("signature") or "")].append(method)
        by_span[(str(method.get("start_line") or ""), str(method.get("end_line") or ""))].append(method)

    resolved: list[tuple[dict, int]] = []
    for block in blocks:
        key = (block["signature"], block["start_line"], block["end_line"])
        candidates = by_key.get(key) or by_signature.get(block["signature"]) or []
        if not candidates:
            candidates = [
                method
                for method in by_span.get((block["start_line"], block["end_line"]), [])
                if str(method.get("signature") or "").startswith(block["signature"])
            ]
        if not candidates:
            raise ValueError(f"Rendered entity cannot be resolved: {key}")
        resolved.append((candidates[0], int(block["source_bearing"])))
    return resolved


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    ids = load_ids(args.ids_file)
    variants = parse_variants(args.variant)
    shards = load_shards(args.shard_ids_root)
    missing_shards = [instance_id for instance_id in ids if instance_id not in shards]
    if missing_shards:
        raise ValueError(f"Missing shard mapping for {len(missing_shards)} instances")

    targets = json.loads(args.targets.read_text(encoding="utf-8"))["items"]
    references = load_reference_rendering(args.reference_rendering) if args.reference_rendering else {}
    os.environ["SWE_BENCH_LOCAL_FILE"] = str(args.dataset_file.resolve())
    os.environ["MURAL_REPAIR_FIRST_PROMPT_PROFILE"] = "compact"
    os.environ["MURAL_REPAIR_PROMPT_TOKEN_LIMIT"] = str(args.prompt_token_limit)
    os.environ["MURAL_REPAIR_RESPONSE_PREFILL"] = "off"
    os.environ.setdefault("OPENAI_API_KEY", "offline-audit")
    repairer = CodeRepair(
        language="python",
        api_type="openai_compat",
        temperature=0.0,
        model_name_override="glm-5.2",
        base_url_override="http://127.0.0.1:1/v1",
        api_key_env="OPENAI_API_KEY",
    )

    original_loader = repairer._load_original_file_content

    @lru_cache(maxsize=8192)
    def cached_loader(repo_path: str, file_path: str, commit_id: str):
        return original_loader(repo_path, file_path, commit_id)

    repairer._load_original_file_content = cached_loader

    original_ast_parse = repair_module.ast.parse

    @lru_cache(maxsize=8192)
    def cached_ast_parse(
        source: str,
        filename: str = "<unknown>",
        mode: str = "exec",
        type_comments: bool = False,
        feature_version=None,
    ):
        return original_ast_parse(
            source,
            filename=filename,
            mode=mode,
            type_comments=type_comments,
            feature_version=feature_version,
        )

    repair_module.ast.parse = cached_ast_parse

    rows: list[dict] = []
    by_variant: dict[str, dict[str, dict]] = defaultdict(dict)
    for label, run_variant in variants:
        for index, instance_id in enumerate(ids, 1):
            location_path = (
                args.input_root
                / run_variant
                / args.preset
                / args.round_tag
                / instance_id
                / "final_locations"
                / f"{instance_id}.json"
            )
            location = json.loads(location_path.read_text(encoding="utf-8"))
            dataset = load_instance_from_dataset(instance_id, "swe-bench")
            problem = repairer._build_issue_context(location, dataset).replace("\r", "")
            methods = list((location.get("related_entities") or {}).get("methods") or [])
            repo_path = (
                args.playground_root
                / shards[instance_id]
                / repository_id(instance_id)
            )
            methods = repairer._enrich_methods_with_file_context(
                methods, str(repo_path), dataset["commit_id"]
            )
            content = repairer._build_compact_repair_context(problem, methods)
            prompt = repairer._get_prompt_template().format(
                problem_statement=problem,
                content=content or "No related code snippets found.",
                file_path_example=repairer.file_path_example,
                language_name=repairer.language_name,
                code_example=repairer.code_example,
                code_block_lang=repairer.code_block_lang,
            )
            prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            if references:
                reference = references[(instance_id, label)]
                if prompt_hash != reference["prompt_sha256"]:
                    raise ValueError(
                        f"Prompt hash mismatch for {instance_id}/{label}: "
                        f"{prompt_hash} != {reference['prompt_sha256']}"
                    )

            rendered = resolve_rendered_methods(parse_rendered_blocks(content), methods)
            source_methods = [method for method, source in rendered if source]
            reference_targets = targets[instance_id]["targets"]
            matched: set[int] = set()
            for method in source_methods:
                for target_index, target in enumerate(reference_targets):
                    if candidate_matches_target(method, target):
                        matched.add(target_index)
            target_count = len(reference_targets)
            row = {
                "instance_id": instance_id,
                "repository": repository_id(instance_id),
                "variant": label,
                "rendered_entities": len(rendered),
                "source_entities": len(source_methods),
                "target_count": target_count,
                "matched_target_count": len(matched),
                "source_target_coverage": len(matched) / target_count,
                "source_hit": int(bool(matched)),
                "source_complete": int(len(matched) == target_count),
                "prompt_tokens": repairer.count_tokens(prompt),
                "prompt_sha256": prompt_hash,
            }
            rows.append(row)
            by_variant[label][instance_id] = row
            if index % 100 == 0:
                print(f"{label}: verified {index}/{len(ids)} prompts")

    summary_rows: list[dict] = []
    for label, _ in variants:
        group = list(by_variant[label].values())
        summary_rows.append(
            {
                "variant": label,
                "N": len(group),
                "rendered_entities_mean": f"{mean(r['rendered_entities'] for r in group):.6f}",
                "source_entities_mean": f"{mean(r['source_entities'] for r in group):.6f}",
                "prompt_tokens_mean": f"{mean(r['prompt_tokens'] for r in group):.6f}",
                "source_target_coverage": f"{100 * mean(r['source_target_coverage'] for r in group):.6f}",
                "source_hit": f"{100 * mean(r['source_hit'] for r in group):.6f}",
                "source_complete": f"{100 * mean(r['source_complete'] for r in group):.6f}",
                "verified_prompt_hashes": len(group) if references else 0,
            }
        )

    if len(variants) != 2:
        raise ValueError("Paired output currently requires exactly two variants")
    baseline, treatment = variants[0][0], variants[1][0]
    paired_rows: list[dict] = []
    for metric in METRICS:
        triples = [
            (
                repository_id(instance_id),
                float(by_variant[baseline][instance_id][metric]),
                float(by_variant[treatment][instance_id][metric]),
            )
            for instance_id in ids
        ]
        delta = mean(treatment_value - baseline_value for _, baseline_value, treatment_value in triples)
        low, high = cluster_bootstrap_ci(triples, args.bootstrap, args.seed)
        paired = {
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
        if metric in {"source_hit", "source_complete"}:
            wins = sum(base == 0 and treat == 1 for _, base, treat in triples)
            losses = sum(base == 1 and treat == 0 for _, base, treat in triples)
            paired.update(
                {
                    "wins": wins,
                    "losses": losses,
                    "mcnemar_p": f"{exact_mcnemar(wins, losses):.12g}",
                }
            )
        paired_rows.append(paired)

    fields = [
        "instance_id",
        "repository",
        "variant",
        "rendered_entities",
        "source_entities",
        "target_count",
        "matched_target_count",
        *METRICS,
        "prompt_tokens",
        "prompt_sha256",
    ]
    write_tsv(args.output_instances, rows, fields)
    write_tsv(args.output_summary, summary_rows, list(summary_rows[0]))
    write_tsv(args.output_paired, paired_rows, list(paired_rows[0]))
    print(f"wrote {args.output_summary}, {args.output_instances}, and {args.output_paired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
