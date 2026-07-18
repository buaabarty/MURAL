# Result traceability

This note maps each retained MURAL result to one ledger and records the
full-workspace commands used to regenerate it.

## Evaluation scope

### SWE-bench Verified

- Population: all 500 official instances.
- Query: original issue title and body.
- Snapshot: official base commit.
- Ranking inputs: issue text, base-commit source, and source-specific retrieval
  records.
- Evaluator-only inputs: official patch and test oracles.
- Final localization budget: 20 distinct entities unless a budget table states
  otherwise.
- Uncertainty: 10,000 paired bootstrap resamples, seed 7.
- Binary paired tests: two-sided exact McNemar.

`results/tse_gt_mapping_v6.tsv` records the deterministic patch-to-entity
mapping. The information-boundary audit is
`results/kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json`.

### SWE-bench-Java Verified

`inputs/java_cross_language_manifest_20260714.json` pins all 91 official
instances from revision `8bd202138a4ab9987daa77111c76a3e66af9f1c9`.
`results/java_cross_language_instances_20260714.jsonl` contains exactly one row
per manifest ID. No instance is excluded.

## Claim-to-ledger map

### RQ-1 and RQ-2: bounded localization

| Result | Ledger |
| --- | --- |
| BM25, BLUiR, CodeGraph, structural, dense, source ablation, MURAL, and fixed-prefix GLM-5 rows | `results/mural_localization_summary_20260716.tsv` |
| Paired intervals and exact tests | `results/mural_localization_paired_20260716.tsv` |
| Per-instance Hit@20 changes | `results/mural_localization_disagreements_20260716.tsv` |
| Four released Qwen2.5-32B localizers | `results/mural_external_localizer_summary_20260716.tsv` |
| Released-localizer paired tests | `results/mural_external_localizer_paired_20260716.tsv` |
| Per-instance released-localizer changes | `results/mural_external_localizer_disagreements_20260716.tsv` |
| Repository strata | `results/mural_repository_localization_20260716.tsv` |
| Equal rendered-token packing and changed-line coverage | `results/token_budget_context_{summary,paired,instances}_20260718.tsv` |
| Simple selector controls | `results/selector_simple_{summary,paired,disagreements}_20260718.tsv` |
| Complete fixed-prefix tails | `results/fixed_prefix_tail_{summary,paired,disagreements,counts}_20260718.tsv` |
| Fallback-excluded localization | `results/localization_nonfallback_{summary,paired,disagreements}_20260718.tsv` |
| Code-only/history source replacement | `results/history_ablation_{summary,paired,disagreements}_20260718.tsv` |

### RQ-3: complete edit-target coverage

| Result | Ledger |
| --- | --- |
| Aggregate edit recall and complete coverage | `results/mural_edit_target_summary_20260716.tsv` and `.json` |
| Paired intervals and exact tests | `results/mural_edit_target_paired_20260716.tsv` |
| Per-instance mapped targets | `results/patch_derived_context_targets_20260702.json` |

### RQ-4: end-to-end repair

| Result | Ledger |
| --- | --- |
| Executed generation rows and selected attempts | `results/repair_equal4000_assembly_20260718.tsv` |
| Equal-4,000-token context audit | `results/repair_equal4000_context_{summary,rendering}_20260718.tsv` |
| Canonical prediction slots and exact reuse audit | `results/repair_equal4000_prediction_mapping_20260718.tsv` and `results/repair_equal4000_deduplication_summary_20260718.json` |
| Per-instance nonempty, applicable, and resolved outcomes with paired tests | `results/repair_equal4000_outcomes_20260718.tsv` and `results/repair_equal4000_summary_20260718.tsv` |
| Direct BM25--MURAL repair transitions | `results/repair_equal4000_transition_summary_20260718.tsv` and `results/repair_equal4000_transitions_20260718.tsv` |

### Supplementary analyses

| Analysis | Ledger |
| --- | --- |
| Budgets 5, 10, 20, and 40 | `results/mural_budget_{summary,paired,disagreements}_20260716.tsv` |
| RRF constants and dense-source weights | `results/mural_rrf_sensitivity_{summary,paired,disagreements}_20260716.tsv` |
| Complete Java benchmark | `results/java_cross_language_*_20260714.*` |
| Context-construction cost | `results/context_construction_cost_20260716.tsv` |
| External-artifact time boundary | `results/time_boundary_external_artifact_sensitivity_20260531.tsv` |
| File-only-fallback exclusion | `results/localization_nonfallback_*_20260718.tsv` |
| Historical-source replacement | `results/history_ablation_*_20260718.tsv` |

## Reproduction commands

Commands below run from the full experiment workspace containing benchmark
checkouts and archived upstream localizer outputs.

### Ranked files to entities

```bash
python3 artifacts/scripts/export_ranked_file_seeds.py \
  --input-dir runs/text_baselines_nohints/2000 \
  --output-dir temp_run/bm25_file_seeds \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --max-files 20 --support-mode count

python3 artifacts/scripts/export_entity_projection.py \
  --input-dir temp_run/bm25_file_seeds \
  --output-dir temp_run/bm25_projection \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --playground-root playground --limit 50
```

The second script retains its historical filename; it implements the shared
Entity Projection operator. Structural and dense ranked-file records use the
same command.

### Default MURAL

```bash
python3 artifacts/scripts/export_multi_source_rrf_fusion.py \
  --source BM25=temp_run/bm25_projection \
  --source Structural=temp_run/structural_projection \
  --source Dense=temp_run/dense_projection \
  --output-dir temp_run/mural \
  --top-k 50 --rrf-k 60 --force
```

### Localization metrics

```bash
python3 artifacts/scripts/analyze_retrieve_localize_controls.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --group BM25_projection=temp_run/bm25_projection \
  --group Structural_projection=temp_run/structural_projection \
  --group Dense_projection=temp_run/dense_projection \
  --group MURAL=temp_run/mural \
  --compare BM25_projection=MURAL \
  --compare Dense_projection=MURAL \
  --output-summary temp_run/mural_localization_summary.tsv \
  --output-paired temp_run/mural_localization_paired.tsv \
  --output-disagreements temp_run/mural_localization_disagreements.tsv
```

### Equal rendered-token control

```bash
python3 artifacts/scripts/evaluate_token_budget_context.py \
  --source BM25_projection=temp_run/bm25_projection \
  --source Structural_projection=temp_run/structural_projection \
  --source Dense_projection=temp_run/dense_projection \
  --source MURAL=temp_run/mural \
  --compare BM25_projection=MURAL \
  --compare Structural_projection=MURAL \
  --compare Dense_projection=MURAL \
  --budget 2000 --budget 4000 --budget 8000 \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --dataset-file temp_run/generated/SWE-bench_Verified.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --output-root temp_run/token_packed \
  --output-summary temp_run/token_budget_summary.tsv \
  --output-paired temp_run/token_budget_paired.tsv \
  --output-instances temp_run/token_budget_instances.tsv
```

### Simple selector controls

```bash
python3 artifacts/scripts/export_selector_simple_baselines.py \
  --input-dir temp_run/bm25_file_seeds \
  --output-root temp_run/selector_simple \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --playground-root playground --limit 50
```

### Fixed-prefix construction

```bash
python3 artifacts/scripts/export_fixed_prefix_fusion.py \
  --primary-dir temp_run/eval_aliyun_glm5_issueonly \
  --secondary-dir temp_run/mural \
  --output-dir temp_run/glm5_mural_b20_p10 \
  --budget 20 --primary-prefix 10 --secondary-pool 20 --force
```

### Released localizers

```bash
python3 artifacts/scripts/evaluate_external_localizer_fusion.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --external-root temp_run/CoSIL-release/loc_to_patch_verified \
  --mural-dir temp_run/mural \
  --tail-label MURAL \
  --output-summary temp_run/external_summary.tsv \
  --output-paired temp_run/external_paired.tsv \
  --output-disagreements temp_run/external_disagreements.tsv
```

### Matched 4,000-token GLM-5.2 repair

The primary repair comparison fixes the complete prompt ceiling at 4,000 tokens
and changes only the projected BM25 or MURAL candidate pool. The hosted key is
read from the environment and is never written to a configuration or ledger.

```bash
export AUTODL_API_KEY='set-outside-the-repository'
python3 artifacts/scripts/run_repair_profile_batch.py \
  --input-root temp_run/repair_equal4000/inputs \
  --output-root temp_run/repair_equal4000/runs \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --variants bm25 mural \
  --preset local_qwen3coder30b --round-tag _base \
  --playground-dir temp_run/repair_equal4000/playgrounds \
  --dataset-file temp_run/generated/SWE-bench_Verified.jsonl \
  --source-root . --model glm-5.2 \
  --base-url https://www.autodl.art/api/v1 \
  --api-key-env AUTODL_API_KEY --disable-thinking \
  --first-prompt-profile compact --prompt-token-limit 4000 \
  --completion-max-tokens 2048 --response-prefill off \
  --max-retries 1 --temperature 0 --timeout 600
```

The executed jobs were split into 21 disjoint ID shards. Retry batches contain
only attempts rejected for provider or worktree infrastructure failure; the
assembler requires exactly one infrastructure-clean attempt per variant and
instance. The rendered prompt audit is reconstructed from the frozen inputs and
base commits:

```bash
python3 artifacts/scripts/audit_repair_context_rendering.py \
  --input-root temp_run/repair_equal4000/inputs \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --dataset-file temp_run/generated/SWE-bench_Verified.jsonl \
  --playground-root temp_run/repair_equal4000/playgrounds --shared-playground \
  --variant bm25=bm25 --variant mural=mural \
  --preset local_qwen3coder30b --round-tag _base \
  --prompt-token-limit 4000 \
  --output artifacts/results/repair_equal4000_context_rendering_20260718.tsv

python3 artifacts/scripts/assemble_repair_profile_predictions.py \
  --run-root temp_run/repair_equal4000/runs \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --output-root temp_run/repair_equal4000/final/predictions \
  --variant bm25=bm25 --variant mural=mural \
  --shards shard_00 shard_01 shard_02 shard_03 shard_04 shard_05 \
    shard_06 shard_07 shard_08 shard_09 shard_10 shard_11 shard_12 \
    shard_13 shard_14 shard_15 shard_16 shard_17 shard_18 shard_19 \
    shard_20 retry_bm25 retry_mural retry3_smoke_mural \
    retry3_mural retry3_bm25 \
  --shard-first --model-prefix glm52_equal4000 \
  --expected-dataset-source temp_run/generated/SWE-bench_Verified.jsonl \
  --dataset-label temp_run/generated/SWE-bench_Verified.jsonl \
  --expected-context-profile rank_stratified_v3_allfiles \
  --expected-max-retries 1 --max-prompt-tokens 4000 \
  --require-no-prefill --require-thinking-disabled

python3 artifacts/scripts/deduplicate_repair_predictions.py \
  --predictions-root temp_run/repair_equal4000/final/predictions \
  --output-root temp_run/repair_equal4000/final/canonical \
  --variants bm25 mural --model-prefix glm52_equal4000 \
  --prompt-audit artifacts/results/repair_equal4000_context_rendering_20260718.tsv
```

Reuse requires the same instance, rendered-prompt SHA-256, and patch SHA-256.
The executed run maps 938 nonempty variant predictions to 932 canonical official
evaluations. Both canonical slots use the official SWE-bench harness; the mirror
changes image transport only.

```bash
for slot in 0 1; do
  python3 -m swebench.harness.run_evaluation \
    --dataset_name temp_run/generated/SWE-bench_Verified.jsonl \
    --predictions_path temp_run/repair_equal4000/final/canonical/slot_${slot}/predictions.jsonl \
    --max_workers 10 --timeout 1800 \
    --namespace dockerproxy.net/swebench \
    --run_id mural_glm52_equal4000_slot_${slot}_20260718

  python3 artifacts/scripts/collect_swebench_reports.py \
    --predictions temp_run/repair_equal4000/final/canonical/slot_${slot}/predictions.jsonl \
    --run-id mural_glm52_equal4000_slot_${slot}_20260718 \
    --output temp_run/repair_equal4000/final/canonical/slot_${slot}/official_results.jsonl \
    --normalize-terminal-errors
done

python3 artifacts/scripts/materialize_repair_variant_reports.py \
  --canonical-root temp_run/repair_equal4000/final/canonical \
  --output-root temp_run/repair_equal4000/final/official \
  --variants bm25 mural

python3 artifacts/scripts/analyze_repair_outcomes.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --predictions-root temp_run/repair_equal4000/final/predictions \
  --official-root temp_run/repair_equal4000/final/official \
  --variants bm25 mural \
  --output-outcomes artifacts/results/repair_equal4000_outcomes_20260718.tsv \
  --output-summary artifacts/results/repair_equal4000_summary_20260718.tsv

python3 artifacts/scripts/analyze_repair_transitions.py \
  --outcomes artifacts/results/repair_equal4000_outcomes_20260718.tsv \
  --baseline bm25 --treatment mural \
  --output-summary artifacts/results/repair_equal4000_transition_summary_20260718.tsv \
  --output-instances artifacts/results/repair_equal4000_transitions_20260718.tsv
```

### Context-construction cost

```bash
python3 artifacts/scripts/analyze_context_construction_cost.py \
  --logs-glob 'logs/kg_verified_evidence_graph/*.log' \
  --run-dir runs/kg_verified_evidence_graph/tse_timesafe_main_20260529_v6 \
  --bm25-time temp_run/timing/bm25_projection.time \
  --dense-time temp_run/timing/dense_projection.time \
  --rrf-time temp_run/timing/mural_rrf.time \
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

### Verification

```bash
python3 artifacts/scripts/verify_paper_results.py --scope all
```
