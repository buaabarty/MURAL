import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parent / "artifacts" / "scripts" / "evaluate_strict_reference_context.py"
SPEC = importlib.util.spec_from_file_location("strict_eval", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def candidate(signature, file_path="pkg/mod.py", source="def target():\n    pass"):
    return {
        "signature": signature,
        "file_path": file_path,
        "source_code": source,
    }


def target(kind, name="Class.target", file_path="pkg/mod.py"):
    return {
        "target_type": kind,
        "qualified_name": name,
        "file_path": file_path,
    }


def test_exact_qualified_name_matches():
    item = candidate("pkg.mod.Class.target(self)")
    assert MODULE.candidate_matches_target(item, target("function"))


def test_same_class_different_method_does_not_match():
    item = candidate("pkg.mod.Class.neighbor(self)")
    assert not MODULE.candidate_matches_target(item, target("function"))


def test_path_must_match_exactly():
    item = candidate("pkg.mod.Class.target(self)", file_path="other/pkg/mod.py")
    assert not MODULE.candidate_matches_target(item, target("function"))


def test_assignment_kind_and_name_are_strict():
    item = candidate(
        "pkg.mod.Class.limit = 10",
        source="limit = 10",
    )
    assert MODULE.candidate_matches_target(item, target("assignment", "Class.limit"))
    assert not MODULE.candidate_matches_target(item, target("function", "Class.limit"))


def test_file_target_accepts_any_ranked_entity_in_exact_file():
    item = candidate("pkg.mod.unrelated()")
    assert MODULE.candidate_matches_target(item, target("file", ""))
    assert not MODULE.candidate_matches_target(
        item, target("file", "", file_path="pkg/other.py")
    )
