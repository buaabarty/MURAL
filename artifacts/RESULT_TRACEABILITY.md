# Result Traceability

This note maps the retained MURAL result ledgers to the main manuscript and its
separately compiled supplementary material.

## Evaluation scope

### Python benchmark

- Benchmark: all 500 SWE-bench Verified instances.
- Query: original issue title/body.
- Code snapshot: official base commit.
- Evaluator-only data: official patch and deterministic target mapping.
- Excluded from ranking: benchmark hints, comments, the target repair pull
  request, patch text, linked repair commits, and future artifacts.
- Paired uncertainty: 10,000 bootstrap resamples with seed 7.
- Binary tests: two-sided exact McNemar.

The boundary audit is
`results/kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json`.

### Java benchmark

`inputs/java_cross_language_manifest_20260714.json` pins the complete
91-instance SWE-bench-Java Verified split from revision
`8bd202138a4ab9987daa77111c76a3e66af9f1c9`. No instance is excluded.
`results/java_cross_language_instances_20260714.jsonl` has one row per official
instance, and the verifier checks its ID-set hash against the manifest.

## Main manuscript

### Experimental setup

| Claim | Ledger |
| --- | --- |
| 500-instance target mapping | `results/tse_gt_mapping_v6.tsv` |
| Input boundary | `issue_comment_boundary.json` |
| GLM-5 repair protocol | `repair_protocol_glm5_20260715.json` |
| Localization prompt | `prompts/llm_fault_location_prompt.md` |
| Repair prompts | `prompts/glm5_repair_prompt.md` |

### RQ-1: controlled context construction

| Result | Ledger |
| --- | --- |
| BM25, BLUiR, CodeGraph, graph-only, KG-local | `results/path_mining_file_expansion_ablation_20260531.tsv` |
| BM25/KG local controls and MURAL-2 | `results/retrieve_then_localize_top20_20260711.tsv` |
| Main paired intervals and exact tests | `results/retrieve_then_localize_paired_20260711.tsv` |
| Per-instance Hit@20 disagreements | `results/retrieve_then_localize_disagreements_20260711.tsv` |
| First-stage ranked-file coverage | `results/ranked_file_source_coverage_20260711.tsv` |
| First-stage paired test | `results/ranked_file_source_paired_20260711.tsv` |
| Dense-local and MURAL-3 | `results/dense_third_source_summary_20260714.tsv` |
| Dense paired tests | `results/dense_third_source_paired_20260714.tsv` |
| Complete repository breakdown | `results/repository_localization_breakdown_20260715.tsv` |

### RQ-2: fixed-prefix fusion

| Result | Ledger |
| --- | --- |
| GLM-5 issue, KG-local, BM25-local, MURAL-2 | `results/retrieve_then_localize_top20_20260711.tsv` |
| GLM-5 paired tests | `results/retrieve_then_localize_paired_20260711.tsv` |
| CodeGraph tail control | `results/glm5_baseline_fusion_controls_top10_20260614.tsv` |
| Four released Qwen2.5-32B prefixes | `results/external_localizer_fusion_summary_20260715.tsv` |
| Released-prefix paired tests | `results/external_localizer_fusion_paired_20260715.tsv` |

### RQ-3: edit-target coverage

| Result | Ledger |
| --- | --- |
| Aggregate recall and complete coverage | `results/patch_derived_context_summary_20260702.tsv` and `.json` |
| Deterministic targets | `results/patch_derived_context_targets_20260702.json` |
| Paired intervals and exact tests | `results/edit_target_paired_stats_20260713.tsv` |

### RQ-4: official repair outcomes

| Result | Ledger |
| --- | --- |
| All 500 x 3 outcomes | `results/repair_glm5_outcomes_20260715.tsv` |
| Aggregate and paired statistics | `results/repair_glm5_summary_20260715.tsv` |
| Request and patch-hash audit | `results/repair_glm5_assembly_20260715.tsv` |
| Complete repository breakdown | `results/repository_repair_breakdown_20260715.tsv` |

The three fixed candidate pools resolve 112/500 (GLM-only), 134/500
(GLM+BM25-local), and 146/500 (GLM+MURAL-2). The paired MURAL-2 comparison
against GLM-only has 44 wins, 10 losses, a 95% interval of [4.0, 9.6]
percentage points, and exact McNemar p=3.39e-6.

## Supplementary material

| Analysis | Ledgers |
| --- | --- |
| Compact selector | `results/selector_simplification_{summary,paired,disagreements}_20260715.tsv` |
| RRF constant and weights | `results/rrf_sensitivity_{summary,paired,disagreements}_20260715.tsv` |
| Budgets 5/10/20/40 | `results/retrieve_then_localize_budget_{curve,paired,disagreements}_20260711.tsv` |
| Dense third source | `results/dense_third_source_{summary,paired,disagreements}_20260714.tsv` |
| Complete Java benchmark | `results/java_cross_language_*_20260714.*` |
| Context construction cost | `results/context_construction_cost_20260715.tsv` |
| Repair rendering | `results/repair_glm5_context_rendering_20260715.tsv` |
| Patch deduplication | `results/repair_glm5_prediction_mapping_20260715.tsv` and `repair_glm5_deduplication_summary_20260715.json` |
| External-artifact sensitivity | `results/time_boundary_external_artifact_sensitivity_20260531.tsv` |

## Reproduction commands

Commands below run from the full experiment workspace containing benchmark
checkouts and archived model outputs.

### Compact BM25-local and KG-local

```bash
python3 artifacts/scripts/export_ranked_file_seeds.py \
  --input-dir runs/text_baselines_nohints/2000 \
  --output-dir temp_run/bm25_top20_file_seeds \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --max-files 20 --support-mode count

python3 artifacts/scripts/export_path_mined_filelocal.py \
  --input-dir temp_run/bm25_top20_file_seeds \
  --output-dir temp_run/bm25_filelocal_compact \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --playground-root playground \
  --limit 50
```

The structural file records use the same second command. The compact key is the
default in `export_path_mined_filelocal.py`.

### MURAL-2 and MURAL-3

```bash
python3 artifacts/scripts/export_equal_rrf_fusion.py \
  --primary-dir temp_run/bm25_filelocal_compact \
  --secondary-dir temp_run/kg_filelocal_compact \
  --output-dir temp_run/mural_2src \
  --top-k 50 --rrf-k 60 --force

python3 artifacts/scripts/export_multi_source_rrf_fusion.py \
  --source BM25=temp_run/bm25_filelocal_compact \
  --source KG=temp_run/kg_filelocal_compact \
  --source Dense=temp_run/dense_filelocal_compact \
  --output-dir temp_run/mural_3src \
  --top-k 50 --rrf-k 60 --force
```

### Main localization and paired statistics

```bash
python3 artifacts/scripts/analyze_retrieve_localize_controls.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --top-k 20 \
  --group BM25_filelocal=temp_run/bm25_filelocal_compact \
  --group KG_filelocal=temp_run/kg_filelocal_compact \
  --group BM25_KG_RRF_filelocal=temp_run/mural_2src \
  --compare KG_filelocal=BM25_filelocal \
  --compare BM25_filelocal=BM25_KG_RRF_filelocal \
  --output-summary temp_run/retrieve_summary.tsv \
  --output-paired temp_run/retrieve_paired.tsv \
  --output-disagreements temp_run/retrieve_disagreements.tsv
```

### Selector simplification

```bash
python3 artifacts/scripts/export_selector_simplification.py \
  --input-dir temp_run/bm25_top20_file_seeds \
  --output-root temp_run/selector_simplification \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --playground-root playground \
  --limit 50
```

Evaluate the emitted directories with
`analyze_retrieve_localize_controls.py`. The reported `Expanded` and `Compact`
rows both reach 57.0 Hit@20.

### RRF sensitivity

Run `export_equal_rrf_fusion.py` with `--rrf-k {10,30,60,100}` and BM25/KG
weight pairs `{0.3/0.7,0.4/0.6,0.5/0.5,0.6/0.4,0.7/0.3}`, then evaluate each
directory with `analyze_retrieve_localize_controls.py`.

### Fixed-prefix construction

```bash
python3 artifacts/scripts/export_fixed_prefix_fusion.py \
  --primary-dir temp_run/eval_aliyun_glm5_issueonly \
  --secondary-dir temp_run/mural_2src \
  --output-dir temp_run/glm5_mural2_b20_p10 \
  --budget 20 --primary-prefix 10 --secondary-pool 20 --force
```

### Released localizers

```bash
python3 artifacts/scripts/evaluate_external_localizer_fusion.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --external-root temp_run/CoSIL-release/loc_to_patch_verified \
  --mural-dir temp_run/mural_2src \
  --output-summary temp_run/external_localizer_summary.tsv \
  --output-paired temp_run/external_localizer_paired.tsv
```

### Repository breakdowns

```bash
python3 artifacts/scripts/analyze_repository_breakdown.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --localization BM25-local=temp_run/bm25_filelocal_compact \
  --localization MURAL-2=temp_run/mural_2src \
  --localization MURAL-3=temp_run/mural_3src \
  --repair-outcomes artifacts/results/repair_glm5_outcomes_20260715.tsv \
  --output-localization temp_run/repository_localization.tsv \
  --output-repair temp_run/repository_repair.tsv
```

### Context-construction cost

```bash
python3 artifacts/scripts/analyze_context_construction_cost.py \
  --logs-glob 'logs/kg_verified_evidence_graph/*.log' \
  --run-dir runs/kg_verified_evidence_graph/tse_timesafe_main_20260529_v6 \
  --bm25-time temp_run/timing/bm25_filelocal.time \
  --rrf-time temp_run/timing/rrf.time \
  --output temp_run/context_construction_cost.tsv
```

### Java

```bash
python3 artifacts/scripts/evaluate_java_retrieve_localize.py \
  --dataset-dir temp_run/java_verified_dataset \
  --kg-seeds artifacts/inputs/java_kg_ranked_file_seeds_20260714.jsonl \
  --repos-dir temp_run/java_repositories \
  --cache-dir temp_run/java_entity_cache \
  --output-summary temp_run/java_summary.tsv \
  --output-paired temp_run/java_paired.tsv \
  --output-instances temp_run/java_instances.jsonl \
  --output-targets temp_run/java_targets.json
```

### Result verification

```bash
python3 artifacts/scripts/verify_paper_results.py
```
