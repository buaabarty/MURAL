#!/usr/bin/env python3
"""Verify the retained MURAL paper ledgers and frozen protocol."""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "artifacts" / "results"
FROZEN = ROOT / "artifacts" / "frozen"
MANIFEST = ROOT / "artifacts" / "submission_manifest_20260719.json"

EXPECTED_RESULTS = {
    "context_construction_cost_20260716.tsv",
    "human_window_agreement_20260718.tsv",
    "human_window_annotations_20260718.tsv",
    "human_window_items_20260718.json",
    "human_window_manifest_20260718.tsv",
    "human_window_provenance_20260718.tsv",
    "human_window_strict_judgments_20260719.tsv",
    "human_window_strict_summary_20260719.tsv",
    "human_window_summary_20260718.tsv",
    "java_cross_language_instances_20260714.jsonl",
    "java_cross_language_paired_20260714.tsv",
    "java_cross_language_summary_20260714.tsv",
    "java_cross_language_targets_20260714.json",
    "repair_equal4000_clustered_paired_20260719.tsv",
    "repair_equal4000_strict_official_bm25_20260719.jsonl",
    "repair_equal4000_strict_official_mural_20260719.jsonl",
    "repair_equal4000_strict_outcomes_20260719.tsv",
    "repair_equal4000_strict_prediction_provenance_20260719.tsv",
    "repair_equal4000_strict_predictions_bm25_20260719.jsonl",
    "repair_equal4000_strict_predictions_mural_20260719.jsonl",
    "repair_equal4000_strict_regeneration_bm25_20260719.tsv",
    "repair_equal4000_strict_regeneration_mural_20260719.tsv",
    "repair_equal4000_strict_summary_20260719.tsv",
    "source_bearing_prompt_instances_20260719.tsv",
    "source_bearing_prompt_paired_20260719.tsv",
    "source_bearing_prompt_summary_20260719.tsv",
    "strict_external_localizer_instances_20260719.tsv",
    "strict_external_localizer_paired_20260719.tsv",
    "strict_external_localizer_summary_20260719.tsv",
    "strict_localization_instances_20260719.tsv",
    "strict_localization_paired_20260719.tsv",
    "strict_localization_summary_20260719.tsv",
    "strict_prefix_tail_instances_20260719.tsv",
    "strict_prefix_tail_paired_20260719.tsv",
    "strict_prefix_tail_summary_20260719.tsv",
    "strict_reference_targets_20260719.json",
    "strict_rrf_sensitivity_instances_20260719.tsv",
    "strict_rrf_sensitivity_paired_20260719.tsv",
    "strict_rrf_sensitivity_summary_20260719.tsv",
    "strict_selector_instances_20260719.tsv",
    "strict_selector_paired_20260719.tsv",
    "strict_selector_summary_20260719.tsv",
    "strict_token_context_instances_20260719.tsv",
    "strict_token_context_paired_20260719.tsv",
    "strict_token_context_summary_20260719.tsv",
    "strict_token_packing_instances_20260719.tsv",
    "strict_token_packing_summary_20260719.tsv",
}
for budget in (5, 10, 20, 40):
    for suffix in ("summary", "instances", "paired"):
        EXPECTED_RESULTS.add(f"strict_budget_b{budget}_{suffix}_20260719.tsv")


def fail(message: str) -> None:
    raise AssertionError(message)


def equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        fail(f"{label}: observed {observed!r}, expected {expected!r}")


def close(observed: float | str, expected: float, label: str, tol: float = 1e-6) -> None:
    value = float(observed)
    if not math.isclose(value, expected, rel_tol=0.0, abs_tol=tol):
        fail(f"{label}: observed {value}, expected {expected}")


def rows(name: str) -> list[dict[str, str]]:
    with (RESULTS / name).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def one(items: list[dict[str, str]], **keys: str) -> dict[str, str]:
    found = [row for row in items if all(row.get(key) == value for key, value in keys.items())]
    if len(found) != 1:
        fail(f"Expected one row for {keys}, found {len(found)}")
    return found[0]


def pair(name: str, baseline: str, treatment: str, metric: str) -> dict[str, str]:
    return one(rows(name), baseline=baseline, treatment=treatment, metric=metric)


def check_inventory() -> None:
    observed = {path.name for path in RESULTS.iterdir() if path.is_file()}
    equal(sorted(observed), sorted(EXPECTED_RESULTS), "paper-facing result inventory")


def check_targets() -> dict[str, Any]:
    data = json_file(RESULTS / "strict_reference_targets_20260719.json")
    meta, items = data["_meta"], data["items"]
    equal(meta["schema_version"], 1, "target schema")
    equal(meta["population"], 500, "target population")
    equal(len(items), 500, "target item count")
    equal(
        meta["ranking_unit"],
        "base-snapshot synchronous module function, direct class method, or simple module/class assignment",
        "target ranking unit",
    )
    equal(
        meta["file_target_policy"],
        "one exact patched-file fallback for every changed path containing a region outside the candidate-unit contract; retained with entity targets",
        "file target policy",
    )
    equal(
        meta["matching"],
        "exact normalized file path, target kind, and qualified name",
        "target matching",
    )
    counts = Counter(
        target["target_type"]
        for item in items.values()
        for target in item["targets"]
    )
    equal(dict(counts), {"function": 836, "file": 176, "assignment": 32}, "target types")
    equal(sum(item["target_count"] for item in items.values()), 1044, "total targets")
    equal(sum(item["target_count"] == 1 for item in items.values()), 319, "single-target instances")
    equal(sum(item["target_count"] > 1 for item in items.values()), 181, "multi-target instances")
    equal(sum(item["file_target_count"] > 0 for item in items.values()), 151, "file-target instances")
    equal(
        sum(item["file_target_count"] > 0 and item["entity_target_count"] > 0 for item in items.values()),
        121,
        "mixed-target instances",
    )
    equal(sum(len(item["patch_files"]) == 1 for item in items.values()), 429, "single-file instances")
    equal(
        meta["diagnostics"],
        {
            "python_files": 622,
            "non_python_files": 1,
            "missing_base_files": 1,
            "base_parse_failures": 0,
            "patched_parse_failures": 5,
            "patch_apply_failures": 0,
        },
        "target diagnostics",
    )
    return data


def check_localization() -> None:
    summary = rows("strict_localization_summary_20260719.tsv")
    equal(len(summary), 13, "strict localization rows")
    expected = {
        "BM25_entities": (77.0, 47.190685, 32.137738, 57.2, 40.2),
        "BM25_projection": (73.6, 49.276162, 31.095705, 57.8, 42.2),
        "Structural_adapter": (59.2, 46.615664, 31.437884, 52.6, 42.0),
        "Dense_projection": (83.6, 55.086248, 34.514952, 64.4, 47.0),
        "MURAL_2src": (77.0, 54.358203, 34.936758, 63.2, 46.8),
        "MURAL": (83.0, 57.588463, 37.950833, 67.2, 49.6),
        "GLM5": (87.4, 54.306883, 55.257309, 66.6, 45.0),
        "GLM5_BM25": (94.2, 68.470043, 57.958244, 79.0, 59.4),
        "GLM5_MURAL2": (94.6, 69.881840, 58.501354, 79.2, 61.4),
        "GLM5_MURAL": (95.2, 69.805996, 58.511191, 79.8, 61.2),
    }
    for approach, values in expected.items():
        row = one(summary, approach=approach)
        equal(int(row["N"]), 500, f"{approach} N")
        for field, value in zip(("file_hit", "target_coverage", "mrr", "hit", "complete"), values):
            close(row[field], value, f"{approach} {field}")

    comparisons = [
        ("BM25_projection", "MURAL", "hit", 9.4, 6.093034, 10.628067, 53, 6, 1.75391874635e-10),
        ("BM25_projection", "MURAL", "complete", 7.4, 2.714932, 9.286533, 41, 4, 9.33488308874e-09),
        ("Dense_projection", "MURAL", "hit", 2.8, 0.530469, 3.916464, 33, 19, 0.0703942210671),
        ("MURAL_2src", "MURAL", "hit", 4.0, 1.327360, 6.644676, 31, 11, 0.00288724797429),
        ("GLM5_BM25", "GLM5_MURAL", "hit", 0.8, -0.450450, 3.608294, 14, 10, 0.541256189346),
    ]
    for baseline, treatment, metric, delta, low, high, wins, losses, p in comparisons:
        row = pair("strict_localization_paired_20260719.tsv", baseline, treatment, metric)
        close(row["delta"], delta, f"{baseline}->{treatment} {metric} delta")
        close(row["clustered_ci_low"], low, f"{baseline}->{treatment} {metric} low")
        close(row["clustered_ci_high"], high, f"{baseline}->{treatment} {metric} high")
        equal(int(row["wins"]), wins, f"{baseline}->{treatment} {metric} wins")
        equal(int(row["losses"]), losses, f"{baseline}->{treatment} {metric} losses")
        close(row["mcnemar_p"], p, f"{baseline}->{treatment} {metric} p", 1e-12)



def check_frozen_rankings(targets: dict[str, Any]) -> None:
    path = FROZEN / "strict_rankings_top50_20260719.jsonl.gz"
    equal(
        hashlib.sha256(path.read_bytes()).hexdigest(),
        "7f0ffa7c5561bf132b9ff075f1e8e8d23c0aff5f0237f03f69e08de704cf5b1d",
        "frozen ranking SHA-256",
    )
    spec = importlib.util.spec_from_file_location(
        "strict_eval", ROOT / "artifacts" / "scripts" / "evaluate_strict_reference_context.py"
    )
    if spec is None or spec.loader is None:
        fail("Cannot import strict evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    identity_spec = importlib.util.spec_from_file_location(
        "entity_identity", ROOT / "artifacts" / "scripts" / "entity_identity.py"
    )
    if identity_spec is None or identity_spec.loader is None:
        fail("Cannot import canonical entity identity")
    identity_module = importlib.util.module_from_spec(identity_spec)
    identity_spec.loader.exec_module(identity_module)

    source_metrics: dict[str, list[dict[str, float]]] = {}
    seen: set[str] = set()
    expected_sources = {
        "BM25_projection",
        "Structural_adapter",
        "Dense_projection",
        "MURAL_2src",
        "MURAL",
    }
    source_manifest = json_file(FROZEN / "source_rankings_manifest_20260719.json")
    equal(source_manifest["frozen_rankings"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest(), "source manifest ranking hash")
    equal(set(source_manifest["rankings"]), expected_sources, "source manifest labels")
    equal(source_manifest["top_k"], 50, "source manifest Top-K")
    boundary = source_manifest["retrieval_boundary"]
    equal(boundary["benchmark_hints_included"], False, "source manifest hint boundary")
    equal(boundary["query_fields"], ["problem_statement"], "source manifest query fields")
    equal(
        source_manifest["rankings"]["Dense_projection"]["encoder"],
        "jinaai/jina-embeddings-v2-base-code@516f4baf13dec4ddddda8631e019b5737c8bc250",
        "dense encoder revision",
    )
    if "--include-hints" in boundary["source_generation_command"]:
        fail("source generation command includes benchmark hints")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            instance_id = row["instance_id"]
            if instance_id in seen:
                fail(f"duplicate frozen ranking instance {instance_id}")
            seen.add(instance_id)
            equal(set(row["sources"]), expected_sources, f"{instance_id} frozen sources")
            for source, candidates in row["sources"].items():
                if len(candidates) > 50:
                    fail(f"{instance_id} {source}: more than Top-50 candidates")
                identities = [identity_module.canonical_entity_id(item) for item in candidates]
                if any(not key[0] or not key[2] for key in identities):
                    fail(f"{instance_id} {source}: incomplete canonical identity")
                if len(identities) != len(set(identities)):
                    fail(f"{instance_id} {source}: duplicate canonical identity")
                source_metrics.setdefault(source, []).append(
                    module.evaluate_instance(candidates, targets["items"][instance_id], 20)
                )
    equal(len(seen), 500, "frozen ranking population")
    summary = rows("strict_localization_summary_20260719.tsv")
    for source, metrics in source_metrics.items():
        ledger = one(summary, approach=source)
        for field in ("file_hit", "target_coverage", "mrr", "hit", "complete"):
            observed = 100 * sum(float(item[field]) for item in metrics) / len(metrics)
            close(observed, float(ledger[field]), f"frozen {source} {field}", 1e-5)


def check_token_budgets() -> None:
    summary = rows("strict_token_context_summary_20260719.tsv")
    expected = {
        2000: (45.2, 55.2, 56.8, 11.6),
        4000: (56.2, 65.4, 66.6, 10.4),
        8000: (62.6, 72.4, 74.8, 12.2),
    }
    for budget, (bm25, dense, mural, delta) in expected.items():
        close(one(summary, approach=f"BM25_t{budget}")["hit"], bm25, f"BM25 T{budget}")
        close(one(summary, approach=f"Dense_t{budget}")["hit"], dense, f"Dense T{budget}")
        close(one(summary, approach=f"MURAL_t{budget}")["hit"], mural, f"MURAL T{budget}")
        paired = pair(
            "strict_token_context_paired_20260719.tsv",
            f"BM25_t{budget}",
            f"MURAL_t{budget}",
            "hit",
        )
        close(paired["delta"], delta, f"T{budget} Hit delta")
        if float(paired["clustered_ci_low"]) <= 0:
            fail(f"T{budget}: principal clustered interval includes zero")

    packing = rows("strict_token_packing_summary_20260719.tsv")
    expected_packing = {
        2000: (8.948, 1861.310, 0.23983012963790792, 0.25331888377133566, 0.202),
        4000: (19.574, 3834.142, 0.23050986001839174, 0.31373611487401787, 0.232),
        8000: (39.306, 7657.458, 0.2355874421207958, 0.3698184773774045, 0.27),
    }
    for budget, values in expected_packing.items():
        row = one(packing, source="MURAL", token_budget=str(budget))
        for field, value in zip(
            ("selected_mean", "context_tokens_mean", "truncated_entity_rate", "changed_line_recall", "complete_changed_line_rate"),
            values,
        ):
            close(row[field], value, f"MURAL packing T{budget} {field}")


def check_controls_and_budgets() -> None:
    selector = rows("strict_selector_summary_20260719.tsv")
    equal(len(selector), 6, "retained selector rows")
    if any("Weighted" in row["approach"] for row in selector):
        fail("exploratory weighted selector remains in paper-facing results")
    for approach, values in {
        "File_source_order": (24.2, 17.4),
        "File_name_overlap": (33.6, 26.4),
        "Within_file_BM25": (36.0, 29.4),
        "Equal_round_robin": (53.0, 33.8),
        "Stable_random": (13.6, 2.8),
        "Compact_projection": (57.8, 42.2),
    }.items():
        row = one(selector, approach=approach)
        close(row["hit"], values[0], f"selector {approach} Hit")
        close(row["complete"], values[1], f"selector {approach} Complete")
    row = pair("strict_selector_paired_20260719.tsv", "Equal_round_robin", "Compact_projection", "hit")
    close(row["delta"], 4.8, "compact vs round-robin Hit")
    close(row["mcnemar_p"], 0.0353236825378, "compact vs round-robin p")

    prefix = rows("strict_prefix_tail_summary_20260719.tsv")
    equal(len(prefix), 9, "retained prefix rows")
    if any("Weighted" in row["approach"] for row in prefix):
        fail("exploratory weighted tail remains in paper-facing results")
    for approach, values in {
        "OwnRemaining": (6.054, 66.6, 45.0),
        "SameFileNeighbors": (16.736, 74.8, 56.6),
        "EqualRoundRobin": (20.0, 77.6, 54.8),
        "BM25Projection": (20.0, 79.0, 59.4),
        "DenseProjection": (20.0, 80.0, 61.6),
        "MURAL": (20.0, 79.8, 61.2),
    }.items():
        row = one(prefix, approach=approach)
        for field, value in zip(("candidate_count_mean", "hit", "complete"), values):
            close(row[field], value, f"prefix {approach} {field}")

    expected_budgets = {
        5: (62.6, 67.8, 68.0),
        10: (66.4, 72.4, 73.8),
        20: (66.6, 79.0, 79.8),
        40: (66.6, 82.0, 86.0),
    }
    for budget, values in expected_budgets.items():
        summary = rows(f"strict_budget_b{budget}_summary_20260719.tsv")
        for approach, value in zip(("Issue", "BM25", "MURAL"), values):
            close(one(summary, approach=approach)["hit"], value, f"B{budget} {approach} Hit")
    row = pair("strict_budget_b40_paired_20260719.tsv", "BM25", "MURAL", "hit")
    close(row["delta"], 4.0, "B40 Hit delta")
    close(row["mcnemar_p"], 3.58819961548e-05, "B40 Hit p", 1e-12)

    sensitivity = rows("strict_rrf_sensitivity_summary_20260719.tsv")
    for approach, hit in {
        "k10": 69.8,
        "k30": 68.2,
        "k60": 67.2,
        "k100": 67.0,
        "dense05": 65.4,
        "dense075": 65.6,
        "dense125": 66.8,
        "dense15": 67.2,
    }.items():
        close(one(sensitivity, approach=approach)["hit"], hit, f"RRF {approach}")


def check_external() -> None:
    summary = rows("strict_external_localizer_summary_20260719.tsv")
    expected = {
        "CoSIL": (4.046, 67.8, 51.0),
        "CoSIL+MURAL": (20.0, 84.0, 65.2),
        "Agentless": (2.518, 47.6, 34.6),
        "Agentless+MURAL": (20.0, 76.4, 58.2),
        "LocAgent": (3.784, 65.0, 49.0),
        "LocAgent+MURAL": (20.0, 81.4, 62.4),
        "OrcaLoca": (0.298, 14.0, 10.8),
        "OrcaLoca+MURAL": (20.0, 70.0, 52.2),
    }
    for approach, values in expected.items():
        row = one(summary, approach=approach)
        for field, value in zip(("candidate_count_mean", "hit", "complete"), values):
            close(row[field], value, f"{approach} {field}")
    for baseline, delta in {
        "CoSIL": 16.2,
        "Agentless": 28.8,
        "LocAgent": 16.4,
        "OrcaLoca": 56.0,
    }.items():
        row = pair("strict_external_localizer_paired_20260719.tsv", baseline, f"{baseline}+MURAL", "hit")
        close(row["delta"], delta, f"{baseline} completion delta")
        equal(int(row["losses"]), 0, f"{baseline} prefix-preserving losses")
        if float(row["clustered_ci_low"]) <= 0:
            fail(f"{baseline}: completion interval includes zero")

    provenance = json_file(FROZEN / "external_localizers_manifest.json")
    equal(provenance["source_commit"], "0568e423735b399d5b089996961fea9ae142e4c7", "external source commit")
    equal(len(provenance["files"]), 4, "external source file count")
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in provenance["files"].values()):
        fail("invalid external source SHA-256")



def check_prompts_and_human() -> None:
    summary = rows("source_bearing_prompt_summary_20260719.tsv")
    expected = {
        "bm25": (16.744, 4.956, 3613.916, 50.247835, 62.2, 42.0),
        "mural": (17.302, 5.146, 3565.324, 52.419892, 64.0, 44.0),
    }
    for variant, values in expected.items():
        row = one(summary, variant=variant)
        equal(int(row["N"]), 500, f"{variant} prompt N")
        for field, value in zip(
            ("rendered_entities_mean", "source_entities_mean", "prompt_tokens_mean", "source_target_coverage", "source_hit", "source_complete"),
            values,
        ):
            close(row[field], value, f"{variant} prompt {field}")
        equal(int(row["verified_prompt_hashes"]), 500, f"{variant} verified prompt hashes")

    prompt_rows = rows("source_bearing_prompt_instances_20260719.tsv")
    equal(len(prompt_rows), 1000, "prompt instance rows")
    equal(Counter(row["variant"] for row in prompt_rows), Counter({"bm25": 500, "mural": 500}), "prompt variants")
    if any(not re.fullmatch(r"[0-9a-f]{64}", row["prompt_sha256"]) for row in prompt_rows):
        fail("invalid rendered prompt SHA-256")

    human = rows("human_window_summary_20260718.tsv")
    expected_decisions = {"MURAL": 54, "BM25-local": 19, "Comparable": 15, "Both insufficient": 12}
    for decision, count in expected_decisions.items():
        row = one(human, scope="all_judgments", category=decision)
        equal(int(row["count"]), count, f"human decision {decision}")
    agreement = rows("human_window_agreement_20260718.tsv")[0]
    equal(int(agreement["overlap_n"]), 20, "human overlap")
    equal(int(agreement["agreement_n"]), 12, "human agreement")
    close(agreement["cohen_kappa"], 0.4666666666666666, "human kappa")

    strict = rows("human_window_strict_summary_20260719.tsv")
    for stratum, count in {"MURAL_only": 31, "BM25_only": 6, "both": 24, "neither": 19}.items():
        row = one(strict, scope="unique_instances", strict_stratum=stratum, decision="instances")
        equal(int(row["count"]), count, f"strict human stratum {stratum}")
    for decision, count in {"aligned": 36, "neutral": 5, "opposed": 3}.items():
        row = one(
            strict,
            scope="exclusive_hit_judgments",
            strict_stratum="MURAL_only_or_BM25_only",
            decision=decision,
        )
        equal(int(row["count"]), count, f"exclusive judgment {decision}")


def check_repair() -> None:
    outcomes = rows("repair_equal4000_strict_outcomes_20260719.tsv")
    equal(len(outcomes), 1000, "strict repair outcome rows")
    aggregate: dict[str, dict[str, int]] = {}
    for variant in ("bm25", "mural"):
        selected = [row for row in outcomes if row["variant"] == variant]
        equal(len(selected), 500, f"{variant} repair rows")
        aggregate[variant] = {
            metric: sum(int(row[metric]) for row in selected)
            for metric in ("nonempty", "applied", "resolved")
        }
    equal(
        aggregate,
        {
            "bm25": {"nonempty": 468, "applied": 466, "resolved": 123},
            "mural": {"nonempty": 472, "applied": 468, "resolved": 128},
        },
        "repair aggregates",
    )

    summary = rows("repair_equal4000_strict_summary_20260719.tsv")
    for variant, values in {"bm25": (468, 466, 123), "mural": (472, 468, 128)}.items():
        row = one(summary, kind="variant", name=variant, metric="all")
        for field, value in zip(("nonempty", "applicable", "resolved"), values):
            equal(int(row[field]), value, f"{variant} summary {field}")
    paired = rows("repair_equal4000_clustered_paired_20260719.tsv")
    expected = {
        "nonempty": (0.8, -1.075298, 4.958678, 12, 8, 0.503444671631),
        "applied": (0.4, -1.670644, 4.958678, 12, 10, 0.831811904907),
        "resolved": (1.0, -1.446672, 6.355932, 25, 20, 0.551484329803),
    }
    for metric, values in expected.items():
        row = one(paired, baseline="bm25", treatment="mural", metric=metric)
        for field, value in zip(
            ("delta", "clustered_ci_low", "clustered_ci_high", "wins", "losses", "mcnemar_p"),
            values,
        ):
            close(row[field], value, f"repair {metric} {field}", 1e-9)
        summary_metric = "applicable" if metric == "applied" else metric
        summary_row = one(
            summary, kind="contrast", name="mural_vs_bm25", metric=summary_metric
        )
        for field, value in zip(
            ("delta_pp", "ci95_low", "ci95_high", "wins", "losses", "p_exact"),
            values,
        ):
            close(summary_row[field], value, f"repair summary {metric} {field}", 1e-9)

    provenance = rows("repair_equal4000_strict_prediction_provenance_20260719.tsv")
    equal(len(provenance), 1000, "repair provenance rows")
    provenance_by_key = {
        (row["instance_id"], row["variant"]): row
        for row in provenance
    }
    equal(len(provenance_by_key), 1000, "unique repair provenance keys")

    for variant in ("bm25", "mural"):
        predictions = jsonl(RESULTS / f"repair_equal4000_strict_predictions_{variant}_20260719.jsonl")
        official = jsonl(RESULTS / f"repair_equal4000_strict_official_{variant}_20260719.jsonl")
        equal(len(predictions), 500, f"{variant} prediction count")
        expected_official = aggregate[variant]["nonempty"]
        equal(len(official), expected_official, f"{variant} official count")
        prediction_by_id = {row["instance_id"]: row for row in predictions}
        official_by_id = {row["instance_id"]: row for row in official}
        equal(len(prediction_by_id), 500, f"{variant} prediction IDs")
        equal(len(official_by_id), expected_official, f"{variant} official IDs")

        for instance_id, prediction in prediction_by_id.items():
            patch = str(prediction.get("model_patch") or "")
            digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()
            provenance_row = provenance_by_key[(instance_id, variant)]
            equal(
                provenance_row["new_patch_sha256"],
                digest,
                f"{variant} {instance_id} provenance patch hash",
            )
            nonempty = int(bool(patch.strip()))
            equal(int(provenance_row["nonempty"]), nonempty, f"{variant} {instance_id} provenance nonempty")
            if nonempty:
                if instance_id not in official_by_id:
                    fail(f"{variant} {instance_id}: nonempty prediction lacks official outcome")
                official_row = official_by_id[instance_id]
                equal(official_row["patch_sha256"], digest, f"{variant} {instance_id} official patch hash")
                equal(int(official_row["patch_chars"]), len(patch), f"{variant} {instance_id} patch chars")
            elif instance_id in official_by_id:
                fail(f"{variant} {instance_id}: empty prediction has official outcome")


def check_java_and_cost() -> None:
    java = rows("java_cross_language_summary_20260714.tsv")
    expected = {
        "Raw_BM25_entities": (61.5384615, 19.9258342, 13.4988129, 34.0659341),
        "BM25_projection": (67.0329670, 31.9343477, 24.1405226, 47.2527473),
        "Structural_projection": (63.7362637, 34.7318549, 24.3507117, 51.6483516),
        "Lexical_structural_fusion": (70.3296703, 34.6052152, 25.9345240, 54.9450549),
    }
    for name, values in expected.items():
        row = one(java, name=name)
        equal(int(row["N"]), 91, f"Java {name} N")
        for field, value in zip(("file_rate", "method_or_entity_rate", "mrr", "hit_rate"), values):
            close(100 * float(row[field]), value, f"Java {name} {field}", 1e-5)
    instances = jsonl(RESULTS / "java_cross_language_instances_20260714.jsonl")
    equal(len(instances), 91, "Java instance count")
    equal(len({row["instance_id"] for row in instances}), 91, "Java unique IDs")
    equal(len({row["repo"] for row in instances}), 6, "Java repository count")

    paired = rows("java_cross_language_paired_20260714.tsv")
    row = one(paired, baseline="Raw_BM25_entities", treatment="BM25_projection", metric="mrr")
    close(100 * float(row["delta"]), 10.6417097, "Java BM25 projection MRR delta")
    close(100 * float(row["ci95_low"]), 3.9955544, "Java BM25 projection MRR low")
    row = one(paired, baseline="Raw_BM25_entities", treatment="BM25_projection", metric="hit")
    close(row["exact_mcnemar_p"], 0.0576126729138, "Java BM25 projection Hit p")

    java_manifest = json_file(
        ROOT / "artifacts" / "inputs" / "java_cross_language_manifest_20260714.json"
    )
    evaluation = java_manifest["evaluation"]
    java_script = ROOT / evaluation["script"]
    equal(
        hashlib.sha256(java_script.read_bytes()).hexdigest(),
        evaluation["script_sha256"],
        "Java evaluator embedded hash",
    )
    equal(
        hashlib.sha256(
            (RESULTS / "java_cross_language_paired_20260714.tsv").read_bytes()
        ).hexdigest(),
        evaluation["output_sha256"]["paired"],
        "Java paired-ledger embedded hash",
    )

    cost = rows("context_construction_cost_20260716.tsv")
    close(one(cost, stage="three_source_equal_weight_rrf")["mean_s"], 0.0091, "RRF mean seconds")
    close(one(cost, stage="structural_adapter")["median_s"], 66.9057985, "structural median seconds")


def check_manifest() -> None:
    manifest = json_file(MANIFEST)
    equal(manifest["schema_version"], 2, "manifest schema")
    equal(manifest["python_benchmark"]["instances"], 500, "manifest Python population")
    equal(manifest["strict_reference"]["target_counts"]["total"], 1044, "manifest target count")
    equal(manifest["java_benchmark"]["evaluated_instances"], 91, "manifest Java population")
    equal(manifest["repair"]["prompt_hash_rows"], 1000, "manifest prompt hashes")
    for name, record in manifest["files"].items():
        path = ROOT / name
        if not path.is_file():
            fail(f"manifest file missing: {name}")
        equal(path.stat().st_size, record["bytes"], f"manifest size {name}")
        equal(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"], f"manifest hash {name}")


def check_instance_ledgers() -> None:
    for name in sorted(EXPECTED_RESULTS):
        if "_instances_" not in name or not name.endswith(".tsv"):
            continue
        items = rows(name)
        ids = {row["instance_id"] for row in items}
        equal(len(ids), 500, f"{name} unique instances")
        if len(items) % 500:
            fail(f"{name}: row count {len(items)} is not a 500-instance multiple")


def check_removed_terms() -> None:
    paper_facing = [
        ROOT / "README.md",
        ROOT / "artifacts" / "README.md",
        ROOT / "artifacts" / "RESULT_TRACEABILITY.md",
    ]
    for path in paper_facing:
        text = path.read_text(encoding="utf-8")
        if "LocalPathRank" in text:
            fail(f"obsolete LocalPathRank term remains in {path.relative_to(ROOT)}")


def main() -> None:
    check_inventory()
    check_instance_ledgers()
    targets = check_targets()
    check_localization()
    check_frozen_rankings(targets)
    check_token_budgets()
    check_controls_and_budgets()
    check_external()
    check_prompts_and_human()
    check_repair()
    check_java_and_cost()
    check_removed_terms()
    check_manifest()
    print("MURAL paper artifact verification passed.")


if __name__ == "__main__":
    main()
