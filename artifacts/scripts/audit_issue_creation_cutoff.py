#!/usr/bin/env python3
"""Verify that archived structural runs use the target issue creation cutoff."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _timestamp(value: str) -> float:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc).timestamp()


def _load_dataset_cutoffs(path: Path) -> dict[str, float]:
    if path.suffix == ".arrow":
        import pyarrow.ipc as ipc

        table = ipc.open_stream(path).read_all()
        rows = table.select(["instance_id", "created_at"]).to_pylist()
    else:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {row["instance_id"]: _timestamp(row["created_at"]) for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare each archived structural cutoff with target issue created_at."
    )
    parser.add_argument("dataset", help="SWE-bench Arrow stream or JSONL file.")
    parser.add_argument("run_dir", help="Directory containing per-instance run JSON files.")
    parser.add_argument("--output-json", help="Optional path for the full audit report.")
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when a cutoff is missing or mismatched.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    run_dir = Path(args.run_dir)
    expected = _load_dataset_cutoffs(dataset_path)
    run_files = sorted(run_dir.glob("*.json"))
    missing_cutoffs = []
    mismatches = []
    unexpected_runs = []
    observed_ids = set()

    for path in run_files:
        instance_id = path.stem
        observed_ids.add(instance_id)
        obj = json.loads(path.read_text())
        run_cutoff = ((obj.get("run_meta") or {}).get("active_root") or {}).get(
            "created_at"
        )
        expected_cutoff = expected.get(instance_id)
        if expected_cutoff is None:
            unexpected_runs.append(instance_id)
        elif run_cutoff is None:
            missing_cutoffs.append(instance_id)
        elif float(run_cutoff) != expected_cutoff:
            mismatches.append(
                {
                    "instance_id": instance_id,
                    "recorded_cutoff": run_cutoff,
                    "target_issue_created_at": expected_cutoff,
                }
            )

    missing_runs = sorted(set(expected) - observed_ids)
    matching_cutoffs = (
        len(run_files)
        - len(unexpected_runs)
        - len(missing_cutoffs)
        - len(mismatches)
    )
    summary = {
        "dataset_instances": len(expected),
        "archived_runs": len(run_files),
        "matching_target_issue_cutoffs": matching_cutoffs,
        "missing_runs": len(missing_runs),
        "unexpected_runs": len(unexpected_runs),
        "missing_cutoffs": len(missing_cutoffs),
        "mismatched_cutoffs": len(mismatches),
    }
    report = {
        "audit": "target_issue_creation_cutoff",
        "dataset": str(dataset_path),
        "run_dir": str(run_dir),
        "comparison": "run_meta.active_root.created_at == epoch(dataset.created_at)",
        "summary": summary,
        "missing_run_instances": missing_runs,
        "unexpected_run_instances": unexpected_runs,
        "missing_cutoff_instances": missing_cutoffs,
        "cutoff_mismatches": mismatches,
    }

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n")

    has_issue = any((missing_runs, unexpected_runs, missing_cutoffs, mismatches))
    return 1 if args.fail_on_mismatch and has_issue else 0


if __name__ == "__main__":
    raise SystemExit(main())
