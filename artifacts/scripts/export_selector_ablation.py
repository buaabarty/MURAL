#!/usr/bin/env python3
"""Export leave-one-signal-group-out variants of the MURAL selector."""

from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "artifacts" / "scripts"))
import export_path_mined_filelocal as miner  # type: ignore  # noqa: E402


VARIANTS = {
    "full": None,
    "minus_g1": "G1",
    "minus_g2": "G2",
    "minus_g3": "G3",
    "minus_g4": "G4",
    "minus_g5": "G5",
}


def install_parse_cache() -> None:
    """Reuse parsed base-commit files across all six variants in this process."""
    original = miner.parse_file_entities

    @lru_cache(maxsize=None)
    def cached(repo: str, base_commit: str, file_path: str):
        return original(repo, base_commit, file_path)

    miner.parse_file_entities = cached  # type: ignore[assignment]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=REPO_ROOT / "temp_run" / "SWE-bench_Verified_ids.jsonl",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--variant",
        action="append",
        choices=sorted(VARIANTS),
        help="Variant to export; repeat as needed. Defaults to all six.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = args.variant or list(VARIANTS)
    ids = miner.load_ids(args.ids_file)
    dataset = miner.load_dataset_items(ids)
    install_parse_cache()

    for name in selected:
        (args.output_root / name).mkdir(parents=True, exist_ok=True)

    completed = 0
    try:
        for instance_id in ids:
            source_path = args.input_dir / f"{instance_id}.json"
            if not source_path.exists():
                continue
            source = json.loads(source_path.read_text(encoding="utf-8"))

            for name in selected:
                group = VARIANTS[name]
                miner.SELECTOR_ABLATION = group
                output = miner.rerank_instance(source, dataset[instance_id])
                entities = output.setdefault("related_entities", {})
                entities["methods"] = (entities.get("methods") or [])[: args.limit]
                entities["classes"] = (entities.get("classes") or [])[: args.limit]
                run_meta = output.setdefault("run_meta", {})
                run_meta["path_mining_source_dir"] = str(args.input_dir)
                run_meta["tag"] = args.output_root.name
                run_meta["selector_ablation"] = group or "FULL"
                output_path = args.output_root / name / f"{instance_id}.json"
                output_path.write_text(
                    json.dumps(output, separators=(",", ":")),
                    encoding="utf-8",
                )

            completed += 1
            if completed % 25 == 0 or completed == len(ids):
                print(f"[selector-ablation] {completed}/{len(ids)}", flush=True)
    finally:
        miner.SELECTOR_ABLATION = None

    print(
        f"Saved {completed} instances for {len(selected)} variants "
        f"to {args.output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
