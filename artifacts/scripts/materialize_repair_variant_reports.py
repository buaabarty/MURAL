#!/usr/bin/env python3
"""Map canonical SWE-bench reports back to each repair-context variant."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--variants", nargs="+", default=["issue", "bm25", "mural"])
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    args = parse_args()
    canonical_root = args.canonical_root.resolve()
    with (canonical_root / "prediction_mapping.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        mapping = list(csv.DictReader(handle, delimiter="\t"))
    if not mapping:
        raise ValueError("Empty prediction mapping")

    slot_numbers = sorted(
        {int(row["slot"]) for row in mapping if int(row["nonempty"])}
    )
    slot_predictions: dict[int, dict[str, dict[str, object]]] = {}
    slot_reports: dict[int, dict[str, dict[str, object]]] = {}
    for slot in slot_numbers:
        slot_dir = canonical_root / f"slot_{slot}"
        prediction_rows = read_jsonl(slot_dir / "predictions.jsonl")
        report_rows = read_jsonl(slot_dir / "official_results.jsonl")
        slot_predictions[slot] = {
            str(row["instance_id"]): row for row in prediction_rows
        }
        slot_reports[slot] = {str(row["instance_id"]): row for row in report_rows}
        if set(slot_predictions[slot]) != set(slot_reports[slot]):
            raise ValueError(f"slot_{slot}: official reports do not match predictions")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    for variant in args.variants:
        rows = []
        for mapping_row in mapping:
            if mapping_row["variant"] != variant or not int(mapping_row["nonempty"]):
                continue
            instance_id = mapping_row["instance_id"]
            slot = int(mapping_row["slot"])
            prediction = slot_predictions[slot].get(instance_id)
            report = slot_reports[slot].get(instance_id)
            if prediction is None or report is None:
                raise ValueError(f"Missing canonical outcome for {variant}/{instance_id}")
            patch = str(prediction.get("model_patch") or "").strip()
            digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()
            if digest != mapping_row["patch_sha256"]:
                raise ValueError(f"Patch hash mismatch for {variant}/{instance_id}")
            materialized = dict(report)
            materialized["evaluation_slot"] = slot
            materialized["patch_sha256"] = digest
            materialized["reused_identical_patch"] = int(
                mapping_row["reused_identical_patch"]
            )
            rows.append(materialized)

        variant_dir = output_root / variant
        variant_dir.mkdir(parents=True, exist_ok=True)
        (variant_dir / "official_results.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
