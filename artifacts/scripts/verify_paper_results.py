#!/usr/bin/env python3
"""Verify the submission-facing MURAL result ledgers."""

from __future__ import annotations

import argparse
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

CORE_FILES = {
    "context_construction_cost_20260716.tsv",
    "java_cross_language_instances_20260714.jsonl",
    "java_cross_language_paired_20260714.tsv",
    "java_cross_language_summary_20260714.tsv",
    "java_cross_language_targets_20260714.json",
    "kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json",
    "mural_budget_disagreements_20260716.tsv",
    "mural_budget_paired_20260716.tsv",
    "mural_budget_summary_20260716.tsv",
    "mural_edit_target_paired_20260716.tsv",
    "mural_edit_target_summary_20260716.json",
    "mural_edit_target_summary_20260716.tsv",
    "mural_external_localizer_disagreements_20260716.tsv",
    "mural_external_localizer_paired_20260716.tsv",
    "mural_external_localizer_summary_20260716.tsv",
    "mural_localization_disagreements_20260716.tsv",
    "mural_localization_paired_20260716.tsv",
    "mural_localization_summary_20260716.tsv",
    "mural_repository_localization_20260716.tsv",
    "mural_rrf_sensitivity_disagreements_20260716.tsv",
    "mural_rrf_sensitivity_paired_20260716.tsv",
    "mural_rrf_sensitivity_summary_20260716.tsv",
    "patch_derived_context_targets_20260702.json",
    "time_boundary_external_artifact_sensitivity_20260531.tsv",
    "tse_gt_mapping_v6.tsv",
}
REPAIR_FILES = {
    "mural_repository_repair_20260716.tsv",
    "repair_glm52_assembly_20260716.tsv",
    "repair_glm52_context_rendering_20260716.tsv",
    "repair_glm52_deduplication_summary_20260716.json",
    "repair_glm52_outcomes_20260716.tsv",
    "repair_glm52_prediction_mapping_20260716.tsv",
    "repair_glm52_summary_20260716.tsv",
}
CHECKS: list[dict[str, Any]] = []


def tsv(name: str) -> list[dict[str, str]]:
    with (RESULTS / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def check(name: str, observed: Any, expected: Any, source: str, ok: bool | None = None) -> None:
    CHECKS.append({
        "name": name,
        "observed": observed,
        "expected": expected,
        "source": source,
        "ok": observed == expected if ok is None else ok,
    })


def close(name: str, observed: float, expected: float, source: str, tol: float = 5e-7) -> None:
    check(name, observed, expected, source, math.isclose(observed, expected, abs_tol=tol))


def one(rows: list[dict[str, str]], key: str, value: str) -> dict[str, str]:
    found = [item for item in rows if item.get(key) == value]
    if len(found) != 1:
        raise AssertionError(f"{key}={value}: expected one row, found {len(found)}")
    return found[0]


def pair(rows: list[dict[str, str]], baseline: str, treatment: str, metric: str = "hit") -> dict[str, str]:
    found = [
        item for item in rows
        if item["baseline"] == baseline
        and item["treatment"] == treatment
        and item.get("metric", "hit") == metric
    ]
    if len(found) != 1:
        raise AssertionError(f"{baseline}->{treatment}/{metric}: found {len(found)} rows")
    return found[0]


def inventory(scope: str) -> None:
    expected = CORE_FILES | (REPAIR_FILES if scope == "all" else set())
    observed = {path.name for path in RESULTS.iterdir() if path.is_file()}
    if scope == "core":
        observed -= REPAIR_FILES
    check("result inventory", sorted(observed), sorted(expected), "artifacts/results")


def setup() -> None:
    source = "tse_gt_mapping_v6.tsv"
    rows = tsv(source)
    expected = {
        "single_file": (429, 85.8), "multi_file": (71, 14.2),
        "has_method_target": (473, 94.6), "has_class_target": (66, 13.2),
        "single_entity": (350, 70.0), "multi_entity": (150, 30.0),
        "file_only_fallback": (9, 1.8),
    }
    for category, values in expected.items():
        item = one(rows, "category", category)
        check(f"{category} count", int(float(item["count"])), values[0], source)
        close(f"{category} percent", float(item["percent"]), values[1], source)


def localization() -> None:
    source = "mural_localization_summary_20260716.tsv"
    rows = tsv(source)
    expected = {
        "BM25_entities": (0.770, 0.3920462482, 0.2525878538, 0.460),
        "Structural_entities": (0.556, 0.3377373737, 0.2224038520, 0.378),
        "BM25_projection": (0.736, 0.5010113276, 0.2881168371, 0.570),
        "Structural_projection": (0.592, 0.4527596681, 0.2631367764, 0.506),
        "Dense_projection": (0.830, 0.5646061688, 0.3205790961, 0.636),
        "MURAL_without_dense": (0.770, 0.5519722222, 0.3199049014, 0.626),
        "MURAL": (0.830, 0.5961367244, 0.3448987389, 0.672),
        "GLM5": (0.874, 0.5298935731, 0.5123071429, 0.624),
        "GLM5_BM25": (0.942, 0.6916631979, 0.5440595658, 0.780),
        "GLM5_MURAL_without_dense": (0.946, 0.7112065601, 0.5476293906, 0.792),
        "GLM5_MURAL": (0.952, 0.7163266900, 0.5495297781, 0.802),
    }
    check("localization rows", len(rows), 15, source)
    for name, values in expected.items():
        item = one(rows, "name", name)
        check(f"{name} N", int(item["N"]), 500, source)
        for field, expected_value in zip(
            ("file_rate", "method_or_entity_rate", "mrr", "hit_rate"), values
        ):
            close(f"{name} {field}", float(item[field]), expected_value, source)

    source = "mural_localization_paired_20260716.tsv"
    rows = tsv(source)
    expected_pairs = [
        ("BM25_entities", "BM25_projection", 0.110, 101, 46, 6.6718656940094816e-06),
        ("Structural_entities", "Structural_projection", 0.128, 66, 2, 1.5903890617646743e-17),
        ("MURAL_without_dense", "MURAL", 0.046, 34, 11, 0.0008240823595997426),
        ("Dense_projection", "MURAL", 0.036, 37, 19, 0.022241389472860112),
        ("GLM5", "GLM5_MURAL", 0.178, 89, 0, 3.2311742677852644e-27),
        ("GLM5_BM25", "GLM5_MURAL", 0.022, 21, 10, 0.07075554598122835),
        ("GLM5_MURAL_without_dense", "GLM5_MURAL", 0.010, 9, 4, 0.266845703125),
    ]
    for baseline, treatment, delta, wins, losses, p_value in expected_pairs:
        item = pair(rows, baseline, treatment)
        close(f"{baseline}->{treatment} delta", float(item["delta"]), delta, source)
        check(f"{baseline}->{treatment} wins", int(item["wins"]), wins, source)
        check(f"{baseline}->{treatment} losses", int(item["losses"]), losses, source)
        close(f"{baseline}->{treatment} p", float(item["exact_mcnemar_p"]), p_value, source)


def edit_targets() -> None:
    source = "mural_edit_target_summary_20260716.tsv"
    rows = tsv(source)
    expected = {
        "BM25 + projection": (0.501011, 0.446),
        "Dense + projection": (0.564606, 0.504),
        "MURAL w/o Dense": (0.551972, 0.490),
        "MURAL": (0.596137, 0.534),
        "GLM-5": (0.529894, 0.462),
        "GLM-5 + BM25 projection": (0.691663, 0.620),
        "GLM-5 + MURAL w/o Dense": (0.711207, 0.644),
        "GLM-5 + MURAL": (0.716327, 0.646),
    }
    check("edit-target rows", len(rows), 11, source)
    for name, values in expected.items():
        item = one(rows, "name", name)
        check(f"{name} N", int(item["N"]), 500, source)
        close(f"{name} recall", float(item["edit_target_recall"]), values[0], source, 5e-6)
        close(f"{name} complete", float(item["complete_edit_target_rate"]), values[1], source)

    source = "mural_edit_target_paired_20260716.tsv"
    rows = tsv(source)
    expected_pairs = [
        ("BM25Proj", "MURAL", 0.088, 49, 5, 3.8913883226854296e-10),
        ("DenseProj", "MURAL", 0.030, 37, 22, 0.06744461190078899),
        ("MURALwoDense", "MURAL", 0.044, 31, 9, 0.0006795482549932785),
        ("GLM5", "GLM5MURAL", 0.184, 92, 0, 4.0389678347315804e-28),
        ("GLM5BM25", "GLM5MURAL", 0.026, 20, 7, 0.0191572904586792),
    ]
    for baseline, treatment, delta, wins, losses, p_value in expected_pairs:
        item = pair(rows, baseline, treatment, "complete_edit")
        close(f"{baseline}->{treatment} complete delta", float(item["delta"]), delta, source)
        check(f"{baseline}->{treatment} wins", int(item["wins"]), wins, source)
        check(f"{baseline}->{treatment} losses", int(item["losses"]), losses, source)
        close(f"{baseline}->{treatment} p", float(item["exact_mcnemar_p"]), p_value, source)


def budget_and_sensitivity() -> None:
    source = "mural_budget_summary_20260716.tsv"
    rows = tsv(source)
    expected = {
        "Issue_B5": .604, "BM25_B5": .664, "MURAL_B5": .670,
        "Issue_B10": .624, "BM25_B10": .724, "MURAL_B10": .738,
        "Issue_B20": .624, "BM25_B20": .780, "MURAL_B20": .802,
        "Issue_B40": .624, "BM25_B40": .814, "MURAL_B40": .856,
    }
    check("budget rows", len(rows), 12, source)
    for name, value in expected.items():
        close(f"{name} Hit", float(one(rows, "name", name)["hit_rate"]), value, source)
    source = "mural_budget_paired_20260716.tsv"
    item = pair(tsv(source), "BM25_B40", "MURAL_B40")
    close("B40 Hit delta", float(item["delta"]), .042, source)
    check("B40 wins/losses", (int(item["wins"]), int(item["losses"])), (23, 2), source)
    close("B40 p", float(item["exact_mcnemar_p"]), 1.9431114196777344e-05, source)

    source = "mural_rrf_sensitivity_summary_20260716.tsv"
    rows = tsv(source)
    expected = {
        "k10": .682, "k30": .678, "k60": .672, "k100": .670,
        "dense05": .654, "dense075": .656, "dense125": .672, "dense15": .676,
    }
    check("RRF sensitivity rows", len(rows), 8, source)
    for name, value in expected.items():
        close(f"{name} Hit", float(one(rows, "name", name)["hit_rate"]), value, source)


def external_localizers() -> None:
    source = "mural_external_localizer_summary_20260716.tsv"
    rows = tsv(source)
    expected = {
        "CoSIL-Qwen2.5-32B": .656, "CoSIL-Qwen2.5-32B+MURAL": .812,
        "LocAgent-Qwen2.5-32B": .612, "LocAgent-Qwen2.5-32B+MURAL": .782,
        "Agentless-Qwen2.5-32B": .578, "Agentless-Qwen2.5-32B+MURAL": .766,
        "OrcaLoca-Qwen2.5-32B": .214, "OrcaLoca-Qwen2.5-32B+MURAL": .514,
    }
    check("external-localizer rows", len(rows), 8, source)
    for name, value in expected.items():
        item = one(rows, "name", name)
        check(f"{name} N", int(item["N"]), 500, source)
        close(f"{name} Hit", float(item["top20_hit_rate"]), value, source)
    source = "mural_external_localizer_paired_20260716.tsv"
    rows = tsv(source)
    expected_pairs = {
        "CoSIL-Qwen2.5-32B": (.156, 78, 0),
        "LocAgent-Qwen2.5-32B": (.170, 86, 1),
        "Agentless-Qwen2.5-32B": (.188, 95, 1),
        "OrcaLoca-Qwen2.5-32B": (.300, 150, 0),
    }
    for baseline, values in expected_pairs.items():
        item = one(rows, "baseline", baseline)
        close(f"{baseline} delta", float(item["delta"]), values[0], source)
        check(f"{baseline} wins/losses", (int(item["wins"]), int(item["losses"])), values[1:], source)


def repository_and_java() -> None:
    source = "mural_repository_localization_20260716.tsv"
    rows = tsv(source)
    check("repository rows", len(rows), 26, source)
    check("repository strata", len({item["repository"] for item in rows if item["repository"] != "ALL"}), 12, source)
    for approach in ("BM25_projection", "MURAL"):
        selected = [item for item in rows if item["method"] == approach and item["repository"] != "ALL"]
        check(f"{approach} repositories", len(selected), 12, source)
        check(f"{approach} instances", sum(int(item["N"]) for item in selected), 500, source)

    source = "java_cross_language_summary_20260714.tsv"
    rows = tsv(source)
    expected = {
        "Raw_BM25_entities": (.6153846154, .1992583424, .1349881290, .3406593407),
        "BM25_projection": (.6703296703, .3215412792, .2415589187, .4725274725),
        "Structural_projection": (.6373626374, .3526560690, .2494900228, .5164835165),
        "Lexical_structural_fusion": (.7032967033, .3513896716, .2649923709, .5494505495),
    }
    check("Java row order", [item["name"] for item in rows], list(expected), source)
    for name, values in expected.items():
        item = one(rows, "name", name)
        check(f"{name} N", int(item["N"]), 91, source)
        for field, value in zip(("file_rate", "method_or_entity_rate", "mrr", "hit_rate"), values):
            close(f"{name} {field}", float(item[field]), value, source)

    source = "java_cross_language_instances_20260714.jsonl"
    instances = jsonl(RESULTS / source)
    ids = sorted(item["instance_id"] for item in instances)
    check("Java instance count", len(instances), 91, source)
    check("Java unique IDs", len(set(ids)), 91, source)
    digest = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    manifest = json_file(INPUTS / "java_cross_language_manifest_20260714.json")
    benchmark = manifest["benchmark"]
    check("Java official/evaluated/excluded", (
        benchmark["official_instances"], benchmark["evaluated_instances"],
        benchmark["excluded_instances"]
    ), (91, 91, 0), "java_cross_language_manifest_20260714.json")
    check("Java instance-ID digest", digest, benchmark["instance_id_set_sha256"],
          "java_cross_language_manifest_20260714.json")


def costs_and_audits() -> None:
    source = "context_construction_cost_20260716.tsv"
    rows = tsv(source)
    stages = [
        "structural_adapter", "bm25_entity_projection",
        "dense_entity_projection", "three_source_equal_weight_rrf",
    ]
    check("cost stage order", [item["stage"] for item in rows], stages, source)
    for item in rows:
        check(f"{item['stage']} N", int(item["N"]), 500, source)
        value = float(item["total_s"])
        check(f"{item['stage']} nonnegative time", value, ">=0", source, value >= 0)
    source = "time_boundary_external_artifact_sensitivity_20260531.tsv"
    check("time-boundary rows", len(tsv(source)), 2, source)
    for source in (
        "kg_evidence_graph_tse_timesafe_main_20260529_v6_audit_final.json",
        "patch_derived_context_targets_20260702.json",
    ):
        value = json_file(RESULTS / source)
        check(f"{source} nonempty", bool(value), True, source)


def repair() -> None:
    source = "repair_glm52_summary_20260716.tsv"
    rows = tsv(source)
    check("repair summary rows", len(rows), 3, source)
    for item in rows:
        check("repair profile N", int(item["N"]), 500, source)
    expected_rows = {
        "repair_glm52_assembly_20260716.tsv": 1500,
        "repair_glm52_context_rendering_20260716.tsv": 1500,
        "repair_glm52_outcomes_20260716.tsv": 1500,
        "repair_glm52_prediction_mapping_20260716.tsv": 1500,
    }
    for source, expected in expected_rows.items():
        check(f"{source} rows", len(tsv(source)), expected, source)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("core", "all"), default="core")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    try:
        inventory(args.scope)
        setup()
        localization()
        edit_targets()
        budget_and_sensitivity()
        external_localizers()
        repository_and_java()
        costs_and_audits()
        if args.scope == "all":
            repair()
    except (AssertionError, FileNotFoundError, KeyError, ValueError) as exc:
        check("verification execution", str(exc), "no exception", "verifier", False)
    failures = [item for item in CHECKS if not item["ok"]]
    payload = {"scope": args.scope, "checks": len(CHECKS), "failures": len(failures), "results": CHECKS}
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for item in failures:
        print(f"FAIL: {item['name']}: observed={item['observed']!r}, "
              f"expected={item['expected']!r} ({item['source']})")
    print(f"Verified {len(CHECKS)} checks in {args.scope} scope; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
