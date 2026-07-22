#!/usr/bin/env python3
"""Summarize the human window audit within its localization strata."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path


EXCLUSIVE = {"MURAL_only", "BM25_only"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judgments", required=True, type=Path)
    parser.add_argument("--audit-instances", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-instances", required=True, type=Path)
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


def exact_two_sided(wins: int, losses: int) -> float:
    discordant = wins + losses
    if not discordant:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def localization_strata(rows: list[dict[str, str]]) -> dict[str, str]:
    hits: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        if row["approach"] in {"BM25-local", "MURAL"}:
            hits[row["instance_id"]][row["approach"]] = int(float(row["hit"]))
    output: dict[str, str] = {}
    for instance_id, values in hits.items():
        if set(values) != {"BM25-local", "MURAL"}:
            continue
        bm25, mural = values["BM25-local"], values["MURAL"]
        output[instance_id] = (
            "MURAL_only"
            if mural and not bm25
            else "BM25_only"
            if bm25 and not mural
            else "both"
            if mural and bm25
            else "neither"
        )
    return output


def main() -> int:
    args = parse_args()
    judgments = read_tsv(args.judgments)
    strata = localization_strata(read_tsv(args.audit_instances))
    if len(strata) != 80:
        raise ValueError(f"Expected 80 audited instances, found {len(strata)}")

    by_instance: dict[str, list[str]] = defaultdict(list)
    recorded_stratum: dict[str, str] = {}
    for row in judgments:
        instance_id = row["instance_id"]
        if strata.get(instance_id) != row["strict_stratum"]:
            raise ValueError(f"Stratum mismatch for {instance_id}")
        by_instance[instance_id].append(row["directional_alignment"])
        recorded_stratum[instance_id] = row["strict_stratum"]

    instance_rows: list[dict[str, object]] = []
    for instance_id in sorted(by_instance):
        values = by_instance[instance_id]
        decision = values[0] if len(set(values)) == 1 else "no_consensus"
        instance_rows.append(
            {
                "instance_id": instance_id,
                "stratum": recorded_stratum[instance_id],
                "judgments": len(values),
                "decision": decision,
            }
        )

    population = Counter(strata.values())
    summary_rows: list[dict[str, object]] = []
    for stratum in ("MURAL_only", "BM25_only", "both", "neither"):
        selected = [row for row in instance_rows if row["stratum"] == stratum]
        counts = Counter(str(row["decision"]) for row in selected)
        directional = counts["aligned"] + counts["opposed"]
        summary_rows.append(
            {
                "stratum": stratum,
                "audit_stratum_instances": population[stratum],
                "audited_instances": len(selected),
                "judgments": sum(int(row["judgments"]) for row in selected),
                "aligned": counts["aligned"],
                "opposed": counts["opposed"],
                "neutral": counts["neutral"] + counts["not_exclusive"],
                "no_consensus": counts["no_consensus"],
                "directional_alignment_rate": (
                    f"{counts['aligned'] / directional:.6f}" if directional else ""
                ),
                "exact_two_sided_p": (
                    f"{exact_two_sided(counts['aligned'], counts['opposed']):.12g}"
                    if directional
                    else ""
                ),
            }
        )

    exclusive = [row for row in instance_rows if row["stratum"] in EXCLUSIVE]
    counts = Counter(str(row["decision"]) for row in exclusive)
    directional = counts["aligned"] + counts["opposed"]
    summary_rows.append(
        {
            "stratum": "exclusive_combined",
            "audit_stratum_instances": population["MURAL_only"] + population["BM25_only"],
            "audited_instances": len(exclusive),
            "judgments": sum(int(row["judgments"]) for row in exclusive),
            "aligned": counts["aligned"],
            "opposed": counts["opposed"],
            "neutral": counts["neutral"],
            "no_consensus": counts["no_consensus"],
            "directional_alignment_rate": f"{counts['aligned'] / directional:.6f}",
            "exact_two_sided_p": f"{exact_two_sided(counts['aligned'], counts['opposed']):.12g}",
        }
    )
    write_tsv(args.output_summary, summary_rows)
    write_tsv(args.output_instances, instance_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
