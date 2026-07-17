# MURAL paper artifact

This directory contains the frozen inputs, prompts, evaluators, and retained
result ledgers used by the MURAL manuscript and separately compiled supplement.
Results not cited by either document are excluded.

## Evaluation boundary

For all localization runs, the query is the original issue title and body and
the code snapshot is the official base commit. Official patches are loaded only
by the evaluator to derive file and entity targets. The ranking pipeline does
not read patch text, repair commits, benchmark hints, or future artifacts.

Paired intervals use 10,000 bootstrap resamples with seed 7. Binary paired
contrasts use the two-sided exact McNemar test.

## Main scripts

- `export_ranked_file_seeds.py`: adapts ranked retrieval output to ranked files.
- `export_entity_projection.py`: shared Entity Projection implementation.
- `export_multi_source_rrf_fusion.py`: equal-weight multi-source entity fusion.
- `export_fixed_prefix_fusion.py`: prefix-preserving context completion.
- `analyze_retrieve_localize_controls.py`: localization metrics, paired
  intervals, and disagreement ledgers.
- `evaluate_patch_derived_context.py`: edit-target recall and complete coverage.
- `evaluate_external_localizer_fusion.py`: released-localizer augmentation.
- `evaluate_java_retrieve_localize.py`: complete Java adapter evaluation.
- `run_repair_profile_batch.py`: fixed GLM-5.2 generation protocol.
- `assemble_repair_profile_predictions.py` and
  `deduplicate_repair_predictions.py`: prediction audit and exact prompt-and-patch reuse.
- `select_repair_retry_ids.py`: provider-failure-only batch resumption.
- `audit_repair_context_rendering.py`: executed candidate and prompt audit.
- `collect_swebench_reports.py`, `materialize_repair_variant_reports.py`, and
  `analyze_repair_outcomes.py`: official SWE-bench outcome analysis.
- `verify_paper_results.py`: exact inventory and value verification.

## Retained result inventory

### Target mapping and information boundary

- `results/tse_gt_mapping_v6.tsv`
- `results/patch_derived_context_targets_20260702.json`
- `results/kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json`
- `results/time_boundary_external_artifact_sensitivity_20260531.tsv`

### Python localization and context coverage

- `results/mural_localization_{summary,paired,disagreements}_20260716.tsv`
- `results/mural_edit_target_summary_20260716.tsv`
- `results/mural_edit_target_summary_20260716.json`
- `results/mural_edit_target_paired_20260716.tsv`
- `results/mural_repository_localization_20260716.tsv`

### Supplementary controls

- `results/mural_budget_{summary,paired,disagreements}_20260716.tsv`
- `results/mural_rrf_sensitivity_{summary,paired,disagreements}_20260716.tsv`
- `results/mural_external_localizer_{summary,paired,disagreements}_20260716.tsv`
- `results/context_construction_cost_20260716.tsv`

### Complete Java benchmark

- `results/java_cross_language_summary_20260714.tsv`
- `results/java_cross_language_paired_20260714.tsv`
- `results/java_cross_language_instances_20260714.jsonl`
- `results/java_cross_language_targets_20260714.json`

The Java benchmark contains all 91 official instances. Its available adapters
are lexical and structural; it tests the shared projection and fusion interface
without representing the default three-source Python configuration. The
manifest pins the compact selector version plus evaluator and output hashes.

### Repair rendering protocol

- `prompts/glm52_repair_prompt.md`
- `results/repair_glm52_context_rendering_20260716.tsv`

### End-to-end repair

- `results/repair_glm52_assembly_20260716.tsv`
- `results/repair_glm52_prediction_mapping_20260716.tsv`
- `results/repair_glm52_deduplication_summary_20260716.json`
- `results/repair_glm52_outcomes_20260716.tsv`
- `results/repair_glm52_summary_20260716.tsv`
- `results/mural_repository_repair_20260716.tsv`

The repair summary reports counts and benchmark-level yields for nonempty,
applicable, and test-resolved patches, plus paired bootstrap intervals and
exact McNemar tests for all three binary outcomes. Here, applicable means that
the official harness records `patch_successfully_applied=1`; resolved means
that the official test oracles accept the prediction. The
`applicable_given_nonempty_percent` field separately reports application
success conditional on a nonempty prediction. Every benchmark-level yield
retains all 500 instances in its denominator.

## Verification

```bash
python3 artifacts/scripts/verify_paper_results.py --scope all
```

The verifier fails on a missing, extra, duplicate, incomplete, hash-inconsistent,
or numerically inconsistent paper-facing ledger.
