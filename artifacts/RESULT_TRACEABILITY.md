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
  two-sided exact McNemar for binary paired contrasts.
- Strict targets: 1,044 total, comprising 836 functions or class methods,
  32 assignments, and 176 exact-file fallbacks.

## Claim-to-ledger map

| Manuscript evidence | Retained ledger |
| --- | --- |
| Strict target policy and population | `results/strict_reference_targets_20260719.json` |
| Top-20 retrieval, projection, fusion, and GLM-prefix rows | `results/strict_localization_{summary,instances,paired}_20260719.tsv` |
| Equal rendered-token comparison | `results/strict_token_context_{summary,instances,paired}_20260719.tsv` |
| Packing, truncation, and changed-line coverage | `results/strict_token_packing_{summary,instances}_20260719.tsv` |
| Selector controls | `results/strict_selector_{summary,instances,paired}_20260719.tsv` |
| Complete GLM-prefix tail controls | `results/strict_prefix_tail_{summary,instances,paired}_20260719.tsv` |
| Released localizer completion | `results/strict_external_localizer_{summary,instances,paired}_20260719.tsv` |
| Entity budgets 5, 10, 20, and 40 | `results/strict_budget_b*_{summary,instances,paired}_20260719.tsv` |
| RRF sensitivity | `results/strict_rrf_sensitivity_{summary,instances,paired}_20260719.tsv` |
| Executed source-bearing prompts | `results/source_bearing_prompt_{summary,instances,paired}_20260719.tsv` |
| Strict repair predictions and official outcomes | `results/repair_equal4000_strict_*_20260719.*` |
| Clustered repair intervals | `results/repair_equal4000_clustered_paired_20260719.tsv` |
| Blinded judgments and agreement | `results/human_window_*_20260718.*` |
| Exact student-visible audit rankings | `frozen/human_window_rankings_20260712.jsonl.gz` |
| Audit window-to-source binding | `results/human_window_binding_20260719.tsv` |
| Exact-window strict evaluation | `results/human_window_exact_instances_20260719.tsv` |
| Strict re-stratification of those judgments | `results/human_window_strict_*_20260719.tsv` |
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
localization ledger.

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
  --top-k 20 --primary-prefix 10 --secondary-pool 20 \
  --bootstrap 10000 --seed 7 \
  --output-summary strict_external_summary.tsv \
  --output-instances strict_external_instances.tsv \
  --output-paired strict_external_paired.tsv
```

## Prompt and repair provenance

`results/source_bearing_prompt_instances_20260719.tsv` records the
SHA-256 of every executed prompt and the exact source-bearing entities retained
by the renderer. Strict predictions and official evaluations are stored
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

The raw annotations and randomized A/B assignment remain exactly as supplied
to the students. Strict alignment is computed from the frozen windows they
actually inspected, while the final 500-instance localization ledger remains
unchanged.

## Final integrity gate

```bash
python3 scripts/build_submission_manifest.py
python3 scripts/verify_paper_results.py
```
