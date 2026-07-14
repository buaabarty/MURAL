#!/usr/bin/env python3
"""Assemble compact-first repair predictions with deterministic fallbacks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


VARIANTS = ("issue", "bm25", "mural")


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


def load_patch(path: Path) -> str:
    if not path.exists():
        return ""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 1:
        raise ValueError(f"Expected one patch row in {path}, found {len(rows)}")
    patch = rows[0].get("fix_patch") or ""
    if not patch.strip():
        return ""
    return patch if patch.endswith("\n") else patch + "\n"


def patch_path(root: Path, variant: str, preset: str, round_tag: str, instance_id: str) -> Path:
    return root / variant / preset / round_tag / instance_id / "patches" / "patch_results.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--compact-root", type=Path, required=True)
    parser.add_argument("--fallback-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--preset", default="local_qwen3coder30b")
    parser.add_argument("--round", default="r1_c20_t0")
    parser.add_argument("--require-complete-fallback", action="store_true")
    args = parser.parse_args()

    ids = load_ids(args.ids_file)
    args.output_root.mkdir(parents=True, exist_ok=True)
    ledger_rows = []
    summaries = {}

    for variant in VARIANTS:
        variant_dir = args.output_root / variant
        variant_dir.mkdir(parents=True, exist_ok=True)
        all_predictions = []
        recovered_predictions = []

        for instance_id in ids:
            compact_file = patch_path(args.compact_root, variant, args.preset, args.round, instance_id)
            fallback_file = patch_path(args.fallback_root, variant, args.preset, args.round, instance_id)
            if not compact_file.exists():
                raise ValueError(f"Missing compact prediction for {variant}/{instance_id}")
            compact_patch = load_patch(compact_file)
            fallback_attempted = fallback_file.exists()
            if args.require_complete_fallback and not compact_patch and not fallback_attempted:
                raise ValueError(f"Missing fallback for {variant}/{instance_id}")
            fallback_patch = load_patch(fallback_file) if fallback_attempted else ""
            if compact_patch:
                patch = compact_patch
                source = "compact"
            elif fallback_patch:
                patch = fallback_patch
                source = "expanded_fallback"
            else:
                patch = ""
                source = "empty"

            prediction = {
                "model_name_or_path": f"qwen3coder30b_glm5_{variant}_iterative",
                "instance_id": instance_id,
                "model_patch": patch,
            }
            all_predictions.append(prediction)
            if source == "expanded_fallback":
                recovered_predictions.append(prediction)
            ledger_rows.append(
                {
                    "instance_id": instance_id,
                    "variant": variant,
                    "compact_nonempty": int(bool(compact_patch)),
                    "fallback_attempted": int(fallback_attempted),
                    "fallback_nonempty": int(bool(fallback_patch)),
                    "selected_source": source,
                    "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest() if patch else "",
                    "patch_chars": len(patch),
                }
            )

        for name, rows in (
            ("predictions_all.jsonl", all_predictions),
            ("predictions_recovered_only.jsonl", recovered_predictions),
        ):
            with (variant_dir / name).open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        summaries[variant] = {
            "instances": len(ids),
            "compact_nonempty": sum(row["variant"] == variant and row["compact_nonempty"] for row in ledger_rows),
            "recovered_nonempty": len(recovered_predictions),
            "final_nonempty": sum(bool(row["model_patch"].strip()) for row in all_predictions),
        }

    ledger_path = args.output_root / "assembly_ledger.tsv"
    with ledger_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ledger_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(ledger_rows)
    (args.output_root / "assembly_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
