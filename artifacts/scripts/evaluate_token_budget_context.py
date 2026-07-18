#!/usr/bin/env python3
"""Evaluate ranked entity windows under equal rendered-token budgets.

The fixed-slot localization experiments remain useful, but a slot does not
have a stable source-code size.  This control greedily renders ranked entities
with the same tokenizer and entity renderer used by the repair workflow and
stops before the next entity would exceed the configured code-context budget.
It archives each packed ranking, rendering diagnostics, aggregate metrics, and
paired uncertainty estimates.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from unidiff import PatchSet


ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ARTIFACT_ROOT / "kgcompass"))

from repair_claude import CodeRepair  # noqa: E402


METRICS: dict[str, Callable[[dict[str, Any]], float]] = {
    "file": lambda row: float(row["find_file"]),
    "entity_recall": lambda row: float(row["ratio"]),
    "mrr": lambda row: 0.0
    if row.get("best_rank") is None
    else 1.0 / float(row["best_rank"]),
    "hit": lambda row: float(row["hit"]),
}


def parse_named_path(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    name, path = (part.strip() for part in raw.split("=", 1))
    if not name or not path:
        raise ValueError(f"Expected NAME=DIR, got {raw!r}")
    return name, Path(path)


def parse_comparison(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise ValueError(f"Expected BASELINE=TREATMENT, got {raw!r}")
    baseline, treatment = (part.strip() for part in raw.split("=", 1))
    if not baseline or not treatment:
        raise ValueError(f"Expected BASELINE=TREATMENT, got {raw!r}")
    return baseline, treatment


def load_ids(path: Path) -> list[str]:
    output: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        output.append(str(json.loads(line)["instance_id"]) if line.startswith("{") else line)
    if not output:
        raise ValueError(f"No instance ids in {path}")
    return list(dict.fromkeys(output))


def load_dataset(path: Path) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        item = json.loads(raw)
        output[str(item["instance_id"])] = item
    return output


def load_eval_module() -> Any:
    path = Path(__file__).with_name("eval_controls_v3.py")
    spec = importlib.util.spec_from_file_location("eval_controls_v3", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_identity(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(item.get("file_path") or "").replace("\\", "/"),
        str(item.get("signature") or item.get("name") or ""),
        int(item.get("start_line") or 0),
        int(item.get("end_line") or 0),
    )


def ranked_entities(payload: dict[str, Any], max_candidates: int) -> list[dict[str, Any]]:
    related = payload.get("related_entities") or {}
    candidates = list(related.get("methods") or []) + list(related.get("classes") or [])
    output: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in candidates:
        identity = canonical_identity(item)
        if not identity[0] or not identity[1] or identity in seen:
            continue
        if not str(item.get("source_code") or "").strip():
            continue
        seen.add(identity)
        output.append(deepcopy(item))
        if len(output) >= max_candidates:
            break
    return output


def render_source(repairer: CodeRepair, item: dict[str, Any], mode: str) -> str:
    source = str(item.get("source_code") or "").rstrip()
    limit = repairer._get_method_source_token_limit(mode == "primary")
    return repairer._truncate_source_preserve_ends(source, limit)


def rendered_line_numbers(
    source: str,
    rendered: str,
    start_line: int,
) -> set[int]:
    source = source.rstrip()
    rendered = rendered.rstrip()
    source_lines = source.splitlines()
    if not source_lines or not rendered:
        return set()
    if rendered == source:
        return set(range(start_line, start_line + len(source_lines)))

    marker = "\n...\n# [middle truncated]\n...\n"
    if marker in rendered:
        head, tail = rendered.split(marker, 1)
        head_lines = head.splitlines()
        tail_lines = tail.splitlines()
        output = set(range(start_line, start_line + len(head_lines)))
        tail_start = start_line + len(source_lines) - len(tail_lines)
        output.update(range(tail_start, start_line + len(source_lines)))
        return output

    prefix = rendered.split("\n\n[truncated for brevity]", 1)[0]
    prefix_lines = prefix.splitlines()
    complete = 0
    for original, kept in zip(source_lines, prefix_lines):
        if original != kept:
            break
        complete += 1
    return set(range(start_line, start_line + complete))


def pack_entities(
    repairer: CodeRepair,
    candidates: list[dict[str, Any]],
    budget: int,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    def render_prefix(size: int) -> tuple[list[dict[str, Any]], str, int]:
        items = [deepcopy(item) for item in candidates[:size]]
        for index, item in enumerate(items):
            item["_prompt_mode"] = "primary" if index == 0 else "secondary"
        rendered = repairer._render_method_context(items)
        return items, rendered, repairer.count_tokens(rendered)

    low, high = 0, len(candidates)
    while low < high:
        middle = (low + high + 1) // 2
        _, _, tokens = render_prefix(middle)
        if tokens <= budget:
            low = middle
        else:
            high = middle - 1

    selected, content, _ = render_prefix(low)
    diagnostics: list[dict[str, Any]] = []
    for index, item in enumerate(selected):
        mode = "primary" if index == 0 else "secondary"
        source = str(item.get("source_code") or "").rstrip()
        rendered = render_source(repairer, item, mode)
        diagnostics.append(
            {
                "identity": canonical_identity(item),
                "mode": mode,
                "full_source_tokens": repairer.count_tokens(source),
                "rendered_source_tokens": repairer.count_tokens(rendered),
                "truncated": int(rendered != source),
                "rendered_lines": rendered_line_numbers(
                    source,
                    rendered,
                    int(item.get("start_line") or 1),
                ),
            }
        )
    return selected, content, diagnostics


def changed_base_lines(patch_text: str) -> dict[str, set[int]]:
    output: dict[str, set[int]] = defaultdict(set)
    for patched_file in PatchSet(patch_text):
        path = str(patched_file.path).replace("\\", "/")
        for hunk in patched_file:
            old_line = int(hunk.source_start)
            for line in hunk:
                if line.is_context:
                    old_line += 1
                elif line.is_removed:
                    output[path].add(max(1, old_line))
                    old_line += 1
                elif line.is_added:
                    output[path].add(max(1, old_line))
    return output


def changed_line_coverage(
    patch_text: str,
    selected: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> tuple[int, int]:
    changed = changed_base_lines(patch_text)
    covered_by_file: dict[str, set[int]] = defaultdict(set)
    for item, diagnostic in zip(selected, diagnostics):
        path = str(item.get("file_path") or "").replace("\\", "/")
        covered_by_file[path].update(diagnostic["rendered_lines"])
    total = sum(len(lines) for lines in changed.values())
    covered = sum(len(lines & covered_by_file[path]) for path, lines in changed.items())
    return covered, total


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return float(ordered[index])


def exact_mcnemar_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = min(wins, losses)
    probability = sum(math.comb(discordant, index) for index in range(tail + 1)) / (
        2**discordant
    )
    return min(1.0, 2.0 * probability)


def bootstrap_ci(
    pairs: list[tuple[float, float]], iterations: int, seed: int
) -> tuple[float, float]:
    rng = random.Random(seed)
    size = len(pairs)
    deltas: list[float] = []
    for _ in range(iterations):
        total = 0.0
        for _ in range(size):
            old, new = pairs[rng.randrange(size)]
            total += new - old
        deltas.append(total / size)
    deltas.sort()
    return (
        deltas[int(0.025 * iterations)],
        deltas[min(iterations - 1, int(0.975 * iterations))],
    )


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"No rows for {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, help="NAME=DIR")
    parser.add_argument("--compare", action="append", default=[], help="BASELINE=TREATMENT")
    parser.add_argument("--budget", action="append", type=int, dest="budgets")
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--dataset-file", required=True, type=Path)
    parser.add_argument("--gt-cache", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-paired", required=True, type=Path)
    parser.add_argument("--output-instances", required=True, type=Path)
    parser.add_argument("--max-candidates", type=int, default=50)
    parser.add_argument("--bootstrap-iters", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = [parse_named_path(raw) for raw in args.source]
    source_names = [name for name, _ in sources]
    if len(source_names) != len(set(source_names)):
        raise ValueError("Source names must be unique")
    budgets = args.budgets or [2000, 4000, 8000]
    if any(budget <= 0 for budget in budgets):
        raise ValueError("Token budgets must be positive")

    ids = load_ids(args.ids_file)
    dataset = load_dataset(args.dataset_file)
    missing_dataset = [instance_id for instance_id in ids if instance_id not in dataset]
    if missing_dataset:
        raise ValueError(f"Dataset misses {len(missing_dataset)} requested instances")

    eval_module = load_eval_module()
    gt_map = eval_module.load_or_build_gt_cache(ids, args.gt_cache)
    os.environ.setdefault("OPENAI_API_KEY", "offline-token-audit")
    repairer = CodeRepair(
        language="python",
        api_type="openai_compat",
        temperature=0.0,
        model_name_override="glm-5.2",
        base_url_override="http://127.0.0.1:1/v1",
        api_key_env="OPENAI_API_KEY",
    )
    uncached_count_tokens = repairer.count_tokens
    uncached_truncate = repairer._truncate_source_preserve_ends

    @lru_cache(maxsize=100000)
    def cached_count_tokens(text: str) -> int:
        return uncached_count_tokens(text)

    @lru_cache(maxsize=50000)
    def cached_truncate(text: str, token_limit: int) -> str:
        return uncached_truncate(text, token_limit)

    repairer.count_tokens = cached_count_tokens
    repairer._truncate_source_preserve_ends = cached_truncate

    instance_rows: list[dict[str, Any]] = []
    eval_rows: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    diagnostic_rows: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)

    for source_name, source_dir in sources:
        for budget in budgets:
            output_dir = args.output_root / f"{source_name}_t{budget}"
            output_dir.mkdir(parents=True, exist_ok=True)
            key = (source_name, budget)
            eval_rows[key] = {}
            for position, instance_id in enumerate(ids, start=1):
                source_path = source_dir / f"{instance_id}.json"
                if not source_path.exists():
                    raise FileNotFoundError(source_path)
                payload = json.loads(source_path.read_text(encoding="utf-8"))
                candidates = ranked_entities(payload, args.max_candidates)
                selected, content, diagnostics = pack_entities(repairer, candidates, budget)
                context_tokens = repairer.count_tokens(content)
                covered_lines, total_lines = changed_line_coverage(
                    str(dataset[instance_id].get("patch") or ""), selected, diagnostics
                )

                output = deepcopy(payload)
                related = output.setdefault("related_entities", {})
                related["methods"] = selected
                related["classes"] = []
                output["token_packing"] = {
                    "budget": budget,
                    "candidate_count": len(candidates),
                    "selected_count": len(selected),
                    "rendered_context_tokens": context_tokens,
                    "tokenizer": "tiktoken-cl100k_base via repair renderer",
                    "policy": "rank-prefix greedy; exact entity renderer",
                }
                destination = output_dir / source_path.name
                destination.write_text(
                    json.dumps(output, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )

                evaluation = eval_module.evaluate_one_instance(
                    output, gt_map[instance_id], args.max_candidates
                )
                eval_rows[key][instance_id] = evaluation
                full_lengths = [float(row["full_source_tokens"]) for row in diagnostics]
                truncated = sum(int(row["truncated"]) for row in diagnostics)
                row = {
                    "instance_id": instance_id,
                    "source": source_name,
                    "token_budget": budget,
                    "candidate_entities": len(candidates),
                    "selected_entities": len(selected),
                    "rendered_context_tokens": context_tokens,
                    "budget_fill": context_tokens / budget,
                    "mean_selected_source_tokens": statistics.mean(full_lengths)
                    if full_lengths
                    else 0.0,
                    "truncated_entities": truncated,
                    "changed_lines_covered": covered_lines,
                    "changed_lines_total": total_lines,
                    "complete_changed_lines": int(total_lines > 0 and covered_lines == total_lines),
                    "file_hit": evaluation["find_file"],
                    "entity_recall": evaluation["ratio"],
                    "mrr": 0.0
                    if evaluation.get("best_rank") is None
                    else 1.0 / float(evaluation["best_rank"]),
                    "hit": evaluation["hit"],
                }
                instance_rows.append(row)
                diagnostic_rows[key].extend(diagnostics)
                if position % 100 == 0 or position == len(ids):
                    print(
                        f"[token-pack] {source_name} budget={budget}: "
                        f"{position}/{len(ids)}",
                        flush=True,
                    )

    summary_rows: list[dict[str, Any]] = []
    for source_name, _ in sources:
        for budget in budgets:
            rows = [
                row
                for row in instance_rows
                if row["source"] == source_name and row["token_budget"] == budget
            ]
            entity_lengths = [
                float(row["full_source_tokens"])
                for row in diagnostic_rows[(source_name, budget)]
            ]
            total_selected = sum(int(row["selected_entities"]) for row in rows)
            total_truncated = sum(int(row["truncated_entities"]) for row in rows)
            changed_total = sum(int(row["changed_lines_total"]) for row in rows)
            changed_covered = sum(int(row["changed_lines_covered"]) for row in rows)
            summary_rows.append(
                {
                    "source": source_name,
                    "token_budget": budget,
                    "N": len(rows),
                    "selected_mean": statistics.mean(row["selected_entities"] for row in rows),
                    "selected_p50": statistics.median(row["selected_entities"] for row in rows),
                    "selected_p95": percentile(
                        [float(row["selected_entities"]) for row in rows], 0.95
                    ),
                    "context_tokens_mean": statistics.mean(
                        row["rendered_context_tokens"] for row in rows
                    ),
                    "context_tokens_p50": statistics.median(
                        row["rendered_context_tokens"] for row in rows
                    ),
                    "context_tokens_p95": percentile(
                        [float(row["rendered_context_tokens"]) for row in rows], 0.95
                    ),
                    "budget_fill_mean": statistics.mean(row["budget_fill"] for row in rows),
                    "entity_tokens_p50": statistics.median(entity_lengths)
                    if entity_lengths
                    else 0.0,
                    "entity_tokens_p95": percentile(entity_lengths, 0.95),
                    "truncated_entity_rate": total_truncated / total_selected
                    if total_selected
                    else 0.0,
                    "changed_line_recall": changed_covered / changed_total
                    if changed_total
                    else 0.0,
                    "complete_changed_line_rate": statistics.mean(
                        row["complete_changed_lines"] for row in rows
                    ),
                    "file_hit_rate": statistics.mean(row["file_hit"] for row in rows),
                    "entity_recall": statistics.mean(row["entity_recall"] for row in rows),
                    "mrr": statistics.mean(row["mrr"] for row in rows),
                    "hit_rate": statistics.mean(row["hit"] for row in rows),
                    "dir": str(args.output_root / f"{source_name}_t{budget}"),
                }
            )

    paired_rows: list[dict[str, Any]] = []
    for comparison_index, raw in enumerate(args.compare):
        baseline, treatment = parse_comparison(raw)
        if baseline not in source_names or treatment not in source_names:
            raise ValueError(f"Unknown comparison {raw!r}")
        for budget in budgets:
            old_rows = eval_rows[(baseline, budget)]
            new_rows = eval_rows[(treatment, budget)]
            for metric_index, (metric, extractor) in enumerate(METRICS.items()):
                pairs = [(extractor(old_rows[i]), extractor(new_rows[i])) for i in ids]
                wins = sum(new > old + 1e-12 for old, new in pairs)
                losses = sum(new < old - 1e-12 for old, new in pairs)
                low, high = bootstrap_ci(
                    pairs,
                    args.bootstrap_iters,
                    args.seed + comparison_index * 100 + metric_index,
                )
                old_mean = statistics.mean(old for old, _ in pairs)
                new_mean = statistics.mean(new for _, new in pairs)
                paired_rows.append(
                    {
                        "baseline": baseline,
                        "treatment": treatment,
                        "token_budget": budget,
                        "metric": metric,
                        "N": len(pairs),
                        "baseline_value": old_mean,
                        "treatment_value": new_mean,
                        "delta": new_mean - old_mean,
                        "ci95_low": low,
                        "ci95_high": high,
                        "wins": wins,
                        "losses": losses,
                        "ties": len(pairs) - wins - losses,
                        "exact_mcnemar_p": exact_mcnemar_p(wins, losses)
                        if metric in {"file", "hit"}
                        else "NA",
                    }
                )

    write_tsv(args.output_instances, instance_rows)
    write_tsv(args.output_summary, summary_rows)
    write_tsv(args.output_paired, paired_rows)
    print(f"wrote {args.output_instances}")
    print(f"wrote {args.output_summary}")
    print(f"wrote {args.output_paired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
