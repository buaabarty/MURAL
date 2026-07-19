#!/usr/bin/env python3
"""Normalize per-instance SWE-bench reports into one audited JSONL ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--logs-root", type=Path, default=Path("logs/run_evaluation"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Record missing reports explicitly instead of failing the audit.",
    )
    parser.add_argument(
        "--normalize-terminal-errors",
        action="store_true",
        help=(
            "Record harness-confirmed patch-application failures and test timeouts "
            "as unresolved; all infrastructure failures still fail closed."
        ),
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def count_tests(status: object, outcome: str) -> int:
    if not isinstance(status, dict):
        return 0
    values = status.get(outcome, [])
    return len(values) if isinstance(values, list) else 0


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def terminal_error_row(
    instance_id: str, patch: str, log_path: Path
) -> dict[str, object] | None:
    if not log_path.exists():
        return None
    log = log_path.read_text(encoding="utf-8", errors="replace")
    patch_apply_failed = ">>>>> Patch Apply Failed:" in log
    test_timed_out = "Test timed out after " in log and " seconds." in log
    if patch_apply_failed and test_timed_out:
        raise ValueError(f"Ambiguous terminal evaluation log: {log_path}")
    if patch_apply_failed:
        error = "patch_apply_failed"
        applied = False
    elif test_timed_out:
        error = "test_timeout"
        applied = True
    else:
        return None
    return {
        "instance_id": instance_id,
        "patch_chars": len(patch),
        "patch_sha256": sha256(patch),
        "patch_successfully_applied": applied,
        "resolved": False,
        "fail_to_pass_success": 0,
        "fail_to_pass_failure": 0,
        "pass_to_pass_success": 0,
        "pass_to_pass_failure": 0,
        "error": error,
    }


def main() -> int:
    args = parse_args()
    predictions = read_jsonl(args.predictions.resolve())
    if not predictions:
        raise ValueError(f"No predictions in {args.predictions}")

    ids = [str(row.get("instance_id") or "") for row in predictions]
    if any(not instance_id for instance_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("Prediction instance IDs must be nonempty and unique")
    models = {str(row.get("model_name_or_path") or "") for row in predictions}
    if len(models) != 1 or not next(iter(models)):
        raise ValueError("Predictions must use one nonempty model_name_or_path")
    model_dir = next(iter(models)).replace("/", "__")

    run_root = args.logs_root.resolve() / args.run_id / model_dir
    rows: list[dict[str, object]] = []
    missing: list[str] = []
    normalized_terminal: list[str] = []
    for prediction in predictions:
        patch = str(prediction.get("model_patch") or "")
        if not patch.strip():
            continue
        instance_id = str(prediction["instance_id"])
        instance_root = run_root / instance_id
        report_path = instance_root / "report.json"
        if not report_path.exists():
            terminal = (
                terminal_error_row(instance_id, patch, instance_root / "run_instance.log")
                if args.normalize_terminal_errors
                else None
            )
            if terminal is not None:
                rows.append(terminal)
                normalized_terminal.append(str(terminal["error"]))
                continue
            missing.append(instance_id)
            if args.allow_missing:
                rows.append(
                    {
                        "instance_id": instance_id,
                        "patch_chars": len(patch),
                        "patch_sha256": sha256(patch),
                        "patch_successfully_applied": False,
                        "resolved": False,
                        "fail_to_pass_success": 0,
                        "fail_to_pass_failure": 0,
                        "pass_to_pass_success": 0,
                        "pass_to_pass_failure": 0,
                        "error": "missing_report",
                    }
                )
            continue

        document = json.loads(report_path.read_text(encoding="utf-8"))
        if set(document) != {instance_id} or not isinstance(document[instance_id], dict):
            raise ValueError(f"Malformed report: {report_path}")
        report = document[instance_id]
        tests = report.get("tests_status", {})
        fail_to_pass = tests.get("FAIL_TO_PASS", {}) if isinstance(tests, dict) else {}
        pass_to_pass = tests.get("PASS_TO_PASS", {}) if isinstance(tests, dict) else {}
        applied = bool(report.get("patch_successfully_applied"))
        resolved = bool(report.get("resolved"))
        if resolved and not applied:
            raise ValueError(f"Resolved patch was not applicable: {report_path}")
        rows.append(
            {
                "instance_id": instance_id,
                "patch_chars": len(patch),
                "patch_sha256": sha256(patch),
                "patch_successfully_applied": applied,
                "resolved": resolved,
                "fail_to_pass_success": count_tests(fail_to_pass, "success"),
                "fail_to_pass_failure": count_tests(fail_to_pass, "failure"),
                "pass_to_pass_success": count_tests(pass_to_pass, "success"),
                "pass_to_pass_failure": count_tests(pass_to_pass, "failure"),
                "error": "",
            }
        )

    if missing and not args.allow_missing:
        preview = ", ".join(missing[:5])
        raise FileNotFoundError(
            f"Missing {len(missing)} reports below {run_root}: {preview}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary = {
        "predictions": len(predictions),
        "nonempty": len(rows),
        "applicable": sum(bool(row["patch_successfully_applied"]) for row in rows),
        "resolved": sum(bool(row["resolved"]) for row in rows),
        "missing": len(missing),
        "normalized_terminal": len(normalized_terminal),
        "patch_apply_failed": normalized_terminal.count("patch_apply_failed"),
        "test_timeout": normalized_terminal.count("test_timeout"),
        "output": str(args.output.resolve()),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
