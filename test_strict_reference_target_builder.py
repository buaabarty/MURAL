import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).parent / "artifacts" / "scripts" / "build_strict_reference_targets.py"
SPEC = importlib.util.spec_from_file_location("strict_targets", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parser_matches_the_published_candidate_unit_contract():
    source = """
LIMIT: int = 3
PLAIN = 4
LEFT, RIGHT = 1, 2
class Owner:
    value: str = 'x'
    plain = 'y'
    first, second = 1, 2
    def direct(self):
        return 1
    async def outer(self):
        def nested():
            return 1
        return nested()
"""
    entities, error = MODULE.parse_entities(source, "pkg/mod.py")
    assert error is None
    identities = {(item.kind, item.qualified_name) for item in entities}
    assert identities == {
        ("assignment", "PLAIN"),
        ("assignment", "Owner.plain"),
        ("function", "Owner.direct"),
    }


def test_mixed_entity_and_file_targets_are_both_retained():
    targets = [
        MODULE.file_target("pkg/mod.py", "outer"),
        MODULE.target_record(
            MODULE.Entity("pkg/mod.py", "function", "target", 2, 4), "line"
        ),
    ]
    selected = MODULE.deduplicate_targets(targets)
    assert [item["target_type"] for item in selected] == ["file", "function"]


def test_file_targets_remain_for_unmappable_instance():
    targets = [
        MODULE.file_target("pkg/mod.py", "outer"),
        MODULE.file_target("pkg/mod.py", "added"),
        MODULE.file_target("pkg/other.py", "non_python"),
    ]
    selected = MODULE.deduplicate_targets(targets)
    assert {item["file_path"] for item in selected} == {"pkg/mod.py", "pkg/other.py"}
