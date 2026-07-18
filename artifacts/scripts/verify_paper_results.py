#!/usr/bin/env python3
"""Verify the submission-facing MURAL result ledgers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "artifacts" / "results"
INPUTS = ROOT / "artifacts" / "inputs"

CORE_FILES = {
    "context_construction_cost_20260716.tsv",
    "fixed_prefix_tail_counts_20260718.tsv",
    "fixed_prefix_tail_disagreements_20260718.tsv",
    "fixed_prefix_tail_paired_20260718.tsv",
    "fixed_prefix_tail_summary_20260718.tsv",
    "history_ablation_disagreements_20260718.tsv",
    "history_ablation_paired_20260718.tsv",
    "history_ablation_summary_20260718.tsv",
    "human_window_agreement_20260718.tsv",
    "human_window_annotations_20260718.tsv",
    "human_window_items_20260718.json",
    "human_window_manifest_20260718.tsv",
    "human_window_provenance_20260718.tsv",
    "human_window_summary_20260718.tsv",
    "localization_nonfallback_disagreements_20260718.tsv",
    "localization_nonfallback_paired_20260718.tsv",
    "localization_nonfallback_summary_20260718.tsv",
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
    "selector_simple_disagreements_20260718.tsv",
    "selector_simple_paired_20260718.tsv",
    "selector_simple_summary_20260718.tsv",
    "time_boundary_external_artifact_sensitivity_20260531.tsv",
    "token_budget_context_instances_20260718.tsv",
    "token_budget_context_paired_20260718.tsv",
    "token_budget_context_summary_20260718.tsv",
    "tse_gt_mapping_v6.tsv",
}
REPAIR_FILES = {
    "repair_equal4000_context_rendering_20260718.tsv",
    "repair_equal4000_context_summary_20260718.tsv",
    "repair_equal4000_assembly_20260718.tsv",
    "repair_equal4000_deduplication_summary_20260718.json",
    "repair_equal4000_outcomes_20260718.tsv",
    "repair_equal4000_prediction_mapping_20260718.tsv",
    "repair_equal4000_summary_20260718.tsv",
    "repair_equal4000_transition_summary_20260718.tsv",
    "repair_equal4000_transitions_20260718.tsv",
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


def where_one(rows: list[dict[str, str]], **keys: str) -> dict[str, str]:
    found = [
        item for item in rows
        if all(item.get(key) == value for key, value in keys.items())
    ]
    if len(found) != 1:
        raise AssertionError(f"{keys}: expected one row, found {len(found)}")
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
        "BM25_projection": (.6703296703, .3193434770, .2414052262, .4725274725),
        "Structural_projection": (.6373626374, .3473185494, .2435071169, .5164835165),
        "Lexical_structural_fusion": (.7032967033, .3460521520, .2593452402, .5494505495),
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

    evaluation = manifest["evaluation"]
    manifest_source = "java_cross_language_manifest_20260714.json"
    check(
        "Java evaluator hash",
        hashlib.sha256((ROOT / evaluation["script"]).read_bytes()).hexdigest(),
        evaluation["script_sha256"],
        manifest_source,
    )
    output_files = {
        "summary": "java_cross_language_summary_20260714.tsv",
        "paired": "java_cross_language_paired_20260714.tsv",
        "targets": "java_cross_language_targets_20260714.json",
        "instances": "java_cross_language_instances_20260714.jsonl",
    }
    for label, filename in output_files.items():
        check(
            f"Java {label} hash",
            hashlib.sha256((RESULTS / filename).read_bytes()).hexdigest(),
            evaluation["output_sha256"][label],
            manifest_source,
        )
    target_meta = json_file(RESULTS / output_files["targets"])["meta"]
    check("Java selector version", target_meta["selector_version"],
          evaluation["selector_version"], manifest_source)


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

    rendering_source = "repair_equal4000_context_rendering_20260718.tsv"
    rendering_path = RESULTS / rendering_source
    if rendering_path.exists():
        rendering_rows = tsv(rendering_source)
        expected_ids = set(
            json_file(RESULTS / "patch_derived_context_targets_20260702.json")[
                "items"
            ]
        )
        rendering_keys = {
            (row["variant"], row["instance_id"]) for row in rendering_rows
        }
        check("context rendering rows", len(rendering_rows), 1000, rendering_source)
        check(
            "context rendering keys unique",
            len(rendering_keys),
            len(rendering_rows),
            rendering_source,
        )
        for variant in ("bm25", "mural"):
            observed_ids = {
                row["instance_id"]
                for row in rendering_rows
                if row["variant"] == variant
            }
            check(
                f"{variant} context rendering IDs",
                observed_ids,
                expected_ids,
                rendering_source,
            )


def human_window_audit() -> None:
    items_source = "human_window_items_20260718.json"
    items_payload = json_file(RESULTS / items_source)
    check("human window item rows", len(items_payload["items"]), 80, items_source)
    check(
        "human window item IDs",
        len({item["annotation_id"] for item in items_payload["items"]}),
        80,
        items_source,
    )
    annotation_source = "human_window_annotations_20260718.tsv"
    annotations = tsv(annotation_source)
    check("human window judgments", len(annotations), 100, annotation_source)
    check(
        "human window annotators",
        {row["annotator"] for row in annotations},
        {"A", "B"},
        annotation_source,
    )
    check(
        "human window instances",
        len({row["annotation_id"] for row in annotations}),
        80,
        annotation_source,
    )
    check(
        "human window preference counts",
        dict(Counter(row["preferred_method"] for row in annotations)),
        {"MURAL": 54, "BM25-local": 19, "Comparable": 15, "Both insufficient": 12},
        annotation_source,
    )
    manifest_source = "human_window_manifest_20260718.tsv"
    manifest = tsv(manifest_source)
    check("human window manifest rows", len(manifest), 80, manifest_source)
    check(
        "human window objective strata",
        dict(Counter(row["objective_outcome"] for row in manifest)),
        {"仅MURAL命中": 43, "仅BM25-local命中": 14, "两者均命中": 12, "两者均未命中": 11},
        manifest_source,
    )
    summary_source = "human_window_summary_20260718.tsv"
    summary = tsv(summary_source)
    check("human window summary rows", len(summary), 17, summary_source)
    agreement_source = "human_window_agreement_20260718.tsv"
    agreement = tsv(agreement_source)
    check("human window agreement rows", len(agreement), 1, agreement_source)
    item = agreement[0]
    check("human window overlap", int(item["overlap_n"]), 20, agreement_source)
    check("human window agreements", int(item["agreement_n"]), 12, agreement_source)
    close("human window observed agreement", float(item["observed_agreement"]), 0.60, agreement_source)
    close(
        "human window Cohen kappa",
        float(item["cohen_kappa"]),
        0.4666666666666666,
        agreement_source,
    )


def reviewer_controls() -> None:
    token_source = "token_budget_context_summary_20260718.tsv"
    token_rows = tsv(token_source)
    check("token control rows", len(token_rows), 12, token_source)
    check("token control N", {int(row["N"]) for row in token_rows}, {500}, token_source)
    mural_4k = where_one(token_rows, source="MURAL", token_budget="4000")
    close("MURAL token Hit@4000", float(mural_4k["hit_rate"]), 0.662, token_source)
    close(
        "MURAL rendered tokens@4000",
        float(mural_4k["context_tokens_mean"]),
        3832.024,
        token_source,
    )
    token_pair_source = "token_budget_context_paired_20260718.tsv"
    token_pairs = tsv(token_pair_source)
    mural_bm25_4k = where_one(
        token_pairs,
        baseline="BM25_projection",
        treatment="MURAL",
        token_budget="4000",
        metric="hit",
    )
    close("MURAL-BM25 token delta@4000", float(mural_bm25_4k["delta"]), 0.106, token_pair_source)
    close(
        "MURAL-BM25 token p@4000",
        float(mural_bm25_4k["exact_mcnemar_p"]),
        1.3280368233066497e-11,
        token_pair_source,
        1e-18,
    )

    fallback_source = "localization_nonfallback_summary_20260718.tsv"
    fallback_rows = tsv(fallback_source)
    check("nonfallback N", {int(row["N"]) for row in fallback_rows}, {491}, fallback_source)
    close(
        "nonfallback MURAL Hit",
        float(one(fallback_rows, "name", "MURAL")["hit_rate"]),
        0.6680244399185336,
        fallback_source,
    )

    selector_source = "selector_simple_summary_20260718.tsv"
    selector_rows = tsv(selector_source)
    close(
        "compact selector Hit",
        float(one(selector_rows, "name", "EntityProjection")["hit_rate"]),
        0.57,
        selector_source,
    )
    close(
        "weighted selector Hit",
        float(one(selector_rows, "name", "WeightedFeatures")["hit_rate"]),
        0.60,
        selector_source,
    )

    tail_source = "fixed_prefix_tail_summary_20260718.tsv"
    tail_rows = tsv(tail_source)
    close("complete-tail MURAL Hit", float(one(tail_rows, "name", "MURAL")["hit_rate"]), 0.802, tail_source)
    count_source = "fixed_prefix_tail_counts_20260718.tsv"
    count_rows = tsv(count_source)
    check(
        "MURAL complete tails",
        int(one(count_rows, "tail", "MURAL")["complete_20"]),
        500,
        count_source,
    )

    history_source = "history_ablation_summary_20260718.tsv"
    history_rows = tsv(history_source)
    close(
        "code-only fusion Hit",
        float(one(history_rows, "name", "MURALCodeOnly")["hit_rate"]),
        0.642,
        history_source,
    )
    close(
        "historical fusion Hit",
        float(one(history_rows, "name", "MURALHistorical")["hit_rate"]),
        0.672,
        history_source,
    )

    transition_source = "repair_equal4000_transition_summary_20260718.tsv"
    transition_rows = tsv(transition_source)
    resolved = one(transition_rows, "outcome", "resolved")
    check(
        "repair resolved transitions",
        (int(resolved["both"]), int(resolved["baseline_only"]), int(resolved["treatment_only"]), int(resolved["neither"])),
        (102, 19, 25, 354),
        transition_source,
    )


def repair_equal4000() -> None:
    variants = ("bm25", "mural")
    outcome_source = "repair_equal4000_outcomes_20260718.tsv"
    outcome_rows = tsv(outcome_source)
    outcome_by_key = {
        (row["variant"], row["instance_id"]): row for row in outcome_rows
    }
    check("equal4000 outcome rows", len(outcome_rows), 1000, outcome_source)
    check(
        "equal4000 outcome keys unique",
        len(outcome_by_key),
        len(outcome_rows),
        outcome_source,
    )
    id_sets = {
        variant: {
            row["instance_id"] for row in outcome_rows if row["variant"] == variant
        }
        for variant in variants
    }
    for variant in variants:
        check(f"equal4000 {variant} N", len(id_sets[variant]), 500, outcome_source)
    check(
        "equal4000 variants share IDs",
        id_sets["bm25"],
        id_sets["mural"],
        outcome_source,
    )
    invalid_flags = []
    for row in outcome_rows:
        flags = tuple(int(row[field]) for field in ("nonempty", "applied", "resolved"))
        if any(value not in (0, 1) for value in flags) or not (
            flags[2] <= flags[1] <= flags[0]
        ):
            invalid_flags.append((row["variant"], row["instance_id"], flags))
    check("equal4000 outcome flags", len(invalid_flags), 0, outcome_source)

    summary_source = "repair_equal4000_summary_20260718.tsv"
    summary_rows = tsv(summary_source)
    variant_rows = [row for row in summary_rows if row["kind"] == "variant"]
    contrast_rows = [row for row in summary_rows if row["kind"] == "contrast"]
    check("equal4000 summary rows", len(summary_rows), 5, summary_source)
    check(
        "equal4000 summary variants",
        sorted(row["name"] for row in variant_rows),
        sorted(variants),
        summary_source,
    )
    check("equal4000 contrast rows", len(contrast_rows), 3, summary_source)

    values: dict[str, dict[str, dict[str, bool]]] = {}
    metric_fields = (
        ("nonempty", "nonempty"),
        ("applicable", "applied"),
        ("resolved", "resolved"),
    )
    for variant in variants:
        rows = [row for row in outcome_rows if row["variant"] == variant]
        summary = one(variant_rows, "name", variant)
        values[variant] = {
            metric: {
                row["instance_id"]: bool(int(row[field])) for row in rows
            }
            for metric, field in metric_fields
        }
        counts = {
            "nonempty": sum(int(row["nonempty"]) for row in rows),
            "applicable": sum(int(row["applied"]) for row in rows),
            "resolved": sum(int(row["resolved"]) for row in rows),
            "patch_apply_failed": sum(
                row["error"] == "patch_apply_failed" for row in rows
            ),
            "test_timeout": sum(
                row["error"].startswith("test_timeout") for row in rows
            ),
        }
        for field, count in counts.items():
            check(f"equal4000 {variant} {field}", int(summary[field]), count, summary_source)
        for count_field, percent_field in (
            ("nonempty", "nonempty_percent"),
            ("applicable", "applicable_percent"),
            ("resolved", "resolved_percent"),
        ):
            close(
                f"equal4000 {variant} {count_field} percent",
                float(summary[percent_field]),
                counts[count_field] / 5.0,
                summary_source,
                5e-4,
            )
        close(
            f"equal4000 {variant} conditional application",
            float(summary["applicable_given_nonempty_percent"]),
            100.0 * counts["applicable"] / counts["nonempty"],
            summary_source,
            5e-4,
        )

    def exact_mcnemar(wins: int, losses: int) -> float:
        discordant = wins + losses
        if discordant == 0:
            return 1.0
        tail = sum(
            math.comb(discordant, index)
            for index in range(min(wins, losses) + 1)
        )
        return min(1.0, 2.0 * tail / (2**discordant))

    ordered_ids = [
        row["instance_id"] for row in outcome_rows if row["variant"] == "bm25"
    ]
    for metric, _ in metric_fields:
        row = pair(contrast_rows, "bm25", "mural", metric)
        baseline = values["bm25"][metric]
        treatment = values["mural"][metric]
        wins = sum(treatment[item] and not baseline[item] for item in ordered_ids)
        losses = sum(baseline[item] and not treatment[item] for item in ordered_ids)
        difference = np.array(
            [float(treatment[item]) - float(baseline[item]) for item in ordered_ids]
        )
        rng = np.random.default_rng(7)
        means = np.empty(10_000, dtype=float)
        for start in range(0, 10_000, 500):
            stop = min(start + 500, 10_000)
            indexes = rng.integers(
                0, len(difference), size=(stop - start, len(difference))
            )
            means[start:stop] = difference[indexes].mean(axis=1)
        low, high = np.percentile(means, [2.5, 97.5]) * 100
        delta = 100.0 * difference.mean()
        close(f"equal4000 {metric} delta", float(row["delta_pp"]), delta, summary_source, 5e-4)
        close(f"equal4000 {metric} CI low", float(row["ci95_low"]), low, summary_source, 5e-4)
        close(f"equal4000 {metric} CI high", float(row["ci95_high"]), high, summary_source, 5e-4)
        check(f"equal4000 {metric} wins", int(row["wins"]), wins, summary_source)
        check(f"equal4000 {metric} losses", int(row["losses"]), losses, summary_source)
        close(
            f"equal4000 {metric} exact p",
            float(row["p_exact"]),
            exact_mcnemar(wins, losses),
            summary_source,
            5e-10,
        )

    assembly_source = "repair_equal4000_assembly_20260718.tsv"
    assembly_rows = tsv(assembly_source)
    assembly_by_key = {
        (row["variant"], row["instance_id"]): row for row in assembly_rows
    }
    check("equal4000 assembly rows", len(assembly_rows), 1000, assembly_source)
    check("equal4000 assembly keys", set(assembly_by_key), set(outcome_by_key), assembly_source)
    protocol_failures = []
    for key, row in assembly_by_key.items():
        try:
            extra_body = json.loads(row["generation_extra_body"])
        except json.JSONDecodeError:
            extra_body = {}
        valid = (
            row["first_prompt_profile"] == "compact"
            and row["context_profile_version"] == "rank_stratified_v3_allfiles"
            and int(row["response_prefill"]) == 0
            and int(row["max_retries"]) == 1
            and 0 < int(row["first_prompt_tokens"]) <= 4000
            and extra_body.get("enable_thinking") is False
            and int(row["nonempty"]) == int(outcome_by_key[key]["nonempty"])
        )
        if not valid:
            protocol_failures.append(key)
    check("equal4000 assembly protocol", len(protocol_failures), 0, assembly_source)

    rendering_source = "repair_equal4000_context_rendering_20260718.tsv"
    rendering_rows = tsv(rendering_source)
    rendering_by_key = {
        (row["variant"], row["instance_id"]): row for row in rendering_rows
    }
    check("equal4000 rendering rows", len(rendering_rows), 1000, rendering_source)
    check("equal4000 rendering keys", set(rendering_by_key), set(outcome_by_key), rendering_source)
    rendering_failures = []
    for key, row in rendering_by_key.items():
        candidate = int(row["candidate_entities"])
        rendered = int(row["rendered_entities"])
        source_entities = int(row["source_entities"])
        valid = (
            0 <= source_entities <= rendered <= candidate <= 20
            and 0 < int(row["prompt_tokens"]) <= 4000
            and len(row["context_sha256"]) == 64
            and len(row["prompt_sha256"]) == 64
        )
        if not valid:
            rendering_failures.append(key)
    check("equal4000 rendering protocol", len(rendering_failures), 0, rendering_source)

    mapping_source = "repair_equal4000_prediction_mapping_20260718.tsv"
    mapping_rows = tsv(mapping_source)
    mapping_by_key = {
        (row["variant"], row["instance_id"]): row for row in mapping_rows
    }
    check("equal4000 mapping rows", len(mapping_rows), 1000, mapping_source)
    check("equal4000 mapping keys", set(mapping_by_key), set(outcome_by_key), mapping_source)
    mapping_failures = []
    for key, row in mapping_by_key.items():
        valid = (
            int(row["nonempty"]) == int(assembly_by_key[key]["nonempty"])
            and row["patch_sha256"] == assembly_by_key[key]["patch_sha256"]
            and row["prompt_sha256"] == rendering_by_key[key]["prompt_sha256"]
            and bool(row["canonical_model"]) == bool(int(row["nonempty"]))
        )
        if not valid:
            mapping_failures.append(key)
    check("equal4000 mapping consistency", len(mapping_failures), 0, mapping_source)

    dedup_source = "repair_equal4000_deduplication_summary_20260718.json"
    dedup = json_file(RESULTS / dedup_source)
    nonempty = sum(int(row["nonempty"]) for row in mapping_rows)
    reuses = sum(int(row["reused_identical_patch"]) for row in mapping_rows)
    check("equal4000 dedup variants", dedup["variants"], list(variants), dedup_source)
    check("equal4000 dedup predictions", dedup["variant_predictions"], 1000, dedup_source)
    check("equal4000 dedup nonempty", dedup["nonempty_variant_predictions"], nonempty, dedup_source)
    check("equal4000 dedup reuses", dedup["identical_patch_reuses"], reuses, dedup_source)
    check("equal4000 canonical predictions", dedup["canonical_predictions"], nonempty - reuses, dedup_source)
    check("equal4000 prompt-match reuse", dedup["reuse_requires_prompt_match"], True, dedup_source)
    check(
        "equal4000 prompt-audit hash",
        dedup["prompt_audit_sha256"],
        hashlib.sha256((RESULTS / rendering_source).read_bytes()).hexdigest(),
        dedup_source,
    )

    transition_source = "repair_equal4000_transition_summary_20260718.tsv"
    transition_rows = tsv(transition_source)
    check("equal4000 transition rows", len(transition_rows), 3, transition_source)
    for metric, _ in metric_fields:
        row = one(transition_rows, "outcome", "applied" if metric == "applicable" else metric)
        baseline = values["bm25"][metric]
        treatment = values["mural"][metric]
        expected = (
            sum(baseline[item] and treatment[item] for item in ordered_ids),
            sum(baseline[item] and not treatment[item] for item in ordered_ids),
            sum(treatment[item] and not baseline[item] for item in ordered_ids),
            sum(not baseline[item] and not treatment[item] for item in ordered_ids),
        )
        observed = tuple(int(row[field]) for field in ("both", "baseline_only", "treatment_only", "neither"))
        check(f"equal4000 {metric} transitions", observed, expected, transition_source)
    transition_instances = tsv("repair_equal4000_transitions_20260718.tsv")
    check("equal4000 transition instances", len(transition_instances), 500, "repair_equal4000_transitions_20260718.tsv")

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
        human_window_audit()
        reviewer_controls()
        if args.scope == "all":
            repair_equal4000()
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
