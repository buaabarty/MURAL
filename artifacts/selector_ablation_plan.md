# Selector Ablation Plan

## Purpose

This experiment isolates the five lexicographic signal groups used by the shared
file-local selector. It uses BM25-ranked files, the common Top-20 entity budget,
all 500 SWE-bench Verified instances, and the same target mapping as RQ-1.
Each treatment removes exactly one group; no benchmark target enters ranking.

| Group | Signals |
|---|---|
| G1 Title agreement | title-to-symbol and title-to-source/docstring overlap |
| G2 Exact anchors | exact qualified-symbol and source/docstring anchors |
| G3 Narrative agreement | narrative-to-symbol, source-only, and source/docstring overlap |
| G4 Source record | support, distance/direct-anchor evidence, file rank, and prior entity rank |
| G5 Stable fallback | boilerplate demotion, source span, and qualified symbol |

The Full variant preserves the released 15-component key exactly. G4 and G5
are labeled signal families whose components retain their released interleaving
(boilerplate demotion precedes the final source-rank tie-breaks). Setting
`MURAL_ABLATE=G1` through `G5` removes that complete group. Empty or
`MURAL_ABLATE=FULL` preserves the released key exactly.

## Export

Use the same count-support ranked-file records as the reported BM25-local row:

```bash
BM25_FILE_SEEDS=temp_run/private_bm25_filelocal_20260704/seeds_top20_files_count
```

A single variant can be generated directly:

```bash
MURAL_ABLATE=G1 python3 artifacts/scripts/export_path_mined_filelocal.py \
  --input-dir "$BM25_FILE_SEEDS" \
  --output-dir temp_run/selector_ablation/minus_g1 \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --limit 50
```

For all six variants, use the cached multi-variant exporter. Splitting the ID
file lets independent workers share one output root while each worker reuses
parsed files across variants:

```bash
mkdir -p temp_run/selector_ablation/shards
split -n l/8 -d -a 2 --additional-suffix=.jsonl \
  temp_run/SWE-bench_Verified_ids.jsonl \
  temp_run/selector_ablation/shards/ids_

for ids in temp_run/selector_ablation/shards/*.jsonl; do
  python3 artifacts/scripts/export_selector_ablation.py \
    --input-dir "$BM25_FILE_SEEDS" \
    --output-root temp_run/selector_ablation \
    --ids-file "$ids" \
    --limit 50 &
done
wait
```

## Evaluation

```bash
python3 artifacts/scripts/analyze_retrieve_localize_controls.py \
  --group Full=temp_run/selector_ablation/full \
  --group minus_G1=temp_run/selector_ablation/minus_g1 \
  --group minus_G2=temp_run/selector_ablation/minus_g2 \
  --group minus_G3=temp_run/selector_ablation/minus_g3 \
  --group minus_G4=temp_run/selector_ablation/minus_g4 \
  --group minus_G5=temp_run/selector_ablation/minus_g5 \
  --compare Full=minus_G1 --compare Full=minus_G2 \
  --compare Full=minus_G3 --compare Full=minus_G4 \
  --compare Full=minus_G5 \
  --top-k 20 --bootstrap-iters 10000 --seed 7 \
  --output-summary artifacts/results/selector_ablation_summary_20260714.tsv \
  --output-paired artifacts/results/selector_ablation_paired_20260714.tsv \
  --output-disagreements temp_run/selector_ablation_disagreements_20260714.tsv
```

The summary reports File Coverage, Entity Coverage, MRR, and Hit@20. Paired
treatment-minus-Full differences use 10,000 paired bootstrap resamples (seed 7);
binary File Coverage and Hit@20 also use two-sided exact McNemar tests. Before
interpreting ablations, Full must reproduce BM25-local Hit@20 = 57.0% on
500 instances.
