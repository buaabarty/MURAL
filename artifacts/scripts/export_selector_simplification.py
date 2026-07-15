#!/usr/bin/env python3
"""Export joint simplification variants of the MURAL selector."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from functools import lru_cache
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "artifacts" / "scripts"))
import export_path_mined_filelocal as miner  # type: ignore  # noqa: E402


# The expanded diagnostic key has 15 components. Each variant masks selected
# components to constants while keeping candidate enumeration and evaluation fixed.
VARIANTS = {
    "expanded": (),
    "stable_only": tuple([*range(0, 10), 11, 12]),
    "file_rank_ast": tuple([*range(0, 10), 12]),
    "title_file_rank_ast": tuple([*range(2, 10), 12]),
    "exact_file_rank_ast": tuple([0, 1, *range(4, 10), 12]),
    "compact": tuple([*range(4, 10), 12]),
}


def install_parse_cache() -> None:
    """Reuse parsed base-commit files across all variants."""
    original = miner.parse_file_entities

    @lru_cache(maxsize=None)
    def cached(repo: str, base_commit: str, file_path: str):
        return original(repo, base_commit, file_path)

    miner.parse_file_entities = cached  # type: ignore[assignment]


def expanded_key(item: dict) -> list:
    evidence = (item.get("evidence") or {}).get("path_mining") or {}
    boilerplate = 1 if miner.is_boilerplate(item) else 0
    if (
        evidence.get("diagnostic_symbol_matches")
        and not evidence.get("title_symbol_matches")
        and not evidence.get("exact_symbol_matches")
        and not evidence.get("narrative_symbol_matches")
        and not evidence.get("source_only_matches")
    ):
        boilerplate += 1
    return [
        -len(evidence.get("title_symbol_matches") or []),
        -len(evidence.get("title_source_matches") or []),
        -len(evidence.get("exact_symbol_matches") or []),
        -len(evidence.get("exact_source_matches") or []),
        -len(evidence.get("narrative_symbol_matches") or []),
        -len(evidence.get("source_only_matches") or []),
        -len(evidence.get("narrative_source_matches") or []),
        -int(evidence.get("file_support") or 0),
        int(evidence.get("file_distance") or 999),
        0 if evidence.get("file_anchor_match") else 1,
        boilerplate,
        int(evidence.get("file_best_rank") or 999),
        int(evidence.get("original_kg_rank") or 9999),
        int(item.get("start_line") or 0),
        item.get("name") or "",
    ]


def variant_key(item: dict, disabled: tuple[int, ...]) -> list:
    key = expanded_key(item)
    for index in disabled:
        key[index] = 0
    return key


def rerank(items: list[dict], disabled: tuple[int, ...], limit: int, variant: str) -> list[dict]:
    ranked = sorted(items, key=lambda item: variant_key(item, disabled))
    output = []
    for item in ranked[:limit]:
        copied = deepcopy(item)
        copied["ranking_key"] = variant_key(item, disabled)
        copied.setdefault("evidence", {}).setdefault("path_mining", {})[
            "selector_simplification"
        ] = variant
        output.append(copied)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=REPO_ROOT / "temp_run" / "SWE-bench_Verified_ids.jsonl",
    )
    parser.add_argument(
        "--playground-root",
        type=Path,
        default=miner.PLAYGROUND_ROOT,
        help="Directory containing repository checkouts named owner__repo or repo.",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--variant",
        action="append",
        choices=sorted(VARIANTS),
        help="Variant to export; repeat as needed. Defaults to all variants.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip instances whose selected variant outputs already exist.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = args.variant or list(VARIANTS)
    miner.PLAYGROUND_ROOT = args.playground_root
    ids = miner.load_ids(args.ids_file)
    dataset = miner.load_dataset_items(ids)
    install_parse_cache()

    for name in selected:
        (args.output_root / name).mkdir(parents=True, exist_ok=True)

    completed = 0
    for instance_id in ids:
        source_path = args.input_dir / f"{instance_id}.json"
        if not source_path.exists():
            continue
        output_paths = [
            args.output_root / name / f"{instance_id}.json" for name in selected
        ]
        if args.resume and all(path.exists() for path in output_paths):
            completed += 1
            if completed % 25 == 0 or completed == len(ids):
                print(
                    f"[selector-simplification] {completed}/{len(ids)}",
                    flush=True,
                )
            continue
        source = json.loads(source_path.read_text(encoding="utf-8"))
        base = miner.rerank_instance(source, dataset[instance_id])
        related = base.get("related_entities") or {}

        for name in selected:
            output = deepcopy(base)
            entities = output.setdefault("related_entities", {})
            entities["methods"] = rerank(
                related.get("methods") or [], VARIANTS[name], args.limit, name
            )
            entities["classes"] = rerank(
                related.get("classes") or [], VARIANTS[name], args.limit, name
            )
            run_meta = output.setdefault("run_meta", {})
            run_meta["path_mining_source_dir"] = str(args.input_dir)
            run_meta["tag"] = args.output_root.name
            run_meta["selector_simplification"] = name
            output_path = args.output_root / name / f"{instance_id}.json"
            output_path.write_text(
                json.dumps(output, separators=(",", ":")), encoding="utf-8"
            )

        completed += 1
        if completed % 25 == 0 or completed == len(ids):
            print(f"[selector-simplification] {completed}/{len(ids)}", flush=True)

    print(
        f"Saved {completed} instances for {len(selected)} variants "
        f"to {args.output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
