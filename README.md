# MURAL

MURAL (Multi-source Unification of Retrieval And Localization) constructs a
fixed-budget code context for issue-driven repository repair. Ranked-file
sources pass through one compact file-local selector, completed entity rankings
are combined with reciprocal-rank fusion (RRF), and an optional localizer prefix
is preserved while MURAL fills the remaining positions.

This repository is the public artifact for the MURAL manuscript and its
separately compiled supplementary material. The historical `kgcompass/`
package name remains for API compatibility. In frozen ledgers, `KGCompass`
corresponds to the paper's `KG-local` source.

## Verify the reported results

```bash
python3 artifacts/scripts/verify_paper_results.py
```

A successful run reports:

```json
{
  "ok": true,
  "scope": "all",
  "failed": []
}
```

The verifier checks the exact result inventory and 1,500+ values and contracts,
including target mapping, localization, paired significance tests, edit-target
coverage, official repair outcomes, complete benchmark splits, repository
breakdowns, and context-construction cost.

## Repository layout

| Path | Purpose |
| --- | --- |
| `kgcompass/` | Core localization and repair implementation. |
| `scripts/` | Full-workspace experiment and aggregation scripts. |
| `artifacts/scripts/` | Submission-side exporters, evaluators, analyzers, and verifier. |
| `artifacts/results/` | Ledgers used by the manuscript and supplementary material. |
| `artifacts/inputs/` | Frozen provenance records and Java structural-source inputs. |
| `artifacts/prompts/` | Verbatim localization and repair prompts. |
| `artifacts/RESULT_TRACEABILITY.md` | Claim-to-ledger mapping and rerun commands. |

The main result families are:

- controlled BM25, KG, dense, and MURAL localization;
- compact-selector simplification and RRF/budget sensitivity;
- fixed-prefix GLM-5 and released Qwen2.5-32B localizer augmentation;
- mapped edit-target recall and complete coverage;
- the complete 500-by-3 GLM-5 repair outcome ledger;
- the complete 91-instance SWE-bench-Java Verified evaluation;
- per-repository and context-construction-cost breakdowns.

See `artifacts/README.md` for the retained file inventory and
`artifacts/RESULT_TRACEABILITY.md` for exact provenance.

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Full reruns additionally require benchmark checkouts and archived model outputs
described in `artifacts/RESULT_TRACEABILITY.md`.

## Web demo

```bash
pip install -r requirements_web.txt
python3 demo_web.py
```

The Flask entry point is also available through `python3 app.py`.
