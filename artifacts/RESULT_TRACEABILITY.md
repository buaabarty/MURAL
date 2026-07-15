# Result Traceability

This note maps every retained result ledger to either the MURAL main manuscript
or its separately compiled supplementary material. Files for unreported
diagnostics, obsolete ablations, partial shards, and the retired KG-only
downstream repair study are intentionally absent.

Frozen ledgers retain historical `KGCompass` labels. In the submitted
documents, `KGCompass` is `KG-local`, `BM25+KG RRF file-local` is standalone
MURAL, and `GLM-5 + BM25+KG RRF file-local` is GLM-5+MURAL. This mapping changes
terminology only; candidate rankings and metric values are unchanged.

## Evaluation Scope

- Benchmark: all 500 SWE-bench Verified instances.
- Structural source:
  `runs/kg_verified_evidence_graph/tse_timesafe_main_20260529_v6/`.
- KG-local rank union:
  `runs/kg_verified_evidence_graph/tse_timesafe_main_20260531_pathunion_v1/`.
- Shared input boundary: original issue title/body plus base-commit code.
- Excluded inputs: benchmark hints, issue/PR comments, evidence from the pull
  request associated with the target repair, patch text, linked repair commits,
  and future artifacts.
- Evaluator-only data: official patches and all derived target mappings.

The final leakage audit is copied to
`artifacts/results/kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json`.
It reports 500/500 valid instances, zero target-PR hits, zero trace hits from
future repair artifacts, and no content, structural, or metadata violations.

## Submission-Side Verification

Run:

```bash
python3 artifacts/scripts/verify_paper_results.py
```

The verifier checks:

- the exact result-file inventory;
- the target-mapping table;
- RQ-1 controlled source, selector, fusion, and paired statistics;
- RQ-2 fixed-prefix controls and paired statistics;
- RQ-3 mapped edit-target coverage and paired uncertainty;
- RQ-4 complete repair outcomes and paired uncertainty;
- supplementary budget, selector, third-source, Java, and repair-audit values; and
- leakage and external-artifact sensitivity statements.

## Main-Manuscript Mapping

### Experimental Setup

- Ground-truth mapping:
  `artifacts/results/tse_gt_mapping_v6.tsv`.
- Input-boundary record:
  `artifacts/issue_comment_boundary.json`.
- Repair endpoint and workflow record:
  `artifacts/repair_protocol_glm5_20260715.json`.

### RQ-1: Controlled Context Windows

- BM25, BLUiR, CodeGraph, graph-only KG, and KG-local:
  `artifacts/results/path_mining_file_expansion_ablation_20260531.tsv`.
- Matched BM25/KG file-local and MURAL rows:
  `artifacts/results/retrieve_then_localize_top20_20260711.tsv`.
- Bootstrap intervals, win/loss counts, and exact tests:
  `artifacts/results/retrieve_then_localize_paired_20260711.tsv`.
- Per-instance Hit@20 disagreements:
  `artifacts/results/retrieve_then_localize_disagreements_20260711.tsv`.
- First-stage Top-20 file coverage:
  `artifacts/results/ranked_file_source_coverage_20260711.tsv` and
  `artifacts/results/ranked_file_source_paired_20260711.tsv`.

### RQ-2: Fixed-Prefix LLM Fusion

- GLM-5 issue-only, KG-local, BM25-local, and MURAL rows:
  `artifacts/results/retrieve_then_localize_top20_20260711.tsv`.
- CodeGraph fixed-prefix control:
  `artifacts/results/glm5_baseline_fusion_controls_top10_20260614.tsv`.
- Paired source and fusion statistics:
  `artifacts/results/retrieve_then_localize_paired_20260711.tsv`.

### RQ-3: Complete Edit-Target Coverage

- Aggregate edit-target recall and complete coverage:
  `artifacts/results/patch_derived_context_summary_20260702.tsv` and `.json`.
- Deterministic mapped targets:
  `artifacts/results/patch_derived_context_targets_20260702.json`.
- Paired bootstrap intervals and exact complete-coverage tests:
  `artifacts/results/edit_target_paired_stats_20260713.tsv`.

### RQ-4: Official Repair Outcomes

- Complete 500-by-3 corrected-workflow outcome ledger:
  `artifacts/results/repair_glm5_outcomes_20260715.tsv`.
- Nonempty/applicable/Resolved totals, paired bootstrap intervals, win/loss
  counts, and exact McNemar tests:
  `artifacts/results/repair_glm5_summary_20260715.tsv`.
- Frozen issue, context-rendering, retry, and patch-hash request audit:
  `artifacts/results/repair_glm5_assembly_20260715.tsv`.

The fixed workflow resolves 112/500 (22.4%) with the GLM-only window, 134/500
(26.8%) with GLM+BM25-local, and 146/500 (29.2%) with GLM+MURAL. Here
GLM-only denotes the issue-conditioned upstream localizer; its repair prompt
still renders base-commit source from those candidates. GLM+MURAL improves over
GLM-only by 6.8 points (44 wins, 10 losses, 95% paired
bootstrap CI [4.0, 9.6], exact McNemar p=3.39e-6). Its 2.4-point advantage
over BM25-local is positive but inconclusive (29/17, CI [-0.2, 5.0], p=.104).
RQ-4 uses three archived complete candidate pools under a common Top-20 ceiling;
it does not reuse the exact prefix-preserving localization ledgers from RQ-2.
The generation workflow is fixed while the complete supplied pool varies.

### Threats to Validity

- Leakage-sentinel audit:
  `artifacts/results/kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json`.
- External-artifact sensitivity:
  `artifacts/results/time_boundary_external_artifact_sensitivity_20260531.tsv`.

## Supplementary-Material Mapping

### Budget Sensitivity

- Four-budget aggregate rows:
  `artifacts/results/retrieve_then_localize_budget_curve_20260711.tsv`.
- Four-budget paired statistics:
  `artifacts/results/retrieve_then_localize_budget_paired_20260711.tsv`.

### Repair Context and Evaluation Audit

- Candidate, rendered, source-bearing, rank-band, and prompt-token audit:
  `artifacts/results/repair_glm5_context_rendering_20260715.tsv`.
- Exact patch-hash mapping and aggregate deduplication counts:
  `artifacts/results/repair_glm5_prediction_mapping_20260715.tsv` and
  `artifacts/results/repair_glm5_deduplication_summary_20260715.json`.

### Selector Signal-Family Ablation

- Full and leave-one-family-out aggregate rows:
  `artifacts/results/selector_ablation_summary_20260714.tsv`.
- Paired bootstrap intervals, win/loss counts, and exact binary tests:
  `artifacts/results/selector_ablation_paired_20260714.tsv`.

### Dense Third-Source Extension

- Dense retrieval, shared-selector, two-/three-source, and GLM-5 fixed-prefix
  aggregate rows:
  `artifacts/results/dense_third_source_summary_20260714.tsv`.
- Paired bootstrap intervals, win/loss counts, and exact binary tests:
  `artifacts/results/dense_third_source_paired_20260714.tsv`.

### Reproduction Settings

- Exact localization prompt:
  `artifacts/prompts/llm_fault_location_prompt.md`.
- Exact GLM-5 repair prompts:
  `artifacts/prompts/glm5_repair_prompt.md`.

## Reproduction Commands

The commands below target the full experiment workspace, where benchmark
checkouts, cached mappings, and per-instance run directories are available.
Scripts mirrored under `artifacts/scripts/` are source-inspection snapshots.

### Leakage Audit

```bash
python3 artifacts/scripts/audit_kg_leakage.py \
  runs/kg_verified_evidence_graph/tse_timesafe_main_20260529_v6 \
  --output-json logs/kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json \
  --fail-on-issue
```

### Controlled Source Rows

```bash
python3 artifacts/scripts/eval_controls_v3.py \
  --group full_pathmined=runs/kg_verified_evidence_graph/tse_timesafe_main_20260531_pathunion_v1 \
  --group strict_kg_ablation=runs/kg_verified_evidence_graph/tse_timesafe_main_20260529_v6 \
  --group bm25_nohint=runs/text_baselines_nohints/2000 \
  --group bluir=runs/text_baselines_bluir/2300 \
  --group no_history_codegraph=runs/codegraph_anchor/tse_timesafe_main_20260531_v2 \
  --output-tsv logs/comparison_current/path_mining_file_expansion_ablation_20260531.tsv \
  --top-k 20
```

### BM25 File-Local Selection and MURAL

```bash
BM25_METHODS=runs/text_baselines_nohints/2000
BM25_SEEDS=temp_run/bm25_top20_file_seeds
BM25_FILELOCAL=temp_run/bm25_filelocal
KG_FILELOCAL=runs/kg_verified_evidence_graph/tse_timesafe_main_20260531_pathunion_v1
RRF_FILELOCAL=temp_run/bm25_kg_rrf_filelocal

python3 artifacts/scripts/export_ranked_file_seeds.py \
  --input-dir "$BM25_METHODS" \
  --output-dir "$BM25_SEEDS" \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --max-files 20 \
  --support-mode count

python3 artifacts/scripts/export_path_mined_filelocal.py \
  --input-dir "$BM25_SEEDS" \
  --output-dir "$BM25_FILELOCAL" \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --limit 50

python3 artifacts/scripts/export_equal_rrf_fusion.py \
  --primary-dir "$BM25_FILELOCAL" \
  --secondary-dir "$KG_FILELOCAL" \
  --output-dir "$RRF_FILELOCAL" \
  --top-k 50 \
  --rrf-k 60 \
  --force
```

### Fixed-Prefix Top-20 Controls

```bash
python3 artifacts/scripts/export_fixed_prefix_fusion.py \
  --primary-dir temp_run/eval_aliyun_glm5_issueonly \
  --secondary-dir "$BM25_FILELOCAL" \
  --output-dir temp_run/glm5_bm25_filelocal_b20 \
  --budget 20 \
  --primary-prefix 10 \
  --secondary-pool 20 \
  --force

python3 artifacts/scripts/export_fixed_prefix_fusion.py \
  --primary-dir temp_run/eval_aliyun_glm5_issueonly \
  --secondary-dir "$RRF_FILELOCAL" \
  --output-dir temp_run/glm5_bm25_kg_rrf_b20 \
  --budget 20 \
  --primary-prefix 10 \
  --secondary-pool 20 \
  --force

python3 artifacts/scripts/analyze_retrieve_localize_controls.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --top-k 20 \
  --group KG_filelocal="$KG_FILELOCAL" \
  --group BM25_filelocal="$BM25_FILELOCAL" \
  --group BM25_KG_RRF_filelocal="$RRF_FILELOCAL" \
  --group GLM5_issue=temp_run/eval_aliyun_glm5_issueonly \
  --group GLM5_KG_filelocal=temp_run/fusions_glm5_baseline_controls_20260614_head10/GLM5_KGCompass_ht10 \
  --group GLM5_BM25_filelocal=temp_run/glm5_bm25_filelocal_b20 \
  --group GLM5_BM25_KG_RRF_filelocal=temp_run/glm5_bm25_kg_rrf_b20 \
  --compare KG_filelocal=BM25_filelocal \
  --compare BM25_filelocal=BM25_KG_RRF_filelocal \
  --compare GLM5_issue=GLM5_BM25_filelocal \
  --compare GLM5_issue=GLM5_BM25_KG_RRF_filelocal \
  --compare GLM5_KG_filelocal=GLM5_BM25_filelocal \
  --compare GLM5_BM25_filelocal=GLM5_BM25_KG_RRF_filelocal \
  --output-summary logs/comparison_current/retrieve_then_localize_top20_20260711.tsv \
  --output-paired logs/comparison_current/retrieve_then_localize_paired_20260711.tsv \
  --output-disagreements logs/comparison_current/retrieve_then_localize_disagreements_20260711.tsv
```

### Selector Signal-Family Ablation

The archived BM25 ranked-file records used for the reported selector run are
the count-support seeds below. The cached exporter processes Full and all five
leave-one-family-out variants in one pass; `artifacts/selector_ablation_plan.md`
also documents an eight-shard invocation.

```bash
BM25_FILE_SEEDS=temp_run/private_bm25_filelocal_20260704/seeds_top20_files_count
SELECTOR_ROOT=temp_run/mural_experiment_additions/selector_ablation_v4

python3 artifacts/scripts/export_selector_ablation.py \
  --input-dir "$BM25_FILE_SEEDS" \
  --output-root "$SELECTOR_ROOT" \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --limit 50

python3 artifacts/scripts/analyze_retrieve_localize_controls.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --group Full="$SELECTOR_ROOT/full" \
  --group minus_G1="$SELECTOR_ROOT/minus_g1" \
  --group minus_G2="$SELECTOR_ROOT/minus_g2" \
  --group minus_G3="$SELECTOR_ROOT/minus_g3" \
  --group minus_G4="$SELECTOR_ROOT/minus_g4" \
  --group minus_G5="$SELECTOR_ROOT/minus_g5" \
  --compare Full=minus_G1 --compare Full=minus_G2 \
  --compare Full=minus_G3 --compare Full=minus_G4 \
  --compare Full=minus_G5 \
  --top-k 20 --bootstrap-iters 10000 --seed 7 \
  --output-summary artifacts/results/selector_ablation_summary_20260714.tsv \
  --output-paired artifacts/results/selector_ablation_paired_20260714.tsv \
  --output-disagreements temp_run/selector_ablation_disagreements_20260714.tsv
```

### Dense Third-Source Extension

The dense entity source uses `jinaai/jina-embeddings-v2-base-code` revision
`516f4baf13dec4ddddda8631e019b5737c8bc250` with cosine similarity over
base-commit Python entities. Each encoded document concatenates
the qualified signature, repository-relative path, docstring, and at most 3,000
source characters; the query is the target issue title/body without benchmark
hints. The adapter below collapses the entity ranking to the Top-20 unique files
by best entity rank, records per-file candidate count as source support, and
then invokes the unchanged selector. `MURAL_2SRC` is the predefined BM25/KG
row; `MURAL_3SRC` adds the dense-local ranking without changing RRF settings.

```bash
DENSE_ENTITIES=runs/text_baselines_nohints/2001
DENSE_FILES=temp_run/mural_experiment_additions/dense_top20_file_seeds_v2
DENSE_LOCAL=temp_run/mural_experiment_additions/dense_top20_files_filelocal_v2
MURAL_2SRC=temp_run/private_bm25_filelocal_20260704/hybrid_rrf/BM25_KG_deterministic_rrf
MURAL_3SRC=temp_run/mural_experiment_additions/mural_3src_dense_v2

python3 artifacts/scripts/export_ranked_file_seeds.py \
  --input-dir "$DENSE_ENTITIES" --output-dir "$DENSE_FILES" \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --max-files 20 --support-mode count \
  --source-name dense --uses-embeddings

python3 artifacts/scripts/export_path_mined_filelocal.py \
  --input-dir "$DENSE_FILES" --output-dir "$DENSE_LOCAL" \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl --limit 50

python3 artifacts/scripts/export_multi_source_rrf_fusion.py \
  --source BM25=temp_run/private_bm25_filelocal_20260704/bm25_top20_files_filelocal \
  --source KG=runs/kg_verified_evidence_graph/tse_timesafe_main_20260531_pathunion_v1 \
  --source Dense="$DENSE_LOCAL" --output-dir "$MURAL_3SRC" \
  --top-k 50 --rrf-k 60 --force

python3 artifacts/scripts/export_fixed_prefix_fusion.py \
  --primary-dir temp_run/eval_aliyun_glm5_issueonly \
  --secondary-dir "$MURAL_3SRC" \
  --output-dir temp_run/mural_experiment_additions/glm5_mural_3src_b20_p10 \
  --budget 20 --primary-prefix 10 --secondary-pool 20 --force

python3 artifacts/scripts/analyze_retrieve_localize_controls.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --group Dense_raw="$DENSE_ENTITIES" --group Dense_local="$DENSE_LOCAL" \
  --group BM25_local=temp_run/private_bm25_filelocal_20260704/bm25_top20_files_filelocal \
  --group KG_local=runs/kg_verified_evidence_graph/tse_timesafe_main_20260531_pathunion_v1 \
  --group MURAL_2src="$MURAL_2SRC" --group MURAL_3src="$MURAL_3SRC" \
  --group GLM5_issue=temp_run/eval_aliyun_glm5_issueonly \
  --group GLM5_BM25_local=temp_run/private_bm25_filelocal_20260704/budget_fusions/GLM5_BM25FileLocal_b20_p10 \
  --group GLM5_MURAL_2src=temp_run/private_bm25_filelocal_20260704/hybrid_rrf/deterministic_budget_fusions/GLM5_Hybrid_b20_p10 \
  --group GLM5_MURAL_3src=temp_run/mural_experiment_additions/glm5_mural_3src_b20_p10 \
  --compare Dense_raw=Dense_local --compare BM25_local=Dense_local \
  --compare MURAL_2src=Dense_local --compare MURAL_2src=MURAL_3src \
  --compare Dense_local=MURAL_3src \
  --compare GLM5_issue=GLM5_MURAL_3src \
  --compare GLM5_BM25_local=GLM5_MURAL_3src \
  --compare GLM5_MURAL_2src=GLM5_MURAL_3src \
  --top-k 20 --bootstrap-iters 10000 --seed 7 \
  --output-summary artifacts/results/dense_third_source_summary_20260714.tsv \
  --output-paired artifacts/results/dense_third_source_paired_20260714.tsv \
  --output-disagreements temp_run/dense_third_source_disagreements_20260714.tsv
```

### Java Cross-Language Diagnostic

The supplementary Java check uses the complete SWE-bench-Java Verified
benchmark: all 91 instances across all six repositories, with no sampling,
repository filtering, or instance exclusion. The release is hosted under the
historical Hugging Face repository name `Daoguang/Multi-SWE-bench`, split
`java_verified`; it is SWE-bench-Java (arXiv:2408.14354), not the later
Multi-SWE-bench benchmark (arXiv:2504.02605). We pin revision
`8bd202138a4ab9987daa77111c76a3e66af9f1c9`. The official JSON has SHA-256
`4f5fd770eb1ff8bbd24540ccc367f38e466ba7426e2dc328867a901061e2ea07`,
and the sorted 91-ID set has SHA-256
`15cbf3065a33f11e328f792eff71761c1168b30425a8e81a15275afe5fc1f690`.
The committed instance ledger and structural seed ledger reproduce that exact
ID set: 91 unique evaluated IDs, zero missing, zero extra, and zero failed.

The evaluator accepts the official `repo`, `base_commit`, `problem_statement`,
and `patch` fields. It rebuilds entities from each base commit, freezes every
ranking, and only then reads the patch to derive evaluation targets. The
committed structural input contains ranked-file records only, including
aggregate direct-anchor and graph-distance fields; see
`artifacts/inputs/java_cross_language_manifest_20260714.json` for provenance.
Files tied on anchor, graph distance, and support are ordered by their first
structural entity rank rather than by path text. Target mapping follows the
Python contract: auxiliary files and entities absent from the base commit do
not enlarge an otherwise mapped target set, and file-level fallback is used
only when an entire patch has no mapped entity. All 91 patches map at least one
base-commit entity; 65 auxiliary or newly added files are recorded separately.

Export the official split without altering its fields:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from datasets import load_dataset

out = Path("temp_run/swe_bench_java_verified/java_verified_dataset.jsonl")
out.parent.mkdir(parents=True, exist_ok=True)
rows = sorted(load_dataset("Daoguang/Multi-SWE-bench", split="java_verified"),
              key=lambda row: row["instance_id"])
with out.open("w", encoding="utf-8") as handle:
    for row in rows:
        handle.write(json.dumps(dict(row), ensure_ascii=True,
                                sort_keys=True, default=str) + "\n")
PY
```

Regenerate the structural rankings with the frozen offline runner before
exporting ranked files. The graph traversal depth remains 50. The exporter may
scan up to 200 ranked entities only to fill at most 20 unique file records after
deduplication; this does not broaden graph traversal.

```bash
python3 artifacts/scripts/run_java_kg_batch.py \
  --dataset temp_run/swe_bench_java_verified/java_verified_dataset.jsonl \
  --workdir temp_run/java_kg_work \
  --repos-dir temp_run/java_cross_language/repos \
  --output-dir temp_run/java_kg_raw \
  --log-dir temp_run/java_kg_logs \
  --embedding-cache temp_run/java_embedding_cache.sqlite \
  --entity-depth 50 --result-limit 200 --reference-workers 4

python3 artifacts/scripts/export_java_kg_file_seeds.py \
  --input-dir temp_run/java_kg_raw \
  --output artifacts/inputs/java_kg_ranked_file_seeds_20260714.jsonl \
  --entity-depth 200 --max-files 20
```

`run_java_kg_batch.py` forces dataset, model, and Transformer offline modes;
disables live GitHub search, patch/timeline expansion, and project-wide method
call expansion; and restricts source parsing to `.java` files.

Then run the frozen ranked-file source through the shared selector and
equal-weight RRF:

```bash
python3 artifacts/scripts/evaluate_java_retrieve_localize.py \
  --dataset-dir temp_run/swe_bench_java_verified \
  --kg-seeds artifacts/inputs/java_kg_ranked_file_seeds_20260714.jsonl \
  --repos-dir temp_run/java_cross_language/repos \
  --cache-dir temp_run/java_cross_language/entity_cache \
  --output-summary artifacts/results/java_cross_language_summary_20260714.tsv \
  --output-paired artifacts/results/java_cross_language_paired_20260714.tsv \
  --output-instances artifacts/results/java_cross_language_instances_20260714.jsonl \
  --output-targets artifacts/results/java_cross_language_targets_20260714.json \
  --bootstrap-iters 10000 --seed 7
```

The evaluator clones missing repositories and caches parsed base-commit
entities. BM25-local raises Hit@20 from 34.1% to 47.3%; corrected KG-local
reaches 51.6%, and MURAL reaches 54.9%. The MURAL--BM25-local difference is
+7.7 points (11 wins, 4 losses), with a 95% interval [0.0, +16.5] and exact
McNemar p=.1185; it remains inconclusive at N=91.

### Official Repair Outcomes

Generation uses `run_repair_profile_batch.py` with the dated settings in
`repair_protocol_glm5_20260715.json`. Repository-disjoint shards prevent
workers from sharing a mutable checkout. The assembler then fails closed on a
missing issue, wrong dataset, stale context profile, prompt overrun, response
prefill, enabled thinking mode, or mismatched retry limit.

```bash
RUN_ROOT=temp_run/mural_experiment_additions/repair_glm5_corrected_v3_20260715
PRED="$RUN_ROOT/predictions"
CANON="$RUN_ROOT/canonical"
OFFICIAL="$RUN_ROOT/official"

python3 artifacts/scripts/assemble_repair_profile_predictions.py \
  --run-root "$RUN_ROOT" \
  --ids-file temp_run/repair_corrected_ids.txt \
  --output-root "$PRED" \
  --variants issue bm25 mural --shards shard_0 shard_1 \
  --model-prefix glm5_corrected \
  --expected-dataset-source "$PWD/temp_run/generated/SWE-bench_Verified.jsonl" \
  --dataset-label temp_run/generated/SWE-bench_Verified.jsonl \
  --expected-context-profile rank_stratified_v3_allfiles \
  --expected-max-retries 1 --max-prompt-tokens 5000 \
  --require-no-prefill --require-thinking-disabled

python3 artifacts/scripts/deduplicate_repair_predictions.py \
  --predictions-root "$PRED" --output-root "$CANON" \
  --variants issue bm25 mural --model-prefix glm5_corrected_unique

for slot in 0 1 2; do
  run_id="mural_glm5_corrected_slot_${slot}_20260715"
  python3 -m swebench.harness.run_evaluation \
    -d temp_run/generated/SWE-bench_Verified.jsonl -s test \
    -p "$CANON/slot_${slot}/predictions.jsonl" \
    --max_workers 5 --open_file_limit 8192 -t 1800 \
    --cache_level env --clean False -id "$run_id"
  python3 artifacts/scripts/collect_swebench_reports.py \
    --predictions "$CANON/slot_${slot}/predictions.jsonl" \
    --run-id "$run_id" \
    --output "$CANON/slot_${slot}/official_results.jsonl" \
    --normalize-terminal-errors
done

python3 artifacts/scripts/materialize_repair_variant_reports.py \
  --canonical-root "$CANON" --output-root "$OFFICIAL" \
  --variants issue bm25 mural

python3 artifacts/scripts/analyze_repair_outcomes.py \
  --ids-file temp_run/repair_corrected_ids.txt \
  --predictions-root "$PRED" --official-root "$OFFICIAL" \
  --output-outcomes artifacts/results/repair_glm5_outcomes_20260715.tsv \
  --output-summary artifacts/results/repair_glm5_summary_20260715.tsv
```

The hash mapping evaluates 1,035 distinct same-instance patches for the 1,319
nonempty variant predictions; the 284 exact duplicates reuse the corresponding
official report. Empty predictions remain in the 500-instance denominator.
Across the 1,035 canonical evaluations, 1,018 produced standard harness
reports; the collector records seven confirmed patch-application failures and
ten confirmed 1,800-second test timeouts as unresolved. Any missing report
caused by an image, network, or other infrastructure failure remains a hard
error rather than an outcome.

### Patch-Derived Coverage

```bash
python3 artifacts/scripts/evaluate_patch_derived_context.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --gt-cache temp_run/output/gt_eval_cache_verified_v3_entities.json \
  --target-cache artifacts/results/patch_derived_context_targets_20260702.json \
  --output-tsv logs/comparison_current/patch_derived_context_summary_20260702.tsv \
  --output-json logs/comparison_current/patch_derived_context_summary_20260702.json \
  --row "BM25 files + file-local=bm25_filelocal=temp_run/private_bm25_filelocal_20260704/bm25_top20_files_filelocal" \
  --row "BM25+KG RRF file-local=bm25_kg_rrf_filelocal=temp_run/private_bm25_filelocal_20260704/hybrid_rrf/BM25_KG_deterministic_rrf" \
  --row "GLM-5 + BM25 files + file-local=glm5_bm25_filelocal=temp_run/private_bm25_filelocal_20260704/budget_fusions/GLM5_BM25FileLocal_b20_p10" \
  --row "GLM-5 + BM25+KG RRF file-local=glm5_bm25_kg_rrf_filelocal=temp_run/private_bm25_filelocal_20260704/hybrid_rrf/deterministic_budget_fusions/GLM5_Hybrid_b20_p10" \
  --top-k 20
```

### Paired Edit-Target Statistics

```bash
python3 artifacts/scripts/analyze_edit_target_paired_stats.py \
  --ids-file temp_run/SWE-bench_Verified_ids.jsonl \
  --target-cache artifacts/results/patch_derived_context_targets_20260702.json \
  --group BM25=runs/text_baselines_nohints/2000 \
  --group BM25_filelocal=temp_run/private_bm25_filelocal_20260704/bm25_top20_files_filelocal \
  --group KG_grounded=runs/kg_verified_evidence_graph/tse_timesafe_main_20260529_v6 \
  --group KG_filelocal=runs/kg_verified_evidence_graph/tse_timesafe_main_20260531_pathunion_v1 \
  --group MURAL=temp_run/private_bm25_filelocal_20260704/hybrid_rrf/BM25_KG_deterministic_rrf \
  --group GLM5_BM25_filelocal=temp_run/private_bm25_filelocal_20260704/budget_fusions/GLM5_BM25FileLocal_b20_p10 \
  --group GLM5_MURAL=temp_run/private_bm25_filelocal_20260704/hybrid_rrf/deterministic_budget_fusions/GLM5_Hybrid_b20_p10 \
  --compare BM25=BM25_filelocal \
  --compare KG_grounded=KG_filelocal \
  --compare BM25_filelocal=MURAL \
  --compare GLM5_BM25_filelocal=GLM5_MURAL \
  --bootstrap-iters 10000 \
  --seed 7 \
  --output artifacts/results/edit_target_paired_stats_20260713.tsv
```

The exact GLM-5 endpoint identifier, evaluation snapshot, and frozen
localization prompt are reported in the supplementary material and under
`artifacts/prompts/`.
