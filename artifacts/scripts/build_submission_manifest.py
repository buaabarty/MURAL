#!/usr/bin/env python3
"""Build the frozen MURAL submission protocol and SHA-256 manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts" / "submission_manifest_20260719.json"

CRITICAL_FILES = [
    "README.md",
    "artifacts/README.md",
    "artifacts/RESULT_TRACEABILITY.md",
    "artifacts/scripts/analyze_clustered_repair_stats.py",
    "artifacts/scripts/analyze_repair_outcomes.py",
    "artifacts/scripts/analyze_human_strict_alignment.py",
    "artifacts/scripts/analyze_source_bearing_prompt_coverage.py",
    "artifacts/scripts/build_strict_reference_targets.py",
    "artifacts/scripts/build_submission_manifest.py",
    "artifacts/scripts/collect_swebench_reports.py",
    "artifacts/scripts/entity_identity.py",
    "artifacts/scripts/evaluate_java_retrieve_localize.py",
    "artifacts/scripts/evaluate_strict_external_localizers.py",
    "artifacts/scripts/evaluate_strict_reference_context.py",
    "artifacts/scripts/evaluate_token_budget_context.py",
    "artifacts/scripts/export_compact_rankings.py",
    "artifacts/scripts/export_dense_filefirst.py",
    "artifacts/scripts/export_entity_projection.py",
    "artifacts/scripts/export_fixed_prefix_fusion.py",
    "artifacts/scripts/export_multi_source_rrf_fusion.py",
    "artifacts/scripts/export_path_mined_filelocal.py",
    "artifacts/scripts/export_ranked_file_seeds.py",
    "artifacts/scripts/fuse_path_mined_with_kg.py",
    "artifacts/scripts/export_selector_simple_baselines.py",
    "artifacts/scripts/export_text_baselines.py",
    "artifacts/scripts/materialize_compact_rankings.py",
    "artifacts/scripts/materialize_repair_variant_reports.py",
    "artifacts/scripts/assemble_repair_profile_predictions.py",
    "artifacts/scripts/merge_repair_official_updates.py",
    "artifacts/scripts/merge_repair_prediction_updates.py",
    "artifacts/scripts/reanalyze_java_clustered_stats.py",
    "artifacts/scripts/reprocess_repair_attempts.py",
    "artifacts/scripts/run_repair_profile_batch.py",
    "artifacts/scripts/run_text_baselines.py",
    "artifacts/scripts/verify_paper_results.py",
    "test_entity_projection_ranking.py",
    "test_fusion_identity.py",
    "test_strict_external_localizers.py",
    "test_strict_reference_evaluator.py",
    "test_strict_reference_target_builder.py",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files_under(directory: str) -> list[str]:
    root = ROOT / directory
    return sorted(
        str(path.relative_to(ROOT))
        for path in root.iterdir()
        if path.is_file()
    )


def main() -> None:
    files = sorted(
        set(
            CRITICAL_FILES
            + files_under("artifacts/results")
            + files_under("artifacts/frozen")
            + files_under("artifacts/inputs")
            + files_under("artifacts/prompts")
        )
    )
    missing = [name for name in files if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit(f"Missing manifest inputs: {missing}")

    manifest = {
        "schema_version": 2,
        "frozen_date": "2026-07-19",
        "paper": {
            "title": "MURAL: Decoupling File Retrieval from Within-File Entity Selection for Bounded Repository-Repair Context",
            "artifact_repository": "https://github.com/buaabarty/MURAL",
        },
        "python_benchmark": {
            "name": "SWE-bench Verified",
            "instances": 500,
            "repositories": 12,
            "query": "original issue title and body",
            "snapshot": "official base commit",
        },
        "strict_reference": {
            "builder": "artifacts/scripts/build_strict_reference_targets.py",
            "parser": "Python standard ast",
            "ranking_unit": "base-snapshot synchronous module function, direct class method, or simple module/class assignment",
            "added_line_policy": "retain an entity only when the same path, kind, and qualified symbol exists in the base snapshot",
            "fallback": "add an exact-file target for each changed path containing a region outside the candidate-unit contract; retain it with entity targets",
            "matching": "exact normalized file path, target kind, and qualified name",
            "target_file": "artifacts/results/strict_reference_targets_20260719.json",
            "target_counts": {
                "function_or_class_method": 836,
                "assignment": 32,
                "exact_file": 176,
                "total": 1044,
                "multi_target_instances": 181,
                "instances_with_file_target": 151,
            },
        },
        "mural": {
            "source_adapters": {
                "BM25": "ranked files through shared Entity Projection",
                "dense": "ranked files through shared Entity Projection",
                "structural": "canonical minimum-rank union of native structural entities and projected structurally ranked files",
            },
            "projection": "one shared deterministic Entity Projection implementation for ranked-file branches",
            "python_identity": "normalized path, inferred kind, and qualified symbol base",
            "fusion": "equal-weight reciprocal-rank fusion over canonical adapter rankings",
            "rrf_k": 60,
            "default_entity_budget": 20,
            "prefix_policy": "preserve resolved prefix; scan secondary head, localizer remainder, then secondary remainder",
            "frozen_rankings": "artifacts/frozen/strict_rankings_top50_20260719.jsonl.gz",
        },
        "statistics": {
            "bootstrap": "paired repository-clustered percentile interval",
            "resamples": 10000,
            "seed": 7,
            "binary_test": "two-sided exact McNemar",
            "confidence_level": 0.95,
        },
        "repair": {
            "generation_dates": ["2026-07-18", "2026-07-19"],
            "provider": "AutoDL",
            "api_style": "OpenAI-compatible",
            "endpoint": "https://www.autodl.art/api/v1",
            "api_key_environment_variable": "AUTODL_API_KEY",
            "model_alias": "glm-5.2",
            "temperature": 0.0,
            "top_p": 0.95,
            "enable_thinking": False,
            "assistant_response_prefill": False,
            "max_output_tokens": 2048,
            "request_timeout_seconds": 600,
            "prompt_token_ceiling": 4000,
            "candidate_entity_budget": 20,
            "failure_conditioned_retries": 1,
            "patch_format": "SEARCH/REPLACE converted to unified diff and checked against base commit",
            "selection": "first applicable patch",
            "official_harness": "swe-bench 4.1.0",
            "test_timeout_seconds": 1800,
            "timeout_outcome": "unresolved",
            "prompt_hash_rows": 1000,
            "variants": ["bm25", "mural"],
        },
        "human_audit": {
            "judgments": 100,
            "unique_instances": 80,
            "double_coded_instances": 20,
            "decision_labels": ["MURAL", "BM25-local", "Comparable", "Both insufficient"],
        },
        "java_benchmark": {
            "name": "SWE-bench-Java Verified",
            "official_instances": 91,
            "evaluated_instances": 91,
            "repositories": 6,
            "excluded_instances": 0,
            "manifest": "artifacts/inputs/java_cross_language_manifest_20260714.json",
        },
        "files": {
            name: {
                "bytes": (ROOT / name).stat().st_size,
                "sha256": sha256(ROOT / name),
            }
            for name in files
        },
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(files)} hashed files")


if __name__ == "__main__":
    main()
