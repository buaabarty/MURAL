# MURAL Submission Artifacts

This directory contains the source snapshots, prompts, inputs, and result
ledgers referenced by the MURAL manuscript and supplementary material.

Frozen names predate the MURAL framing:

- `KGCompass` means the `KG-local` source.
- `BM25+KG RRF file-local` means standalone MURAL-2.
- `GLM-5 + BM25+KG RRF file-local` means GLM-5+MURAL-2.

## Core files

- `motivating_case_django_15503.json`: motivating-example evidence.
- `issue_comment_boundary.json`: evaluated information boundary.
- `repair_protocol_glm5_20260715.json`: endpoint, decoding, context-rendering,
  retry, deduplication, and official-test contracts for RQ-4.
- `prompts/llm_fault_location_prompt.md`: localization prompt.
- `prompts/glm5_repair_prompt.md`: repair system and user templates.
- `RESULT_TRACEABILITY.md`: claim-to-ledger mapping and rerun commands.

## Retained scripts

### Source adaptation and context construction

- `export_ranked_file_seeds.py`: converts ranked entity outputs to the shared
  ranked-file record.
- `export_path_mined_filelocal.py`: applies the compact selector based on title
  agreement, exact issue anchors, source file rank, boilerplate demotion, and
  stable source order.
- `export_equal_rrf_fusion.py`: deterministic two-source RRF.
- `export_multi_source_rrf_fusion.py`: deterministic RRF for two or more sources.
- `export_fixed_prefix_fusion.py`: preserves an existing prefix and fills the
  residual budget.
- `export_selector_simplification.py`: exports the expanded selector and the
  jointly simplified selector variants.

### Evaluation and statistics

- `analyze_retrieve_localize_controls.py`: aggregate metrics, paired bootstrap
  intervals, exact McNemar tests, and disagreement records.
- `analyze_ranked_file_sources.py`: first-stage ranked-file coverage.
- `evaluate_patch_derived_context.py`: mapped edit-target recall and complete
  edit-target coverage.
- `analyze_edit_target_paired_stats.py`: paired edit-target statistics.
- `evaluate_external_localizer_fusion.py`: four released Qwen2.5-32B prefixes
  with a MURAL-2 tail.
- `analyze_repository_breakdown.py`: complete localization and repair
  per-repository ledgers.
- `analyze_context_construction_cost.py`: structural, BM25-local, and RRF timing
  and memory summary.
- `verify_paper_results.py`: strict inventory and value checker.

### Repair and cross-language evaluation

- `run_repair_profile_batch.py`, `assemble_repair_profile_predictions.py`,
  `deduplicate_repair_predictions.py`, `collect_swebench_reports.py`,
  `materialize_repair_variant_reports.py`, and
  `analyze_repair_outcomes.py`: the fixed RQ-4 workflow.
- `audit_repair_context_rendering.py`: all 1,500 rendered-context audits.
- `export_java_kg_file_seeds.py` and
  `evaluate_java_retrieve_localize.py`: complete SWE-bench-Java Verified
  construction and evaluation.
- `audit_kg_leakage.py`: input-boundary audit.

## Main-manuscript ledgers

- `results/tse_gt_mapping_v6.tsv`
- `results/path_mining_file_expansion_ablation_20260531.tsv`
- `results/ranked_file_source_coverage_20260711.tsv`
- `results/ranked_file_source_paired_20260711.tsv`
- `results/retrieve_then_localize_top20_20260711.tsv`
- `results/retrieve_then_localize_paired_20260711.tsv`
- `results/retrieve_then_localize_disagreements_20260711.tsv`
- `results/glm5_baseline_fusion_controls_top10_20260614.tsv`
- `results/patch_derived_context_summary_20260702.tsv`
- `results/patch_derived_context_summary_20260702.json`
- `results/patch_derived_context_targets_20260702.json`
- `results/edit_target_paired_stats_20260713.tsv`
- `results/repair_glm5_summary_20260715.tsv`
- `results/repair_glm5_outcomes_20260715.tsv`
- `results/repair_glm5_assembly_20260715.tsv`

## Supplementary ledgers

- selector simplification:
  `selector_simplification_{summary,paired,disagreements}_20260715.tsv`;
- RRF sensitivity:
  `rrf_sensitivity_{summary,paired,disagreements}_20260715.tsv`;
- budget sensitivity:
  `retrieve_then_localize_budget_{curve,paired,disagreements}_20260711.tsv`;
- dense third source:
  `dense_third_source_{summary,paired,disagreements}_20260714.tsv`;
- released localizers:
  `external_localizer_fusion_{summary,paired}_20260715.tsv`;
- Java:
  `java_cross_language_{summary,paired,instances,targets}_20260714.*`;
- repositories:
  `repository_{localization,repair}_breakdown_20260715.tsv`;
- cost:
  `context_construction_cost_20260715.tsv`;
- repair audit:
  `repair_glm5_context_rendering_20260715.tsv`,
  `repair_glm5_prediction_mapping_20260715.tsv`, and
  `repair_glm5_deduplication_summary_20260715.json`;
- information boundary:
  `kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json` and
  `time_boundary_external_artifact_sensitivity_20260531.tsv`.

## Verification

```bash
python3 artifacts/scripts/verify_paper_results.py
```

The checker fails if a retained value changes or an unexpected file appears in
`artifacts/results/`.
