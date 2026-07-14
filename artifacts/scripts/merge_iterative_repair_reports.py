#!/usr/bin/env python3
"""Merge reused compact reports with newly evaluated fallback reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


VARIANTS = ("issue", "bm25", "mural")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def keyed(rows: list[dict], source: Path) -> dict[str, dict]:
    result = {row["instance_id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate instance IDs in {source}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions-root", type=Path, required=True)
    parser.add_argument("--compact-official-root", type=Path, required=True)
    parser.add_argument("--fallback-official-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)

    summaries = {}
    for variant in VARIANTS:
        all_path = args.predictions_root / variant / "predictions_all.jsonl"
        recovered_path = args.predictions_root / variant / "predictions_recovered_only.jsonl"
        compact_path = args.compact_official_root / variant / "official_results.jsonl"
        fallback_path = args.fallback_official_root / variant / "official_results.jsonl"

        predictions = keyed(read_jsonl(all_path), all_path)
        recovered_ids = set(keyed(read_jsonl(recovered_path), recovered_path))
        compact_reports = keyed(read_jsonl(compact_path), compact_path)
        fallback_reports = keyed(read_jsonl(fallback_path), fallback_path)
        if set(fallback_reports) != recovered_ids:
            raise ValueError(
                f"{variant}: fallback reports do not match recovered predictions; "
                f"missing={sorted(recovered_ids - set(fallback_reports))[:5]}, "
                f"extra={sorted(set(fallback_reports) - recovered_ids)[:5]}"
            )

        rows = []
        for instance_id, prediction in predictions.items():
            if not (prediction.get("model_patch") or "").strip():
                continue
            report = fallback_reports.get(instance_id) if instance_id in recovered_ids else compact_reports.get(instance_id)
            if report is None:
                raise ValueError(f"{variant}: missing official report for {instance_id}")
            rows.append(report)

        output_dir = args.output_root / variant
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / "official_results.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        summary = {
            "predictions": len(predictions),
            "patch_nonempty": len(rows),
            "patch_successfully_applied": sum(bool(row.get("patch_successfully_applied")) for row in rows),
            "resolved": sum(bool(row.get("resolved")) for row in rows),
            "reused_compact_reports": len(rows) - len(recovered_ids),
            "fallback_reports": len(recovered_ids),
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        summaries[variant] = summary

    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
