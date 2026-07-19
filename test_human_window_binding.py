import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent
SCRIPT = ROOT / "artifacts" / "scripts" / "verify_human_window_binding.py"
SPEC = importlib.util.spec_from_file_location("verify_human_window_binding", SCRIPT)
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


def test_verify_accepts_exact_blinded_windows_and_rejects_drift():
    mural = [candidate("pkg/m.py", f"pkg.m{i}") for i in range(20)]
    bm25 = [candidate("pkg/b.py", f"pkg.b{i}") for i in range(20)]
    payload = {
        "items": [
            {
                "annotation_id": "WIN-001",
                "instance_id": "repo__repo-1",
                "assignment": "shared",
                "method_a": "MURAL_2src",
                "method_b": "BM25_projection",
                "window_a": MODULE.render_window(mural),
                "window_b": MODULE.render_window(bm25),
            }
        ]
    }
    rankings = {
        "repo__repo-1": {
            "MURAL_2src": mural,
            "BM25_projection": bm25,
        }
    }
    binding = MODULE.verify(payload, rankings)
    assert binding[0]["exact_match_a"] == 1
    assert binding[0]["exact_match_b"] == 1

    payload["items"][0]["window_b"] = "changed"
    with pytest.raises(ValueError, match="does not match"):
        MODULE.verify(payload, rankings)
