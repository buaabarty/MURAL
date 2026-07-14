#!/usr/bin/env python3
"""Build a complete repair-outcome ledger and paired summary statistics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np


VARIANTS = ("issue", "bm25", "mural")
CONTRASTS = (
    ("bm25_vs_issue", "issue", "bm25"),
    ("mural_vs_issue", "issue", "mural"),
    ("mural_vs_bm25", "bm25", "mural"),
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_timeout_outcomes(path: Path | None) -> dict[tuple[str, str], dict]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    outcomes = {}
    for row in rows:
        key = (row["variant"], row["instance_id"])
        if key in outcomes:
            raise ValueError(f"Duplicate timeout outcome for {key} in {path}")
        if row["variant"] not in VARIANTS:
            raise ValueError(f"Unknown timeout variant {row['variant']} in {path}")
        if int(row["resolved"]) != 0:
            raise ValueError("A timed-out evaluation must be recorded as unresolved")
        outcomes[key] = row
    return outcomes


def load_ids(path: Path) -> list[str]:
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line) if line.lstrip().startswith("{") else line.strip()
        ids.append(value["instance_id"] if isinstance(value, dict) else value)
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate IDs in {path}")
    return ids


def exact_mcnemar(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    lower = min(wins, losses)
    tail = sum(math.comb(discordant, j) for j in range(lower + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def paired_bootstrap_ci(baseline: np.ndarray, treatment: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(7)
    difference = treatment.astype(float) - baseline.astype(float)
    means = np.empty(10_000, dtype=float)
    for start in range(0, 10_000, 500):
        stop = min(start + 500, 10_000)
        indexes = rng.integers(0, len(difference), size=(stop - start, len(difference)))
        means[start:stop] = difference[indexes].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low * 100), float(high * 100)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--predictions-root", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--timeout-outcomes", type=Path)
    parser.add_argument("--output-outcomes", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    args = parser.parse_args()

    ids = load_ids(args.ids_file)
    id_set = set(ids)
    timeout_outcomes = read_timeout_outcomes(args.timeout_outcomes)
    unknown_timeout_ids = {instance_id for _, instance_id in timeout_outcomes} - id_set
    if unknown_timeout_ids:
        raise ValueError(f"Timeout outcomes contain unknown IDs: {sorted(unknown_timeout_ids)[:5]}")
    outcomes = {}
    outcome_rows = []
    summaries = {}

    for variant in VARIANTS:
        prediction_path = args.predictions_root / variant / "predictions_all.jsonl"
        official_path = args.official_root / variant / "official_results.jsonl"
        prediction_rows = read_jsonl(prediction_path)
        report_rows = read_jsonl(official_path)
        predictions = {row["instance_id"]: row for row in prediction_rows}
        reports = {row["instance_id"]: row for row in report_rows}
        if len(predictions) != len(prediction_rows) or len(reports) != len(report_rows):
            raise ValueError(f"{variant}: duplicate instance IDs")
        if set(predictions) != id_set:
            raise ValueError(f"{variant}: prediction IDs do not match the benchmark")
        for (timeout_variant, instance_id), timeout_row in timeout_outcomes.items():
            if timeout_variant != variant:
                continue
            report = reports.get(instance_id)
            if report is None or report.get("error") != "missing_report":
                raise ValueError(f"{variant}/{instance_id}: timeout override lacks a missing-report record")
            report = dict(report)
            report["patch_successfully_applied"] = bool(int(timeout_row["patch_successfully_applied"]))
            report["resolved"] = False
            report["error"] = f"test_timeout_{int(timeout_row['timeout_seconds'])}s"
            reports[instance_id] = report
        nonempty = {key for key, row in predictions.items() if (row.get("model_patch") or "").strip()}
        if set(reports) != nonempty:
            raise ValueError(f"{variant}: official reports do not match nonempty predictions")
        if any(row.get("resolved") and not row.get("patch_successfully_applied") for row in reports.values()):
            raise ValueError(f"{variant}: a resolved prediction was not applicable")

        resolved = np.array([bool(reports.get(key, {}).get("resolved")) for key in ids], dtype=bool)
        outcomes[variant] = resolved
        for instance_id in ids:
            report = reports.get(instance_id, {})
            outcome_rows.append(
                {
                    "instance_id": instance_id,
                    "variant": variant,
                    "nonempty": int(instance_id in nonempty),
                    "applied": int(bool(report.get("patch_successfully_applied"))),
                    "resolved": int(bool(report.get("resolved"))),
                }
            )
        summaries[variant] = {
            "nonempty": len(nonempty),
            "applicable": sum(bool(row.get("patch_successfully_applied")) for row in reports.values()),
            "resolved": int(resolved.sum()),
            "resolved_percent": float(resolved.mean() * 100),
        }

    summary_rows = []
    for variant in VARIANTS:
        row = summaries[variant]
        summary_rows.append(
            {
                "kind": "variant",
                "name": variant,
                **row,
                "resolved_percent": f"{row['resolved_percent']:.3f}",
                "baseline": "NA",
                "treatment": "NA",
                "delta_pp": "NA",
                "ci95_low": "NA",
                "ci95_high": "NA",
                "wins": "NA",
                "losses": "NA",
                "p_exact": "NA",
            }
        )
    for name, baseline_name, treatment_name in CONTRASTS:
        baseline = outcomes[baseline_name]
        treatment = outcomes[treatment_name]
        wins = int(np.sum(treatment & ~baseline))
        losses = int(np.sum(baseline & ~treatment))
        low, high = paired_bootstrap_ci(baseline, treatment)
        summary_rows.append(
            {
                "kind": "contrast",
                "name": name,
                "baseline": baseline_name,
                "treatment": treatment_name,
                "delta_pp": f"{(treatment.mean() - baseline.mean()) * 100:.3f}",
                "ci95_low": f"{low:.3f}",
                "ci95_high": f"{high:.3f}",
                "wins": wins,
                "losses": losses,
                "p_exact": f"{exact_mcnemar(wins, losses):.12g}",
            }
        )

    args.output_outcomes.parent.mkdir(parents=True, exist_ok=True)
    with args.output_outcomes.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(outcome_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(outcome_rows)

    fields = [
        "kind", "name", "nonempty", "applicable", "resolved", "resolved_percent",
        "baseline", "treatment", "delta_pp", "ci95_low", "ci95_high", "wins", "losses", "p_exact",
    ]
    with args.output_summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary_rows)
    print(json.dumps({"variants": summaries, "contrasts": summary_rows[3:]}, indent=2))


if __name__ == "__main__":
    main()
