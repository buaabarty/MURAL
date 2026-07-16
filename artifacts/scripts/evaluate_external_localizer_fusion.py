#!/usr/bin/env python3
"""Evaluate released localizer prefixes with a MURAL tail."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Any, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=Path("temp_run/SWE-bench_Verified_ids.jsonl"),
    )
    parser.add_argument(
        "--gt-cache",
        type=Path,
        default=Path("temp_run/output/gt_eval_cache_verified_v3_entities.json"),
    )
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--mural-dir", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--primary-prefix", type=int, default=10)
    parser.add_argument("--secondary-pool", type=int, default=20)
    parser.add_argument(
        "--tail-label",
        default="MURAL",
        help="Reader-facing label for the appended localization tail.",
    )
    parser.add_argument("--bootstrap-iters", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-paired", type=Path, required=True)
    parser.add_argument("--output-disagreements", type=Path)
    return parser.parse_args()


def load_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            ids.append(json.loads(line)["instance_id"] if line.startswith("{") else line)
    return ids


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_gt(path: Path) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["items"]


def signature_to_base(signature: str) -> str:
    base = (signature or "").strip()
    if not base:
        return ""
    base = base.split(" = ", 1)[0].strip()
    return base.split("(", 1)[0].strip()


def short_label(label: str) -> str:
    base = signature_to_base(label)
    if not base:
        return ""
    parts = base.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else base


def file_matches(candidate_file: str, patch_files: Iterable[str]) -> bool:
    return any(
        patch_file == candidate_file
        or patch_file in candidate_file
        or candidate_file in patch_file
        for patch_file in patch_files
    )


def method_label_matches(candidate: str, gt_signature: str) -> bool:
    base = signature_to_base(gt_signature)
    if not base:
        return False
    return (
        base == candidate
        or base.endswith("." + candidate)
        or short_label(candidate) == short_label(base)
    )


def class_label_matches(candidate: str, gt_class: str) -> bool:
    return (
        gt_class == candidate
        or gt_class.endswith("." + candidate)
        or short_label(candidate) == short_label(gt_class)
    )


def signature_matches_class(signature: str, class_name: str) -> bool:
    base = signature_to_base(signature)
    return bool(base and class_name and (base == class_name or base.startswith(class_name + ".")))


def flatten_locations(raw_locations: Any) -> list[str]:
    if raw_locations is None:
        return []
    if isinstance(raw_locations, str):
        raw_locations = [raw_locations]
    output: list[str] = []
    for item in raw_locations:
        if item is None:
            continue
        lines = item.splitlines() if isinstance(item, str) else [str(item)]
        output.extend(line.strip() for line in lines if line.strip())
    return output


def normalize_location(location: str) -> tuple[str, str] | None:
    raw = location.strip()
    if not raw:
        return None
    lower = raw.lower()
    for prefix, kind in (
        ("class:", "class"),
        ("function:", "function"),
        ("variable:", "variable"),
    ):
        if lower.startswith(prefix):
            return kind, raw.split(":", 1)[1].strip()
    if lower.startswith("line:"):
        return None
    return "unknown", raw


def external_candidates(row: dict[str, Any] | None, limit: int = 50) -> list[dict[str, str]]:
    if row is None:
        return []
    related = row.get("found_related_locs") or {}
    ranked: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for file_path in row.get("found_files") or []:
        for location in flatten_locations(related.get(file_path) or []):
            normalized = normalize_location(location)
            if normalized is None:
                continue
            kind, label = normalized
            key = (file_path, kind, label)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(
                {
                    "source": "external",
                    "file_path": file_path,
                    "kind": kind,
                    "label": label,
                }
            )
            if len(ranked) >= limit:
                return ranked
    return ranked


def mural_candidates(path: Path, limit: int = 50) -> list[dict[str, str]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    methods = sorted(
        ((data.get("related_entities") or {}).get("methods") or []),
        key=lambda item: item.get("similarity", 0.0),
        reverse=True,
    )
    ranked: list[dict[str, str]] = []
    seen: set[str] = set()
    for method in methods:
        signature = method.get("signature") or ""
        if not signature or signature in seen:
            continue
        seen.add(signature)
        ranked.append(
            {
                "source": "mural",
                "file_path": method.get("file_path") or "",
                "kind": "method",
                "label": signature,
                "signature": signature,
            }
        )
        if len(ranked) >= limit:
            break
    return ranked


def candidate_keys(candidate: dict[str, str]) -> set[tuple[str, str]]:
    file_path = candidate.get("file_path") or ""
    label = candidate.get("signature") or candidate.get("label") or ""
    keys = {
        (file_path, signature_to_base(label).lower()),
        (file_path, short_label(label).lower()),
    }
    return {key for key in keys if key[1]}


def fill_unique(base: list[dict[str, str]], extra: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in [*base, *extra]:
        keys = candidate_keys(candidate)
        if seen & keys:
            continue
        seen.update(keys)
        output.append(candidate)
        if len(output) >= limit:
            break
    return output


def fuse_candidates(
    primary: list[dict[str, str]],
    secondary: list[dict[str, str]],
    primary_prefix: int,
    secondary_pool: int,
    top_k: int,
) -> list[dict[str, str]]:
    merged = fill_unique(primary[:primary_prefix], secondary[:secondary_pool], top_k)
    if len(merged) < top_k:
        merged = fill_unique(merged, primary[primary_prefix:], top_k)
    if len(merged) < top_k:
        merged = fill_unique(merged, secondary[secondary_pool:], top_k)
    return merged[:top_k]


def evaluate_one(candidates: list[dict[str, str]], gt: dict[str, Any], top_k: int) -> dict[str, Any]:
    patch_files = gt["patch_files"]
    found_methods = set(gt["found_methods"])
    found_classes = set(gt["found_classes"])
    use_file_fallback = bool(gt["fallback_file_target"])
    matched_methods: set[str] = set()
    matched_classes: set[str] = set()
    found_count = 0
    best_rank: int | None = None
    find_file = 0
    fallback_hit = 0

    for rank, candidate in enumerate(candidates[:top_k], start=1):
        file_path = candidate.get("file_path") or ""
        kind = candidate.get("kind") or ""
        label = candidate.get("label") or ""
        matched = False

        if candidate.get("source") == "mural":
            signature = candidate.get("signature") or label
            if signature in found_methods and signature not in matched_methods:
                matched_methods.add(signature)
                matched = True
            else:
                for class_name in sorted(found_classes):
                    if class_name in matched_classes:
                        continue
                    if signature_matches_class(signature, class_name):
                        matched_classes.add(class_name)
                        matched = True
                        break
        else:
            if kind in {"function", "unknown"}:
                for gt_signature in sorted(found_methods):
                    if gt_signature in matched_methods:
                        continue
                    if file_matches(file_path, patch_files) and method_label_matches(label, gt_signature):
                        matched_methods.add(gt_signature)
                        matched = True
                        break
            if not matched and kind in {"class", "function", "unknown"}:
                for gt_class in sorted(found_classes):
                    if gt_class in matched_classes:
                        continue
                    if file_matches(file_path, patch_files) and class_label_matches(label, gt_class):
                        matched_classes.add(gt_class)
                        matched = True
                        break

        if matched:
            found_count += 1
            if best_rank is None:
                best_rank = rank
        if file_matches(file_path, patch_files):
            find_file = 1
            if use_file_fallback:
                fallback_hit = 1
                if best_rank is None:
                    best_rank = rank

    if use_file_fallback:
        found_count = fallback_hit
    return {
        "find_file": find_file,
        "ratio": found_count / max(1, int(gt["gt_entities_n"])),
        "best_rank": best_rank,
        "hit": int(found_count > 0),
    }


def summarize(
    name: str,
    source: str,
    ids: list[str],
    rankings: dict[str, list[dict[str, str]]],
    gt_map: dict[str, dict[str, Any]],
    top_k: int,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    evaluated = {
        instance_id: evaluate_one(rankings.get(instance_id, []), gt_map[instance_id], top_k)
        for instance_id in ids
    }
    n = len(ids)
    return (
        {
            "name": name,
            "N": n,
            "ranked_nonempty": sum(bool(rankings.get(instance_id)) for instance_id in ids),
            "file_rate": sum(row["find_file"] for row in evaluated.values()) / n,
            "method_or_entity_rate": sum(row["ratio"] for row in evaluated.values()) / n,
            "mrr": sum(
                0.0 if row["best_rank"] is None else 1.0 / row["best_rank"]
                for row in evaluated.values()
            )
            / n,
            "top20_hit_rate": sum(row["hit"] for row in evaluated.values()) / n,
            "source": source,
        },
        evaluated,
    )


def exact_mcnemar_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = min(wins, losses)
    probability = sum(math.comb(discordant, index) for index in range(tail + 1)) / (2**discordant)
    return min(1.0, 2.0 * probability)


def bootstrap_ci(pairs: list[tuple[int, int]], iterations: int, seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(pairs)
    deltas: list[float] = []
    for _ in range(iterations):
        total = 0
        for _ in range(n):
            old, new = pairs[rng.randrange(n)]
            total += new - old
        deltas.append(total / n)
    deltas.sort()
    return deltas[int(0.025 * iterations)], deltas[min(iterations - 1, int(0.975 * iterations))]


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    ids = load_ids(args.ids_file)
    gt_map = load_gt(args.gt_cache)
    specs = {
        "CoSIL-Qwen2.5-32B": args.external_root / "CoSIL" / "CoSIL_qwen_coder_32b_func.jsonl",
        "Agentless-Qwen2.5-32B": args.external_root / "agentless" / "agentless_qwen_coder_32b_func.jsonl",
        "LocAgent-Qwen2.5-32B": args.external_root / "locagent" / "locagent_qwen_coder_32b_func.jsonl",
        "OrcaLoca-Qwen2.5-32B": args.external_root / "orcaloca" / "orcaloca_qwen_coder_32b_func.jsonl",
    }
    secondary = {
        instance_id: mural_candidates(
            args.mural_dir / f"{instance_id}.json",
            max(args.top_k, args.secondary_pool),
        )
        for instance_id in ids
    }

    summaries: list[dict[str, Any]] = []
    paired_rows: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    for comparison_index, (name, source_path) in enumerate(specs.items()):
        external_map = {row["instance_id"]: row for row in load_jsonl(source_path)}
        primary = {
            instance_id: external_candidates(
                external_map.get(instance_id),
                max(args.top_k, args.primary_prefix),
            )
            for instance_id in ids
        }
        fused = {
            instance_id: fuse_candidates(
                primary[instance_id],
                secondary[instance_id],
                args.primary_prefix,
                args.secondary_pool,
                args.top_k,
            )
            for instance_id in ids
        }
        baseline_summary, baseline_eval = summarize(
            name,
            str(source_path),
            ids,
            primary,
            gt_map,
            args.top_k,
        )
        treatment_name = f"{name}+{args.tail_label}"
        treatment_summary, treatment_eval = summarize(
            treatment_name,
            f"{source_path} + {args.mural_dir}",
            ids,
            fused,
            gt_map,
            args.top_k,
        )
        summaries.extend([baseline_summary, treatment_summary])

        pairs = [
            (baseline_eval[instance_id]["hit"], treatment_eval[instance_id]["hit"])
            for instance_id in ids
        ]
        wins = sum(new > old for old, new in pairs)
        losses = sum(new < old for old, new in pairs)
        low, high = bootstrap_ci(pairs, args.bootstrap_iters, args.seed + comparison_index)
        baseline_hit = sum(old for old, _ in pairs) / len(pairs)
        treatment_hit = sum(new for _, new in pairs) / len(pairs)
        paired_rows.append(
            {
                "baseline": name,
                "treatment": treatment_name,
                "N": len(pairs),
                "baseline_hit": baseline_hit,
                "treatment_hit": treatment_hit,
                "delta": treatment_hit - baseline_hit,
                "ci95_low": low,
                "ci95_high": high,
                "wins": wins,
                "losses": losses,
                "ties": len(pairs) - wins - losses,
                "exact_mcnemar_p": exact_mcnemar_p(wins, losses),
            }
        )
        for instance_id, (old, new) in zip(ids, pairs):
            if old == new:
                continue
            disagreements.append(
                {
                    "baseline": name,
                    "treatment": treatment_name,
                    "instance_id": instance_id,
                    "direction": "treatment_only" if new > old else "baseline_only",
                }
            )

    summaries.sort(key=lambda row: row["method_or_entity_rate"], reverse=True)
    formatted_summaries = []
    for row in summaries:
        formatted = dict(row)
        for field in (
            "file_rate",
            "method_or_entity_rate",
            "mrr",
            "top20_hit_rate",
        ):
            formatted[field] = f"{float(row[field]):.6f}"
        formatted_summaries.append(formatted)
    write_tsv(
        args.output_summary,
        formatted_summaries,
        [
            "name",
            "N",
            "ranked_nonempty",
            "file_rate",
            "method_or_entity_rate",
            "mrr",
            "top20_hit_rate",
            "source",
        ],
    )
    write_tsv(
        args.output_paired,
        paired_rows,
        [
            "baseline",
            "treatment",
            "N",
            "baseline_hit",
            "treatment_hit",
            "delta",
            "ci95_low",
            "ci95_high",
            "wins",
            "losses",
            "ties",
            "exact_mcnemar_p",
        ],
    )
    if args.output_disagreements:
        write_tsv(
            args.output_disagreements,
            disagreements,
            ["baseline", "treatment", "instance_id", "direction"],
        )
    print(f"wrote {args.output_summary}")
    print(f"wrote {args.output_paired}")
    if args.output_disagreements:
        print(f"wrote {args.output_disagreements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
