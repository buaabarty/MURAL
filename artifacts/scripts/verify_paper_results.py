#!/usr/bin/env python3
"""Verify submission-facing numbers from retained artifact ledgers.

This checker reads only committed files under artifacts/results/ and validates
the quantitative values used by the MURAL manuscript and supplementary
material. It also checks that the result directory does not contain unreported
legacy ledgers.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "artifacts" / "results"
INPUTS = ROOT / "artifacts" / "inputs"

EXPECTED_RESULT_FILES = {
    "dense_third_source_paired_20260714.tsv",
    "dense_third_source_summary_20260714.tsv",
    "edit_target_paired_stats_20260713.tsv",
    "glm5_baseline_fusion_controls_top10_20260614.tsv",
    "java_cross_language_instances_20260714.jsonl",
    "java_cross_language_paired_20260714.tsv",
    "java_cross_language_summary_20260714.tsv",
    "java_cross_language_targets_20260714.json",
    "kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json",
    "path_mining_file_expansion_ablation_20260531.tsv",
    "patch_derived_context_summary_20260702.json",
    "patch_derived_context_summary_20260702.tsv",
    "patch_derived_context_targets_20260702.json",
    "ranked_file_source_coverage_20260711.tsv",
    "ranked_file_source_paired_20260711.tsv",
    "repair_glm5_assembly_20260715.tsv",
    "repair_glm5_context_rendering_20260715.tsv",
    "repair_glm5_deduplication_summary_20260715.json",
    "repair_glm5_outcomes_20260715.tsv",
    "repair_glm5_prediction_mapping_20260715.tsv",
    "repair_glm5_summary_20260715.tsv",
    "retrieve_then_localize_budget_curve_20260711.tsv",
    "retrieve_then_localize_budget_paired_20260711.tsv",
    "retrieve_then_localize_disagreements_20260711.tsv",
    "retrieve_then_localize_paired_20260711.tsv",
    "retrieve_then_localize_top20_20260711.tsv",
    "selector_ablation_paired_20260714.tsv",
    "selector_ablation_summary_20260714.tsv",
    "time_boundary_external_artifact_sensitivity_20260531.tsv",
    "tse_gt_mapping_v6.tsv",
}

checks: list[dict[str, Any]] = []


def read_tsv(name: str) -> list[dict[str, str]]:
    path = RESULTS / name
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_json(name: str) -> Any:
    path = RESULTS / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def row_by(rows: list[dict[str, str]], key: str, value: str) -> dict[str, str]:
    for row in rows:
        if row.get(key) == value:
            return row
    raise AssertionError(f"row not found: {key}={value}")


def pct(value: str | float) -> float:
    return float(value) * 100.0


def record(name: str, observed: Any, expected: Any, ok: bool, source: str) -> None:
    if isinstance(observed, set):
        observed = sorted(observed)
    if isinstance(expected, set):
        expected = sorted(expected)
    checks.append(
        {
            "name": name,
            "ok": ok,
            "observed": observed,
            "expected": expected,
            "source": source,
        }
    )


def expect_close(name: str, observed: float, expected: float, source: str, tol: float = 0.05) -> None:
    record(name, round(observed, 6), expected, math.isclose(observed, expected, abs_tol=tol), source)


def expect_equal(name: str, observed: Any, expected: Any, source: str) -> None:
    record(name, observed, expected, observed == expected, source)


def expect_row_set(name: str, rows: list[dict[str, str]], key: str, expected: list[str], source: str) -> None:
    observed = [row[key] for row in rows]
    expect_equal(name, observed, expected, source)


def expect_metric_row(source: str, row: dict[str, str], expected: tuple[float, float, float, float], prefix: str) -> None:
    observed = (
        pct(row["file_rate"]),
        pct(row["method_or_entity_rate"]),
        pct(row["mrr"]),
        pct(row.get("top20_hit_rate", row.get("hit@20", row.get("hit_rate", "nan")))),
    )
    for metric, obs, exp in zip(("file", "method", "mrr", "hit"), observed, expected):
        expect_close(f"{prefix} {metric}", obs, exp, source)


def verify_result_inventory() -> None:
    observed = {
        str(path.relative_to(RESULTS)).replace("\\", "/")
        for path in RESULTS.rglob("*")
        if path.is_file()
    }
    expect_equal(
        "Submission-facing result file inventory",
        sorted(observed),
        sorted(EXPECTED_RESULT_FILES),
        "artifacts/results",
    )


def verify_setup() -> None:
    source = "tse_gt_mapping_v6.tsv"
    rows = read_tsv(source)
    expected = {
        "single_file": (429, 85.8),
        "multi_file": (71, 14.2),
        "has_method_target": (473, 94.6),
        "has_class_target": (66, 13.2),
        "single_entity": (350, 70.0),
        "multi_entity": (150, 30.0),
        "file_only_fallback": (9, 1.8),
    }
    for category, (count, percent) in expected.items():
        row = row_by(rows, "category", category)
        expect_equal(f"GT mapping {category} count", int(float(row["count"])), count, source)
        expect_close(f"GT mapping {category} percent", float(row["percent"]), percent, source)


def verify_rq1() -> None:
    source = "path_mining_file_expansion_ablation_20260531.tsv"
    rows = read_tsv(source)
    expected_rows = [
        "bm25_nohint",
        "bluir",
        "no_history_codegraph",
        "strict_kg_ablation",
        "full_pathmined",
    ]
    expect_row_set("RQ1/RQ3 controlled row set", rows, "name", expected_rows, source)
    expected = {
        "bm25_nohint": (77.0, 39.2, 25.3, 46.0),
        "bluir": (55.6, 38.6, 28.9, 43.4),
        "no_history_codegraph": (63.6, 35.2, 22.9, 41.0),
        "strict_kg_ablation": (55.6, 33.8, 22.2, 37.8),
        "full_pathmined": (59.2, 45.4, 26.3, 50.8),
    }
    for name, values in expected.items():
        expect_metric_row(source, row_by(rows, "name", name), values, f"RQ1 {name}")

    verify_retrieve_then_localize_controls()
    verify_selector_ablation()
    verify_dense_third_source()
    verify_java_cross_language()


def verify_selector_ablation() -> None:
    source = "selector_ablation_summary_20260714.tsv"
    rows = read_tsv(source)
    expected = {
        "Full": (73.6, 50.1, 28.6, 57.0),
        "minus_G1": (73.0, 48.4, 27.9, 55.2),
        "minus_G2": (73.2, 49.7, 28.5, 56.6),
        "minus_G3": (73.6, 50.1, 28.7, 57.0),
        "minus_G4": (73.6, 50.1, 28.5, 57.0),
        "minus_G5": (73.6, 50.1, 28.6, 57.0),
    }
    expect_row_set("Selector ablation row set", rows, "name", list(expected), source)
    for name, values in expected.items():
        expect_metric_row(source, row_by(rows, "name", name), values, f"Selector ablation {name}")

    paired_source = "selector_ablation_paired_20260714.tsv"
    paired = read_tsv(paired_source)
    hit_rows = {
        row["treatment"]: row
        for row in paired
        if row["baseline"] == "Full" and row["metric"] == "hit"
    }
    expect_equal("Selector ablation paired treatments", list(hit_rows), list(expected)[1:], paired_source)
    g1 = hit_rows["minus_G1"]
    expect_close("Selector minus G1 Hit delta", pct(g1["delta"]), -1.8, paired_source)
    expect_close("Selector minus G1 Hit CI low", pct(g1["ci95_low"]), -5.4, paired_source)
    expect_close("Selector minus G1 Hit CI high", pct(g1["ci95_high"]), 1.8, paired_source)
    expect_equal("Selector minus G1 Hit wins", int(g1["wins"]), 36, paired_source)
    expect_equal("Selector minus G1 Hit losses", int(g1["losses"]), 45, paired_source)
    expect_close(
        "Selector minus G1 exact p",
        float(g1["exact_mcnemar_p"]),
        0.3741744176047079,
        paired_source,
        tol=1e-15,
    )


def verify_dense_third_source() -> None:
    source = "dense_third_source_summary_20260714.tsv"
    rows = read_tsv(source)
    expected = {
        "Dense_raw": (89.4, 55.3, 36.4, 62.0),
        "Dense_local": (83.0, 56.7, 32.0, 64.0),
        "BM25_local": (73.6, 50.1, 28.6, 57.0),
        "KG_local": (59.2, 45.4, 26.3, 50.8),
        "MURAL_2src": (77.0, 55.3, 32.0, 62.8),
        "MURAL_3src": (82.6, 59.7, 34.2, 67.4),
        "GLM5_issue": (87.4, 53.0, 51.2, 62.4),
        "GLM5_BM25_local": (94.2, 69.2, 54.4, 78.0),
        "GLM5_MURAL_2src": (94.6, 70.9, 54.7, 79.0),
        "GLM5_MURAL_3src": (95.2, 71.7, 54.9, 80.2),
    }
    expect_row_set("Dense third-source row set", rows, "name", list(expected), source)
    for name, values in expected.items():
        expect_metric_row(source, row_by(rows, "name", name), values, f"Dense third source {name}")

    paired_source = "dense_third_source_paired_20260714.tsv"
    paired = read_tsv(paired_source)
    expected_hit = {
        ("Dense_raw", "Dense_local"): (2.0, -3.0, 6.8, 80, 70, 0.4625495178668303),
        ("BM25_local", "Dense_local"): (7.0, 3.8, 10.4, 54, 19, 5.0622659111780655e-05),
        ("MURAL_2src", "Dense_local"): (1.2, -2.4, 4.8, 46, 40, 0.5900356111485574),
        ("MURAL_2src", "MURAL_3src"): (4.6, 2.2, 7.2, 33, 10, 0.0006061066312668117),
        ("Dense_local", "MURAL_3src"): (3.4, 0.6, 6.4, 35, 18, 0.027008317653722358),
        ("GLM5_issue", "GLM5_MURAL_3src"): (17.8, 14.4, 21.2, 89, 0, 3.2311742677852644e-27),
        ("GLM5_BM25_local", "GLM5_MURAL_3src"): (2.2, 0.0, 4.4, 21, 10, 0.07075554598122835),
        ("GLM5_MURAL_2src", "GLM5_MURAL_3src"): (1.2, -0.2, 2.6, 9, 3, 0.14599609375),
    }
    observed_hit = {
        (row["baseline"], row["treatment"]): row for row in paired if row["metric"] == "hit"
    }
    expect_equal("Dense third-source paired Hit set", list(observed_hit), list(expected_hit), paired_source)
    for comparison, values in expected_hit.items():
        delta, low, high, wins, losses, p_value = values
        row = observed_hit[comparison]
        prefix = f"Dense third source {comparison[0]}->{comparison[1]} Hit"
        expect_close(f"{prefix} delta", pct(row["delta"]), delta, paired_source)
        expect_close(f"{prefix} CI low", pct(row["ci95_low"]), low, paired_source)
        expect_close(f"{prefix} CI high", pct(row["ci95_high"]), high, paired_source)
        expect_equal(f"{prefix} wins", int(row["wins"]), wins, paired_source)
        expect_equal(f"{prefix} losses", int(row["losses"]), losses, paired_source)
        expect_close(f"{prefix} exact p", float(row["exact_mcnemar_p"]), p_value, paired_source, tol=1e-15)


def verify_java_cross_language() -> None:
    manifest_source = "java_cross_language_manifest_20260714.json"
    with (INPUTS / manifest_source).open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    benchmark = manifest["benchmark"]
    expect_equal("Java benchmark name", benchmark["name"], "SWE-bench-Java Verified", manifest_source)
    expect_equal(
        "Java benchmark source repository",
        benchmark["dataset_repository"],
        "Daoguang/Multi-SWE-bench",
        manifest_source,
    )
    expect_equal(
        "Java benchmark source revision",
        benchmark["revision"],
        "8bd202138a4ab9987daa77111c76a3e66af9f1c9",
        manifest_source,
    )
    expect_equal("Java benchmark split", benchmark["split"], "java_verified", manifest_source)
    expect_equal("Java official instance count", benchmark["official_instances"], 91, manifest_source)
    expect_equal("Java evaluated instance count", benchmark["evaluated_instances"], 91, manifest_source)
    expect_equal("Java excluded instance count", benchmark["excluded_instances"], 0, manifest_source)
    expect_equal("Java official repository count", benchmark["repositories"], 6, manifest_source)
    expect_equal(
        "Java official ID-set hash",
        benchmark["instance_id_set_sha256"],
        "15cbf3065a33f11e328f792eff71761c1168b30425a8e81a15275afe5fc1f690",
        manifest_source,
    )

    source = "java_cross_language_summary_20260714.tsv"
    rows = read_tsv(source)
    expected = {
        "BM25": (61.5, 19.9, 13.5, 34.1),
        "BM25_local": (67.0, 32.2, 24.2, 47.3),
        "KG_local": (63.7, 35.3, 24.9, 51.6),
        "MURAL": (70.3, 35.1, 26.5, 54.9),
    }
    expect_row_set("Java cross-language row set", rows, "name", list(expected), source)
    for name, values in expected.items():
        row = row_by(rows, "name", name)
        expect_equal(f"Java cross-language {name} N", int(row["N"]), 91, source)
        expect_metric_row(source, row, values, f"Java cross-language {name}")

    paired_source = "java_cross_language_paired_20260714.tsv"
    paired = read_tsv(paired_source)
    expected_hit = {
        ("BM25", "BM25_local"): (13.2, 1.1, 25.3, 23, 11, 0.05761267291381955),
        ("BM25_local", "KG_local"): (4.4, -6.6, 15.4, 15, 11, 0.557197093963623),
        ("BM25_local", "MURAL"): (7.7, 0.0, 16.5, 11, 4, 0.11846923828125),
        ("KG_local", "MURAL"): (3.3, -4.4, 11.0, 8, 5, 0.5810546875),
    }
    observed_hit = {
        (row["baseline"], row["treatment"]): row
        for row in paired
        if row["metric"] == "hit"
    }
    expect_equal("Java cross-language paired Hit set", list(observed_hit), list(expected_hit), paired_source)
    for comparison, values in expected_hit.items():
        delta, low, high, wins, losses, p_value = values
        row = observed_hit[comparison]
        prefix = f"Java cross-language {comparison[0]}->{comparison[1]} Hit"
        expect_equal(f"{prefix} N", int(row["N"]), 91, paired_source)
        expect_close(f"{prefix} delta", pct(row["delta"]), delta, paired_source)
        expect_close(f"{prefix} CI low", pct(row["ci95_low"]), low, paired_source)
        expect_close(f"{prefix} CI high", pct(row["ci95_high"]), high, paired_source)
        expect_equal(f"{prefix} wins", int(row["wins"]), wins, paired_source)
        expect_equal(f"{prefix} losses", int(row["losses"]), losses, paired_source)
        expect_close(f"{prefix} exact p", float(row["exact_mcnemar_p"]), p_value, paired_source, tol=1e-15)

    targets_source = "java_cross_language_targets_20260714.json"
    targets = read_json(targets_source)
    expect_equal("Java cross-language target instances", targets["meta"]["N"], 91, targets_source)
    expect_equal("Java cross-language failures", targets["meta"]["failure_count"], 0, targets_source)
    expect_equal("Java cross-language target rows", len(targets["items"]), 91, targets_source)
    expect_equal("Java cross-language top-k", targets["meta"]["top_k"], 20, targets_source)
    expect_equal("Java cross-language RRF k", targets["meta"]["rrf_k"], 60, targets_source)
    expect_equal("Java cross-language bootstrap iterations", targets["meta"]["bootstrap_iterations"], 10000, targets_source)
    expect_equal("Java cross-language random seed", targets["meta"]["seed"], 7, targets_source)
    expect_equal(
        "Java cross-language mapped target count",
        sum(len(row["targets"]) for row in targets["items"]),
        342,
        targets_source,
    )
    expect_equal(
        "Java cross-language instance fallbacks",
        sum(int(row["file_fallbacks"]) for row in targets["items"]),
        0,
        targets_source,
    )
    expect_equal(
        "Java cross-language unmapped auxiliary or new files",
        sum(int(row["unmapped_patched_files"]) for row in targets["items"]),
        65,
        targets_source,
    )

    instance_source = "java_cross_language_instances_20260714.jsonl"
    instances = read_jsonl(RESULTS / instance_source)
    expect_equal("Java cross-language instance ledger rows", len(instances), 91, instance_source)
    expect_equal(
        "Java cross-language unique instance ids",
        len({row["instance_id"] for row in instances}),
        91,
        instance_source,
    )

    evaluated_ids = sorted(row["instance_id"] for row in instances)
    evaluated_id_hash = hashlib.sha256("\n".join(evaluated_ids).encode("utf-8")).hexdigest()
    expect_equal(
        "Java evaluated ID set matches complete official split",
        evaluated_id_hash,
        benchmark["instance_id_set_sha256"],
        instance_source,
    )
    expect_equal(
        "Java target-cache official ID-set hash",
        targets["meta"]["dataset_sha256"],
        benchmark["instance_id_set_sha256"],
        targets_source,
    )

    seed_source = "java_kg_ranked_file_seeds_20260714.jsonl"
    seeds = read_jsonl(INPUTS / seed_source)
    expect_equal("Java structural seed rows", len(seeds), 91, seed_source)
    expect_equal(
        "Java structural seed IDs match evaluated IDs",
        sorted(row["instance_id"] for row in seeds),
        evaluated_ids,
        seed_source,
    )
    allowed = {
        "file_path",
        "rank",
        "support",
        "first_entity_rank",
        "graph_distance",
        "direct_anchor",
    }
    observed_fields = {
        key
        for row in seeds
        for record in row.get("ranked_files", [])
        for key in record
    }
    expect_equal(
        "Java structural retained file fields",
        sorted(observed_fields),
        sorted(allowed),
        seed_source,
    )
    for row in seeds:
        expect_equal(
            f"Java structural entity scan limit {row['instance_id']}",
            row["entity_depth"],
            200,
            seed_source,
        )
        expect_equal(
            f"Java structural file limit {row['instance_id']}",
            row["max_files"],
            20,
            seed_source,
        )
        ranked_files = row.get("ranked_files", [])
        expect_equal(
            f"Java structural file count {row['instance_id']}",
            len(ranked_files) <= 20,
            True,
            seed_source,
        )
        for file_record in ranked_files:
            file_path = file_record["file_path"]
            expect_equal(
                f"Java structural repository-relative path {row['instance_id']}:{file_path}",
                Path(file_path).is_absolute() or ".." in Path(file_path).parts,
                False,
                seed_source,
            )


def verify_retrieve_then_localize_controls() -> None:
    file_source = "ranked_file_source_coverage_20260711.tsv"
    file_rows = read_tsv(file_source)
    expect_row_set(
        "Ranked file-source row set",
        file_rows,
        "name",
        ["KG_grounded_files", "BM25_ranked_files"],
        file_source,
    )
    for name, hits, coverage in [
        ("KG_grounded_files", 291, 58.2),
        ("BM25_ranked_files", 402, 80.4),
    ]:
        row = row_by(file_rows, "name", name)
        expect_equal(f"Ranked file source {name} hits", int(row["file_hits"]), hits, file_source)
        expect_close(f"Ranked file source {name} coverage", pct(row["file_coverage"]), coverage, file_source)

    file_paired_source = "ranked_file_source_paired_20260711.tsv"
    file_paired = read_tsv(file_paired_source)[0]
    expect_close("Ranked file source BM25-KG delta", pct(file_paired["delta"]), 22.2, file_paired_source)
    expect_equal("Ranked file source BM25 wins", int(file_paired["wins"]), 144, file_paired_source)
    expect_equal("Ranked file source BM25 losses", int(file_paired["losses"]), 33, file_paired_source)
    expect_close(
        "Ranked file source exact p",
        float(file_paired["exact_mcnemar_p"]),
        9.79369029978302e-18,
        file_paired_source,
        tol=1e-20,
    )

    source = "retrieve_then_localize_top20_20260711.tsv"
    rows = read_tsv(source)
    expected_rows = [
        "BM25",
        "KG_grounded",
        "BM25_filelocal",
        "KG_filelocal",
        "BM25_KG_RRF_filelocal",
        "GLM5_issue",
        "GLM5_KG_filelocal",
        "GLM5_BM25_filelocal",
        "GLM5_BM25_KG_RRF_filelocal",
    ]
    expect_row_set("Retrieve-then-localize Top-20 row set", rows, "name", expected_rows, source)
    expected = {
        "BM25": (77.0, 39.2, 25.3, 46.0),
        "KG_grounded": (55.6, 33.8, 22.2, 37.8),
        "BM25_filelocal": (73.6, 50.1, 28.6, 57.0),
        "KG_filelocal": (59.2, 45.4, 26.3, 50.8),
        "BM25_KG_RRF_filelocal": (77.0, 55.3, 32.0, 62.8),
        "GLM5_issue": (87.4, 53.0, 51.2, 62.4),
        "GLM5_KG_filelocal": (93.2, 65.5, 53.7, 74.0),
        "GLM5_BM25_filelocal": (94.2, 69.2, 54.4, 78.0),
        "GLM5_BM25_KG_RRF_filelocal": (94.6, 70.9, 54.7, 79.0),
    }
    for name, values in expected.items():
        expect_metric_row(source, row_by(rows, "name", name), values, f"Retrieve/localize {name}")

    paired_source = "retrieve_then_localize_paired_20260711.tsv"
    paired = read_tsv(paired_source)
    comparisons = {
        ("BM25", "BM25_filelocal"): (11.0, 100, 45, 5.72317416461909e-06),
        ("KG_grounded", "KG_filelocal"): (13.0, 67, 2, 8.185726402265558e-18),
        ("KG_filelocal", "BM25_filelocal"): (6.2, 90, 59, 0.013712033079849216),
        ("BM25_filelocal", "BM25_KG_RRF_filelocal"): (5.8, 43, 14, 0.00015388902244434233),
        ("KG_filelocal", "BM25_KG_RRF_filelocal"): (12.0, 80, 20, 1.1159089057251951e-09),
        ("GLM5_issue", "GLM5_KG_filelocal"): (11.6, 58, 0, 6.938893903907228e-18),
        ("GLM5_issue", "GLM5_BM25_filelocal"): (15.6, 78, 0, 6.617444900424222e-24),
        ("GLM5_issue", "GLM5_BM25_KG_RRF_filelocal"): (16.6, 83, 0, 2.0679515313825692e-25),
        ("GLM5_KG_filelocal", "GLM5_BM25_filelocal"): (4.0, 39, 19, 0.011928139715763175),
        ("GLM5_BM25_filelocal", "GLM5_BM25_KG_RRF_filelocal"): (1.0, 17, 12, 0.45825831964612007),
        ("GLM5_KG_filelocal", "GLM5_BM25_KG_RRF_filelocal"): (5.0, 31, 6, 4.12575900554657e-05),
    }
    for (baseline, treatment), (delta, wins, losses, p_value) in comparisons.items():
        row = next(
            item
            for item in paired
            if item["baseline"] == baseline and item["treatment"] == treatment and item["metric"] == "hit"
        )
        prefix = f"Retrieve/localize {baseline}->{treatment}"
        expect_close(f"{prefix} Hit delta", pct(row["delta"]), delta, paired_source)
        expect_equal(f"{prefix} wins", int(row["wins"]), wins, paired_source)
        expect_equal(f"{prefix} losses", int(row["losses"]), losses, paired_source)
        expect_close(f"{prefix} exact p", float(row["exact_mcnemar_p"]), p_value, paired_source, tol=1e-15)

    budget_source = "retrieve_then_localize_budget_curve_20260711.tsv"
    budget_rows = read_tsv(budget_source)
    expected_hits = {
        "GLM5_issue_b5": 60.4,
        "GLM5_KG_filelocal_b5": 65.0,
        "GLM5_BM25_filelocal_b5": 66.2,
        "GLM5_BM25_KG_RRF_b5": 66.6,
        "GLM5_issue_b10": 62.4,
        "GLM5_KG_filelocal_b10": 70.0,
        "GLM5_BM25_filelocal_b10": 72.4,
        "GLM5_BM25_KG_RRF_b10": 73.4,
        "GLM5_issue_b20": 62.4,
        "GLM5_KG_filelocal_b20": 74.0,
        "GLM5_BM25_filelocal_b20": 78.0,
        "GLM5_BM25_KG_RRF_b20": 79.0,
        "GLM5_issue_b40": 62.4,
        "GLM5_KG_filelocal_b40": 76.8,
        "GLM5_BM25_filelocal_b40": 81.6,
        "GLM5_BM25_KG_RRF_b40": 83.8,
    }
    expect_row_set("Retrieve/localize budget row set", budget_rows, "name", list(expected_hits), budget_source)
    for name, expected_hit in expected_hits.items():
        expect_close(
            f"Retrieve/localize budget {name} Hit",
            pct(row_by(budget_rows, "name", name)["hit_rate"]),
            expected_hit,
            budget_source,
        )

    budget_paired_source = "retrieve_then_localize_budget_paired_20260711.tsv"
    budget_paired = read_tsv(budget_paired_source)
    b40_hybrid = next(
        row
        for row in budget_paired
        if row["baseline"] == "GLM5_BM25_filelocal_b40"
        and row["treatment"] == "GLM5_BM25_KG_RRF_b40"
        and row["metric"] == "hit"
    )
    expect_close("Hybrid B40 Hit delta over BM25", pct(b40_hybrid["delta"]), 2.2, budget_paired_source)
    expect_equal("Hybrid B40 Hit wins over BM25", int(b40_hybrid["wins"]), 17, budget_paired_source)
    expect_equal("Hybrid B40 Hit losses over BM25", int(b40_hybrid["losses"]), 6, budget_paired_source)
    expect_close(
        "Hybrid B40 exact p over BM25",
        float(b40_hybrid["exact_mcnemar_p"]),
        0.03468966484069824,
        budget_paired_source,
        tol=1e-15,
    )

    disagreement_source = "retrieve_then_localize_disagreements_20260711.tsv"
    disagreements = read_tsv(disagreement_source)
    key_rows = [
        row
        for row in disagreements
        if row["baseline"] == "GLM5_KG_filelocal" and row["treatment"] == "GLM5_BM25_filelocal"
    ]
    expect_equal("Retrieve/localize KG-vs-BM25 disagreement count", len(key_rows), 58, disagreement_source)
    expect_equal(
        "Retrieve/localize KG-vs-BM25 treatment-only count",
        sum(row["direction"] == "treatment_only" for row in key_rows),
        39,
        disagreement_source,
    )
    expect_equal(
        "Retrieve/localize KG-vs-BM25 baseline-only count",
        sum(row["direction"] == "baseline_only" for row in key_rows),
        19,
        disagreement_source,
    )


def verify_rq2() -> None:
    source = "retrieve_then_localize_top20_20260711.tsv"
    rows = read_tsv(source)
    expected = {
        "GLM5_issue": (87.4, 53.0, 51.2, 62.4),
        "GLM5_KG_filelocal": (93.2, 65.5, 53.7, 74.0),
        "GLM5_BM25_filelocal": (94.2, 69.2, 54.4, 78.0),
        "GLM5_BM25_KG_RRF_filelocal": (94.6, 70.9, 54.7, 79.0),
    }
    for name, values in expected.items():
        expect_metric_row(source, row_by(rows, "name", name), values, f"RQ2 {name}")

    controls_source = "glm5_baseline_fusion_controls_top10_20260614.tsv"
    controls = read_tsv(controls_source)
    control_rows = [
        "GLM5_issue_only",
        "GLM5_CodeGraph_ht10",
    ]
    expect_row_set("RQ2 GLM-5 tail-control row set", controls, "name", control_rows, controls_source)
    control_expected = {
        "GLM5_issue_only": (87.4, 53.0, 51.2, 62.4, 0, 0),
        "GLM5_CodeGraph_ht10": (93.6, 60.9, 53.0, 69.6, 36, 0),
    }
    for name, values in control_expected.items():
        row = row_by(controls, "name", name)
        expect_metric_row(controls_source, row, values[:4], f"RQ2 GLM tail {name}")
        expect_equal(f"RQ2 GLM tail {name} hit wins", int(row["hit_wins_vs_issue"]), values[4], controls_source)
        expect_equal(f"RQ2 GLM tail {name} hit losses", int(row["hit_losses_vs_issue"]), values[5], controls_source)


def verify_rq4() -> None:
    summary_source = "repair_glm5_summary_20260715.tsv"
    rows = read_tsv(summary_source)
    names = [
        "issue",
        "bm25",
        "mural",
        "bm25_vs_issue",
        "mural_vs_issue",
        "mural_vs_bm25",
    ]
    expect_row_set("RQ4 summary row set", rows, "name", names, summary_source)
    variants = {
        "issue": (416, 415, 112, 22.4, 1, 5),
        "bm25": (453, 451, 134, 26.8, 2, 4),
        "mural": (450, 446, 146, 29.2, 4, 3),
    }
    for name, expected in variants.items():
        row = row_by(rows, "name", name)
        fields = (
            "nonempty",
            "applicable",
            "resolved",
            "resolved_percent",
            "patch_apply_failed",
            "test_timeout",
        )
        for field, value in zip(fields, expected):
            observed = float(row[field]) if field == "resolved_percent" else int(row[field])
            if field == "resolved_percent":
                expect_close(f"RQ4 {name} {field}", observed, value, summary_source)
            else:
                expect_equal(f"RQ4 {name} {field}", observed, value, summary_source)

    contrasts = {
        "bm25_vs_issue": (4.4, 1.6, 7.2, 36, 14, 0.00260217145672),
        "mural_vs_issue": (6.8, 4.0, 9.6, 44, 10, 3.38568595337e-06),
        "mural_vs_bm25": (2.4, -0.2, 5.0, 29, 17, 0.103805355504),
    }
    for name, expected in contrasts.items():
        row = row_by(rows, "name", name)
        prefix = f"RQ4 {name}"
        expect_close(f"{prefix} delta", float(row["delta_pp"]), expected[0], summary_source)
        expect_close(f"{prefix} CI low", float(row["ci95_low"]), expected[1], summary_source)
        expect_close(f"{prefix} CI high", float(row["ci95_high"]), expected[2], summary_source)
        expect_equal(f"{prefix} wins", int(row["wins"]), expected[3], summary_source)
        expect_equal(f"{prefix} losses", int(row["losses"]), expected[4], summary_source)
        expect_close(
            f"{prefix} exact p",
            float(row["p_exact"]),
            expected[5],
            summary_source,
            tol=1e-12,
        )

    outcomes_source = "repair_glm5_outcomes_20260715.tsv"
    outcomes = read_tsv(outcomes_source)
    expect_equal("RQ4 outcome rows", len(outcomes), 1500, outcomes_source)
    expect_equal(
        "RQ4 outcome keys",
        len({(row["instance_id"], row["variant"]) for row in outcomes}),
        1500,
        outcomes_source,
    )
    for name, expected in variants.items():
        variant_rows = [row for row in outcomes if row["variant"] == name]
        expect_equal(f"RQ4 {name} outcome instances", len(variant_rows), 500, outcomes_source)
        for field, value in zip(("nonempty", "applied", "resolved"), expected[:3]):
            expect_equal(
                f"RQ4 {name} ledger {field}",
                sum(int(row[field]) for row in variant_rows),
                value,
                outcomes_source,
            )
        expect_equal(
            f"RQ4 {name} patch-application failures",
            sum(row["error"] == "patch_apply_failed" for row in variant_rows),
            expected[4],
            outcomes_source,
        )
        expect_equal(
            f"RQ4 {name} test timeouts",
            sum(row["error"] == "test_timeout" for row in variant_rows),
            expected[5],
            outcomes_source,
        )
    expect_equal(
        "RQ4 outcome error vocabulary",
        sorted({row["error"] for row in outcomes}),
        ["none", "patch_apply_failed", "test_timeout"],
        outcomes_source,
    )
    expect_equal(
        "RQ4 resolved implies applied",
        sum(int(row["resolved"]) and not int(row["applied"]) for row in outcomes),
        0,
        outcomes_source,
    )
    expect_equal(
        "RQ4 patch-application failure contract",
        sum(
            row["error"] == "patch_apply_failed"
            and (int(row["applied"]) or int(row["resolved"]))
            for row in outcomes
        ),
        0,
        outcomes_source,
    )
    expect_equal(
        "RQ4 timeout contract",
        sum(
            row["error"] == "test_timeout"
            and (not int(row["applied"]) or int(row["resolved"]))
            for row in outcomes
        ),
        0,
        outcomes_source,
    )

    assembly_source = "repair_glm5_assembly_20260715.tsv"
    assembly = read_tsv(assembly_source)
    expect_equal("RQ4 assembly rows", len(assembly), 1500, assembly_source)
    assembly_by = {(row["instance_id"], row["variant"]): row for row in assembly}
    expect_equal("RQ4 assembly keys", len(assembly_by), 1500, assembly_source)
    expect_equal(
        "RQ4 frozen dataset source",
        {row["dataset_source"] for row in assembly},
        {"temp_run/generated/SWE-bench_Verified.jsonl"},
        assembly_source,
    )
    expect_equal(
        "RQ4 nonempty issue text",
        sum(int(row["problem_statement_tokens"]) > 0 for row in assembly),
        1500,
        assembly_source,
    )
    expect_equal(
        "RQ4 context profile",
        {row["context_profile_version"] for row in assembly},
        {"rank_stratified_v3_allfiles"},
        assembly_source,
    )
    expect_equal(
        "RQ4 no assistant prefill",
        {row["response_prefill"] for row in assembly},
        {"0"},
        assembly_source,
    )
    expect_equal(
        "RQ4 retry contract",
        {row["max_retries"] for row in assembly},
        {"1"},
        assembly_source,
    )
    expect_equal(
        "RQ4 thinking disabled",
        {json.loads(row["generation_extra_body"])["enable_thinking"] for row in assembly},
        {False},
        assembly_source,
    )
    expect_equal(
        "RQ4 prompt ceiling",
        max(int(row["first_prompt_tokens"]) for row in assembly),
        4998,
        assembly_source,
    )
    expect_equal(
        "RQ4 per-request retry ceiling",
        max(int(row["retry_count"]) for row in assembly),
        1,
        assembly_source,
    )

    context_source = "repair_glm5_context_rendering_20260715.tsv"
    context = read_tsv(context_source)
    context_by = {(row["instance_id"], row["variant"]): row for row in context}
    expect_equal("RQ4 context audit rows", len(context), 1500, context_source)
    expect_equal("RQ4 context audit keys", set(context_by), set(assembly_by), context_source)
    field_pairs = {
        "candidate_entities": "candidate_entity_count",
        "rendered_entities": "first_prompt_rendered_entity_count",
        "source_entities": "first_prompt_source_entity_count",
        "prompt_tokens": "first_prompt_tokens",
    }
    for context_field, assembly_field in field_pairs.items():
        expect_equal(
            f"RQ4 context/assembly {context_field}",
            sum(
                int(row[context_field])
                != int(assembly_by[key][assembly_field])
                for key, row in context_by.items()
            ),
            0,
            context_source,
        )
    context_expected = {
        "issue": (1879, 1879, 1195, 1008457, 6),
        "bm25": (8914, 8593, 3319, 2034218, 453),
        "mural": (8921, 8715, 3249, 1957560, 465),
    }
    for name, expected in context_expected.items():
        variant_rows = [row for row in context if row["variant"] == name]
        observed = (
            sum(int(row["candidate_entities"]) for row in variant_rows),
            sum(int(row["rendered_entities"]) for row in variant_rows),
            sum(int(row["source_entities"]) for row in variant_rows),
            sum(int(row["prompt_tokens"]) for row in variant_rows),
            sum(int(row["tail_source_entities"]) > 0 for row in variant_rows),
        )
        expect_equal(f"RQ4 {name} context audit totals", observed, expected, context_source)

    mapping_source = "repair_glm5_prediction_mapping_20260715.tsv"
    mapping = read_tsv(mapping_source)
    expect_equal("RQ4 prediction mapping rows", len(mapping), 1500, mapping_source)
    mapping_by = {(row["instance_id"], row["variant"]): row for row in mapping}
    expect_equal("RQ4 prediction mapping keys", len(mapping_by), 1500, mapping_source)
    expect_equal(
        "RQ4 mapping nonempty contract",
        sum(
            int(row["nonempty"]) != int(assembly_by[key]["nonempty"])
            for key, row in mapping_by.items()
        ),
        0,
        mapping_source,
    )
    expect_equal(
        "RQ4 mapping hash contract",
        sum(bool(row["patch_sha256"]) != bool(int(row["nonempty"])) for row in mapping),
        0,
        mapping_source,
    )
    nonempty_mapping = [row for row in mapping if int(row["nonempty"])]
    canonical_mapping = [
        row for row in nonempty_mapping if not int(row["reused_identical_patch"])
    ]
    expect_equal("RQ4 nonempty mapping rows", len(nonempty_mapping), 1319, mapping_source)
    expect_equal("RQ4 canonical mapping rows", len(canonical_mapping), 1035, mapping_source)
    expect_equal(
        "RQ4 identical patch reuses",
        sum(int(row["reused_identical_patch"]) for row in mapping),
        284,
        mapping_source,
    )
    for slot, expected in (("0", 471), ("1", 359), ("2", 205)):
        expect_equal(
            f"RQ4 canonical slot {slot}",
            sum(row["slot"] == slot for row in canonical_mapping),
            expected,
            mapping_source,
        )
    patch_slots: dict[tuple[str, str], set[str]] = {}
    for row in nonempty_mapping:
        patch_slots.setdefault((row["instance_id"], row["patch_sha256"]), set()).add(
            row["slot"]
        )
    expect_equal(
        "RQ4 same-instance hash slot consistency",
        sum(len(slots) != 1 for slots in patch_slots.values()),
        0,
        mapping_source,
    )

    dedup_source = "repair_glm5_deduplication_summary_20260715.json"
    dedup = read_json(dedup_source)
    expect_equal("RQ4 dedup variant predictions", dedup["variant_predictions"], 1500, dedup_source)
    expect_equal("RQ4 dedup nonempty", dedup["nonempty_variant_predictions"], 1319, dedup_source)
    expect_equal("RQ4 dedup canonical", dedup["canonical_predictions"], 1035, dedup_source)
    expect_equal("RQ4 dedup reuses", dedup["identical_patch_reuses"], 284, dedup_source)
    expect_equal(
        "RQ4 dedup slot counts",
        dedup["slot_counts"],
        {"slot_0": 471, "slot_1": 359, "slot_2": 205},
        dedup_source,
    )

    protocol_source = "artifacts/repair_protocol_glm5_20260715.json"
    protocol = json.loads((ROOT / protocol_source).read_text(encoding="utf-8"))
    expect_equal("RQ4 protocol instances", protocol["instances"], 500, protocol_source)
    expect_equal("RQ4 protocol model", protocol["model"]["alias"], "glm-5", protocol_source)
    expect_equal("RQ4 protocol temperature", protocol["decoding"]["temperature"], 0.0, protocol_source)
    expect_equal("RQ4 protocol top-p", protocol["decoding"]["top_p"], 0.95, protocol_source)
    expect_equal("RQ4 protocol thinking", protocol["decoding"]["enable_thinking"], False, protocol_source)
    expect_equal("RQ4 protocol prefill", protocol["decoding"]["assistant_response_prefill"], False, protocol_source)
    expect_equal("RQ4 protocol output cap", protocol["decoding"]["max_output_tokens"], 2048, protocol_source)
    expect_equal("RQ4 protocol context profile", protocol["context"]["profile"], "rank_stratified_v3_allfiles", protocol_source)
    expect_equal("RQ4 protocol prompt ceiling", protocol["context"]["prompt_token_ceiling"], 5000, protocol_source)
    expect_equal("RQ4 protocol retry count", protocol["retry"]["maximum_failure_conditioned_retries"], 1, protocol_source)
    expect_equal("RQ4 protocol harness", protocol["official_harness"], "swe-bench 4.1.0", protocol_source)
    expect_equal("RQ4 protocol test timeout", protocol["test_timeout_seconds"], 1800, protocol_source)
    expect_equal("RQ4 protocol timeout outcome", protocol["timeout_outcome"], "Unresolved", protocol_source)
    expect_equal(
        "RQ4 protocol official outcome counts",
        protocol["official_evaluation_outcomes"],
        {
            "canonical_predictions": 1035,
            "standard_harness_reports": 1018,
            "patch_application_failures_recorded_unresolved": 7,
            "test_timeouts_recorded_unresolved": 10,
            "infrastructure_failures_recorded_as_outcomes": 0,
        },
        protocol_source,
    )

    source_tree = ast.parse(
        (ROOT / "kgcompass" / "repair_claude.py").read_text(encoding="utf-8")
    )
    prompt_constants = {}
    for node in source_tree.body:
        if (
            not isinstance(node, ast.Assign)
            or len(node.targets) != 1
            or not isinstance(node.targets[0], ast.Name)
        ):
            continue
        name = node.targets[0].id
        if name in {"OPEN_MODEL_SYSTEM_PROMPT", "OPEN_MODEL_PROMPT_TEMPLATE"}:
            prompt_constants[name] = ast.literal_eval(node.value)
    prompt_source = "artifacts/prompts/glm5_repair_prompt.md"
    prompt_text = (ROOT / prompt_source).read_text(encoding="utf-8")
    tick = chr(96)
    archived_system = prompt_text.split(tick * 3 + "text\n", 1)[1].split(
        "\n" + tick * 3, 1
    )[0]
    archived_user = prompt_text.split(tick * 4 + "text\n", 1)[1].rsplit(
        "\n" + tick * 4, 1
    )[0]
    expect_equal(
        "RQ4 archived system prompt",
        archived_system,
        prompt_constants["OPEN_MODEL_SYSTEM_PROMPT"],
        prompt_source,
    )
    expect_equal(
        "RQ4 archived user prompt",
        archived_user.strip(),
        prompt_constants["OPEN_MODEL_PROMPT_TEMPLATE"].strip(),
        prompt_source,
    )


def verify_patch_derived_context() -> None:
    source = "patch_derived_context_summary_20260702.tsv"
    rows = read_tsv(source)
    expected_rows = [
        "BM25",
        "KGCompass w/o file-local paths",
        "KGCompass",
        "GLM-5 issue-only",
        "GLM-5+KGCompass",
        "BM25 files + file-local",
        "BM25+KG RRF file-local",
        "GLM-5 + BM25 files + file-local",
        "GLM-5 + BM25+KG RRF file-local",
    ]
    expect_row_set("Patch-derived context row set", rows, "name", expected_rows, source)
    expected = {
        "BM25": (500, 39.2, 35.0),
        "KGCompass w/o file-local paths": (500, 33.8, 30.8),
        "KGCompass": (500, 45.4, 41.4),
        "GLM-5 issue-only": (500, 53.0, 46.2),
        "GLM-5+KGCompass": (500, 65.5, 58.8),
        "BM25 files + file-local": (500, 50.1, 44.6),
        "BM25+KG RRF file-local": (500, 55.3, 49.0),
        "GLM-5 + BM25 files + file-local": (500, 69.2, 62.2),
        "GLM-5 + BM25+KG RRF file-local": (500, 70.9, 64.2),
    }
    for name, values in expected.items():
        row = row_by(rows, "name", name)
        n, edit_recall, complete_edit = values
        expect_equal(f"Patch context {name} N", int(row["N"]), n, source)
        expect_close(f"Patch context {name} edit target recall", pct(row["edit_target_recall"]), edit_recall, source)
        expect_close(f"Patch context {name} complete edit target", pct(row["complete_edit_target_rate"]), complete_edit, source)

    json_source = "patch_derived_context_summary_20260702.json"
    json_rows = read_json(json_source)["rows"]
    expect_equal("Patch context JSON row set", sorted(json_rows), sorted(expected), json_source)
    for name, (_, edit_recall, complete_edit) in expected.items():
        expect_close(f"Patch context JSON {name} edit target recall", pct(json_rows[name]["edit_target_recall"]), edit_recall, json_source)
        expect_close(f"Patch context JSON {name} complete edit target", pct(json_rows[name]["complete_edit_target_rate"]), complete_edit, json_source)

    target_source = "patch_derived_context_targets_20260702.json"
    targets = read_json(target_source)
    items = targets["items"]
    expect_equal("Patch context target cache version", targets["_meta"]["cache_version"], 3, target_source)
    expect_equal("Patch context target cache size", targets["_meta"]["n"], 500, target_source)
    expect_equal("Patch context target item count", len(items), 500, target_source)
    expect_equal(
        "Patch context file-fallback instances",
        sum(int(item["fallback_file_target"]) for item in items.values()),
        9,
        target_source,
    )
    expect_equal(
        "Patch context retired proxy fields",
        sum(any(key.startswith("support_") for key in item) for item in items.values()),
        0,
        target_source,
    )

    paired_source = "edit_target_paired_stats_20260713.tsv"
    paired_rows = read_tsv(paired_source)
    expected_paired = {
        ("BM25", "BM25_filelocal", "edit_recall"): (10.9, 6.6, 15.1, 121, 54, None),
        ("BM25", "BM25_filelocal", "complete_edit"): (9.6, 5.4, 14.0, 88, 40, 2.6629957497431587e-05),
        ("KG_grounded", "KG_filelocal", "edit_recall"): (11.7, 8.8, 14.6, 79, 10, None),
        ("KG_grounded", "KG_filelocal", "complete_edit"): (10.6, 7.6, 13.8, 60, 7, 1.3280368233066497e-11),
        ("BM25_filelocal", "MURAL", "edit_recall"): (5.2, 2.6, 7.9, 49, 21, None),
        ("BM25_filelocal", "MURAL", "complete_edit"): (4.4, 1.8, 7.2, 35, 13, 0.0020881073339964473),
        ("GLM5_BM25_filelocal", "GLM5_MURAL", "edit_recall"): (1.6, -0.2, 3.6, 27, 17, None),
        ("GLM5_BM25_filelocal", "GLM5_MURAL", "complete_edit"): (2.0, 0.0, 4.0, 19, 9, 0.08715855330228806),
    }
    observed_keys = [(row["baseline"], row["treatment"], row["metric"]) for row in paired_rows]
    expect_equal("Patch context paired row set", observed_keys, list(expected_paired), paired_source)
    for row in paired_rows:
        key = (row["baseline"], row["treatment"], row["metric"])
        delta, low, high, wins, losses, p_value = expected_paired[key]
        prefix = f"Patch context paired {key[0]}->{key[1]} {key[2]}"
        expect_equal(f"{prefix} N", int(row["N"]), 500, paired_source)
        expect_close(f"{prefix} delta", pct(row["delta"]), delta, paired_source)
        expect_close(f"{prefix} CI low", pct(row["ci95_low"]), low, paired_source)
        expect_close(f"{prefix} CI high", pct(row["ci95_high"]), high, paired_source)
        expect_equal(f"{prefix} wins", int(row["wins"]), wins, paired_source)
        expect_equal(f"{prefix} losses", int(row["losses"]), losses, paired_source)
        if p_value is None:
            expect_equal(f"{prefix} exact p", row["exact_mcnemar_p"], "NA", paired_source)
        else:
            expect_close(f"{prefix} exact p", float(row["exact_mcnemar_p"]), p_value, paired_source, tol=1e-15)


def verify_boundary() -> None:
    audit_source = "kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json"
    audit = read_json(audit_source)["summary"]
    expect_equal("Boundary audit ok instances", audit["ok"], 500, audit_source)
    expect_equal("Boundary audit target PR hits", audit["target_pr_hits"], 0, audit_source)
    expect_equal("Boundary audit future-fix hits", audit["future_fix_trace_hits"], 0, audit_source)
    expect_equal("Boundary audit metadata issues", audit["metadata_issues"], 0, audit_source)
    expect_equal("Boundary audit content issue counts", audit["content_issue_counts"], {}, audit_source)
    expect_equal("Boundary audit structural issue counts", audit["structural_issue_counts"], {}, audit_source)

    sensitivity_source = "time_boundary_external_artifact_sensitivity_20260531.tsv"
    sensitivity = read_tsv(sensitivity_source)
    full_row = row_by(sensitivity, "setting", "full_pathmined")
    expect_equal("External artifact sensitivity instances", int(full_row["external_instances"]), 1, sensitivity_source)
    expect_equal("External artifact sensitivity Top-20 candidates", int(full_row["external_top20_candidates"]), 2, sensitivity_source)
    expect_equal("External artifact sensitivity Hit@20 losses", int(full_row["hit_losses"]), 0, sensitivity_source)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify MURAL submission-facing artifact values.")
    parser.add_argument(
        "--rq",
        choices=("all", "setup", "rq1", "rq2", "rq3", "rq4", "boundary"),
        default="all",
        help="Restrict checks to one section. Default: all.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_checks = {
        "setup": verify_setup,
        "rq1": verify_rq1,
        "rq2": verify_rq2,
        "rq3": verify_patch_derived_context,
        "rq4": verify_rq4,
        "boundary": verify_boundary,
    }
    try:
        verify_result_inventory()
        if args.rq == "all":
            for check in selected_checks.values():
                check()
        else:
            selected_checks[args.rq]()
    except Exception as exc:  # noqa: BLE001 - reviewer-facing script should print context.
        print(json.dumps({"ok": False, "error": str(exc), "checks": checks}, indent=2), file=sys.stderr)
        return 1

    failed = [item for item in checks if not item["ok"]]
    report = {
        "ok": not failed,
        "scope": args.rq,
        "checked_values": len(checks),
        "failed": failed,
        "checks": checks,
    }
    print(json.dumps(report, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
