import importlib.util
import sys
from pathlib import Path


SCRIPT = (
    Path(__file__).parent
    / "artifacts"
    / "scripts"
    / "evaluate_strict_external_localizers.py"
)
SPEC = importlib.util.spec_from_file_location("strict_external", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


SOURCE = """
class Class:
    def target(self):
        return 1

    def neighbor(self):
        return 2
"""


def resolve(monkeypatch, location):
    monkeypatch.setattr(MODULE, "read_commit_file", lambda *args: SOURCE)
    row = {
        "found_files": ["pkg/mod.py"],
        "found_related_locs": {"pkg/mod.py": [location]},
    }
    reference = {"repo": "owner/repo", "base_commit": "abc"}
    return MODULE.resolve_external_candidates(
        row,
        reference,
        Path("."),
        limit=20,
        entity_cache={},
    )


def test_unknown_kind_requires_exact_unique_base_entity(monkeypatch):
    result = resolve(monkeypatch, "Class.target")
    assert len(result) == 1
    assert result[0]["label"] == "Class.target"


def test_suffix_only_external_label_is_rejected(monkeypatch):
    assert resolve(monkeypatch, "target") == []


def test_class_tagged_method_resolves_to_exact_entity(monkeypatch):
    result = resolve(monkeypatch, "class: Class.target")
    assert [item["label"] for item in result] == ["Class.target"]


def test_class_prediction_expands_to_direct_members(monkeypatch):
    result = resolve(monkeypatch, "class: Class")
    assert [item["label"] for item in result] == ["Class.target", "Class.neighbor"]


def test_declared_kind_must_match_base_entity(monkeypatch):
    assert resolve(monkeypatch, "variable: Class.target") == []
