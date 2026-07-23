import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).parent / "artifacts" / "scripts"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


COMPLETION = load("external_completion", "export_external_localizer_completions.py")
HUMAN = load("human_window_strata", "analyze_human_window_strata.py")
CLUSTER = load("cluster_randomization", "analyze_primary_cluster_randomization.py")
FALLBACK = load("fallback_evidence", "analyze_target_fallback_evidence.py")
REPAIR_COVERAGE = load(
    "repair_target_coverage", "analyze_repair_target_coverage.py"
)


def candidate(name: str) -> dict:
    return {
        "file_path": "pkg/mod.py",
        "kind": "function",
        "name": name,
        "label": name,
        "signature": f"{name}()",
        "source_code": f"def {name}():\n    pass",
    }


def test_round_robin_deduplicates_without_changing_source_order():
    shared = candidate("shared")
    result = COMPLETION.round_robin(
        [[candidate("a"), shared], [candidate("b"), shared]], limit=4
    )
    assert [item["name"] for item in result] == ["a", "b", "shared"]


def test_audit_strata_uses_the_exact_displayed_windows():
    rows = [
        {"approach": "BM25-local", "instance_id": "repo__x-1", "hit": "0"},
        {"approach": "MURAL", "instance_id": "repo__x-1", "hit": "1"},
        {"approach": "BM25-local", "instance_id": "repo__x-2", "hit": "1"},
        {"approach": "MURAL", "instance_id": "repo__x-2", "hit": "1"},
    ]
    assert HUMAN.localization_strata(rows) == {
        "repo__x-1": "MURAL_only",
        "repo__x-2": "both",
    }


def test_exact_cluster_sign_flip_enumerates_all_assignments():
    assert CLUSTER.exact_sign_flip([1.0, 1.0]) == 0.5
    assert CLUSTER.exact_sign_flip([0.0, 0.0]) == 1.0


def test_fallback_evidence_flags_are_exact_tokens():
    flags = FALLBACK.evidence_flags(
        "base_scope_change+added_or_outer_scope_change"
    )
    assert flags["base_scope"] == 1
    assert flags["added_or_outer_scope"] == 1
    assert flags["patched_parse_failure"] == 0


def test_repair_target_coverage_joins_and_bins_by_variant():
    prompts = [
        {
            "instance_id": instance_id,
            "repository": "repo__x",
            "variant": variant,
            "target_count": "2",
            "source_target_coverage": coverage,
        }
        for instance_id, coverage in (
            ("repo__x-1", "0"),
            ("repo__x-2", "1"),
        )
        for variant in ("bm25", "mural")
    ]
    outcomes = [
        {"instance_id": "repo__x-2", "variant": "mural", "resolved": "1"},
        {"instance_id": "repo__x-1", "variant": "bm25", "resolved": "0"},
        {"instance_id": "repo__x-2", "variant": "bm25", "resolved": "1"},
        {"instance_id": "repo__x-1", "variant": "mural", "resolved": "0"},
    ]
    joined = REPAIR_COVERAGE.join_rows(prompts, outcomes)
    assert len(joined) == 4
    assert {row["target_band"] for row in joined} == {"multi"}

    rows = REPAIR_COVERAGE.summarize_two_target_bins(joined)
    indexed = {
        (row["variant"], row["coverage_bin"]): row
        for row in rows
    }
    assert indexed[("bm25", "zero")]["resolved_rate"] == "0.000000"
    assert indexed[("bm25", "complete")]["resolved_rate"] == "100.000000"
    assert indexed[("mural", "partial")]["N"] == 0
    assert indexed[("mural", "complete")] == {
        "target_count": 2,
        "variant": "mural",
        "coverage_bin": "complete",
        "N": 1,
        "resolved": 1,
        "resolved_rate": "100.000000",
    }
