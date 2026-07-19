import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

IDENTITY_SCRIPT = Path(__file__).parent / "artifacts" / "scripts" / "entity_identity.py"
IDENTITY_SPEC = importlib.util.spec_from_file_location("entity_identity", IDENTITY_SCRIPT)
IDENTITY_MODULE = importlib.util.module_from_spec(IDENTITY_SPEC)
assert IDENTITY_SPEC.loader is not None
sys.modules[IDENTITY_SPEC.name] = IDENTITY_MODULE
IDENTITY_SPEC.loader.exec_module(IDENTITY_MODULE)


SCRIPT = (
    Path(__file__).parent
    / "artifacts"
    / "scripts"
    / "export_path_mined_filelocal.py"
)
SPEC = importlib.util.spec_from_file_location("entity_projection", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sections(**overrides):
    values = {
        "title_terms": set(),
        "title_exact_terms": set(),
        "narrative_terms": set(),
        "exact_terms": set(),
        "diagnostic_terms": set(),
        "issue_terms": set(),
    }
    values.update(overrides)
    return values


def item(name="target", source="def target():\n    return 1", line=10):
    return {
        "name": name,
        "signature": f"pkg.mod.{name}()",
        "file_path": "pkg/mod.py",
        "source_code": source,
        "doc_string": "",
        "start_line": line,
    }


def file_record(rank=1):
    return {
        "best_rank": rank,
        "support": 0,
        "distance": rank,
        "anchor_match": False,
    }


def score(candidate, record, issue):
    return MODULE.score_item(
        deepcopy(candidate),
        deepcopy(record),
        deepcopy(issue),
        original_rank=None,
    )["ranking_key"]


def test_selector_schema_is_the_released_compact_key():
    key = score(item(), file_record(), sections())
    assert MODULE.SELECTOR_VERSION == "compact_title_exact_file_rank_ast_v1"
    assert len(key) == 8
    assert key[5:] == [1, 10, "target"]


def test_title_symbol_precedes_file_rank():
    issue = sections(title_terms={"target"})
    title_match = score(item("target"), file_record(rank=20), issue)
    no_match = score(item("other"), file_record(rank=1), issue)
    assert title_match < no_match


def test_exact_symbol_precedes_file_rank_when_title_ties():
    issue = sections(exact_terms={"parse_value"})
    exact_match = score(item("parse_value"), file_record(rank=20), issue)
    no_match = score(item("other"), file_record(rank=1), issue)
    assert exact_match < no_match


def test_file_rank_and_source_span_break_remaining_ties():
    issue = sections()
    first_file = score(item(line=30), file_record(rank=1), issue)
    later_file = score(item(line=1), file_record(rank=2), issue)
    assert first_file < later_file

    earlier_span = score(item(line=10), file_record(rank=1), issue)
    later_span = score(item(line=20), file_record(rank=1), issue)
    assert earlier_span < later_span
