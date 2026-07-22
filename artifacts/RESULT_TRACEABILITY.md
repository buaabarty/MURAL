# Result traceability

All paths below are relative to `artifacts/`.

## Frozen scope

- Python: all 500 SWE-bench Verified instances.
- Java: all 91 SWE-bench-Java Verified instances across six repositories.
- Input: original issue plus official base commit.
- Default output: 20 distinct base-snapshot entities.
- Sources: BM25 and dense ranked-file projections plus the structural adapter, which canonically unifies native structural entities with its projected file branch.
- Fusion: equal-weight RRF with `k=60`.
- Statistics: 10,000 repository-clustered bootstrap resamples, seed 7;
  two-sided exact McNemar for binary paired contrasts; exact sign-flip tests
  over all 12 repository clusters for Hit@20 and LineRecall.
- Strict targets: 1,044 total, comprising 836 functions or class methods,
  32 assignments, and 176 exact-file fallbacks.
- Context objects: ranked candidates precede rendering; metadata-visible
  candidates appear by path and symbol; source-bearing candidates additionally
  contribute concrete excerpts.
- Renderers: controlled token analyses use strict-prefix packing; executed
  repair prompts use the fixed rank-banded renderer documented below.

## Claim-to-ledger map

| Manuscript evidence | Retained ledger |
| --- | --- |
| Dataset profile shown in the paper | `results/paper_dataset_profile_20260722.tsv`, derived from `results/strict_reference_targets_20260719.json` |
| Main Top-20 rows shown in the paper | `results/paper_main_results_20260722.tsv`, derived from `results/strict_localization_summary_20260719.tsv` |
| Strict target policy and per-instance targets | `results/strict_reference_targets_20260719.json` |
| Exact Top-20 rows, per-instance outcomes, paired statistics, and GLM-prefix rows | `results/strict_localization_{summary,instances,paired}_20260719.tsv` |
| Controlled strict-prefix rendered-token comparison | `results/strict_token_context_{summary,instances,paired}_20260719.tsv` |
| All single-source, pairwise, and three-source combinations at Top-20, 4,000 tokens, and after the GLM-5 prefix | `results/source_combinations_*_20260722.tsv`, `results/source_combination_attribution_20260722.tsv` |
| Packing, truncation, and changed-line coverage | `results/strict_token_packing_{summary,instances}_20260719.tsv` |
| Insertion/deletion/mixed changed-line analysis | `results/changed_line_hunk_profile_20260722.tsv`, `results/changed_line_strata_*_20260722.tsv` |
| Selector controls | `results/strict_selector_{summary,instances,paired}_20260719.tsv` |
| File-primary versus entity-primary ordering | `results/entity_ordering_control_{summary,instances,paired}_20260721.tsv` |
| File-level versus entity-level fusion and native structural branch | `results/architecture_control_{summary,instances,paired}_20260721.tsv` |
| Entity and rendered changed-line coverage by target stratum | `results/reference_coverage_strata_4000_20260721.tsv`, `results/line_coverage_{summary,instances}_4000_20260721.tsv` |
| Complete GLM-prefix tail controls | `results/strict_prefix_tail_{summary,instances,paired}_20260719.tsv` |
| Released localizer completion and granularity normalization | `results/strict_external_localizer_{summary,instances,paired}_20260722.tsv`, `results/external_localizer_resolution_20260722.tsv` |
| Matched 4,000-token completion across four released localizers | `results/external_token_completion_{summary,instances,paired}_20260722.tsv`, `results/external_token_completion_packing_{summary,instances}_20260722.tsv` |
| Entity budgets 5, 10, 20, and 40 | `results/strict_budget_b*_{summary,instances,paired}_20260719.tsv` |
| RRF sensitivity | `results/strict_rrf_sensitivity_{summary,instances,paired}_20260719.tsv` |
| Opportunity-matched entity selection and shared-hit rank shifts | `results/strict_mechanism_analysis_20260719.tsv` |
| Target-multiplicity coverage analysis | `results/strict_target_multiplicity_20260719.tsv` |
| Repository and leave-one-repository-out effects | `results/strict_repository_robustness_20260719.tsv` |
| Executed source-bearing prompts | `results/source_bearing_prompt_{summary,instances,paired}_20260719.tsv` |
| Strict repair predictions and official outcomes | `results/repair_equal4000_strict_*_20260719.*` |
| Clustered repair intervals | `results/repair_equal4000_clustered_paired_20260719.tsv` |
| Strict structural-artifact temporal provenance | `results/structural_temporal_provenance_20260722.json`, `results/structural_temporal_provenance_instances_20260722.tsv`, `structural_temporal_metadata_20260722.json` |
| Static-only structural replay | `results/structural_static_ablation_{summary,instances}_20260722.*`, `results/structural_static_top20_*_20260722.tsv`, `results/structural_static_token4000_*_20260722.tsv` |
| Exact repository-cluster sign-flip tests | `results/primary_cluster_signflip_{summary,repositories}_20260722.tsv` |
| Exact-file fallback evidence | `results/target_fallback_evidence_{summary,instances}_20260722.tsv` |
| Token candidate-cap exhaustion | `results/token_candidate_exhaustion_summary_20260722.tsv` |
| Patch-grounded target-consistency judgments and agreement | `results/human_window_*_20260718.*` |
| Exact annotator-visible audit rankings | `frozen/human_window_rankings_20260712.jsonl.gz` |
| Audit window-to-source binding | `results/human_window_binding_20260719.tsv` |
| Exact-window strict evaluation | `results/human_window_exact_instances_20260719.tsv` |
| Strict re-stratification of those judgments | `results/human_window_strict_*_20260719.tsv` |
| Unique-instance strict judgment alignment | `results/human_window_unique_strict_summary_20260719.tsv`, `results/human_window_strata_{summary,instances}_20260722.tsv` |
| Task-A construct audit | `results/human_construct_*_20260721.tsv` |
| Task-B support-role audit | `results/human_support_*_20260721.tsv` |
| Evidence-audit summary and provenance | `results/human_evidence_audit_*_20260721.*` |
| Complete Java evaluation | `results/java_cross_language_*_20260714.*` |
| Context-construction time | `results/context_construction_cost_20260716.tsv` |

## Reproduce the frozen source rows

Materialize the retained Top-50 ranking ledger:

```bash
python3 scripts/materialize_compact_rankings.py \
  --input frozen/strict_rankings_top50_20260719.jsonl.gz \
  --output-root ../temp_run/mural_strict_rankings
```

Recompute the five retained standalone source rows:

```bash
python3 scripts/evaluate_strict_reference_context.py \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --targets results/strict_reference_targets_20260719.json \
  --row BM25_projection=../temp_run/mural_strict_rankings/BM25_projection \
  --row Structural_adapter=../temp_run/mural_strict_rankings/Structural_adapter \
  --row Dense_projection=../temp_run/mural_strict_rankings/Dense_projection \
  --row MURAL_2src=../temp_run/mural_strict_rankings/MURAL_2src \
  --row MURAL=../temp_run/mural_strict_rankings/MURAL \
  --compare BM25_projection=MURAL \
  --compare Dense_projection=MURAL \
  --compare MURAL_2src=MURAL \
  --top-k 20 --bootstrap 10000 --seed 7 \
  --output-summary ../temp_run/strict_source_summary.tsv \
  --output-instances ../temp_run/strict_source_instances.tsv \
  --output-paired ../temp_run/strict_source_paired.tsv
```

The verifier compares these frozen-source values with the article-facing
localization ledger. `scripts/analyze_source_combinations.py` evaluates the
remaining pairwise combinations and records leave-one-source-out and
single-source-exclusive attribution from these same instance ledgers.

## Reproduce the architecture controls

Materialize the compact control rankings:

```bash
python3 scripts/materialize_compact_rankings.py \
  --input frozen/architecture_control_rankings_20260721.jsonl.gz \
  --output-root ../temp_run/mural_architecture_controls
```

Recompute the fixed-pool ordering comparison:

```bash
python3 scripts/evaluate_strict_reference_context.py \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --targets results/strict_reference_targets_20260719.json \
  --row FilePrimary=../temp_run/mural_architecture_controls/FilePrimary \
  --row EntityPrimary=../temp_run/mural_strict_rankings/BM25_projection \
  --compare FilePrimary=EntityPrimary --top-k 20 --bootstrap 10000 --seed 7 \
  --output-summary ../temp_run/entity_ordering_summary.tsv \
  --output-instances ../temp_run/entity_ordering_instances.tsv \
  --output-paired ../temp_run/entity_ordering_paired.tsv
```

Recompute the fusion-point and native-structural comparison:

```bash
python3 scripts/evaluate_strict_reference_context.py \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --targets results/strict_reference_targets_20260719.json \
  --row FileFusionProjection=../temp_run/mural_architecture_controls/FileFusionProjection \
  --row ProjectedEntityRRF=../temp_run/mural_architecture_controls/ProjectedEntityRRF \
  --row MURAL=../temp_run/mural_strict_rankings/MURAL \
  --compare FileFusionProjection=ProjectedEntityRRF \
  --compare ProjectedEntityRRF=MURAL --top-k 20 --bootstrap 10000 --seed 7 \
  --output-summary ../temp_run/architecture_summary.tsv \
  --output-instances ../temp_run/architecture_instances.tsv \
  --output-paired ../temp_run/architecture_paired.tsv
```

The retained compact-ranking digest and control definitions are recorded in
`frozen/architecture_control_manifest_20260721.json`.

## Reproduce rendered changed-line coverage

Pack the retained BM25 and MURAL rankings with the controlled strict-prefix renderer:

```bash
python3 scripts/evaluate_token_budget_context.py \
  --source BM25=../temp_run/mural_strict_rankings/BM25_projection \
  --source MURAL=../temp_run/mural_strict_rankings/MURAL \
  --compare BM25=MURAL --budget 4000 \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --dataset-file SWE_BENCH_VERIFIED_ARROW \
  --targets results/strict_reference_targets_20260719.json \
  --output-root ../temp_run/line4000 \
  --output-summary ../temp_run/line4000_summary.tsv \
  --output-paired ../temp_run/line4000_paired.tsv \
  --output-instances ../temp_run/line4000_instances.tsv \
  --output-packing-summary ../temp_run/line4000_packing_summary.tsv \
  --output-packing-instances ../temp_run/line4000_packing_instances.tsv \
  --max-candidates 50 --bootstrap-iters 10000 --seed 7
```

Compute entity and changed-line metrics separately for entity-only, mixed, and
file-only reference strata:

```bash
python3 scripts/analyze_reference_coverage_strata.py \
  --targets results/strict_reference_targets_20260719.json \
  --row BM25=../temp_run/line4000/BM25_t4000 \
  --row MURAL=../temp_run/line4000/MURAL_t4000 \
  --budget-label 4000-token \
  --packing-instances ../temp_run/line4000_packing_instances.tsv \
  --output ../temp_run/reference_coverage_strata_4000.tsv
```

## Regenerate source rankings

Generate BM25 and dense entity rankings from the original problem statement and
official base-commit repositories. Benchmark hints are excluded by default:

```bash
python3 scripts/export_text_baselines.py \
  --instance-ids frozen/swebench_verified_ids_20260719.txt \
  --dataset-arrow SWE_BENCH_VERIFIED_ARROW \
  --repos-dir BASE_COMMIT_REPOSITORIES \
  --output SOURCE_RUNS --top-k 50 --fusion-depth 200
```

Materialize ranked-file seeds from the retained runs, then pass both through the
shared projection:

```bash
python3 scripts/export_ranked_file_seeds.py \
  --input-dir RUN_ENTITY_RANKINGS \
  --output-dir FILE_SEEDS \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --max-files 20 --support-mode count

python3 scripts/export_entity_projection.py \
  --input-dir FILE_SEEDS \
  --output-dir PROJECTED_RANKINGS \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --playground-root BENCHMARK_CHECKOUTS --limit 50
```

The retained source-generation entry points are
`scripts/export_text_baselines.py`, `scripts/run_text_baselines.py`, and
`scripts/export_dense_filefirst.py`. The dense encoder revision is pinned in
the script and submission manifest. Construct the structural adapter by taking
the canonical minimum-rank union of its native entity ranking and projected
file branch:

```bash
python3 scripts/fuse_path_mined_with_kg.py   --kg-dir STRUCTURAL_NATIVE   --path-mined-dir STRUCTURAL_PROJECTED   --output-dir STRUCTURAL_ADAPTER   --ids-file frozen/swebench_verified_ids_20260719.txt --limit 50
```

Fuse the canonical adapter rankings:

```bash
python3 scripts/export_multi_source_rrf_fusion.py   --source BM25=BM25_PROJECTED   --source Structural=STRUCTURAL_ADAPTER   --source Dense=DENSE_PROJECTED   --output-dir MURAL_PROJECTED   --top-k 50 --rrf-k 60 --force
```

The exact source definitions and frozen-ranking digest are recorded in
`frozen/source_rankings_manifest_20260719.json`.

## Released localizers

External source identity is frozen in
`frozen/external_localizers_manifest.json`.

```bash
python3 scripts/evaluate_strict_external_localizers.py \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --targets results/strict_reference_targets_20260719.json \
  --external-root RELEASED_LOCALIZER_FILES \
  --mural-dir MURAL_PROJECTED \
  --workspace-root BENCHMARK_CHECKOUTS \
  --top-k 20 --primary-prefix 10 \
  --bootstrap 10000 --seed 7 \
  --output-summary strict_external_summary.tsv \
  --output-instances strict_external_instances.tsv \
  --output-paired strict_external_paired.tsv
```

For the equal-token comparison, first export the six completion strategies per
localizer and then run the common renderer:

```bash
python3 scripts/export_external_localizer_completions.py \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --targets results/strict_reference_targets_20260719.json \
  --external-root RELEASED_LOCALIZER_FILES \
  --rankings-archive frozen/strict_rankings_top50_20260719.jsonl.gz \
  --workspace-root BENCHMARK_CHECKOUTS \
  --output-root ../temp_run/external_completion \
  --primary-prefix 10 --max-candidates 50

python3 scripts/evaluate_token_budget_context.py \
  --source CoSIL_MURAL=../temp_run/external_completion/CoSIL__MURAL \
  --source CoSIL_Dense=../temp_run/external_completion/CoSIL__Dense \
  --compare CoSIL_Dense=CoSIL_MURAL --budget 4000 \
  --ids-file frozen/swebench_verified_ids_20260719.txt \
  --dataset-file SWE_BENCH_VERIFIED_ARROW \
  --targets results/strict_reference_targets_20260719.json \
  --output-root ../temp_run/external_packed \
  --output-summary ../temp_run/external_summary.tsv \
  --output-paired ../temp_run/external_paired.tsv \
  --output-instances ../temp_run/external_instances.tsv
```

## Prompt and repair provenance

`results/source_bearing_prompt_instances_20260719.tsv` records the
SHA-256 of every executed prompt and the exact source-bearing entities retained
by the renderer. The executed renderer reserves excerpts for up to four
candidates from ranks 1 to 10 and four from ranks 11 to 20, with at most two
excerpts per file in each band; other retained candidates remain metadata-only.
Strict predictions and official evaluations are stored
separately for BM25 and MURAL. The provenance ledger records whether each prompt
and patch changed during canonical-identity regeneration; an official outcome
is reused only when instance and patch SHA-256 are identical.

Recompute clustered repair statistics:

```bash
python3 scripts/analyze_clustered_repair_stats.py \
  --outcomes results/repair_equal4000_strict_outcomes_20260719.tsv \
  --baseline bm25 --treatment mural --bootstrap 10000 --seed 7 \
  --output ../temp_run/repair_clustered.tsv
```

Hosted generation reads `AUTODL_API_KEY` from the environment. No credential is
stored in the artifact.

## Human audit

```bash
python3 scripts/verify_human_window_binding.py \
  --items results/human_window_items_20260718.json \
  --rankings frozen/human_window_rankings_20260712.jsonl.gz \
  --output-binding ../temp_run/human_window_binding.tsv

python3 scripts/evaluate_human_window_exact_hits.py \
  --items results/human_window_items_20260718.json \
  --rankings frozen/human_window_rankings_20260712.jsonl.gz \
  --targets results/strict_reference_targets_20260719.json \
  --output ../temp_run/human_window_exact_instances.tsv

python3 scripts/analyze_human_strict_alignment.py \
  --annotations results/human_window_annotations_20260718.tsv \
  --strict-instances ../temp_run/human_window_exact_instances.tsv \
  --output-judgments ../temp_run/human_strict_judgments.tsv \
  --output-summary ../temp_run/human_strict_summary.tsv
```

```bash
python3 scripts/analyze_human_evidence_audit.py

python3 scripts/analyze_human_window_strata.py \
  --judgments results/human_window_strict_judgments_20260719.tsv \
  --audit-instances results/human_window_exact_instances_20260719.tsv \
  --output-summary ../temp_run/human_strata_summary.tsv \
  --output-instances ../temp_run/human_strata_instances.tsv
```

The raw annotations and randomized A/B assignment remain exactly as supplied
to the annotators. They audit the main RQ-1 `BM25_projection` versus
`MURAL_2src` comparison. Strict alignment is computed from the exact windows
the annotators inspected. The accompanying ledgers retain all Task-A
construct and Task-B support-role judgments, bind Task A to the current strict
target ledger, and record the evidence-adjudicated Task-B labels without
overwriting either annotator's original decisions.

## Regenerate the stratified analyses

```bash
python3 scripts/analyze_stratified_context_findings.py \
  --targets results/strict_reference_targets_20260719.json \
  --localization-instances results/strict_localization_instances_20260719.tsv \
  --human-judgments results/human_window_strict_judgments_20260719.tsv \
  --bootstrap 10000 --seed 7 \
  --output-mechanisms results/strict_mechanism_analysis_20260719.tsv \
  --output-multiplicity results/strict_target_multiplicity_20260719.tsv \
  --output-repositories results/strict_repository_robustness_20260719.tsv \
  --output-human results/human_window_unique_strict_summary_20260719.tsv
```

## Regenerate the article figures

```bash
python3 scripts/plot_paper_findings.py \
  --token-summary results/strict_token_context_summary_20260719.tsv \
  --multiplicity results/strict_target_multiplicity_20260719.tsv \
  --output-dir ../temp_run/paper_figures
```

The command emits vector PDF and 300-dpi PNG versions of both figures.

## Final integrity gate

```bash
python3 scripts/build_submission_manifest.py
python3 scripts/verify_paper_results.py
```
