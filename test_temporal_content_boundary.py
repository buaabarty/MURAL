import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent / "kgcompass"))

from fl import CodeAnalyzer


def analyzer_at(timestamp: float) -> CodeAnalyzer:
    analyzer = CodeAnalyzer.__new__(CodeAnalyzer)
    analyzer.created_at = timestamp
    analyzer.artifact_stats = {
        "skipped_due_to_time": 0,
        "skipped_due_to_content_time": 0,
        "skipped_due_to_unknown_content_time": 0,
        "valid_related_items": 0,
    }
    analyzer.counted_skipped_artifact_ids = set()
    analyzer.counted_valid_artifact_ids = set()
    analyzer.counted_content_time_skips = set()
    analyzer.counted_unknown_content_time_skips = set()
    return analyzer


def artifact(created: float, updated: float | None):
    return SimpleNamespace(
        created_at=datetime.fromtimestamp(created, timezone.utc),
        updated_at=(
            None if updated is None else datetime.fromtimestamp(updated, timezone.utc)
        ),
    )


def test_content_must_be_created_and_final_by_cutoff(monkeypatch):
    monkeypatch.setenv("KGCOMPASS_STRICT_CONTENT_CUTOFF", "1")
    analyzer = analyzer_at(1_000.0)

    assert analyzer._artifact_content_visible_at_cutoff(artifact(100, 900), "old")
    assert not analyzer._artifact_content_visible_at_cutoff(artifact(100, 1_100), "edited")
    assert not analyzer._artifact_content_visible_at_cutoff(artifact(1_100, 1_100), "future")
    assert not analyzer._artifact_content_visible_at_cutoff(artifact(100, None), "unknown")
    assert analyzer.artifact_stats["skipped_due_to_content_time"] == 1
    assert analyzer.artifact_stats["skipped_due_to_time"] == 1
    assert analyzer.artifact_stats["skipped_due_to_unknown_content_time"] == 1


def test_non_strict_mode_keeps_creation_time_boundary(monkeypatch):
    monkeypatch.setenv("KGCOMPASS_STRICT_CONTENT_CUTOFF", "0")
    analyzer = analyzer_at(1_000.0)

    assert analyzer._artifact_content_visible_at_cutoff(artifact(100, 1_100), "edited")
    assert not analyzer._artifact_content_visible_at_cutoff(artifact(1_100, 1_100), "future")
