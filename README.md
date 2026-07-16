# MURAL

MURAL (Multi-source Unification of Retrieval And Localization) constructs a
fixed-budget code context for issue-driven repository repair. Each retrieval
adapter emits ranked files, one shared Entity Projection operator resolves those
files into concrete code entities, and reciprocal-rank fusion (RRF) combines the
entity rankings. MURAL can also preserve an existing localizer prefix and fill
only its remaining context slots.

The default configuration uses three interchangeable sources:

- lexical file retrieval with BM25;
- dense code retrieval;
- a typed structural repository adapter.

The structural adapter is one source implementation, not a prerequisite for the
framework. The historical `kgcompass/` package name remains for API
compatibility.

## Verify the paper-facing results

```bash
python3 artifacts/scripts/verify_paper_results.py --scope all
```

The verifier checks the exact retained result inventory, benchmark completeness,
aggregate values, paired bootstrap intervals, exact McNemar tests for
nonempty, applicable, and resolved repair outcomes, prediction provenance, and
the cross-language ID-set contract. No API key is
stored in this repository.

## Repository layout

| Path | Purpose |
| --- | --- |
| `kgcompass/` | Source adapters, localization, context rendering, and repair integration. |
| `artifacts/scripts/` | Exporters, evaluators, statistical analyzers, and the result verifier. |
| `artifacts/results/` | Paper-facing aggregate and per-instance ledgers only. |
| `artifacts/inputs/` | Frozen provenance records and Java structural-source inputs. |
| `artifacts/prompts/` | Verbatim localization and repair prompts. |
| `artifacts/RESULT_TRACEABILITY.md` | Claim-to-ledger mapping and rerun commands. |

The retained evaluation covers:

- all 500 SWE-bench Verified instances for localization and edit-target
  coverage;
- BM25, dense, structural, and released-LLM source controls under one Top-20
  entity budget;
- source composition, RRF, budget, and repository-level analyses;
- all 91 official SWE-bench-Java Verified instances for the cross-language
  adapter check;
- end-to-end GLM-5.2 repair and official test-oracle outcomes on all 500
  SWE-bench Verified instances;
- measured context-construction time and memory.

See `artifacts/README.md` for the publication inventory and
`artifacts/RESULT_TRACEABILITY.md` for exact provenance.

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Full reruns require the benchmark repositories and archived upstream localizer
outputs listed in `artifacts/RESULT_TRACEABILITY.md`. Hosted repair generation
reads its key from `AUTODL_API_KEY`; the key must be supplied through the
environment.

## Web demo

```bash
pip install -r requirements_web.txt
python3 demo_web.py
```

The Flask entry point is also available through `python3 app.py`.
