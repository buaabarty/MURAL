#!/usr/bin/env python3
"""Merge prompt-triggered repair updates into frozen full-dataset predictions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", action="append", required=True, metavar="LABEL=JSONL")
    parser.add_argument("--updates", action="append", required=True, metavar="LABEL=JSONL")
    parser.add_argument("--changed-ids", action="append", required=True, metavar="LABEL=FILE")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--model-prefix", default="glm52_equal4000")
    return parser.parse_args()


def parse_specs(values: list[str], flag: str) -> dict[str, Path]:
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


def read_jsonl(path: Path) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        row = json.loads(raw_line)
        instance_id = str(row.get("instance_id") or "").strip()
        if not instance_id or instance_id in rows:
            raise ValueError(f"Missing or duplicate instance_id in {path}: {instance_id!r}")
        rows[instance_id] = row
    if not rows:
        raise ValueError(f"No predictions in {path}")
    return rows


def read_ids(path: Path) -> set[str]:
    values = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if not values:
        raise ValueError(f"No instance ids in {path}")
    return values


def patch_hash(patch: str) -> str:
    return hashlib.sha256(patch.encode("utf-8")).hexdigest()


def main() -> int:
    args = parse_args()
    old_specs = parse_specs(args.old, "--old")
    update_specs = parse_specs(args.updates, "--updates")
    changed_specs = parse_specs(args.changed_ids, "--changed-ids")
    if set(old_specs) != set(update_specs) or set(old_specs) != set(changed_specs):
        raise ValueError("Labels must match across --old, --updates, and --changed-ids")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    audit_rows: list[dict[str, object]] = []

    for label in sorted(old_specs):
        old = read_jsonl(old_specs[label])
        updates = read_jsonl(update_specs[label])
        changed_ids = read_ids(changed_specs[label])
        if changed_ids != set(updates):
            missing = sorted(changed_ids - set(updates))
            extra = sorted(set(updates) - changed_ids)
            raise ValueError(f"Update coverage mismatch for {label}: missing={missing}, extra={extra}")
        if not changed_ids <= set(old):
            raise ValueError(f"Unknown changed ids for {label}: {sorted(changed_ids - set(old))}")

        merged_rows: list[dict[str, str]] = []
        reevaluate: list[str] = []
        for instance_id, old_row in old.items():
            old_patch = str(old_row.get("model_patch") or "")
            selected = updates[instance_id] if instance_id in changed_ids else old_row
            new_patch = str(selected.get("model_patch") or "")
            changed = old_patch != new_patch
            if changed:
                reevaluate.append(instance_id)
            merged_rows.append(
                {
                    "model_name_or_path": f"{args.model_prefix}_{label}",
                    "instance_id": instance_id,
                    "model_patch": new_patch,
                }
            )
            audit_rows.append(
                {
                    "instance_id": instance_id,
                    "variant": label,
                    "prompt_changed": int(instance_id in changed_ids),
                    "prediction_source": "regenerated" if instance_id in changed_ids else "frozen_reuse",
                    "old_patch_sha256": patch_hash(old_patch),
                    "new_patch_sha256": patch_hash(new_patch),
                    "patch_changed": int(changed),
                    "nonempty": int(bool(new_patch.strip())),
                }
            )

        variant_dir = output_root / label
        variant_dir.mkdir(parents=True, exist_ok=True)
        (variant_dir / "predictions_all.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=True) for row in merged_rows) + "\n",
            encoding="utf-8",
        )
        (variant_dir / "reevaluate_ids.txt").write_text(
            "\n".join(reevaluate) + ("\n" if reevaluate else ""), encoding="utf-8"
        )
        print(
            f"{label}: {len(merged_rows)} predictions, "
            f"{len(changed_ids)} changed prompts, {len(reevaluate)} changed patches"
        )

    with (output_root / "prediction_provenance.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(audit_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
