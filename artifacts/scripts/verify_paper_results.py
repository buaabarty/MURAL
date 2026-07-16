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

    rendering_source = "repair_glm52_context_rendering_20260716.tsv"
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
        check("context rendering rows", len(rendering_rows), 1500, rendering_source)
        check(
            "context rendering keys unique",
            len(rendering_keys),
            len(rendering_rows),
            rendering_source,
        )
        for variant in ("issue", "bm25", "mural"):
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


def repair() -> None:
    variants = ("issue", "bm25", "mural")
    outcome_source = "repair_glm52_outcomes_20260716.tsv"
    outcome_rows = tsv(outcome_source)
    outcome_by_key = {
        (row["variant"], row["instance_id"]): row for row in outcome_rows
    }
    check("repair outcome rows", len(outcome_rows), 1500, outcome_source)
    check(
        "repair outcome keys unique",
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
        check(f"{variant} repair N", len(id_sets[variant]), 500, outcome_source)
    check(
        "repair variants share IDs",
        len({frozenset(values) for values in id_sets.values()}),
        1,
        outcome_source,
    )
    invalid_flags = []
    for row in outcome_rows:
        flags = tuple(int(row[field]) for field in ("nonempty", "applied", "resolved"))
        if any(value not in (0, 1) for value in flags) or not (
            flags[2] <= flags[1] <= flags[0]
        ):
            invalid_flags.append((row["variant"], row["instance_id"], flags))
    check("repair outcome flag consistency", len(invalid_flags), 0, outcome_source)

    summary_source = "repair_glm52_summary_20260716.tsv"
    summary_rows = tsv(summary_source)
    variant_rows = [row for row in summary_rows if row["kind"] == "variant"]
    contrast_rows = [row for row in summary_rows if row["kind"] == "contrast"]
    check("repair summary rows", len(summary_rows), 6, summary_source)
    check(
        "repair summary variants",
        sorted(row["name"] for row in variant_rows),
        sorted(variants),
        summary_source,
    )
    check("repair contrast rows", len(contrast_rows), 3, summary_source)
    resolved_by_variant: dict[str, dict[str, bool]] = {}
    for variant in variants:
        rows = [row for row in outcome_rows if row["variant"] == variant]
        summary = one(variant_rows, "name", variant)
        resolved_by_variant[variant] = {
            row["instance_id"]: bool(int(row["resolved"])) for row in rows
        }
        expected = {
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
        for field, value in expected.items():
            check(f"{variant} {field}", int(summary[field]), value, summary_source)
        close(
            f"{variant} resolved percent",
            float(summary["resolved_percent"]),
            100.0 * expected["resolved"] / 500,
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

    contrast_specs = (
        ("bm25_vs_issue", "issue", "bm25"),
        ("mural_vs_issue", "issue", "mural"),
        ("mural_vs_bm25", "bm25", "mural"),
    )
    for name, baseline, treatment in contrast_specs:
        row = one(contrast_rows, "name", name)
        check(f"{name} baseline", row["baseline"], baseline, summary_source)
        check(f"{name} treatment", row["treatment"], treatment, summary_source)
        ids = id_sets[baseline]
        wins = sum(
            resolved_by_variant[treatment][instance_id]
            and not resolved_by_variant[baseline][instance_id]
            for instance_id in ids
        )
        losses = sum(
            resolved_by_variant[baseline][instance_id]
            and not resolved_by_variant[treatment][instance_id]
            for instance_id in ids
        )
        delta = (
            sum(resolved_by_variant[treatment].values())
            - sum(resolved_by_variant[baseline].values())
        ) / 5.0
        close(f"{name} delta", float(row["delta_pp"]), delta, summary_source, 5e-4)
        check(f"{name} wins", int(row["wins"]), wins, summary_source)
        check(f"{name} losses", int(row["losses"]), losses, summary_source)
        close(
            f"{name} exact p",
            float(row["p_exact"]),
            exact_mcnemar(wins, losses),
            summary_source,
            5e-10,
        )
        low, high = float(row["ci95_low"]), float(row["ci95_high"])
        check(
            f"{name} CI contains effect",
            (low, delta, high),
            "low <= delta <= high",
            summary_source,
            low <= delta <= high,
        )

    assembly_source = "repair_glm52_assembly_20260716.tsv"
    assembly_rows = tsv(assembly_source)
    assembly_by_key = {
        (row["variant"], row["instance_id"]): row for row in assembly_rows
    }
    check("repair assembly rows", len(assembly_rows), 1500, assembly_source)
    check(
        "repair assembly keys",
        set(assembly_by_key),
        set(outcome_by_key),
        assembly_source,
    )
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
            and 0 < int(row["first_prompt_tokens"]) <= 5000
            and extra_body.get("enable_thinking") is False
            and int(row["nonempty"]) == int(outcome_by_key[key]["nonempty"])
        )
        if not valid:
            protocol_failures.append(key)
    check("repair assembly protocol", len(protocol_failures), 0, assembly_source)

    rendering_source = "repair_glm52_context_rendering_20260716.tsv"
    rendering_rows = tsv(rendering_source)
    rendering_by_key = {
        (row["variant"], row["instance_id"]): row for row in rendering_rows
    }
    check("context rendering rows", len(rendering_rows), 1500, rendering_source)
    check(
        "context rendering keys",
        set(rendering_by_key),
        set(outcome_by_key),
        rendering_source,
    )
    rendering_failures = []
    for key, row in rendering_by_key.items():
        candidate = int(row["candidate_entities"])
        rendered = int(row["rendered_entities"])
        source_entities = int(row["source_entities"])
        valid = (
            0 <= source_entities <= rendered <= candidate <= 20
            and 0 < int(row["prompt_tokens"]) <= 5000
            and len(row["context_sha256"]) == 64
            and len(row["prompt_sha256"]) == 64
        )
        if not valid:
            rendering_failures.append(key)
    check("context rendering protocol", len(rendering_failures), 0, rendering_source)
    expected_rendering = {
        "issue": (1879, 1195, 1008457, 4105),
        "bm25": (8914, 3319, 2034218, 4988),
        "mural": (8921, 3225, 1937200, 4991),
    }
    for variant, expected in expected_rendering.items():
        rows = [
            row for row in rendering_rows if row["variant"] == variant
        ]
        observed = (
            sum(int(row["candidate_entities"]) for row in rows),
            sum(int(row["source_entities"]) for row in rows),
            sum(int(row["prompt_tokens"]) for row in rows),
            max(int(row["prompt_tokens"]) for row in rows),
        )
        check(f"{variant} rendering aggregate", observed, expected, rendering_source)

    mapping_source = "repair_glm52_prediction_mapping_20260716.tsv"
    mapping_rows = tsv(mapping_source)
    mapping_by_key = {
        (row["variant"], row["instance_id"]): row for row in mapping_rows
    }
    check("prediction mapping rows", len(mapping_rows), 1500, mapping_source)
    check(
        "prediction mapping keys",
        set(mapping_by_key),
        set(outcome_by_key),
        mapping_source,
    )
    mapping_failures = []
    seen_reuse_keys: set[tuple[str, str, str, str]] = set()
    for key, row in mapping_by_key.items():
        assembly = assembly_by_key[key]
        reuse_key = (
            row["instance_id"],
            row["slot"],
            row["patch_sha256"],
            row["prompt_sha256"],
        )
        expected_reuse = int(
            int(row["nonempty"]) == 1 and reuse_key in seen_reuse_keys
        )
        valid = (
            int(row["nonempty"]) == int(assembly["nonempty"])
            and row["patch_sha256"] == assembly["patch_sha256"]
            and row["prompt_sha256"]
            == rendering_by_key[key]["prompt_sha256"]
            and bool(row["canonical_model"]) == bool(int(row["nonempty"]))
            and int(row["reused_identical_patch"]) == expected_reuse
        )
        if not valid:
            mapping_failures.append(key)
        if int(row["nonempty"]):
            seen_reuse_keys.add(reuse_key)
    check("prediction mapping consistency", len(mapping_failures), 0, mapping_source)

    dedup_source = "repair_glm52_deduplication_summary_20260716.json"
    dedup = json_file(RESULTS / dedup_source)
    nonempty = sum(int(row["nonempty"]) for row in mapping_rows)
    reuses = sum(int(row["reused_identical_patch"]) for row in mapping_rows)
    canonical = nonempty - reuses
    check("dedup variants", dedup["variants"], list(variants), dedup_source)
    check(
        "dedup prompt-match requirement",
        dedup["reuse_requires_prompt_match"],
        True,
        dedup_source,
    )
    check(
        "dedup prompt-audit hash",
        dedup["prompt_audit_sha256"],
        hashlib.sha256((RESULTS / rendering_source).read_bytes()).hexdigest(),
        dedup_source,
    )
    check("dedup variant predictions", dedup["variant_predictions"], 1500, dedup_source)
    check(
        "dedup nonempty predictions",
        dedup["nonempty_variant_predictions"],
        nonempty,
        dedup_source,
    )
    check("dedup identical reuses", dedup["identical_patch_reuses"], reuses, dedup_source)
    check("dedup canonical predictions", dedup["canonical_predictions"], canonical, dedup_source)
    check(
        "dedup slot total",
        sum(int(value) for value in dedup["slot_counts"].values()),
        canonical,
        dedup_source,
    )

    repository_source = "mural_repository_repair_20260716.tsv"
    repository_rows = [
        row for row in tsv(repository_source) if row["repository"] == "ALL"
    ]
    check("repository repair ALL rows", len(repository_rows), 3, repository_source)
    for variant in variants:
        row = one(repository_rows, "variant", variant)
        summary = one(variant_rows, "name", variant)
        check(f"{variant} repository N", int(row["N"]), 500, repository_source)
        for field, summary_field in (
            ("nonempty", "nonempty"),
            ("applied", "applicable"),
            ("resolved", "resolved"),
        ):
            check(
                f"{variant} repository {field}",
                int(row[field]),
                int(summary[summary_field]),
                repository_source,
            )


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
