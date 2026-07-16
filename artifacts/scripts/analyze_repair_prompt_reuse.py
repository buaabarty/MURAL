#!/usr/bin/env python3
"""Compare rendered repair prompts for exact output-reuse eligibility."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--treatment", required=True)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-changed", required=True, type=Path)
    return parser.parse_args()


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    with args.audit.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    by_variant: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        by_variant.setdefault(row["variant"], {})[row["instance_id"]] = row
    baseline = by_variant.get(args.baseline, {})
    treatment = by_variant.get(args.treatment, {})
    if set(baseline) != set(treatment) or not baseline:
        raise ValueError("Baseline and treatment must contain the same nonempty id set")

    changed: list[dict[str, object]] = []
    identical_context = 0
    identical_prompt = 0
    for instance_id in sorted(baseline):
        old = baseline[instance_id]
        new = treatment[instance_id]
        same_context = old["context_sha256"] == new["context_sha256"]
        same_prompt = old["prompt_sha256"] == new["prompt_sha256"]
        identical_context += int(same_context)
        identical_prompt += int(same_prompt)
        if same_prompt:
            continue
        changed.append(
            {
                "instance_id": instance_id,
                "baseline_candidates": old["candidate_entities"],
                "treatment_candidates": new["candidate_entities"],
                "baseline_rendered": old["rendered_entities"],
                "treatment_rendered": new["rendered_entities"],
                "baseline_prompt_tokens": old["prompt_tokens"],
                "treatment_prompt_tokens": new["prompt_tokens"],
                "context_identical": int(same_context),
                "baseline_prompt_sha256": old["prompt_sha256"],
                "treatment_prompt_sha256": new["prompt_sha256"],
            }
        )

    total = len(baseline)
    summary = [
        {
            "baseline": args.baseline,
            "treatment": args.treatment,
            "N": total,
            "identical_context": identical_context,
            "changed_context": total - identical_context,
            "identical_prompt": identical_prompt,
            "changed_prompt": total - identical_prompt,
            "prompt_reuse_rate": f"{identical_prompt / total:.6f}",
        }
    ]
    write_tsv(args.output_summary, summary, list(summary[0]))
    changed_fields = [
        "instance_id",
        "baseline_candidates",
        "treatment_candidates",
        "baseline_rendered",
        "treatment_rendered",
        "baseline_prompt_tokens",
        "treatment_prompt_tokens",
        "context_identical",
        "baseline_prompt_sha256",
        "treatment_prompt_sha256",
    ]
    write_tsv(args.output_changed, changed, changed_fields)
    print(f"wrote {args.output_summary}")
    print(f"wrote {args.output_changed} ({len(changed)} changed prompts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
