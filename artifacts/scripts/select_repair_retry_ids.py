#!/usr/bin/env python3
"""Select only repair runs whose model request failed at the provider boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assemble_repair_profile_predictions import (
    load_ids,
    parse_variant_specs,
    provider_failure,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--shards", nargs="+", required=True)
    parser.add_argument(
        "--variant",
        action="append",
        dest="variant_specs",
        required=True,
        metavar="LABEL=RUN_VARIANT",
    )
    parser.set_defaults(variants=[])
    return parser.parse_args()


def classify_instance(
    run_root: Path,
    run_variant: str,
    instance_id: str,
    shards: list[str],
) -> str:
    clean = 0
    provider_failed = 0
    incomplete: list[Path] = []
    for shard in shards:
        patches = (
            run_root
            / run_variant
            / shard
            / run_variant
            / instance_id
            / "patches"
        )
        if not patches.exists():
            continue
        audit_path = patches / f"{instance_id}.run.json"
        result_path = patches / "patch_results.jsonl"
        if not audit_path.exists() or not result_path.exists():
            incomplete.append(patches)
            continue
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if provider_failure(audit):
            provider_failed += 1
        else:
            clean += 1
    if clean == 1:
        return "complete"
    if clean > 1:
        raise ValueError(
            f"Multiple provider-clean runs for {run_variant}/{instance_id}: {clean}"
        )
    if provider_failed or incomplete:
        return "retry"
    raise ValueError(f"No run found for {run_variant}/{instance_id}")


def main() -> int:
    args = parse_args()
    run_root = args.run_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ids = load_ids(args.ids_file.resolve())
    summary: dict[str, dict[str, int]] = {}
    for label, run_variant in parse_variant_specs(args):
        retry_ids = [
            instance_id
            for instance_id in ids
            if classify_instance(
                run_root, run_variant, instance_id, args.shards
            ) == "retry"
        ]
        output = output_dir / f"{label}.ids"
        output.write_text("\n".join(retry_ids) + ("\n" if retry_ids else ""), encoding="utf-8")
        summary[label] = {
            "total": len(ids),
            "complete": len(ids) - len(retry_ids),
            "retry": len(retry_ids),
        }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
