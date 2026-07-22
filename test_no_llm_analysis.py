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
