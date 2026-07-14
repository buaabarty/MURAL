# MURAL Submission Artifacts

This directory contains the files that directly support the MURAL manuscript
and its separately compiled supplementary material. The result ledgers under
`artifacts/results/` are restricted to reported rows and audit records.
Unreported diagnostics, obsolete ablations, partial shard metrics, and the
retired KG-only downstream repair study are not included.

The implementation package and several frozen result-row names predate the
MURAL framing. In retained ledgers, `KGCompass` denotes the manuscript's
`KG-local` source, `BM25+KG RRF file-local` denotes standalone MURAL, and
`GLM-5 + BM25+KG RRF file-local` denotes GLM-5+MURAL. Historical labels remain
unchanged so archived commands and checksums stay stable.

## Top-Level Files

- `motivating_case_django_15503.json`: evidence for the motivating example.
- `issue_comment_boundary.json`: input-boundary and leakage-audit note.
- `prompts/llm_fault_location_prompt.md`: verbatim LLM localization prompt,
  reproduced in the supplementary material.
- `RESULT_TRACEABILITY.md`: file-to-claim mapping and reproduction commands.
- `scripts/verify_paper_results.py`: strict result-inventory and value checker.
- `scripts/export_ranked_file_seeds.py`: converts any ranked code-entity output
  to source-labelled file records for the shared file-local selector; the
  defaults preserve the original BM25 export.
- `scripts/export_selector_ablation.py`: exports the Full selector and all five
  leave-one-signal-family-out variants while caching parsed source files.
- `scripts/export_fixed_prefix_fusion.py`: builds prefix-preserving context
  windows under a fixed output budget.
- `scripts/export_equal_rrf_fusion.py`: combines BM25-local and KG-local
  rankings with deterministic RRF; defaults reproduce equal weighting and
  optional source weights support the reported sensitivity sweep.
- `scripts/export_multi_source_rrf_fusion.py`: applies the same deterministic
  RRF contract to two or more named entity-ranking sources.
- `scripts/analyze_retrieve_localize_controls.py`: computes aggregate metrics,
  paired bootstrap intervals, exact McNemar tests, and disagreement records.
- `scripts/evaluate_patch_derived_context.py`: computes mapped edit-target
  recall and complete edit-target coverage.
- `scripts/analyze_edit_target_paired_stats.py`: computes paired bootstrap
  intervals and exact McNemar tests for the primary RQ-3 comparisons.
- `scripts/export_java_kg_file_seeds.py`: converts the archived Java structural
  source to the same ranked-file contract without retaining entity source text
  or path-level records.
- `scripts/evaluate_java_retrieve_localize.py`: rebuilds base-commit Java
  entities, applies BM25 and the shared selector, freezes rankings, and then
  maps official patches for the supplementary cross-language check.
- `inputs/java_cross_language_manifest_20260714.json` and
  `inputs/java_kg_ranked_file_seeds_20260714.jsonl`: provenance and the 91
  ranked-file inputs for the Java structural source.

## Main-Manuscript Ledgers

- `tse_gt_mapping_v6.tsv`: target-mapping summary for all 500 instances.
- `path_mining_file_expansion_ablation_20260531.tsv`: BM25, BLUiR, CodeGraph,
  graph-only KG, and KG-local controlled rows.
- `retrieve_then_localize_top20_20260711.tsv`: matched BM25/KG file-source,
  file-local, MURAL, and GLM-5 fixed-prefix rows.
- `retrieve_then_localize_paired_20260711.tsv`: paired deltas, bootstrap
  intervals, win/loss counts, and exact tests for the main comparisons.
- `retrieve_then_localize_disagreements_20260711.tsv`: per-instance Hit@20
  disagreement records for the reported source comparisons.
- `ranked_file_source_coverage_20260711.tsv` and
  `ranked_file_source_paired_20260711.tsv`: first-stage Top-20 file coverage.
- `glm5_baseline_fusion_controls_top10_20260614.tsv`: fixed-prefix CodeGraph and
  KG-local controls used in RQ-2.
- `patch_derived_context_summary_20260702.tsv` and `.json`: mapped edit-target
  coverage used in RQ-3.
- `patch_derived_context_targets_20260702.json`: deterministic edit-target
  cache used by the patch-derived evaluation.
- `edit_target_paired_stats_20260713.tsv`: paired uncertainty for edit-target
  recall and complete edit-target coverage in the primary RQ-3 comparisons.
- `time_boundary_external_artifact_sensitivity_20260531.tsv`: external-artifact
  sensitivity statement in threats to validity.
- `kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json`: final
  leakage-sentinel audit.

## Supplementary Ledgers

- `retrieve_then_localize_budget_curve_20260711.tsv` and
  `retrieve_then_localize_budget_paired_20260711.tsv`: budgets 5, 10, 20, and
  40 for KG-local, BM25-local, and MURAL tails.
- `selector_ablation_summary_20260714.tsv` and
  `selector_ablation_paired_20260714.tsv`: BM25-local Full and five
  leave-one-signal-family-out selector variants, including paired uncertainty
  and exact Hit@20 tests.
- `rrf_sensitivity_summary_20260714.tsv` and
  `rrf_sensitivity_paired_20260714.tsv`: four RRF constants and a symmetric
  five-setting BM25/KG weight sweep, with all variants paired against the
  predefined equal-weight (k=60) row.
- `dense_third_source_summary_20260714.tsv` and
  `dense_third_source_paired_20260714.tsv`: the Jina code-embedding source,
  its shared-selector output, two- and three-source MURAL, and GLM-5
  fixed-prefix controls with paired uncertainty and exact Hit@20 tests.
- `java_cross_language_summary_20260714.tsv` and
  `java_cross_language_paired_20260714.tsv`: the 91-instance
  Multi-SWE-bench Java check, including the BM25-to-BM25-local selector
  comparison and the two-source diagnostic.
- `java_cross_language_instances_20260714.jsonl` and
  `java_cross_language_targets_20260714.json`: the per-instance ranking ledger
  and deterministic patch-to-entity target cache for that Java check.

## Verifier

Run:

```bash
python3 artifacts/scripts/verify_paper_results.py
```

The verifier checks every retained main-manuscript and supplementary value. It
also fails when an unexpected file appears under `artifacts/results/`, which
keeps the public result inventory aligned with the submitted documents.
