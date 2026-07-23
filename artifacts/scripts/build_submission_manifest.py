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
    "artifacts/scripts/analyze_human_window_strata.py",
    "artifacts/scripts/analyze_primary_cluster_randomization.py",
    "artifacts/scripts/analyze_target_fallback_evidence.py",
    "artifacts/scripts/analyze_token_candidate_exhaustion.py",
    "artifacts/scripts/analyze_changed_line_strata.py",
    "artifacts/scripts/analyze_repair_outcomes.py",
    "artifacts/scripts/analyze_repair_target_coverage.py",
    "artifacts/scripts/analyze_source_combinations.py",
    "artifacts/scripts/analyze_human_strict_alignment.py",
    "artifacts/scripts/analyze_reference_coverage_strata.py",
    "artifacts/scripts/analyze_human_evidence_audit.py",
    "artifacts/scripts/analyze_source_bearing_prompt_coverage.py",
    "artifacts/scripts/analyze_stratified_context_findings.py",
    "artifacts/scripts/plot_paper_findings.py",
    "artifacts/scripts/audit_issue_creation_cutoff.py",
    "artifacts/scripts/audit_structural_temporal_provenance.py",
    "artifacts/scripts/build_paper_ledgers.py",
    "artifacts/scripts/build_strict_reference_targets.py",
    "artifacts/scripts/build_submission_manifest.py",
    "artifacts/scripts/collect_swebench_reports.py",
    "artifacts/scripts/entity_identity.py",
    "artifacts/scripts/evaluate_human_window_exact_hits.py",
    "artifacts/scripts/evaluate_java_retrieve_localize.py",
    "artifacts/scripts/evaluate_strict_external_localizers.py",
    "artifacts/scripts/evaluate_strict_reference_context.py",
    "artifacts/scripts/export_external_localizer_completions.py",
    "artifacts/scripts/export_static_structural_ablation.py",
    "artifacts/scripts/export_file_primary_ranking.py",
    "artifacts/scripts/export_file_rrf_seeds.py",
    "artifacts/scripts/evaluate_token_budget_context.py",
    "artifacts/scripts/freeze_human_window_rankings.py",
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
    "artifacts/scripts/verify_human_window_binding.py",
    "artifacts/scripts/verify_paper_results.py",
    "artifacts/structural_temporal_metadata_20260722.json",
    "kgcompass/fl.py",
    "test_entity_projection_ranking.py",
    "test_fusion_identity.py",
    "test_human_window_binding.py",
    "test_no_llm_analysis.py",
    "test_strict_external_localizers.py",
    "test_strict_reference_evaluator.py",
    "test_strict_reference_target_builder.py",
    "test_temporal_content_boundary.py",
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
        "schema_version": 6,
        "frozen_date": "2026-07-23",
        "annotation_snapshot": "2026-07-21",
        "paper": {
            "title": "MURAL: Unifying Fault Localization and Bounded Context Construction for Repository Repair",
            "artifact_repository": "https://github.com/buaabarty/MURAL",
        },
        "python_benchmark": {
            "name": "SWE-bench Verified",
            "instances": 500,
            "repositories": 12,
            "query": "original issue title and body",
            "snapshot": "official base commit",
        },
        "paper_ledgers": {
            "dataset_profile": "artifacts/results/paper_dataset_profile_20260722.tsv",
            "main_results": "artifacts/results/paper_main_results_20260722.tsv",
            "generator": "artifacts/scripts/build_paper_ledgers.py",
        },
        "strict_reference": {
            "builder": "artifacts/scripts/build_strict_reference_targets.py",
            "parser": "Python standard ast",
            "ranking_unit": "base-snapshot synchronous module function, direct class method, or simple module/class assignment",
            "added_line_policy": "retain an entity only when the same path, kind, and qualified symbol exists in the base snapshot",
            "fallback": "add an exact-file target for each changed path containing a region outside the candidate-unit contract; retain it with entity targets",
            "matching": "exact normalized file path, target kind, and qualified name",
            "target_file": "artifacts/results/strict_reference_targets_20260719.json",
            "fallback_evidence": "artifacts/results/target_fallback_evidence_summary_20260722.tsv",
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
            "projection": "one shared deterministic global issue-conditioned entity ranking over each retrieved file pool",
            "python_identity": "normalized path, inferred kind, and qualified symbol base",
            "fusion": "equal-weight reciprocal-rank fusion over canonical adapter rankings",
            "rrf_k": 60,
            "default_entity_budget": 20,
            "prefix_policy": "preserve resolved prefix; fill remaining capacity from the selected secondary ranking",
            "context_objects": {
                "ranked_candidate": "canonical entity before prompt rendering",
                "metadata_visible_candidate": "ranked candidate shown by path and symbol in the prompt",
                "source_bearing_candidate": "metadata-visible candidate with a concrete source excerpt",
            },
            "controlled_token_renderer": "strict ranked-prefix packing with 700 source tokens for the first entity and 260 thereafter",
            "frozen_rankings": "artifacts/frozen/strict_rankings_top50_20260719.jsonl.gz",
            "token_candidate_exhaustion": "artifacts/results/token_candidate_exhaustion_summary_20260722.tsv",
        },
        "source_composition": {
            "sources": ["BM25", "structural", "dense"],
            "combinations": [
                "BM25",
                "Structural",
                "Dense",
                "BM25_Structural",
                "BM25_Dense",
                "Structural_Dense",
                "MURAL",
            ],
            "scenarios": ["standalone Top-20", "4,000 rendered tokens", "GLM-5 prefix completion"],
            "attribution": "artifacts/results/source_combination_attribution_20260722.tsv",
            "external_localizer_token_completion": "artifacts/results/external_token_completion_summary_20260722.tsv",
        },
        "architecture_controls": {
            "frozen_rankings": "artifacts/frozen/architecture_control_rankings_20260721.jsonl.gz",
            "manifest": "artifacts/frozen/architecture_control_manifest_20260721.json",
            "ordering": "same BM25 files and candidate entities; file-primary versus entity-primary",
            "fusion_point": "file-level RRF then projection versus per-source projection then entity-level RRF",
            "native_structural_branch": "projected-entity RRF versus full MURAL",
        },
        "rendered_coverage": {
            "token_budget": 4000,
            "strata": ["entity-only", "mixed", "file-only"],
            "identity_metrics": ["EntityCov", "EntityComplete"],
            "line_metrics": ["LineRecall", "CompleteLine"],
            "summary": "artifacts/results/line_coverage_summary_4000_20260721.tsv",
            "instances": "artifacts/results/line_coverage_instances_4000_20260721.tsv",
            "strata_ledger": "artifacts/results/reference_coverage_strata_4000_20260721.tsv",
            "hunk_profile": "artifacts/results/changed_line_hunk_profile_20260722.tsv",
            "hunk_strata": "artifacts/results/changed_line_strata_4000_20260722.tsv",
            "hunk_strata_paired": "artifacts/results/changed_line_strata_paired_4000_20260722.tsv",
        },
        "statistics": {
            "bootstrap": "paired repository-clustered percentile interval",
            "resamples": 10000,
            "seed": 7,
            "binary_test": "two-sided exact McNemar",
            "confidence_level": 0.95,
            "cluster_randomization": "exact sign flip over all 2^12 repository assignments",
            "cluster_randomization_endpoints": ["Hit@20", "LineRecall@4000"],
            "cluster_randomization_results": "artifacts/results/primary_cluster_signflip_summary_20260722.tsv",
        },
        "repair": {
            "generation_dates": ["2026-07-18", "2026-07-19"],
            "provider": "AutoDL",
            "api_style": "OpenAI-compatible",
            "endpoint": "https://www.autodl.art/api/v1",
            "api_key_environment_variable": "AUTODL_API_KEY",
            "model": "GLM-5",
            "endpoint_request_alias": "glm-5.2",
            "temperature": 0.0,
            "top_p": 0.95,
            "enable_thinking": False,
            "assistant_response_prefill": False,
            "max_output_tokens": 2048,
            "request_timeout_seconds": 600,
            "prompt_token_ceiling": 4000,
            "candidate_entity_budget": 20,
            "renderer": "rank-banded excerpts: up to four candidates from ranks 1-10 and four from ranks 11-20, at most two excerpts per file in each band",
            "coverage_unit": "only source-bearing candidate excerpts contribute prompt TargetCov and RefComplete",
            "failure_conditioned_retries": 1,
            "patch_format": "SEARCH/REPLACE converted to unified diff and checked against base commit",
            "selection": "first applicable patch",
            "official_harness": "swe-bench 4.1.0",
            "test_timeout_seconds": 1800,
            "timeout_outcome": "unresolved",
            "prompt_hash_rows": 1000,
            "variants": ["bm25", "mural"],
            "target_coverage_by_outcome": "artifacts/results/repair_target_coverage_outcome_20260723.tsv",
            "two_target_coverage_bins": "artifacts/results/repair_two_target_coverage_bins_20260723.tsv",
        },
        "human_audit": {
            "judgments": 100,
            "audit_scope": "patch-grounded target consistency",
            "unique_instances": 80,
            "double_coded_instances": 20,
            "decision_labels": ["MURAL", "BM25-local", "Comparable", "Both insufficient"],
            "window_rankings": "artifacts/frozen/human_window_rankings_20260712.jsonl.gz",
            "window_binding": "artifacts/results/human_window_binding_20260719.tsv",
            "strict_window_evaluation": "artifacts/results/human_window_exact_instances_20260719.tsv",
            "source_workbook_provenance": "artifacts/results/human_window_provenance_20260718.tsv",
            "stratified_unique_decisions": "artifacts/results/human_window_strata_summary_20260722.tsv",
            "paper_comparison": "RQ-1 source-composition comparison",
            "configurations": {
                "MURAL": "MURAL_2src (paper label: MURAL (BM25 + Structural))",
                "BM25-local": "BM25_projection",
            },
            "construct_audit": {
                "judgments": 80,
                "unique_instances": 60,
                "double_coded_instances": 20,
                "strict_target_binding": "artifacts/results/human_construct_adjudicated_20260721.tsv",
                "covered_instances": 60,
                "exact_entity_only_instances": 26,
                "instances_using_file_fallback": 34,
            },
            "evidence_audit_provenance": "artifacts/results/human_evidence_audit_provenance_20260721.tsv",
        },
        "structural_temporal_boundary": {
            "cutoff": "target issue created_at",
            "artifact_policy": "created and last modified no later than the cutoff",
            "audited_instances": 500,
            "cutoff_record_audit": "artifacts/results/issue_creation_cutoff_audit_20260719.json",
            "provenance_audit": "artifacts/results/structural_temporal_provenance_20260722.json",
            "historical_artifacts_observed": 1,
            "time_ineligible_path_rows": 0,
            "changed_top20_windows": 0,
            "changed_4000_token_windows": 0,
            "static_replay": "artifacts/results/structural_static_ablation_summary_20260722.json",
            "history_derived_candidates_removed": 2,
            "static_replay_target_metric_changes": 0,
        },
        "java_benchmark": {
            "name": "SWE-bench-Java Verified",
            "official_instances": 91,
            "evaluated_instances": 91,
            "repositories": 6,
            "excluded_instances": 0,
            "sources": ["BM25", "structural", "dense"],
            "configurations": [
                "Raw_BM25_entities",
                "BM25_projection",
                "Structural_projection",
                "Dense_projection",
                "MURAL_2src",
                "BM25_Dense",
                "Structural_Dense",
                "MURAL",
            ],
            "dense_encoder": "jinaai/jina-embeddings-v2-base-code@516f4baf13dec4ddddda8631e019b5737c8bc250",
            "fusion": "equal-weight reciprocal-rank fusion with k=60",
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
