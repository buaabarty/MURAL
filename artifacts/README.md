# MURAL paper artifact

This directory contains the prompts, strict evaluators, frozen rankings,
article-facing result ledgers, and protocol manifest used by the manuscript and
its independently compiled supplement.

## Canonical paper-facing ledgers

- `results/paper_main_results_20260722.tsv` contains the rows and one-decimal
  values displayed in the main Top-20 localization table. In particular,
  `MURAL (BM25 + Structural)` maps to `MURAL_2src`, while `MURAL` is the three-source
  configuration.
- `results/paper_dataset_profile_20260722.tsv` contains the target strata and
  multiplicity counts displayed in the dataset table.

Both files are generated from the strict result ledgers by
`scripts/build_paper_ledgers.py`. The development ledgers
`retrieve_then_localize_top20_20260711.tsv` and `tse_gt_mapping_v6.tsv` are
superseded and excluded from the paper-facing inventory.

## Evaluation contract

Localization reads the original issue and official base commit. Official
patches are evaluator-only. Retrieval never reads the target repair record,
patch, linked repair commit, comments, benchmark hints, test outcomes, or later
repository artifacts. Historical issue or pull-request text is admitted only
when both its creation and last-modification timestamps precede the target
issue's creation time.

The Python candidate unit is a synchronous module function, direct synchronous
class method, or simple module/class assignment. The independent target builder
maps changed regions to the same base-snapshot unit. A changed path containing a
region outside this contract receives an exact-file fallback, retained alongside
entity targets from other regions. Matching requires exact normalized path,
entity kind, and qualified symbol. The final mapping contains 1,044 targets:
836 functions or class methods, 32 assignments, and 176 file fallbacks. The Java
evaluation maps changed lines to declarations present in the official base commit;
its complete benchmark includes all 91 instances and six repositories.

`RefComplete` denotes complete matching of these evaluator identities. Exact-file
fallbacks contribute path identity only. Rendered changed-line recall and
`CompleteLine` separately measure whether the final source excerpts contain the
base-side changed lines.

Context records distinguish three objects: ranked candidates before rendering,
metadata-visible candidates shown by path and symbol, and source-bearing
candidates whose concrete excerpts enter the model input. Controlled RQ-1 and
RQ-2 token analyses use deterministic strict-prefix packing. The archived RQ-3
prompts and repair execution use the fixed rank-banded renderer, which may
show metadata for more candidates than it supplies with excerpts. Prompt
identity and changed-line metrics count only source-bearing candidates.

Every Python comparison retains all 500 SWE-bench Verified instances. Confidence
intervals use 10,000 repository-clustered bootstrap resamples with seed 7;
binary paired contrasts use the two-sided exact McNemar test. Exact sign-flip
tests enumerate all $2^{12}$ repository-cluster assignments for Hit@20 and
LineRecall at 4,000 tokens.

## Core scripts

- `build_paper_ledgers.py`: derives the canonical paper-facing tables from the strict ledgers.
- `build_strict_reference_targets.py`: independent Python-AST target builder.
- `evaluate_strict_reference_context.py`: exact localization evaluator.
- `evaluate_strict_external_localizers.py`: released-prefix completion with class-to-member granularity normalization.
- `export_external_localizer_completions.py`: matched completion rankings for released localizer prefixes.
- `evaluate_token_budget_context.py`: controlled strict-prefix rendered-token packing.
- `export_static_structural_ablation.py`: history-free structural replay.
- `analyze_primary_cluster_randomization.py`: exact repository-cluster sign-flip tests.
- `analyze_target_fallback_evidence.py`: exact-file fallback evidence accounting.
- `analyze_token_candidate_exhaustion.py`: pre-render candidate-cap accounting.
- `analyze_human_window_strata.py`: unique-instance audit decisions by exact-hit stratum.
- `entity_identity.py`: shared canonical entity identity and deduplication.
- `export_ranked_file_seeds.py`: ranked-file seed materialization.
- `export_entity_projection.py`: projection entry point.
- `export_path_mined_filelocal.py`: shared projection implementation.
- `export_file_primary_ranking.py`: file-primary ordering control over a fixed projected pool.
- `export_file_rrf_seeds.py`: file-level RRF followed by projection control.
- `analyze_reference_coverage_strata.py`: entity and changed-line coverage by target stratum.
- `fuse_path_mined_with_kg.py`: canonical union of native structural and projected entities.
- `export_multi_source_rrf_fusion.py`: deterministic multi-source RRF.
- `export_fixed_prefix_fusion.py`: prefix-preserving completion.
- `export_selector_simple_baselines.py`: selector controls.
- `export_compact_rankings.py`: compact ranking export.
- `materialize_compact_rankings.py`: evaluator-compatible reconstruction.
- `analyze_source_bearing_prompt_coverage.py`: rendered-prompt audit.
- `freeze_human_window_rankings.py`: freezes the exact rankings shown to annotators.
- `verify_human_window_binding.py`: verifies each rendered A/B window byte-for-byte.
- `evaluate_human_window_exact_hits.py`: evaluates those exact windows against strict targets.
- `analyze_human_strict_alignment.py`: re-stratifies judgments from exact-window hits.
- `analyze_stratified_context_findings.py`: opportunity-matched, multiplicity, rank-shift, repository, and instance-level audit statistics.
- `plot_paper_findings.py`: publication figures for token-budget robustness and target-scope coverage.
- `analyze_clustered_repair_stats.py`: clustered repair statistics.
- `analyze_source_combinations.py`: all single-source and pairwise source combinations.
- `analyze_changed_line_strata.py`: changed-line coverage by patch-hunk type.
- `audit_structural_temporal_provenance.py`: strict created/last-modified provenance audit.
- `evaluate_java_retrieve_localize.py`: complete Java evaluator.
- `build_submission_manifest.py`: protocol and digest manifest.
- `verify_paper_results.py`: end-to-end artifact check.

## Retained results

### Strict Python localization

- `results/paper_main_results_20260722.tsv`
- `results/paper_dataset_profile_20260722.tsv`
- `results/strict_reference_targets_20260719.json`
- `results/strict_localization_{summary,instances,paired}_20260719.tsv`
- `results/strict_token_context_{summary,instances,paired}_20260719.tsv`
- `results/strict_token_packing_{summary,instances}_20260719.tsv`
- `results/strict_budget_b{5,10,20,40}_{summary,instances,paired}_20260719.tsv`
- `results/strict_selector_{summary,instances,paired}_20260719.tsv`
- `results/strict_prefix_tail_{summary,instances,paired}_20260719.tsv`
- `results/strict_external_localizer_{summary,instances,paired}_20260722.tsv`
- `results/external_localizer_resolution_20260722.tsv`
- `results/external_token_completion_{summary,instances,paired}_20260722.tsv`
- `results/external_token_completion_packing_{summary,instances}_20260722.tsv`
- `results/external_token_completion_resolution_20260722.tsv`
- `results/strict_rrf_sensitivity_{summary,instances,paired}_20260719.tsv`
- `results/strict_mechanism_analysis_20260719.tsv`
- `results/strict_target_multiplicity_20260719.tsv`
- `results/strict_repository_robustness_20260719.tsv`
- `results/context_construction_cost_20260716.tsv`

### Complete source composition and robustness

- `results/source_combinations_top20_{summary,instances,paired}_20260722.tsv`
- `results/source_combinations_token4000_{summary,instances,paired}_20260722.tsv`
- `results/source_combinations_token4000_packing_{summary,instances}_20260722.tsv`
- `results/source_combinations_glm_prefix_{summary,instances,paired}_20260722.tsv`
- `results/source_combination_attribution_20260722.tsv`
- `results/structural_temporal_provenance_20260722.json`
- `results/structural_temporal_provenance_instances_20260722.tsv`
- `results/structural_static_ablation_{summary,instances}_20260722.*`
- `results/structural_static_top20_{summary,instances,paired}_20260722.tsv`
- `results/structural_static_token4000_{summary,instances,paired}_20260722.tsv`
- `results/structural_static_token4000_packing_{summary,instances}_20260722.tsv`
- `results/primary_cluster_signflip_{summary,repositories}_20260722.tsv`
- `results/target_fallback_evidence_{summary,instances}_20260722.tsv`
- `results/token_candidate_exhaustion_summary_20260722.tsv`
- `structural_temporal_metadata_20260722.json`

These ledgers enumerate all three single sources, all three pairwise fusions,
and full MURAL at Top-20, under 4,000 rendered tokens, and after the fixed
GLM-5 prefix. The temporal audit verifies both creation and last-modification
times for every historical artifact observed in the frozen structural paths.
The static replay removes all history-derived candidates before RRF and records
the resulting Top-20 and 4,000-token metrics.

### Architecture and rendered-line controls

- `results/entity_ordering_control_{summary,instances,paired}_20260721.tsv`
- `results/architecture_control_{summary,instances,paired}_20260721.tsv`
- `results/reference_coverage_strata_4000_20260721.tsv`
- `results/line_coverage_{summary,instances}_4000_20260721.tsv`
- `results/changed_line_strata_{4000,paired_4000}_20260722.tsv`
- `results/changed_line_hunk_profile_20260722.tsv`
- `frozen/architecture_control_rankings_20260721.jsonl.gz`
- `frozen/architecture_control_manifest_20260721.json`

The ordering control holds the BM25 files and projected candidates fixed. The
fusion-point control compares file-level RRF followed by one projection with
per-source projection followed by entity-level RRF.
### Repair prompts and official outcomes

- `results/source_bearing_prompt_{summary,instances,paired}_20260719.tsv`
- `results/repair_equal4000_strict_predictions_{bm25,mural}_20260719.jsonl`
- `results/repair_equal4000_strict_official_{bm25,mural}_20260719.jsonl`
- `results/repair_equal4000_strict_{outcomes,summary}_20260719.tsv`
- `results/repair_equal4000_clustered_paired_20260719.tsv`
- `results/repair_equal4000_strict_prediction_provenance_20260719.tsv`
- `results/repair_equal4000_strict_regeneration_{bm25,mural}_20260719.tsv`

Nonempty, applicable, and resolved retain 500 instances per context in the
denominator. The official rows are keyed by instance and patch SHA-256.

### Human and Java evaluations

- `results/human_window_{annotations,manifest,summary,agreement,provenance}_20260718.tsv`
- `results/human_window_items_20260718.json`
- `results/human_window_binding_20260719.tsv`
- `results/human_window_exact_instances_20260719.tsv`
- `results/human_window_strict_{judgments,summary}_20260719.tsv`
- `results/human_window_unique_strict_summary_20260719.tsv`
- `results/human_window_strata_{summary,instances}_20260722.tsv`
- `frozen/human_window_rankings_20260712.jsonl.gz`
- `frozen/human_window_rankings_manifest_20260719.json`
- `results/human_construct_{annotations_raw,adjudicated}_20260721.tsv`
- `results/human_support_{annotations_raw,adjudicated}_20260721.tsv`
- `results/human_evidence_audit_summary_20260721.{tsv,json}`
- `results/human_evidence_audit_provenance_20260721.tsv`
- `scripts/analyze_human_evidence_audit.py`
- `results/java_cross_language_{summary,paired}_20260714.tsv`
- `results/java_cross_language_instances_20260714.jsonl`
- `results/java_cross_language_targets_20260714.json`
- `results/repair_target_coverage_outcome_20260723.tsv`
- `results/repair_two_target_coverage_bins_20260723.tsv`
- `scripts/analyze_repair_target_coverage.py`
- repository-clustered coverage/outcome intervals use 10,000 resamples (seed 7)
- two-target coverage bins hold reference-target multiplicity fixed at exactly two

Task C has 100 judgments over 80 instances, including 20 double-coded items.
The packet is preserved without relabeling or replacing any annotator-visible
window. It audits the main RQ-1 source-composition comparison: `MURAL` maps to
`MURAL_2src` (the `MURAL (BM25 + Structural)` row), and `BM25-local` maps to
`BM25_projection`. The exact 80-instance ranking snapshot is the sample-level
record for that main experiment.
`results/human_window_provenance_20260718.tsv` records the two anonymized
source-workbook SHA-256 values and 50 Task-C rows per annotator. A row-wise
source check found no mismatch across all 100 released judgments.

Task A retains both annotators' 80 construct judgments over 60 instances.
Evidence adjudication binds these records to the current strict target ledger:
all 60 audited instances are covered, 26 entirely by exact entity targets and
34 through at least one explicit exact-file fallback. The two source-workbook
SHA-256 values are recorded in
`human_evidence_audit_provenance_20260721.tsv`. The release also preserves the
Task-B annotations as auxiliary records; manuscript findings do not use their
labels.

The Java evaluation retains all 91 instances pinned by
`inputs/java_cross_language_manifest_20260714.json` and reports raw BM25,
all three projected single sources, all three pairwise fusions, and the full
three-source MURAL configuration.

## Frozen rankings and provenance

`frozen/strict_rankings_top50_20260719.jsonl.gz` contains Top-50 candidates for
BM25 projection, the structural adapter, dense projection, two-source MURAL, and
three-source MURAL for all 500 Python instances.
`frozen/source_rankings_manifest_20260719.json` records the construction and
canonical-identity contract for those five rankings. The two missing pairwise
rankings are deterministically derived from the same frozen single-source
rankings, and their complete evaluation ledgers are retained above.
`frozen/architecture_control_rankings_20260721.jsonl.gz` contains file-primary,
file-fusion-then-projection, and projected-entity-RRF rankings for all 500
instances. `frozen/architecture_control_manifest_20260721.json` records their
construction, digest, and relation to the retained BM25-projection and MURAL
rankings.
`frozen/external_localizers_manifest.json` records the upstream repository commit
and SHA-256 values for released localizer files.

```bash
python3 artifacts/scripts/build_submission_manifest.py
python3 artifacts/scripts/verify_paper_results.py
```
