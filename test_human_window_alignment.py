import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).parent
SCRIPT = ROOT / "artifacts" / "scripts" / "prepare_human_window_reaudit.py"
SPEC = importlib.util.spec_from_file_location("prepare_human_window_reaudit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def candidate(path, name, signature=None, line=10):
    return {
        "file_path": path,
        "entity_type": "method",
        "name": name,
        "signature": signature or f"{name}()",
        "start_line": line,
        "end_line": line + 2,
    }


def test_render_window_has_stable_rank_and_signature_compaction():
    long_signature = "pkg.target(" + "value " * 100 + ")"
    candidates = [candidate("pkg/a.py", "pkg.target", long_signature)] * 20
    rendered = MODULE.render_window(candidates)
    first = rendered.splitlines()[0]
    assert first.startswith("01. pkg/a.py :: pkg.target(")
    assert first.endswith("...")
    assert len(first.split(" :: ", 1)[1]) == MODULE.DISPLAY_WIDTH


def test_rebuild_preserves_blinding_and_flags_changed_windows():
    mural = [candidate("pkg/m.py", f"pkg.m{i}") for i in range(20)]
    bm25 = [candidate("pkg/b.py", f"pkg.b{i}") for i in range(20)]
    old = {
        "protocol": {"random_seed": 7},
        "items": [
            {
                "annotation_id": "WIN-001",
                "instance_id": "repo__repo-1",
                "assignment": "shared",
                "method_a": "MURAL",
                "method_b": "BM25-local",
                "window_a": MODULE.render_window(mural),
                "window_b": "old window",
            }
        ],
    }
    rebuilt, alignment = MODULE.rebuild(
        old,
        {"repo__repo-1": {"MURAL": mural, "BM25_projection": bm25}},
        "a" * 64,
        "2026-07-19",
    )
    item = rebuilt["items"][0]
    assert item["method_a"] == "MURAL"
    assert item["method_b"] == "BM25-local"
    assert item["window_a"] == MODULE.render_window(mural)
    assert item["window_b"] == MODULE.render_window(bm25)
    assert item["requires_reannotation"] is True
    assert alignment[0]["window_a_changed"] == 0
    assert alignment[0]["window_b_changed"] == 1
