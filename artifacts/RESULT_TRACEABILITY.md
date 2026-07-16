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

### RQ-3: complete edit-target coverage

| Result | Ledger |
| --- | --- |
| Aggregate edit recall and complete coverage | `results/mural_edit_target_summary_20260716.tsv` and `.json` |
| Paired intervals and exact tests | `results/mural_edit_target_paired_20260716.tsv` |
| Per-instance mapped targets | `results/patch_derived_context_targets_20260702.json` |

### RQ-4: end-to-end repair

| Result | Ledger |
| --- | --- |
| Executed generation rows and selected attempts | `results/repair_glm52_assembly_20260716.tsv` |
| Rendered context and prompt hashes | `results/repair_glm52_context_rendering_20260716.tsv` |
| Canonical prediction slots and exact reuse audit | `results/repair_glm52_prediction_mapping_20260716.tsv` and `results/repair_glm52_deduplication_summary_20260716.json` |
| Per-instance nonempty, applicable, and resolved outcomes with paired tests | `results/repair_glm52_outcomes_20260716.tsv` and `results/repair_glm52_summary_20260716.tsv` |
| Repository strata | `results/mural_repository_repair_20260716.tsv` |

### Supplementary analyses

| Analysis | Ledger |
| --- | --- |
| Budgets 5, 10, 20, and 40 | `results/mural_budget_{summary,paired,disagreements}_20260716.tsv` |
| RRF constants and dense-source weights | `results/mural_rrf_sensitivity_{summary,paired,disagreements}_20260716.tsv` |
| Complete Java benchmark | `results/java_cross_language_*_20260714.*` |
| Context-construction cost | `results/context_construction_cost_20260716.tsv` |
| External-artifact time boundary | `results/time_boundary_external_artifact_sensitivity_20260531.tsv` |

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

### GLM-5.2 repair generation

```bash
export AUTODL_API_KEY='set-outside-the-repository'
python3 artifacts/scripts/run_repair_profile_batch.py \
  --input-root temp_run/repair_inputs \
  --output-root temp_run/repair_glm52 \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --variants issue bm25 mural \
  --preset local_qwen3coder30b --round-tag _base \
  --playground-dir playground \
  --dataset-file temp_run/generated/SWE-bench_Verified.jsonl \
  --source-root . --model glm-5.2 \
  --base-url https://www.autodl.art/api/v1 \
  --api-key-env AUTODL_API_KEY --disable-thinking \
  --first-prompt-profile compact --prompt-token-limit 5000 \
  --completion-max-tokens 2048 --response-prefill off \
  --max-retries 1 --temperature 0 --timeout 600
```

No credential is written to a run configuration or result ledger.

The executed candidate pools and rendered prompts are reconstructed offline
from the same frozen inputs and base commits:

```bash
python3 artifacts/scripts/audit_repair_context_rendering.py \
  --input-root temp_run/repair_inputs \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --dataset-file temp_run/generated/SWE-bench_Verified.jsonl \
  --playground-root playground --shared-playground \
  --variant issue=issue --variant bm25=bm25 --variant mural=mural3 \
  --preset local_qwen3coder30b --round-tag _base \
  --prompt-token-limit 5000 \
  --output temp_run/repair_glm52_context_rendering.tsv
```

Provider-failure retries are assembled before official testing. The assembly
checks the frozen dataset, context profile, prompt ceiling, decoding settings,
and model endpoint recorded by every contributing shard.

```bash
python3 artifacts/scripts/assemble_repair_profile_predictions.py \
  --run-root temp_run/repair_glm52_runs \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --output-root temp_run/repair_glm52_final/predictions \
  --variant issue=issue --variant bm25=bm25 --variant mural=mural3 \
  --shards shard_0 shard_1 retry_0 retry_1 retry_2a retry_2b \
  --model-prefix glm52 \
  --expected-dataset-source temp_run/generated/SWE-bench_Verified.jsonl \
  --dataset-label temp_run/generated/SWE-bench_Verified.jsonl \
  --expected-context-profile rank_stratified_v3_allfiles \
  --expected-max-retries 1 --max-prompt-tokens 5000 \
  --require-no-prefill --require-thinking-disabled

python3 artifacts/scripts/deduplicate_repair_predictions.py \
  --predictions-root temp_run/repair_glm52_final/predictions \
  --output-root temp_run/repair_glm52_final/canonical \
  --variants issue bm25 mural --model-prefix glm52 \
  --prompt-audit artifacts/results/repair_glm52_context_rendering_20260716.tsv
```

Reuse requires the same instance, rendered-prompt SHA-256, and patch SHA-256.
The executed run therefore maps 1,052 nonempty variant predictions to 1,051
official evaluations.

Each canonical slot is evaluated with the official SWE-bench harness. The
registry mirror changes image transport only; image tags, benchmark records,
patches, and test oracles are unchanged.

```bash
for slot in 0 1 2; do
  python3 -m swebench.harness.run_evaluation \
    --dataset_name temp_run/generated/SWE-bench_Verified.jsonl \
    --predictions_path temp_run/repair_glm52_final/canonical/slot_${slot}/predictions.jsonl \
    --max_workers 8 --timeout 1800 \
    --namespace dockerproxy.net/swebench \
    --run_id mural_glm52_slot_${slot}_20260716

  python3 artifacts/scripts/collect_swebench_reports.py \
    --predictions temp_run/repair_glm52_final/canonical/slot_${slot}/predictions.jsonl \
    --run-id mural_glm52_slot_${slot}_20260716 \
    --output temp_run/repair_glm52_final/canonical/slot_${slot}/official_results.jsonl \
    --normalize-terminal-errors
done

python3 artifacts/scripts/materialize_repair_variant_reports.py \
  --canonical-root temp_run/repair_glm52_final/canonical \
  --output-root temp_run/repair_glm52_final/official \
  --variants issue bm25 mural

python3 artifacts/scripts/analyze_repair_outcomes.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --predictions-root temp_run/repair_glm52_final/predictions \
  --official-root temp_run/repair_glm52_final/official \
  --output-outcomes temp_run/repair_glm52_outcomes.tsv \
  --output-summary temp_run/repair_glm52_summary.tsv
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
