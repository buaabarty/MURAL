# MURAL

MURAL (Multi-source Unification of Retrieval And Localization) constructs
bounded code context for issue-driven repository repair. BM25 and dense
ranked-file adapters feed one deterministic Entity Projection operator. The
structural adapter canonically unifies its native entity ranking with the same
projection applied to structurally ranked files. Reciprocal-rank fusion combines
the three entity rankings, and prefix-preserving filling completes an upstream
localizer without changing its resolved prefix.

The default configuration combines BM25 lexical retrieval, dense code
retrieval, and typed structural retrieval. Every adapter obeys the same entity
identity and budget contract before fusion. The historical `kgcompass/` package
name remains for API compatibility.

## Verify the paper-facing artifact

```bash
python3 artifacts/scripts/verify_paper_results.py
```

The verifier checks the retained result inventory, 1,044-target mapping, all
article-facing aggregates and paired statistics, prompt hashes, the exact
annotator-visible audit windows and judgments, the complete Java population,
frozen ranking digests, and every SHA-256 entry in the submission manifest.

## Evaluation scope

- all 500 SWE-bench Verified instances, with entity targets matched by exact
  path, kind, and qualified symbol and out-of-contract regions matched by an
  exact-path fallback;
- Top-20 localization, 2,000--8,000-token controls, selector controls, source
  composition, RRF sensitivity, and fixed-prefix completion;
- four released Qwen2.5-32B localizer outputs completed through the same
  prefix-preserving interface;
- all 91 SWE-bench-Java Verified instances across all six repositories;
- 100 blinded judgments over 80 Python instances;
- matched 4,000-token GLM-5.2 repair on all 500 Python instances, evaluated by
  the official SWE-bench harness.

## Layout

| Path | Purpose |
| --- | --- |
| `kgcompass/` | Retrieval, context rendering, and repair integration. |
| `artifacts/scripts/` | Exporters, evaluators, statistical analyzers, and verifier. |
| `artifacts/results/` | Retained aggregate and per-instance paper ledgers. |
| `artifacts/frozen/` | Compact Top-50 rankings and external-source provenance. |
| `artifacts/inputs/` | Frozen Java inputs and benchmark manifests. |
| `artifacts/prompts/` | Localization and repair prompts. |
| `artifacts/submission_manifest_20260719.json` | Protocol and SHA-256 inventory. |
| `artifacts/RESULT_TRACEABILITY.md` | Claim-to-ledger and regeneration map. |

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Full source regeneration additionally requires benchmark repository checkouts,
Neo4j for the structural adapter, and the pinned dense encoder. Hosted repair
generation reads `AUTODL_API_KEY` from the environment; no credential is stored
in this repository.
