#!/usr/bin/env python3
"""Summarize structural-run and batch timing records used by the supplement."""

from __future__ import annotations

import argparse
import ast
import csv
import glob
import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


START_RE = re.compile(r"Starting execution time: (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")
DURATION_RE = re.compile(r"Total execution duration: (\d+):(\d+):(\d+(?:\.\d+)?)")


def parse_duration(match: re.Match[str]) -> float:
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_structural_records(pattern: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_path in sorted(glob.glob(pattern)):
        path = Path(raw_path)
        with path.open(errors="ignore") as handle:
            for line in handle:
                start_match = START_RE.search(line)
                if start_match:
                    current = {
                        "start": datetime.strptime(
                            start_match.group(1), "%Y-%m-%d %H:%M:%S"
                        ).timestamp(),
                        "instance_id": None,
                        "log": str(path),
                    }
                    continue
                if current is None:
                    continue
                if line.startswith("Configuration: "):
                    payload = ast.literal_eval(line.split("Configuration: ", 1)[1])
                    current["instance_id"] = payload.get("instance_id")
                    continue
                duration_match = DURATION_RE.search(line)
                if duration_match and current.get("instance_id"):
                    current["duration_s"] = parse_duration(duration_match)
                    current["finish"] = current["start"] + current["duration_s"]
                    records.append(current)
                    current = None
    return records


def select_output_records(records: list[dict[str, Any]], run_dir: Path) -> list[dict[str, Any]]:
    by_instance: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_instance.setdefault(record["instance_id"], []).append(record)

    selected: list[dict[str, Any]] = []
    for output_path in sorted(run_dir.glob("*.json")):
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        saved_at = (payload.get("run_meta") or {}).get("saved_at")
        if not saved_at:
            raise ValueError(f"Missing saved_at in {output_path}")
        saved_ts = datetime.fromisoformat(saved_at).timestamp()
        candidates = by_instance.get(output_path.stem) or []
        if not candidates:
            raise ValueError(f"No completed timing record for {output_path.stem}")
        selected.append(min(candidates, key=lambda row: abs(saved_ts - row["finish"])))
    return selected


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * quantile))]


def parse_gnu_time(path: Path) -> tuple[float, float]:
    text = path.read_text(encoding="utf-8")
    elapsed_match = re.search(
        r"Elapsed \(wall clock\) time .*: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)",
        text,
    )
    rss_match = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    if not elapsed_match or not rss_match:
        raise ValueError(f"Cannot parse GNU time output: {path}")
    hours, minutes, seconds = elapsed_match.groups()
    elapsed_s = int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)
    return elapsed_s, int(rss_match.group(1)) / 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-glob", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--bm25-time", required=True, type=Path)
    parser.add_argument("--rrf-time", required=True, type=Path)
    parser.add_argument("--instances", type=int, default=500)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = select_output_records(
        parse_structural_records(args.logs_glob), args.run_dir
    )
    durations = [row["duration_s"] for row in selected]
    bm25_s, bm25_rss = parse_gnu_time(args.bm25_time)
    rrf_s, rrf_rss = parse_gnu_time(args.rrf_time)
    rows = [
        {
            "stage": "structural_adapter",
            "scope": "per_instance",
            "N": len(durations),
            "total_s": sum(durations),
            "mean_s": statistics.mean(durations),
            "median_s": statistics.median(durations),
            "p95_s": percentile(durations, 0.95),
            "max_s": max(durations),
            "max_rss_mib": "NA",
        },
        {
            "stage": "bm25_file_local",
            "scope": "batch",
            "N": args.instances,
            "total_s": bm25_s,
            "mean_s": bm25_s / args.instances,
            "median_s": "NA",
            "p95_s": "NA",
            "max_s": "NA",
            "max_rss_mib": bm25_rss,
        },
        {
            "stage": "equal_weight_rrf",
            "scope": "batch",
            "N": args.instances,
            "total_s": rrf_s,
            "mean_s": rrf_s / args.instances,
            "median_s": "NA",
            "p95_s": "NA",
            "max_s": "NA",
            "max_rss_mib": rrf_rss,
        },
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, delimiter="\t", fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
