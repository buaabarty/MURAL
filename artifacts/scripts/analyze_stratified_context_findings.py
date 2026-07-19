#!/usr/bin/env python3
"""Derive article-facing mechanism and target-complexity statistics."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Callable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--localization-instances", type=Path, required=True)
    parser.add_argument("--human-judgments", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-mechanisms", type=Path, required=True)
    parser.add_argument("--output-multiplicity", type=Path, required=True)
    parser.add_argument("--output-repositories", type=Path, required=True)
    parser.add_argument("--output-human", type=Path, required=True)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def clustered_ci(
    rows: list[dict[str, object]],
    difference: Callable[[dict[str, object]], float],
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    clusters: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        clusters[str(row["repository"])].append(row)
    names = sorted(clusters)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(resamples):
        sampled: list[dict[str, object]] = []
        for _ in names:
            sampled.extend(clusters[rng.choice(names)])
        draws.append(mean(difference(row) for row in sampled))
    return percentile(draws, 0.025), percentile(draws, 0.975)


def exact_two_sided(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, j) for j in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def f6(value: float) -> str:
    return f"{value:.6f}"


def fp(value: float) -> str:
    return f"{value:.12g}"


def build_joined(
    targets: dict[str, dict[str, object]], localization_rows: list[dict[str, str]]
) -> list[dict[str, object]]:
    by_instance: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in localization_rows:
        by_instance[row["instance_id"]][row["approach"]] = row

    required = {"BM25_projection", "MURAL"}
    joined: list[dict[str, object]] = []
    for instance_id, reference in sorted(targets.items()):
        missing = required - set(by_instance[instance_id])
        if missing:
            raise ValueError(f"{instance_id}: missing localization rows {sorted(missing)}")
        baseline = by_instance[instance_id]["BM25_projection"]
        treatment = by_instance[instance_id]["MURAL"]
        item: dict[str, object] = {
            "instance_id": instance_id,
            "repository": baseline["repository"],
            "target_count": int(reference["target_count"]),
            "file_target_count": int(reference["file_target_count"]),
            "patch_file_count": len(reference["patch_files"]),
        }
        for label, row in (("bm25", baseline), ("mural", treatment)):
            for metric in (
                "file_hit",
                "target_coverage",
                "hit",
                "mrr",
                "complete",
                "first_rank",
            ):
                item[f"{label}_{metric}"] = float(row[metric])
        joined.append(item)
    return joined


def mechanism_rows(
    joined: list[dict[str, object]], resamples: int, seed: int
) -> list[dict[str, object]]:
    common_file = [
        row
        for row in joined
        if row["patch_file_count"] == 1
        and row["file_target_count"] == 0
        and row["bm25_file_hit"] == 1
        and row["mural_file_hit"] == 1
    ]
    output: list[dict[str, object]] = []
    for metric in ("target_coverage", "hit", "complete"):
        baseline_key = f"bm25_{metric}"
        treatment_key = f"mural_{metric}"
        low, high = clustered_ci(
            common_file,
            lambda row, a=baseline_key, b=treatment_key: float(row[b]) - float(row[a]),
            resamples,
            seed,
        )
        wins = sum(float(row[treatment_key]) > float(row[baseline_key]) for row in common_file)
        losses = sum(float(row[treatment_key]) < float(row[baseline_key]) for row in common_file)
        binary = metric in {"hit", "complete"}
        output.append(
            {
                "analysis": "opportunity_matched",
                "stratum": "single_file_entity_only_both_file_hit",
                "metric": metric,
                "N": len(common_file),
                "baseline": f6(100 * mean(float(row[baseline_key]) for row in common_file)),
                "treatment": f6(100 * mean(float(row[treatment_key]) for row in common_file)),
                "delta": f6(
                    100
                    * mean(
                        float(row[treatment_key]) - float(row[baseline_key])
                        for row in common_file
                    )
                ),
                "clustered_ci_low": f6(100 * low),
                "clustered_ci_high": f6(100 * high),
                "wins": wins if binary else "",
                "ties": len(common_file) - wins - losses if binary else "",
                "losses": losses if binary else "",
                "exact_p": fp(exact_two_sided(wins, losses)) if binary else "",
            }
        )

    shared_hits = [row for row in joined if row["bm25_hit"] == 1 and row["mural_hit"] == 1]
    earlier = sum(float(row["mural_first_rank"]) < float(row["bm25_first_rank"]) for row in shared_hits)
    later = sum(float(row["mural_first_rank"]) > float(row["bm25_first_rank"]) for row in shared_hits)
    same = len(shared_hits) - earlier - later
    low, high = clustered_ci(
        shared_hits,
        lambda row: float(row["mural_first_rank"]) - float(row["bm25_first_rank"]),
        resamples,
        seed,
    )
    output.append(
        {
            "analysis": "shared_hit_rank_shift",
            "stratum": "both_hit",
            "metric": "first_rank",
            "N": len(shared_hits),
            "baseline": f6(mean(float(row["bm25_first_rank"]) for row in shared_hits)),
            "treatment": f6(mean(float(row["mural_first_rank"]) for row in shared_hits)),
            "delta": f6(
                mean(
                    float(row["mural_first_rank"]) - float(row["bm25_first_rank"])
                    for row in shared_hits
                )
            ),
            "clustered_ci_low": f6(low),
            "clustered_ci_high": f6(high),
            "wins": earlier,
            "ties": same,
            "losses": later,
            "exact_p": fp(exact_two_sided(earlier, later)),
        }
    )
    return output


def multiplicity_rows(joined: list[dict[str, object]]) -> list[dict[str, object]]:
    groups = (
        ("1", lambda count: count == 1),
        ("2", lambda count: count == 2),
        ("3+", lambda count: count >= 3),
        ("2+", lambda count: count >= 2),
    )
    output: list[dict[str, object]] = []
    for name, predicate in groups:
        selected = [row for row in joined if predicate(int(row["target_count"]))]
        hit_count = sum(int(row["mural_hit"]) for row in selected)
        complete_count = sum(int(row["mural_complete"]) for row in selected)
        output.append(
            {
                "target_count": name,
                "N": len(selected),
                "target_coverage": f6(100 * mean(float(row["mural_target_coverage"]) for row in selected)),
                "hit": f6(100 * hit_count / len(selected)),
                "complete": f6(100 * complete_count / len(selected)),
                "partial_hits": hit_count - complete_count,
                "complete_given_hit": f6(100 * complete_count / hit_count),
            }
        )
    return output


def repository_rows(joined: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    repositories = sorted({str(row["repository"]) for row in joined})

    def summarize(analysis: str, repository: str, selected: list[dict[str, object]]) -> None:
        wins = sum(float(row["mural_hit"]) > float(row["bm25_hit"]) for row in selected)
        losses = sum(float(row["mural_hit"]) < float(row["bm25_hit"]) for row in selected)
        output.append(
            {
                "analysis": analysis,
                "repository": repository,
                "N": len(selected),
                "bm25_hit": f6(100 * mean(float(row["bm25_hit"]) for row in selected)),
                "mural_hit": f6(100 * mean(float(row["mural_hit"]) for row in selected)),
                "delta_hit": f6(
                    100 * mean(float(row["mural_hit"]) - float(row["bm25_hit"]) for row in selected)
                ),
                "bm25_complete": f6(100 * mean(float(row["bm25_complete"]) for row in selected)),
                "mural_complete": f6(100 * mean(float(row["mural_complete"]) for row in selected)),
                "delta_complete": f6(
                    100
                    * mean(
                        float(row["mural_complete"]) - float(row["bm25_complete"])
                        for row in selected
                    )
                ),
                "wins": wins,
                "losses": losses,
            }
        )

    for repository in repositories:
        summarize(
            "repository",
            repository,
            [row for row in joined if row["repository"] == repository],
        )
    for repository in repositories:
        summarize(
            "leave_one_repository_out",
            repository,
            [row for row in joined if row["repository"] != repository],
        )
    return output


def human_rows(judgments: list[dict[str, str]]) -> list[dict[str, object]]:
    by_instance: dict[str, list[str]] = defaultdict(list)
    for row in judgments:
        if row["strict_stratum"] in {"MURAL_only", "BM25_only"}:
            by_instance[row["instance_id"]].append(row["directional_alignment"])

    decisions: Counter[str] = Counter()
    for values in by_instance.values():
        decisions[values[0] if len(set(values)) == 1 else "no_consensus"] += 1

    output: list[dict[str, object]] = []
    total = len(by_instance)
    for decision in ("aligned", "neutral", "opposed", "no_consensus"):
        count = decisions[decision]
        output.append(
            {
                "scope": "unique_exclusive_hit_instances",
                "decision": decision,
                "count": count,
                "denominator": total,
                "share": f6(count / total),
                "exact_p": "",
            }
        )
    aligned = decisions["aligned"]
    opposed = decisions["opposed"]
    directional = aligned + opposed
    output.append(
        {
            "scope": "directional_unique_instances",
            "decision": "aligned",
            "count": aligned,
            "denominator": directional,
            "share": f6(aligned / directional),
            "exact_p": fp(exact_two_sided(aligned, opposed)),
        }
    )
    return output


def main() -> int:
    args = parse_args()
    target_data = json.loads(args.targets.read_text(encoding="utf-8"))["items"]
    joined = build_joined(target_data, read_tsv(args.localization_instances))
    if len(joined) != 500:
        raise ValueError(f"Expected 500 instances, found {len(joined)}")

    write_tsv(
        args.output_mechanisms,
        mechanism_rows(joined, args.bootstrap, args.seed),
        [
            "analysis",
            "stratum",
            "metric",
            "N",
            "baseline",
            "treatment",
            "delta",
            "clustered_ci_low",
            "clustered_ci_high",
            "wins",
            "ties",
            "losses",
            "exact_p",
        ],
    )
    write_tsv(
        args.output_multiplicity,
        multiplicity_rows(joined),
        [
            "target_count",
            "N",
            "target_coverage",
            "hit",
            "complete",
            "partial_hits",
            "complete_given_hit",
        ],
    )
    write_tsv(
        args.output_repositories,
        repository_rows(joined),
        [
            "analysis",
            "repository",
            "N",
            "bm25_hit",
            "mural_hit",
            "delta_hit",
            "bm25_complete",
            "mural_complete",
            "delta_complete",
            "wins",
            "losses",
        ],
    )
    write_tsv(
        args.output_human,
        human_rows(read_tsv(args.human_judgments)),
        ["scope", "decision", "count", "denominator", "share", "exact_p"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
