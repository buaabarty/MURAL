# MURAL paper artifact

This directory contains the prompts, strict evaluators, frozen rankings,
article-facing result ledgers, and protocol manifest used by the manuscript and
its independently compiled supplement.

## Evaluation contract

Localization reads the original issue and official base commit. Official
patches are evaluator-only. Retrieval never reads the target repair record,
patch, linked repair commit, comments, benchmark hints, test outcomes, or later
repository artifacts.

The Python candidate unit is a synchronous module function, direct synchronous
class method, or simple module/class assignment. The independent target builder
maps changed regions to the same base-snapshot unit. A changed path containing a
region outside this contract receives an exact-file fallback, retained alongside
entity targets from other regions. Matching requires exact normalized path,
entity kind, and qualified symbol. The final mapping contains 1,044 targets:
836 functions or class methods, 32 assignments, and 176 file fallbacks. The Java
evaluation maps changed lines to declarations present in the official base commit;
its complete benchmark includes all 91 instances and six repositories.

Every Python comparison retains all 500 SWE-bench Verified instances. Confidence
intervals use 10,000 repository-clustered bootstrap resamples with seed 7;
binary paired contrasts use the two-sided exact McNemar test.

## Core scripts

- `build_strict_reference_targets.py`: independent Python-AST target builder.
- `evaluate_strict_reference_context.py`: exact localization evaluator.
- `evaluate_strict_external_localizers.py`: released-prefix completion.
- `evaluate_token_budget_context.py`: rendered-token packing.
- `entity_identity.py`: shared canonical entity identity and deduplication.
- `export_ranked_file_seeds.py`: ranked-file seed materialization.
- `export_entity_projection.py`: projection entry point.
- `export_path_mined_filelocal.py`: shared projection implementation.
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
- `evaluate_java_retrieve_localize.py`: complete Java evaluator.
- `build_submission_manifest.py`: protocol and digest manifest.
- `verify_paper_results.py`: end-to-end artifact check.

## Retained results

### Strict Python localization

- `results/strict_reference_targets_20260719.json`
- `results/strict_localization_{summary,instances,paired}_20260719.tsv`
- `results/strict_token_context_{summary,instances,paired}_20260719.tsv`
- `results/strict_token_packing_{summary,instances}_20260719.tsv`
- `results/strict_budget_b{5,10,20,40}_{summary,instances,paired}_20260719.tsv`
- `results/strict_selector_{summary,instances,paired}_20260719.tsv`
- `results/strict_prefix_tail_{summary,instances,paired}_20260719.tsv`
- `results/strict_external_localizer_{summary,instances,paired}_20260719.tsv`
- `results/strict_rrf_sensitivity_{summary,instances,paired}_20260719.tsv`
- `results/strict_mechanism_analysis_20260719.tsv`
- `results/strict_target_multiplicity_20260719.tsv`
- `results/strict_repository_robustness_20260719.tsv`
- `results/context_construction_cost_20260716.tsv`

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

Task C has 100 judgments over 80 instances, including 20 double-coded items.
The packet is preserved without relabeling or replacing any annotator-visible
window. It audits the main RQ-1 source-composition comparison: `MURAL` maps to
`MURAL_2src` (the `MURAL w/o Dense` row), and `BM25-local` maps to
`BM25_projection`. The exact 80-instance ranking snapshot is the sample-level
record for that main experiment.
`results/human_window_provenance_20260718.tsv` records the two anonymized
source-workbook SHA-256 values and 50 Task-C rows per annotator. A row-wise
source check found no mismatch across all 100 released judgments.

Tasks A and B retain both annotators' 80 construct judgments over 60 instances
and 120 support-role judgments over 100 candidate pairs. Evidence
adjudication binds the construct records to the current strict target ledger:
all 60 audited instances are covered, 26 entirely by exact entity targets and
34 through at least one explicit exact-file fallback. The support-role ledger
retains every independent label and the final B1--B4 evidence decision. Its 100
adjudicated pairs contain 68 irrelevant, 18 weak, 12 strong, and two required
candidates. The two source-workbook SHA-256 values and 100 Task-A/B rows per
annotator are recorded in `human_evidence_audit_provenance_20260721.tsv`.
Run `python3 scripts/analyze_human_evidence_audit.py` to recompute the counts and
shared-item reliability values.

The Java evaluation retains all 91 instances pinned by
`inputs/java_cross_language_manifest_20260714.json`.

## Frozen rankings and provenance

`frozen/strict_rankings_top50_20260719.jsonl.gz` contains Top-50 candidates for
BM25 projection, the structural adapter, dense projection, two-source MURAL, and
three-source MURAL for all 500 Python instances.
`frozen/source_rankings_manifest_20260719.json` records the construction and
canonical-identity contract for those five rankings.
`frozen/external_localizers_manifest.json` records the upstream repository commit
and SHA-256 values for released localizer files.

```bash
python3 artifacts/scripts/build_submission_manifest.py
python3 artifacts/scripts/verify_paper_results.py
```
