#!/usr/bin/env python3
"""Merge selective SWE-bench reevaluations with frozen official outcomes."""

from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-official", action="append", required=True, metavar="LABEL=JSONL")
    parser.add_argument("--predictions", action="append", required=True, metavar="LABEL=JSONL")
    parser.add_argument("--reevaluate-ids", action="append", required=True, metavar="LABEL=FILE")
    parser.add_argument("--logs", action="append", metavar="LABEL=DIR")
    parser.add_argument(
        "--normalized",
        action="append",
        metavar="LABEL=JSONL",
        help="Normalized official updates produced by collect_swebench_reports.py.",
    )
    parser.add_argument("--output-root", required=True, type=Path)
    return parser.parse_args()


def specs(values: list[str], flag: str) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{flag} expects LABEL=PATH, received {value!r}")
        label, raw_path = value.split("=", 1)
        label = label.strip()
        if not label or label in parsed:
            raise ValueError(f"Invalid or duplicate label for {flag}: {label!r}")
        parsed[label] = Path(raw_path).resolve()
    return parsed


def jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def by_id(rows: list[dict[str, object]], path: Path) -> dict[str, dict[str, object]]:
    indexed = {str(row.get("instance_id") or ""): row for row in rows}
    if "" in indexed or len(indexed) != len(rows):
        raise ValueError(f"Missing or duplicate instance_id in {path}")
    return indexed


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def count_status(report: dict[str, object], group: str, status: str) -> int:
    tests_status = report.get("tests_status") or {}
    group_status = tests_status.get(group) or {}
    values = group_status.get(status) or []
    return len(values)


def materialize_report(instance_id: str, patch: str, report_path: Path) -> dict[str, object]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if set(payload) != {instance_id}:
        raise ValueError(f"Unexpected report keys in {report_path}: {sorted(payload)}")
    report = payload[instance_id]
    applied = bool(report.get("patch_successfully_applied"))
    resolved = bool(report.get("resolved"))
    if resolved and not applied:
        raise ValueError(f"Resolved patch was not applied: {instance_id}")
    return {
        "error": "" if applied else "patch_apply_failed",
        "evaluation_slot": -1,
        "fail_to_pass_failure": count_status(report, "FAIL_TO_PASS", "failure"),
        "fail_to_pass_success": count_status(report, "FAIL_TO_PASS", "success"),
        "instance_id": instance_id,
        "pass_to_pass_failure": count_status(report, "PASS_TO_PASS", "failure"),
        "pass_to_pass_success": count_status(report, "PASS_TO_PASS", "success"),
        "patch_chars": len(patch),
        "patch_sha256": sha256(patch),
        "patch_successfully_applied": applied,
        "resolved": resolved,
        "reused_identical_patch": 0,
    }


def main() -> int:
    args = parse_args()
    old_specs = specs(args.old_official, "--old-official")
    prediction_specs = specs(args.predictions, "--predictions")
    id_specs = specs(args.reevaluate_ids, "--reevaluate-ids")
    log_specs = specs(args.logs, "--logs") if args.logs else {}
    normalized_specs = specs(args.normalized, "--normalized") if args.normalized else {}
    labels = set(old_specs)
    if labels != set(prediction_specs) or labels != set(id_specs):
        raise ValueError("Labels must match across old outcomes, predictions, and reevaluation IDs")
    if bool(log_specs) == bool(normalized_specs):
        raise ValueError("Provide exactly one of --logs or --normalized")
    selected_specs = log_specs or normalized_specs
    if labels != set(selected_specs):
        raise ValueError("Variant labels must match the selected update source")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    for label in sorted(labels):
        old = by_id(jsonl(old_specs[label]), old_specs[label])
        predictions = by_id(jsonl(prediction_specs[label]), prediction_specs[label])
        reevaluate = {
            line.strip()
            for line in id_specs[label].read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        normalized = (
            by_id(jsonl(normalized_specs[label]), normalized_specs[label])
            if normalized_specs
            else {}
        )
        if not reevaluate <= set(predictions):
            raise ValueError(f"Unknown reevaluation ids for {label}")

        merged: list[dict[str, object]] = []
        reused = 0
        refreshed = 0
        for instance_id, prediction in predictions.items():
            patch = str(prediction.get("model_patch") or "")
            if not patch.strip():
                continue
            digest = sha256(patch)
            if instance_id in reevaluate:
                if normalized_specs:
                    row = normalized.get(instance_id)
                    if row is None:
                        raise ValueError(f"Missing normalized update for {label}/{instance_id}")
                    if row.get("patch_sha256") != digest:
                        raise ValueError(f"Normalized update hash mismatch for {label}/{instance_id}")
                    retained = dict(row)
                    retained.setdefault("evaluation_slot", -1)
                    retained["reused_identical_patch"] = 0
                    merged.append(retained)
                else:
                    report_path = log_specs[label] / instance_id / "report.json"
                    if not report_path.exists():
                        raise FileNotFoundError(report_path)
                    merged.append(materialize_report(instance_id, patch, report_path))
                refreshed += 1
            else:
                row = old.get(instance_id)
                if row is None or row.get("patch_sha256") != digest:
                    raise ValueError(f"Frozen outcome hash mismatch for {label}/{instance_id}")
                retained = dict(row)
                retained["reused_identical_patch"] = 1
                merged.append(retained)
                reused += 1

        variant_dir = output_root / label
        variant_dir.mkdir(parents=True, exist_ok=True)
        (variant_dir / "official_results.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in merged),
            encoding="utf-8",
        )
        print(f"{label}: {len(merged)} nonempty outcomes, {reused} reused, {refreshed} reevaluated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
