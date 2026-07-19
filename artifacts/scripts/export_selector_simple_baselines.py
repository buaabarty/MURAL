#!/usr/bin/env python3
"""Export simple within-file allocation baselines for Entity Projection.

Every variant starts from the same ranked BM25 files and the same parsed
base-commit entities.  Only the within-file ordering/allocation policy changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ARTIFACT_ROOT / "artifacts" / "scripts"))

import export_path_mined_filelocal as miner  # noqa: E402


VARIANTS = (
    "file_source_order",
    "file_name_overlap",
    "file_bm25",
    "round_robin_bm25",
    "weighted_features",
    "stable_random",
)


def install_parse_cache() -> None:
    original = miner.parse_file_entities

    @lru_cache(maxsize=None)
    def cached(repo: str, base_commit: str, file_path: str):
        return original(repo, base_commit, file_path)

    miner.parse_file_entities = cached  # type: ignore[assignment]


def file_rank(item: dict[str, Any]) -> int:
    evidence = ((item.get("evidence") or {}).get("path_mining") or {})
    return int(evidence.get("file_best_rank") or 999)


def source_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        file_rank(item),
        int(item.get("start_line") or 0),
        int(item.get("end_line") or 0),
        str(item.get("signature") or item.get("name") or ""),
    )


def entity_tokens(item: dict[str, Any], include_source: bool = True) -> list[str]:
    values = [item.get("name"), item.get("signature"), item.get("file_path")]
    if include_source:
        values.extend([item.get("source_code"), item.get("doc_string")])
    output: list[str] = []
    for value in values:
        output.extend(miner.split_identifier(value))
    return output


def query_tokens(payload: dict[str, Any], dataset_item: dict[str, Any]) -> list[str]:
    root = (payload.get("run_meta") or {}).get("active_root") or {}
    text = "\n".join(
        [
            str(root.get("title") or ""),
            str(root.get("content") or ""),
            str(dataset_item.get("problem_statement") or ""),
        ]
    )
    return miner.split_identifier(text)


def bm25_scores(
    candidates: list[dict[str, Any]], query: list[str], k1: float = 1.2, b: float = 0.75
) -> list[float]:
    documents = [entity_tokens(item, include_source=True) for item in candidates]
    if not documents:
        return []
    lengths = [len(document) for document in documents]
    average_length = sum(lengths) / len(lengths) or 1.0
    frequencies = [Counter(document) for document in documents]
    document_frequency = Counter(
        term for frequency in frequencies for term in frequency
    )
    query_frequency = Counter(query)
    scores: list[float] = []
    for length, frequency in zip(lengths, frequencies):
        score = 0.0
        normalization = k1 * (1.0 - b + b * length / average_length)
        for term, query_count in query_frequency.items():
            term_frequency = frequency.get(term, 0)
            if not term_frequency:
                continue
            df = document_frequency[term]
            inverse_document_frequency = math.log(
                1.0 + (len(documents) - df + 0.5) / (df + 0.5)
            )
            score += query_count * inverse_document_frequency * (
                term_frequency * (k1 + 1.0)
            ) / (term_frequency + normalization)
        scores.append(score)
    return scores


def feature_score(item: dict[str, Any]) -> float:
    evidence = ((item.get("evidence") or {}).get("path_mining") or {})
    title = len(evidence.get("title_symbol_matches") or []) + len(
        evidence.get("title_source_matches") or []
    )
    exact = len(evidence.get("exact_symbol_matches") or []) + len(
        evidence.get("exact_source_matches") or []
    )
    narrative = len(evidence.get("narrative_symbol_matches") or []) + len(
        evidence.get("narrative_source_matches") or []
    )
    diagnostic = len(evidence.get("diagnostic_symbol_matches") or [])
    boilerplate = int(miner.is_boilerplate(item))
    return (
        3.0 * title
        + 4.0 * exact
        + narrative
        - 2.0 * diagnostic
        - 2.0 * boilerplate
        - 0.05 * file_rank(item)
    )


def round_robin(
    candidates: list[dict[str, Any]], scores: dict[tuple[Any, ...], float]
) -> list[dict[str, Any]]:
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        buckets[file_rank(item)].append(item)
    for rows in buckets.values():
        rows.sort(
            key=lambda item: (
                -scores[identity(item)],
                int(item.get("start_line") or 0),
                str(item.get("signature") or item.get("name") or ""),
            )
        )
    output: list[dict[str, Any]] = []
    ordered_ranks = sorted(buckets)
    position = 0
    while True:
        added = False
        for rank in ordered_ranks:
            if position < len(buckets[rank]):
                output.append(buckets[rank][position])
                added = True
        if not added:
            return output
        position += 1


def identity(item: dict[str, Any]) -> tuple[Any, ...]:
    return miner.canonical_entity_id(item)


def rank_variant(
    instance_id: str,
    candidates: list[dict[str, Any]],
    query: list[str],
    variant: str,
) -> list[dict[str, Any]]:
    bm25 = bm25_scores(candidates, query)
    bm25_by_identity = {
        identity(item): score for item, score in zip(candidates, bm25)
    }
    query_set = set(query)
    name_overlap = {
        identity(item): len(query_set & set(entity_tokens(item, include_source=False)))
        for item in candidates
    }

    if variant == "file_source_order":
        ranked = sorted(candidates, key=source_key)
    elif variant == "file_name_overlap":
        ranked = sorted(
            candidates,
            key=lambda item: (
                file_rank(item),
                -name_overlap[identity(item)],
                int(item.get("start_line") or 0),
                str(item.get("signature") or item.get("name") or ""),
            ),
        )
    elif variant == "file_bm25":
        ranked = sorted(
            candidates,
            key=lambda item: (
                file_rank(item),
                -bm25_by_identity[identity(item)],
                int(item.get("start_line") or 0),
                str(item.get("signature") or item.get("name") or ""),
            ),
        )
    elif variant == "round_robin_bm25":
        ranked = round_robin(candidates, bm25_by_identity)
    elif variant == "weighted_features":
        ranked = sorted(
            candidates,
            key=lambda item: (
                -feature_score(item),
                file_rank(item),
                int(item.get("start_line") or 0),
                str(item.get("signature") or item.get("name") or ""),
            ),
        )
    elif variant == "stable_random":
        ranked = sorted(
            candidates,
            key=lambda item: hashlib.sha256(
                (instance_id + "|" + "|".join(map(str, identity(item)))).encode("utf-8")
            ).hexdigest(),
        )
    else:
        raise ValueError(f"Unknown variant: {variant}")

    output: list[dict[str, Any]] = []
    for rank, item in enumerate(ranked, start=1):
        copied = deepcopy(item)
        copied["similarity"] = 1.0 / rank
        copied.setdefault("evidence", {})["simple_selector_baseline"] = {
            "variant": variant,
            "rank": rank,
            "file_rank": file_rank(item),
            "name_overlap": name_overlap[identity(item)],
            "bm25_score": bm25_by_identity[identity(item)],
            "weighted_score": feature_score(item),
        }
        output.append(copied)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument(
        "--playground-root",
        type=Path,
        default=Path("playground"),
        help="Base-commit repository checkouts named owner__repo or repo.",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--variant", action="append", choices=VARIANTS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    miner.PLAYGROUND_ROOT = args.playground_root.resolve()
    variants = args.variant or list(VARIANTS)
    ids = miner.load_ids(args.ids_file)
    dataset = miner.load_dataset_items(ids)
    install_parse_cache()
    for variant in variants:
        (args.output_root / variant).mkdir(parents=True, exist_ok=True)

    for position, instance_id in enumerate(ids, start=1):
        source_path = args.input_dir / f"{instance_id}.json"
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        source = json.loads(source_path.read_text(encoding="utf-8"))
        expanded = miner.rerank_instance(source, dataset[instance_id])
        candidates = list((expanded.get("related_entities") or {}).get("methods") or [])
        query = query_tokens(source, dataset[instance_id])
        for variant in variants:
            output = deepcopy(expanded)
            related = output.setdefault("related_entities", {})
            related["methods"] = rank_variant(
                instance_id, candidates, query, variant
            )[: args.limit]
            related["classes"] = []
            output.setdefault("run_meta", {})["simple_selector_baseline"] = {
                "variant": variant,
                "input_dir": str(args.input_dir),
                "candidate_count": len(candidates),
                "limit": args.limit,
            }
            (args.output_root / variant / source_path.name).write_text(
                json.dumps(output, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        if position % 25 == 0 or position == len(ids):
            print(f"[selector-simple] {position}/{len(ids)}", flush=True)

    print(f"wrote {len(variants)} variants to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
