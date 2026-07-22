#!/usr/bin/env python3
"""Run exact repository-cluster sign-flip tests for primary paired endpoints."""

from __future__ import annotations

import argparse
import csv
import itertools
from collections import defaultdict
from pathlib import Path
from statistics import mean


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--localization-instances", required=True, type=Path)
    parser.add_argument("--line-instances", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-repositories", required=True, type=Path)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
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


def repository(instance_id: str) -> str:
    return instance_id.rsplit("-", 1)[0]


def exact_sign_flip(cluster_sums: list[float]) -> float:
    observed = abs(sum(cluster_sums))
    tolerance = 1e-12
    extreme = 0
    total = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(cluster_sums)):
        total += 1
        statistic = abs(sum(sign * value for sign, value in zip(signs, cluster_sums)))
        extreme += statistic + tolerance >= observed
    return extreme / total


def localization_pairs(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    by_instance: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        if row["approach"] in {"BM25_projection", "MURAL"}:
            by_instance[row["instance_id"]][row["approach"]] = row
    output: list[dict[str, object]] = []
    for instance_id, values in sorted(by_instance.items()):
        if set(values) != {"BM25_projection", "MURAL"}:
            continue
        for endpoint, field in (
            ("Hit@20", "hit"),
            ("TargetCov@20", "target_coverage"),
            ("CompleteTarget@20", "complete"),
        ):
            output.append(
                {
                    "endpoint": endpoint,
                    "instance_id": instance_id,
                    "repository": values["MURAL"]["repository"],
                    "baseline": float(values["BM25_projection"][field]),
                    "treatment": float(values["MURAL"][field]),
                }
            )
    return output


def line_pairs(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    by_instance: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        if row["source"] in {"BM25", "MURAL"} and int(row["token_budget"]) == 4000:
            by_instance[row["instance_id"]][row["source"]] = row
    output: list[dict[str, object]] = []
    for instance_id, values in sorted(by_instance.items()):
        if set(values) != {"BM25", "MURAL"}:
            continue
        output.append(
            {
                "endpoint": "LineRecall@4000",
                "instance_id": instance_id,
                "repository": repository(instance_id),
                "baseline": float(values["BM25"]["changed_lines_covered"]),
                "treatment": float(values["MURAL"]["changed_lines_covered"]),
                "denominator": float(values["BM25"]["changed_lines_total"]),
            }
        )
        output.append(
            {
                "endpoint": "CompleteLine@4000",
                "instance_id": instance_id,
                "repository": repository(instance_id),
                "baseline": float(values["BM25"]["complete_changed_lines"]),
                "treatment": float(values["MURAL"]["complete_changed_lines"]),
            }
        )
    return output


def main() -> int:
    args = parse_args()
    pairs = localization_pairs(read_tsv(args.localization_instances))
    pairs.extend(line_pairs(read_tsv(args.line_instances)))
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in pairs:
        grouped[str(row["endpoint"])].append(row)

    summary_rows: list[dict[str, object]] = []
    repository_rows: list[dict[str, object]] = []
    for endpoint, endpoint_rows in grouped.items():
        clusters: dict[str, list[float]] = defaultdict(list)
        for row in endpoint_rows:
            clusters[str(row["repository"])].append(
                float(row["treatment"]) - float(row["baseline"])
            )
        cluster_sums = [sum(clusters[name]) for name in sorted(clusters)]
        deltas = [value for values in clusters.values() for value in values]
        if endpoint == "LineRecall@4000":
            denominator = sum(float(row["denominator"]) for row in endpoint_rows)
            baseline_value = sum(float(row["baseline"]) for row in endpoint_rows) / denominator
            treatment_value = sum(float(row["treatment"]) for row in endpoint_rows) / denominator
            delta_value = treatment_value - baseline_value
        else:
            baseline_value = mean(float(row["baseline"]) for row in endpoint_rows)
            treatment_value = mean(float(row["treatment"]) for row in endpoint_rows)
            delta_value = mean(deltas)
        summary_rows.append(
            {
                "endpoint": endpoint,
                "instances": len(deltas),
                "repositories": len(clusters),
                "baseline": f"{baseline_value:.6f}",
                "treatment": f"{treatment_value:.6f}",
                "delta": f"{delta_value:.6f}",
                "repositories_positive": sum(sum(values) > 0 for values in clusters.values()),
                "repositories_zero": sum(sum(values) == 0 for values in clusters.values()),
                "repositories_negative": sum(sum(values) < 0 for values in clusters.values()),
                "exact_cluster_signflip_p": f"{exact_sign_flip(cluster_sums):.12g}",
            }
        )
        for name in sorted(clusters):
            selected = [row for row in endpoint_rows if row["repository"] == name]
            if endpoint == "LineRecall@4000":
                repository_denominator = sum(float(row["denominator"]) for row in selected)
                repository_delta = sum(clusters[name]) / repository_denominator
            else:
                repository_delta = mean(clusters[name])
            repository_rows.append(
                {
                    "endpoint": endpoint,
                    "repository": name,
                    "instances": len(clusters[name]),
                    "delta": f"{repository_delta:.6f}",
                    "sum_paired_difference": f"{sum(clusters[name]):.6f}",
                }
            )
    write_tsv(args.output_summary, summary_rows)
    write_tsv(args.output_repositories, repository_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
