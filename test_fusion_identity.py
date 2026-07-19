import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).parent


def load_module(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


IDENTITY = load_module(
    "entity_identity",
    "artifacts/scripts/entity_identity.py",
)
RRF = load_module(
    "rrf_fusion",
    "artifacts/scripts/export_multi_source_rrf_fusion.py",
)
PREFIX = load_module(
    "fixed_prefix_fusion",
    "artifacts/scripts/export_fixed_prefix_fusion.py",
)
STRUCTURAL = load_module(
    "structural_union",
    "artifacts/scripts/fuse_path_mined_with_kg.py",
)


def entity(path, signature, source="def target():\n    pass", score=1.0):
    return {
        "file_path": path,
        "name": signature.split("(", 1)[0].split(" = ", 1)[0],
        "signature": signature,
        "source_code": source,
        "similarity": score,
        "start_line": 10,
    }


def test_rrf_preserves_adapter_order_even_when_native_scores_differ():
    first = entity("pkg/first.py", "pkg.first.target()", score=0.1)
    second = entity("pkg/second.py", "pkg.second.target()", score=0.9)
    payload = {"related_entities": {"methods": [first, second]}}
    assert RRF.ranked_entities(payload, "methods") == [first, second]


def test_rrf_identity_keeps_same_symbol_in_different_files():
    left = entity("pkg/a.py", "pkg.a.target()")
    right = entity("pkg/b.py", "pkg.b.target()")
    assert RRF.entity_id(left) != RRF.entity_id(right)


def test_rrf_identity_merges_getter_and_setter_but_not_assignment():
    getter = entity("pkg/a.py", "pkg.a.C.value(self)")
    setter = entity("pkg/a.py", "pkg.a.C.value(self, value)")
    assignment = entity(
        "pkg/a.py",
        "pkg.a.C.value = 1",
        source="value = 1",
    )
    assert RRF.entity_id(getter) == RRF.entity_id(setter)
    assert RRF.entity_id(getter) != RRF.entity_id(assignment)


def test_canonical_identity_preserves_classes_as_a_distinct_kind():
    class_item = entity("pkg/a.py", "pkg.a.C", source="class C:\n    pass")
    class_item["entity_type"] = "class"
    function_item = entity("pkg/a.py", "pkg.a.C()")
    assert IDENTITY.canonical_entity_id(class_item) == ("pkg/a.py", "class", "pkg.a.C")
    assert IDENTITY.canonical_entity_id(class_item) != IDENTITY.canonical_entity_id(
        function_item
    )


def test_structural_union_deduplicates_signature_and_span_variants():
    original = entity("pkg/a.py", "pkg.a.target(value)")
    projected = entity("pkg/a.py", "pkg.a.target(other)")
    projected["start_line"] = 30
    fused = STRUCTURAL.fuse_entity_lists([original], [projected])
    assert len(fused) == 1
    assert fused[0]["evidence"]["rank_union"] == {
        "kg_rank": 1,
        "path_mined_rank": 1,
    }


def test_fixed_prefix_uses_path_kind_symbol_identity():
    primary = [
        entity("pkg/a.py", "pkg.a.C.value(self)"),
        entity("pkg/b.py", "pkg.b.C.value(self)"),
    ]
    secondary = [
        entity("pkg/a.py", "pkg.a.C.value(self, value)"),
        entity("pkg/a.py", "pkg.a.C.other(self)"),
    ]
    result = PREFIX.fuse(primary, secondary, budget=4, primary_prefix=1, secondary_pool=2)
    identities = [PREFIX.entity_id(item) for item in result]
    assert identities == [
        PREFIX.entity_id(primary[0]),
        PREFIX.entity_id(secondary[1]),
        PREFIX.entity_id(primary[1]),
    ]
