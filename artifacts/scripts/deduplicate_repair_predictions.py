#!/usr/bin/env python3
"""Deduplicate identical per-instance patches into canonical evaluation slots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--variants", nargs="+", default=["issue", "bm25", "mural"])
    parser.add_argument("--model-prefix", default="glm5_corrected_unique")
    parser.add_argument(
        "--prompt-audit",
        type=Path,
        help="Rendered-context TSV used to require exact prompt matches for reuse.",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, str]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def patch_hash(patch: str) -> str:
    return hashlib.sha256(patch.encode("utf-8")).hexdigest()


def read_prompt_hashes(path: Path) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    hashes: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (row["variant"], row["instance_id"])
        value = row["prompt_sha256"]
        if key in hashes:
            raise ValueError(f"Duplicate prompt-audit key: {key}")
        if len(value) != 64:
            raise ValueError(f"Invalid prompt hash for {key}: {value!r}")
        hashes[key] = value
    return hashes


def assign_slots(
    predictions: dict[str, dict[str, dict[str, str]]],
    variants: list[str],
    prompt_hashes: dict[tuple[str, str], str] | None = None,
) -> tuple[list[list[dict[str, str]]], list[dict[str, object]]]:
    id_order = list(predictions[variants[0]])
    expected_ids = set(id_order)
    for variant in variants[1:]:
        if set(predictions[variant]) != expected_ids:
            raise ValueError(f"{variant}: prediction IDs do not match {variants[0]}")
    if prompt_hashes is not None:
        expected_prompt_keys = {
            (variant, instance_id)
            for variant in variants
            for instance_id in id_order
        }
        if set(prompt_hashes) != expected_prompt_keys:
            raise ValueError("Prompt-audit keys do not match prediction keys")

    slots: list[list[dict[str, str]]] = [[] for _ in variants]
    mapping: list[dict[str, object]] = []
    for instance_id in id_order:
        unique_patches: list[str] = []
        reuse_key_to_slot: dict[tuple[str, str], int] = {}
        for variant in variants:
            patch = str(predictions[variant][instance_id].get("model_patch") or "").strip()
            prompt_sha256 = (
                prompt_hashes[(variant, instance_id)]
                if prompt_hashes is not None
                else ""
            )
            if not patch:
                mapping.append(
                    {
                        "instance_id": instance_id,
                        "variant": variant,
                        "nonempty": 0,
                        "patch_sha256": "",
                        "prompt_sha256": prompt_sha256,
                        "slot": "",
                        "canonical_model": "",
                        "reused_identical_patch": 0,
                    }
                )
                continue
            reuse_key = (patch, prompt_sha256)
            reused = reuse_key in reuse_key_to_slot
            if reused:
                slot = reuse_key_to_slot[reuse_key]
            else:
                slot = len(unique_patches)
                reuse_key_to_slot[reuse_key] = slot
                unique_patches.append(patch)
            mapping.append(
                {
                    "instance_id": instance_id,
                    "variant": variant,
                    "nonempty": 1,
                    "patch_sha256": patch_hash(patch),
                    "prompt_sha256": prompt_sha256,
                    "slot": slot,
                    "canonical_model": "",
                    "reused_identical_patch": int(reused),
                }
            )
        for slot, patch in enumerate(unique_patches):
            slots[slot].append(
                {
                    "instance_id": instance_id,
                    "model_patch": patch,
                }
            )
    return slots, mapping


def main() -> int:
    args = parse_args()
    predictions: dict[str, dict[str, dict[str, str]]] = {}
    for variant in args.variants:
        path = args.predictions_root.resolve() / variant / "predictions_all.jsonl"
        rows = read_jsonl(path)
        by_id = {str(row.get("instance_id") or ""): row for row in rows}
        if not rows or "" in by_id or len(by_id) != len(rows):
            raise ValueError(f"{variant}: prediction IDs must be nonempty and unique")
        predictions[variant] = by_id

    prompt_hashes = (
        read_prompt_hashes(args.prompt_audit.resolve())
        if args.prompt_audit is not None
        else None
    )
    slots, mapping = assign_slots(predictions, args.variants, prompt_hashes)
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    models = {}
    for slot, rows in enumerate(slots):
        model = f"{args.model_prefix}_slot{slot}"
        models[slot] = model
        for row in rows:
            row["model_name_or_path"] = model
        slot_dir = output_root / f"slot_{slot}"
        slot_dir.mkdir(parents=True, exist_ok=True)
        (slot_dir / "predictions.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    for row in mapping:
        if row["nonempty"]:
            row["canonical_model"] = models[int(row["slot"])]
    mapping_path = output_root / "prediction_mapping.tsv"
    with mapping_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(mapping[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(mapping)

    summary = {
        "variants": args.variants,
        "variant_predictions": len(mapping),
        "nonempty_variant_predictions": sum(int(row["nonempty"]) for row in mapping),
        "canonical_predictions": sum(len(rows) for rows in slots),
        "slot_counts": {f"slot_{i}": len(rows) for i, rows in enumerate(slots)},
        "reuse_requires_prompt_match": prompt_hashes is not None,
        "prompt_audit_sha256": (
            hashlib.sha256(args.prompt_audit.resolve().read_bytes()).hexdigest()
            if args.prompt_audit is not None
            else ""
        ),
        "identical_patch_reuses": sum(
            int(row["reused_identical_patch"]) for row in mapping
        ),
    }
    (output_root / "deduplication_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
