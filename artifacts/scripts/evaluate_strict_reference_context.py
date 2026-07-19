#!/usr/bin/env python3
"""Evaluate frozen ranked contexts against strict repair targets."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable


METRICS = ("file_hit", "target_coverage", "hit", "mrr", "complete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--row", action="append", required=True, metavar="LABEL=DIR")
    parser.add_argument("--compare", action="append", default=[], metavar="BASELINE=TREATMENT")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-instances", type=Path, required=True)
    parser.add_argument("--output-paired", type=Path, required=True)
    return parser.parse_args()


def parse_specs(values: Iterable[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"Invalid specification {raw!r}; expected NAME=VALUE")
        name, value = (part.strip() for part in raw.split("=", 1))
        if not name or not value:
            raise ValueError(f"Invalid specification {raw!r}")
        result.append((name, value))
    return result


def load_ids(path: Path) -> list[str]:
    ids: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(str(json.loads(line)["instance_id"]) if line.startswith("{") else line)
    return ids


def normalized_path(value: str | None) -> str:
    value = (value or "").replace("\\", "/")
    if value.startswith(("a/", "b/")):
        value = value[2:]
    while value.startswith("./"):
        value = value[2:]
    return value


def signature_base(signature: str) -> str:
    return signature.split(" = ", 1)[0].split("(", 1)[0].strip()


def candidate_kind(candidate: dict) -> str:
    signature = str(candidate.get("signature") or "")
    source = str(candidate.get("source_code") or "").lstrip()
    if " = " in signature and not source.startswith(("def ", "async def ")):
        return "assignment"
    return "function"


def candidate_local_name(candidate: dict) -> str:
    base = signature_base(str(candidate.get("signature") or candidate.get("name") or ""))
    parts = [part for part in base.split(".") if part]
    file_path = normalized_path(str(candidate.get("file_path") or ""))
    module_parts = [part for part in file_path[:-3].split("/") if part] if file_path.endswith(".py") else []

    best = 0
    for start in range(len(module_parts)):
        suffix = module_parts[start:]
        if len(suffix) <= len(parts) and parts[: len(suffix)] == suffix:
            best = max(best, len(suffix))
    local = parts[best:] if best else parts
    return ".".join(local)


def candidate_matches_target(candidate: dict, target: dict) -> bool:
    if normalized_path(candidate.get("file_path")) != normalized_path(target.get("file_path")):
        return False
    if target["target_type"] == "file":
        return True
    if candidate_kind(candidate) != target["target_type"]:
        return False
    candidate_name = candidate_local_name(candidate)
    target_name = str(target.get("qualified_name") or "")
    return candidate_name == target_name


def ranked_methods(path: Path, instance_id: str) -> list[dict]:
    data = json.loads((path / f"{instance_id}.json").read_text(encoding="utf-8"))
    methods = list((data.get("related_entities") or {}).get("methods") or [])
    if any(isinstance(item.get("similarity"), (int, float)) for item in methods):
        methods.sort(
            key=lambda item: (
                float(item["similarity"])
                if isinstance(item.get("similarity"), (int, float))
                else float("-inf")
            ),
            reverse=True,
        )
    return methods


def evaluate_instance(candidates: list[dict], reference: dict, top_k: int) -> dict:
    window = candidates[:top_k]
    targets = reference["targets"]
    matched: set[int] = set()
    first_rank: int | None = None
    patch_files = {normalized_path(path) for path in reference.get("patch_files") or []}
    file_hit = 0

    for rank, candidate in enumerate(window, 1):
        candidate_file = normalized_path(candidate.get("file_path"))
        if candidate_file in patch_files:
            file_hit = 1
        for index, target in enumerate(targets):
            if candidate_matches_target(candidate, target):
                matched.add(index)
                if first_rank is None:
                    first_rank = rank

    target_count = len(targets)
    return {
        "file_hit": file_hit,
        "target_coverage": len(matched) / target_count,
        "hit": int(bool(matched)),
        "mrr": 0.0 if first_rank is None else 1.0 / first_rank,
        "complete": int(len(matched) == target_count),
        "candidate_count": len(window),
        "target_count": target_count,
        "matched_target_count": len(matched),
        "first_rank": first_rank or 0,
    }


def repository_id(instance_id: str) -> str:
    return instance_id.rsplit("-", 1)[0]


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def cluster_bootstrap_ci(
    pairs: list[tuple[str, float, float]], resamples: int, seed: int
) -> tuple[float, float]:
    clusters: dict[str, list[float]] = defaultdict(list)
    for repo, baseline, treatment in pairs:
        clusters[repo].append(treatment - baseline)
    names = sorted(clusters)
    cluster_summaries = {
        name: (sum(clusters[name]), len(clusters[name])) for name in names
    }
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(resamples):
        total = 0.0
        count = 0
        for _ in names:
            selected = rng.choice(names)
            cluster_sum, cluster_count = cluster_summaries[selected]
            total += cluster_sum
            count += cluster_count
        deltas.append(total / count)
    return percentile(deltas, 0.025), percentile(deltas, 0.975)


def exact_mcnemar(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, j) for j in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def write_tsv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    ids = load_ids(args.ids_file)
    target_data = json.loads(args.targets.read_text(encoding="utf-8"))["items"]
    row_specs = [(name, Path(path)) for name, path in parse_specs(args.row)]
    labels = {name for name, _ in row_specs}
    instance_rows: list[dict] = []
    by_label: dict[str, dict[str, dict]] = defaultdict(dict)

    for label, source_dir in row_specs:
        for instance_id in ids:
            result = evaluate_instance(
                ranked_methods(source_dir, instance_id), target_data[instance_id], args.top_k
            )
            result.update(
                {
                    "approach": label,
                    "instance_id": instance_id,
                    "repository": repository_id(instance_id),
                }
            )
            instance_rows.append(result)
            by_label[label][instance_id] = result

    summary_rows: list[dict] = []
    for label, _ in row_specs:
        rows = list(by_label[label].values())
        summary_rows.append(
            {
                "approach": label,
                "N": len(rows),
                "top_k": args.top_k,
                "candidate_count_mean": f"{mean(r['candidate_count'] for r in rows):.6f}",
                "file_hit": f"{100 * mean(r['file_hit'] for r in rows):.6f}",
                "target_coverage": f"{100 * mean(r['target_coverage'] for r in rows):.6f}",
                "mrr": f"{100 * mean(r['mrr'] for r in rows):.6f}",
                "hit": f"{100 * mean(r['hit'] for r in rows):.6f}",
                "complete": f"{100 * mean(r['complete'] for r in rows):.6f}",
            }
        )

    paired_rows: list[dict] = []
    for baseline, treatment in parse_specs(args.compare):
        if baseline not in labels or treatment not in labels:
            raise ValueError(f"Unknown comparison {baseline}={treatment}")
        for metric in METRICS:
            triples = [
                (
                    repository_id(instance_id),
                    float(by_label[baseline][instance_id][metric]),
                    float(by_label[treatment][instance_id][metric]),
                )
                for instance_id in ids
            ]
            differences = [treatment_value - baseline_value for _, baseline_value, treatment_value in triples]
            low, high = cluster_bootstrap_ci(triples, args.bootstrap, args.seed)
            row = {
                "baseline": baseline,
                "treatment": treatment,
                "metric": metric,
                "delta": f"{100 * mean(differences):.6f}",
                "clustered_ci_low": f"{100 * low:.6f}",
                "clustered_ci_high": f"{100 * high:.6f}",
                "wins": "",
                "losses": "",
                "mcnemar_p": "",
            }
            if metric in {"file_hit", "hit", "complete"}:
                wins = sum(base == 0 and treat == 1 for _, base, treat in triples)
                losses = sum(base == 1 and treat == 0 for _, base, treat in triples)
                row.update(
                    {
                        "wins": wins,
                        "losses": losses,
                        "mcnemar_p": f"{exact_mcnemar(wins, losses):.12g}",
                    }
                )
            paired_rows.append(row)

    instance_fields = [
        "approach",
        "instance_id",
        "repository",
        "candidate_count",
        "target_count",
        "matched_target_count",
        "first_rank",
        *METRICS,
    ]
    write_tsv(args.output_instances, instance_rows, instance_fields)
    write_tsv(args.output_summary, summary_rows, list(summary_rows[0]))
    paired_fields = list(paired_rows[0]) if paired_rows else [
        "baseline",
        "treatment",
        "metric",
        "delta",
        "clustered_ci_low",
        "clustered_ci_high",
        "wins",
        "losses",
        "mcnemar_p",
    ]
    write_tsv(args.output_paired, paired_rows, paired_fields)
    print(f"wrote {args.output_summary}, {args.output_instances}, and {args.output_paired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
