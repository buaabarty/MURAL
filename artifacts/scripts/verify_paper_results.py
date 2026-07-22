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
    "architecture_control_instances_20260721.tsv",
    "architecture_control_paired_20260721.tsv",
    "architecture_control_summary_20260721.tsv",
    "entity_ordering_control_instances_20260721.tsv",
    "entity_ordering_control_paired_20260721.tsv",
    "entity_ordering_control_summary_20260721.tsv",
    "line_coverage_instances_4000_20260721.tsv",
    "line_coverage_summary_4000_20260721.tsv",
    "reference_coverage_strata_4000_20260721.tsv",
    "human_construct_adjudicated_20260721.tsv",
    "human_construct_annotations_raw_20260721.tsv",
    "human_evidence_audit_provenance_20260721.tsv",
    "human_evidence_audit_summary_20260721.json",
    "human_evidence_audit_summary_20260721.tsv",
    "human_support_adjudicated_20260721.tsv",
    "human_support_annotations_raw_20260721.tsv",
    "human_window_agreement_20260718.tsv",
    "human_window_annotations_20260718.tsv",
    "human_window_binding_20260719.tsv",
    "human_window_exact_instances_20260719.tsv",
    "human_window_items_20260718.json",
    "human_window_manifest_20260718.tsv",
    "human_window_provenance_20260718.tsv",
    "human_window_strict_judgments_20260719.tsv",
    "human_window_strict_summary_20260719.tsv",
    "human_window_unique_strict_summary_20260719.tsv",
    "human_window_summary_20260718.tsv",
    "issue_creation_cutoff_audit_20260719.json",
    "java_cross_language_instances_20260714.jsonl",
    "paper_dataset_profile_20260722.tsv",
    "paper_main_results_20260722.tsv",
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
    "strict_mechanism_analysis_20260719.tsv",
    "strict_prefix_tail_instances_20260719.tsv",
    "strict_prefix_tail_paired_20260719.tsv",
    "strict_prefix_tail_summary_20260719.tsv",
    "strict_reference_targets_20260719.json",
    "strict_rrf_sensitivity_instances_20260719.tsv",
    "strict_rrf_sensitivity_paired_20260719.tsv",
    "strict_rrf_sensitivity_summary_20260719.tsv",
    "strict_repository_robustness_20260719.tsv",
    "strict_selector_instances_20260719.tsv",
    "strict_selector_paired_20260719.tsv",
    "strict_selector_summary_20260719.tsv",
    "strict_target_multiplicity_20260719.tsv",
    "strict_token_context_instances_20260719.tsv",
    "strict_token_context_paired_20260719.tsv",
    "strict_token_context_summary_20260719.tsv",
    "strict_token_packing_instances_20260719.tsv",
    "strict_token_packing_summary_20260719.tsv",
}
STALE_RESULTS = {
    "retrieve_then_localize_top20_20260711.tsv",
    "tse_gt_mapping_v6.tsv",
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
    stale = sorted(observed & STALE_RESULTS)
    if stale:
        fail(f"superseded result ledgers remain in paper-facing inventory: {stale}")
    equal(sorted(observed), sorted(EXPECTED_RESULTS), "paper-facing result inventory")


def check_issue_creation_cutoff() -> None:
    audit = json_file(RESULTS / "issue_creation_cutoff_audit_20260719.json")
    equal(audit["audit"], "target_issue_creation_cutoff", "issue-cutoff audit kind")
    summary = audit["summary"]
    equal(summary["dataset_instances"], 500, "issue-cutoff dataset population")
    equal(summary["archived_runs"], 500, "issue-cutoff run population")
    equal(summary["matching_target_issue_cutoffs"], 500, "matching issue cutoffs")
    for field in ("mismatched_cutoffs", "missing_cutoffs", "missing_runs", "unexpected_runs"):
        equal(summary[field], 0, f"issue-cutoff {field}")
    for field in (
        "cutoff_mismatches", "missing_cutoff_instances", "missing_run_instances", "unexpected_run_instances"
    ):
        equal(audit[field], [], f"issue-cutoff {field}")


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
    equal(
        sum(item["file_target_count"] == 0 and item["entity_target_count"] > 0 for item in items.values()),
        349,
        "entity-only instances",
    )
    equal(
        sum(item["file_target_count"] > 0 and item["entity_target_count"] == 0 for item in items.values()),
        30,
        "file-only instances",
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

    profile = rows("paper_dataset_profile_20260722.tsv")
    observed_profile = {
        (row["category"], row["item"]): int(row["count"])
        for row in profile
    }
    expected_profile = {
        ("population", "instances"): 500,
        ("targets", "total"): 1044,
        ("target_type", "function"): 836,
        ("target_type", "assignment"): 32,
        ("target_type", "file_fallback"): 176,
        ("target_stratum", "entity_only"): 349,
        ("target_stratum", "mixed"): 121,
        ("target_stratum", "file_only"): 30,
        ("target_multiplicity", "single"): 319,
        ("target_multiplicity", "multi"): 181,
        ("file_fallback", "instances_with_file_fallback"): 151,
    }
    equal(observed_profile, expected_profile, "paper dataset profile")
    equal(
        {row["source_ledger"] for row in profile},
        {"artifacts/results/strict_reference_targets_20260719.json"},
        "paper dataset profile source",
    )
    return data


def check_localization() -> None:
    summary = rows("strict_localization_summary_20260719.tsv")
    equal(len(summary), 13, "strict localization rows")
    expected_glm = {
        "GLM5": (87.4, 54.306883, 55.257309, 66.6, 45.0),
        "GLM5_BM25": (94.2, 68.470043, 57.958244, 79.0, 59.4),
        "GLM5_MURAL2": (94.6, 69.881840, 58.501354, 79.2, 61.4),
        "GLM5_MURAL": (95.2, 69.805996, 58.511191, 79.8, 61.2),
    }
    for approach, values in expected_glm.items():
        row = one(summary, approach=approach)
        equal(int(row["N"]), 500, f"{approach} N")
        for field, value in zip(("file_hit", "target_coverage", "mrr", "hit", "complete"), values):
            close(row[field], value, f"{approach} {field}")

    paper = rows("paper_main_results_20260722.tsv")
    expected_mapping = [
        ("BM25 entities", "BM25_entities"),
        ("BM25 projection", "BM25_projection"),
        ("Dense projection", "Dense_projection"),
        ("BLUiR", "BLUiR"),
        ("CodeGraph", "CodeGraph"),
        ("Structural entities", "Structural_entities"),
        ("Structural adapter", "Structural_adapter"),
        ("MURAL w/o Dense", "MURAL_2src"),
        ("MURAL", "MURAL"),
    ]
    equal(
        [(row["paper_label"], row["source_approach"]) for row in paper],
        expected_mapping,
        "paper main-result row mapping",
    )
    equal(
        {row["approach"] for row in summary},
        {source for _, source in expected_mapping} | set(expected_glm),
        "strict localization approach inventory",
    )
    metric_mapping = {
        "file_hit": "file_hit",
        "target_coverage": "target_coverage",
        "mrr": "mrr",
        "hit_at_20": "hit",
        "ref_complete": "complete",
    }
    for paper_row in paper:
        approach = paper_row["source_approach"]
        strict_row = one(summary, approach=approach)
        equal(int(paper_row["N"]), int(strict_row["N"]), f"{approach} paper N")
        equal(int(paper_row["top_k"]), int(strict_row["top_k"]), f"{approach} paper Top-K")
        equal(
            paper_row["source_ledger"],
            "artifacts/results/strict_localization_summary_20260719.tsv",
            f"{approach} paper source ledger",
        )
        for paper_field, strict_field in metric_mapping.items():
            rounded = float(f'{float(strict_row[strict_field]):.1f}')
            close(paper_row[paper_field], rounded, f"{approach} paper {paper_field}")

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


def check_stratified_findings() -> None:
    mechanisms = rows("strict_mechanism_analysis_20260719.tsv")
    equal(len(mechanisms), 4, "mechanism-analysis rows")
    expected_opportunity = {
        "target_coverage": (69.978632, 74.928775, 4.950142, 1.231061, 6.269592, None),
        "hit": (72.222222, 76.923077, 4.700855, 1.234568, 6.140473, (12, 1, 0.00341796875)),
        "complete": (67.948718, 73.076923, 5.128205, 1.030665, 6.756757, (13, 1, 0.0018310546875)),
    }
    for metric, values in expected_opportunity.items():
        row = one(
            mechanisms,
            analysis="opportunity_matched",
            stratum="single_file_entity_only_both_file_hit",
            metric=metric,
        )
        equal(int(row["N"]), 234, f"opportunity {metric} N")
        for field, value in zip(
            ("baseline", "treatment", "delta", "clustered_ci_low", "clustered_ci_high"),
            values[:5],
        ):
            close(row[field], value, f"opportunity {metric} {field}")
        binary = values[5]
        if binary is not None:
            wins, losses, p = binary
            equal(int(row["wins"]), wins, f"opportunity {metric} wins")
            equal(int(row["losses"]), losses, f"opportunity {metric} losses")
            close(row["exact_p"], p, f"opportunity {metric} p", 1e-12)

    rank = one(mechanisms, analysis="shared_hit_rank_shift", stratum="both_hit", metric="first_rank")
    equal(int(rank["N"]), 283, "shared-hit rank N")
    for field, value in {
        "baseline": 4.346290,
        "treatment": 3.593640,
        "delta": -0.752650,
        "clustered_ci_low": -1.170910,
        "clustered_ci_high": -0.053186,
    }.items():
        close(rank[field], value, f"shared-hit rank {field}")
    for field, value in {"wins": 102, "ties": 151, "losses": 30}.items():
        equal(int(rank[field]), value, f"shared-hit rank {field}")
    close(rank["exact_p"], 2.25726725605e-10, "shared-hit rank p", 1e-16)

    multiplicity = rows("strict_target_multiplicity_20260719.tsv")
    equal(len(multiplicity), 4, "target-multiplicity rows")
    expected_multiplicity = {
        "1": (319, 61.128527, 61.128527, 0, 100.0),
        "2": (86, 76.744186, 51.162791, 22, 66.666667),
        "3+": (95, 78.947368, 9.473684, 66, 12.0),
        "2+": (181, 77.900552, 29.281768, 88, 37.588652),
    }
    for group, (n, hit, complete, partial, conditional) in expected_multiplicity.items():
        row = one(multiplicity, target_count=group)
        equal(int(row["N"]), n, f"multiplicity {group} N")
        close(row["hit"], hit, f"multiplicity {group} Hit")
        close(row["complete"], complete, f"multiplicity {group} Complete")
        equal(int(row["partial_hits"]), partial, f"multiplicity {group} partial hits")
        close(row["complete_given_hit"], conditional, f"multiplicity {group} conditional complete")

    repositories = rows("strict_repository_robustness_20260719.tsv")
    equal(len(repositories), 24, "repository-robustness rows")
    direct = [row for row in repositories if row["analysis"] == "repository"]
    leave_one_out = [row for row in repositories if row["analysis"] == "leave_one_repository_out"]
    equal(len(direct), 12, "repository direct rows")
    equal(len(leave_one_out), 12, "leave-one-repository-out rows")
    equal(sum(float(row["delta_hit"]) > 0 for row in direct), 8, "positive repository Hit deltas")
    equal(sum(float(row["delta_hit"]) < 0 for row in direct), 0, "negative repository Hit deltas")
    close(min(float(row["delta_hit"]) for row in leave_one_out), 8.550186, "minimum leave-one-out Hit delta")
    close(max(float(row["delta_hit"]) for row in leave_one_out), 9.771310, "maximum leave-one-out Hit delta")

    human = rows("human_window_unique_strict_summary_20260719.tsv")
    expected_human = {"aligned": 40, "neutral": 4, "opposed": 3, "no_consensus": 2}
    for decision, count in expected_human.items():
        row = one(human, scope="unique_exclusive_hit_instances", decision=decision)
        equal(int(row["count"]), count, f"unique strict human {decision}")
        equal(int(row["denominator"]), 49, f"unique strict human {decision} denominator")
    directional = one(human, scope="directional_unique_instances", decision="aligned")
    equal(int(directional["count"]), 40, "directional strict alignment")
    equal(int(directional["denominator"]), 43, "directional strict denominator")
    close(directional["share"], 0.930233, "directional strict share")
    close(directional["exact_p"], 3.02134139929e-09, "directional strict p", 1e-15)



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
    paper = {
        row["source_approach"]: row
        for row in rows("paper_main_results_20260722.tsv")
    }
    paper_fields = {
        "file_hit": "file_hit",
        "target_coverage": "target_coverage",
        "mrr": "mrr",
        "hit": "hit_at_20",
        "complete": "ref_complete",
    }
    for source, metrics in source_metrics.items():
        ledger = one(summary, approach=source)
        for field in ("file_hit", "target_coverage", "mrr", "hit", "complete"):
            observed = 100 * sum(float(item[field]) for item in metrics) / len(metrics)
            close(observed, float(ledger[field]), f"frozen {source} {field}", 1e-5)
            rounded = float(f"{observed:.1f}")
            close(rounded, float(paper[source][paper_fields[field]]), f"frozen {source} paper {field}")


def check_architecture_and_line_coverage() -> None:
    ordering = rows("entity_ordering_control_summary_20260721.tsv")
    equal(len(ordering), 2, "entity-ordering summary rows")
    expected_ordering = {
        "FilePrimary": (64.8, 46.136955, 30.406252, 54.0, 39.6),
        "EntityPrimary": (73.6, 49.276162, 31.095705, 57.8, 42.2),
    }
    for approach, values in expected_ordering.items():
        row = one(ordering, approach=approach)
        equal(int(row["N"]), 500, f"{approach} ordering N")
        for field, value in zip(
            ("file_hit", "target_coverage", "mrr", "hit", "complete"), values
        ):
            close(row[field], value, f"{approach} ordering {field}")

    row = pair(
        "entity_ordering_control_paired_20260721.tsv",
        "FilePrimary",
        "EntityPrimary",
        "hit",
    )
    close(row["delta"], 3.8, "entity-primary Hit delta")
    close(row["clustered_ci_low"], 0.751833, "entity-primary Hit low")
    close(row["clustered_ci_high"], 5.560033, "entity-primary Hit high")
    equal(int(row["wins"]), 40, "entity-primary Hit wins")
    equal(int(row["losses"]), 21, "entity-primary Hit losses")
    close(row["mcnemar_p"], 0.0204147137996, "entity-primary Hit p", 1e-12)

    architecture = rows("architecture_control_summary_20260721.tsv")
    equal(len(architecture), 3, "architecture-control summary rows")
    expected_architecture = {
        "FileFusionProjection": (84.4, 55.090216, 33.934454, 64.6, 46.8),
        "ProjectedEntityRRF": (82.2, 55.947035, 37.423157, 65.4, 47.8),
        "MURAL": (83.0, 57.588463, 37.950833, 67.2, 49.6),
    }
    for approach, values in expected_architecture.items():
        row = one(architecture, approach=approach)
        equal(int(row["N"]), 500, f"{approach} architecture N")
        for field, value in zip(
            ("file_hit", "target_coverage", "mrr", "hit", "complete"), values
        ):
            close(row[field], value, f"{approach} architecture {field}")

    fusion_hit = pair(
        "architecture_control_paired_20260721.tsv",
        "FileFusionProjection",
        "ProjectedEntityRRF",
        "hit",
    )
    close(fusion_hit["delta"], 0.8, "entity-level fusion Hit delta")
    close(fusion_hit["mcnemar_p"], 0.658738077024, "entity-level fusion Hit p")
    fusion_mrr = pair(
        "architecture_control_paired_20260721.tsv",
        "FileFusionProjection",
        "ProjectedEntityRRF",
        "mrr",
    )
    close(fusion_mrr["delta"], 3.488703, "entity-level fusion MRR delta")
    native_hit = pair(
        "architecture_control_paired_20260721.tsv",
        "ProjectedEntityRRF",
        "MURAL",
        "hit",
    )
    close(native_hit["delta"], 1.8, "native structural Hit delta")
    close(native_hit["mcnemar_p"], 0.00390625, "native structural Hit p")

    ranking_path = FROZEN / "architecture_control_rankings_20260721.jsonl.gz"
    ranking_hash = hashlib.sha256(ranking_path.read_bytes()).hexdigest()
    equal(
        ranking_hash,
        "332a3dd430b033320ef5104a7316e43b6a40e353b6e8ff270cf02d5e69a5499e",
        "architecture ranking SHA-256",
    )
    control_manifest = json_file(
        FROZEN / "architecture_control_manifest_20260721.json"
    )
    equal(control_manifest["rankings"]["sha256"], ranking_hash, "architecture manifest hash")
    equal(control_manifest["population"], 500, "architecture manifest population")
    expected_sources = {"FilePrimary", "FileFusionProjection", "ProjectedEntityRRF"}
    seen: set[str] = set()
    with gzip.open(ranking_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            seen.add(item["instance_id"])
            equal(set(item["sources"]), expected_sources, "architecture ranking sources")
            equal(int(item["top_k"]), 20, "architecture ranking Top-K")
            for candidates in item["sources"].values():
                equal(len(candidates), 20, "architecture ranking candidate count")
    equal(len(seen), 500, "architecture ranking population")

    line_summary = rows("line_coverage_summary_4000_20260721.tsv")
    equal(len(line_summary), 2, "line-coverage summary rows")
    expected_lines = {
        "BM25": (0.2568409645082633, 0.194, 0.2725600519368102),
        "MURAL": (0.31373611487401787, 0.232, 0.23050986001839174),
    }
    for source, values in expected_lines.items():
        row = one(line_summary, source=source)
        equal(int(row["N"]), 500, f"{source} line-coverage N")
        close(row["changed_line_recall"], values[0], f"{source} changed-line recall")
        close(row["complete_changed_line_rate"], values[1], f"{source} CompleteLine")
        close(row["truncated_entity_rate"], values[2], f"{source} truncation rate")

    strata = rows("reference_coverage_strata_4000_20260721.tsv")
    equal(len(strata), 6, "reference-coverage stratum rows")
    entity_only = one(strata, approach="MURAL", stratum="entity-only")
    close(entity_only["entity_target_coverage"], 57.1698048847046, "MURAL entity-only EntityCov")
    close(entity_only["complete_entity"], 54.154727793696274, "MURAL entity-only EntityComplete")
    mixed = one(strata, approach="MURAL", stratum="mixed")
    close(mixed["changed_line_recall"], 26.801922050186867, "MURAL mixed LineRecall")
    file_only = one(strata, approach="MURAL", stratum="file-only")
    close(file_only["changed_line_recall"], 6.779661016949152, "MURAL file-only LineRecall")


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

    annotations = rows("human_window_annotations_20260718.tsv")
    equal(len(annotations), 100, "human annotation rows")
    equal(Counter(row["annotator"] for row in annotations), Counter({"A": 50, "B": 50}), "human annotator rows")
    provenance = rows("human_window_provenance_20260718.tsv")
    expected_sources = {
        "annotator_A": ("55aa81725343df92dda7e2d203932a994ef95a46f7441186cc8b67f70c14d640", 50),
        "annotator_B": ("29cc124822aad02b5c4267191724ce99ed8d5e45379be80ae853ab4f16fa0f77", 50),
    }
    equal(len(provenance), 2, "human source-workbook rows")
    for source_role, (digest, task_rows) in expected_sources.items():
        row = one(provenance, source_role=source_role)
        equal(row["sha256"], digest, f"{source_role} workbook hash")
        equal(int(row["task_c_rows"]), task_rows, f"{source_role} Task-C rows")

    human = rows("human_window_summary_20260718.tsv")
    expected_decisions = {"MURAL": 54, "BM25-local": 19, "Comparable": 15, "Both insufficient": 12}
    for decision, count in expected_decisions.items():
        row = one(human, scope="all_judgments", category=decision)
        equal(int(row["count"]), count, f"human decision {decision}")
    agreement = rows("human_window_agreement_20260718.tsv")[0]
    equal(int(agreement["overlap_n"]), 20, "human overlap")
    equal(int(agreement["agreement_n"]), 12, "human agreement")
    close(agreement["cohen_kappa"], 0.4666666666666666, "human kappa")

    audit_manifest = json_file(FROZEN / "human_window_rankings_manifest_20260719.json")
    audit_rankings = FROZEN / "human_window_rankings_20260712.jsonl.gz"
    equal(audit_manifest["audited_instances"], 80, "frozen human-audit items")
    equal(
        audit_manifest["main_experiment"]["configurations"],
        ["BM25_projection", "MURAL_2src"],
        "human-audit main comparison",
    )
    equal(
        audit_manifest["method_mapping"],
        {
            "BM25-local": "BM25_projection",
            "MURAL": "MURAL_2src (paper label: MURAL w/o Dense)",
        },
        "human-audit method mapping",
    )
    equal(
        hashlib.sha256(audit_rankings.read_bytes()).hexdigest(),
        audit_manifest["rankings"]["sha256"],
        "frozen human-audit ranking hash",
    )
    spec = importlib.util.spec_from_file_location(
        "human_window_binding", ROOT / "artifacts" / "scripts" / "verify_human_window_binding.py"
    )
    if spec is None or spec.loader is None:
        fail("cannot import human-window binding verifier")
    binding_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(binding_module)
    payload = json_file(RESULTS / "human_window_items_20260718.json")
    computed_binding = binding_module.verify(
        payload, binding_module.read_rankings(audit_rankings)
    )
    stored_binding = rows("human_window_binding_20260719.tsv")
    equal(len(computed_binding), 80, "computed human-window bindings")
    equal(len(stored_binding), 80, "stored human-window bindings")
    for computed, stored in zip(computed_binding, stored_binding):
        for field in stored:
            equal(str(computed[field]), stored[field], f"human binding {stored['annotation_id']} {field}")

    exact_windows = rows("human_window_exact_instances_20260719.tsv")
    equal(len(exact_windows), 160, "exact audited window rows")
    equal(
        Counter(row["approach"] for row in exact_windows),
        Counter({"MURAL": 80, "BM25-local": 80}),
        "exact audited window approaches",
    )
    strict = rows("human_window_strict_summary_20260719.tsv")
    for stratum, count in {"MURAL_only": 37, "BM25_only": 12, "both": 18, "neither": 13}.items():
        row = one(strict, scope="unique_instances", strict_stratum=stratum, decision="instances")
        equal(int(row["count"]), count, f"strict human stratum {stratum}")
    for decision, count in {"aligned": 48, "neutral": 7, "opposed": 4}.items():
        row = one(
            strict,
            scope="exclusive_hit_judgments",
            strict_stratum="MURAL_only_or_BM25_only",
            decision=decision,
        )
        equal(int(row["count"]), count, f"exclusive judgment {decision}")


def check_human_evidence_audit() -> None:
    construct_raw = rows("human_construct_annotations_raw_20260721.tsv")
    equal(len(construct_raw), 80, "construct-audit judgments")
    equal(Counter(row["annotator"] for row in construct_raw), Counter({"A": 40, "B": 40}), "construct annotators")
    construct_counts = Counter(row["annotation_id"] for row in construct_raw)
    equal(len(construct_counts), 60, "construct unique items")
    equal(Counter(construct_counts.values()), Counter({1: 40, 2: 20}), "construct coding multiplicity")
    shared_construct = [
        [row for row in construct_raw if row["annotation_id"] == annotation_id]
        for annotation_id, count in construct_counts.items()
        if count == 2
    ]
    equal(sum(pair[0]["mapping_label"] == pair[1]["mapping_label"] for pair in shared_construct), 10, "construct mapping agreement")
    equal(sum(pair[0]["extra_entity"] == pair[1]["extra_entity"] for pair in shared_construct), 16, "construct extra-entity agreement")

    construct_final = rows("human_construct_adjudicated_20260721.tsv")
    equal(len(construct_final), 60, "construct adjudicated items")
    equal(Counter(row["final_coverage"] for row in construct_final), Counter({"covered": 60}), "construct final coverage")
    equal(sum(int(row["unmatched_regions"]) for row in construct_final), 0, "construct unmatched regions")
    equal(sum(int(row["fallback_regions"]) == 0 for row in construct_final), 26, "construct exact-only instances")
    equal(sum(int(row["fallback_regions"]) > 0 for row in construct_final), 34, "construct fallback instances")

    support_raw = rows("human_support_annotations_raw_20260721.tsv")
    equal(len(support_raw), 120, "support-audit judgments")
    equal(Counter(row["annotator"] for row in support_raw), Counter({"A": 60, "B": 60}), "support annotators")
    support_counts = Counter(row["annotation_id"] for row in support_raw)
    equal(len(support_counts), 100, "support unique pairs")
    equal(Counter(support_counts.values()), Counter({1: 80, 2: 20}), "support coding multiplicity")
    shared_support = [
        [row for row in support_raw if row["annotation_id"] == annotation_id]
        for annotation_id, count in support_counts.items()
        if count == 2
    ]
    equal(sum(pair[0]["support_role"] == pair[1]["support_role"] for pair in shared_support), 0, "support role agreement")
    equal(sum(pair[0]["exact_receiver"] == pair[1]["exact_receiver"] for pair in shared_support), 11, "support receiver agreement")

    support_final = rows("human_support_adjudicated_20260721.tsv")
    equal(len(support_final), 100, "support adjudicated pairs")
    equal(
        Counter(row["final_role"] for row in support_final),
        Counter({"irrelevant": 68, "weak": 18, "strong": 12, "required": 2}),
        "support adjudicated roles",
    )
    provenance = rows("human_evidence_audit_provenance_20260721.tsv")
    equal(len(provenance), 2, "evidence-audit provenance rows")
    expected_hashes = {
        "A": "95da3addff52a896a565aec051e6d9bc42c8dfa2d56458eacd207d2b12c9b005",
        "B": "dc14e96c117c37e63a2dfb136ab839e33baf23042fcc53d0861ae1b0d1a5e06e",
    }
    for annotator, digest in expected_hashes.items():
        row = one(provenance, annotator=annotator)
        equal(row["source_sha256"], digest, f"evidence-audit {annotator} workbook hash")
        equal(int(row["source_rows"]), 100, f"evidence-audit {annotator} source rows")


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
    equal(manifest["schema_version"], 3, "manifest schema")
    equal(
        manifest["paper"]["title"],
        "MURAL: Multi-Source Retrieval-to-Entity Context Construction for Repository Repair",
        "manifest paper title",
    )
    equal(
        manifest["architecture_controls"]["manifest"],
        "artifacts/frozen/architecture_control_manifest_20260721.json",
        "manifest architecture controls",
    )
    equal(
        manifest["rendered_coverage"]["line_metrics"],
        ["LineRecall", "CompleteLine"],
        "manifest line metrics",
    )
    equal(
        manifest["human_audit"]["audit_scope"],
        "patch-grounded target consistency",
        "manifest human audit scope",
    )
    equal(manifest["python_benchmark"]["instances"], 500, "manifest Python population")
    equal(
        manifest["paper_ledgers"]["dataset_profile"],
        "artifacts/results/paper_dataset_profile_20260722.tsv",
        "manifest paper dataset profile",
    )
    equal(
        manifest["paper_ledgers"]["main_results"],
        "artifacts/results/paper_main_results_20260722.tsv",
        "manifest paper main results",
    )
    equal(
        manifest["paper_ledgers"]["generator"],
        "artifacts/scripts/build_paper_ledgers.py",
        "manifest paper ledger generator",
    )
    equal(manifest["strict_reference"]["target_counts"]["total"], 1044, "manifest target count")
    equal(manifest["java_benchmark"]["evaluated_instances"], 91, "manifest Java population")
    equal(manifest["repair"]["prompt_hash_rows"], 1000, "manifest prompt hashes")
    equal(manifest["repair"]["model"], "GLM-5", "manifest repair model")
    equal(manifest["human_audit"]["judgments"], 100, "manifest human judgments")
    equal(
        manifest["human_audit"]["window_rankings"],
        "artifacts/frozen/human_window_rankings_20260712.jsonl.gz",
        "manifest human ranking snapshot",
    )
    equal(
        manifest["human_audit"]["configurations"]["MURAL"],
        "MURAL_2src (paper label: MURAL w/o Dense)",
        "manifest human MURAL mapping",
    )
    equal(
        manifest["human_audit"]["source_workbook_provenance"],
        "artifacts/results/human_window_provenance_20260718.tsv",
        "manifest human source provenance",
    )
    equal(manifest["human_audit"]["construct_audit"]["judgments"], 80, "manifest construct judgments")
    equal(manifest["human_audit"]["construct_audit"]["covered_instances"], 60, "manifest construct coverage")
    equal(manifest["human_audit"]["support_role_audit"]["judgments"], 120, "manifest support judgments")
    equal(manifest["human_audit"]["support_role_audit"]["strong_or_required"], 14, "manifest strong support")
    equal(
        manifest["human_audit"]["evidence_audit_provenance"],
        "artifacts/results/human_evidence_audit_provenance_20260721.tsv",
        "manifest evidence-audit provenance",
    )
    equal(manifest["annotation_snapshot"], "2026-07-21", "manifest annotation snapshot")
    equal(manifest["structural_temporal_boundary"]["cutoff"], "target issue created_at", "manifest issue cutoff")
    equal(
        manifest["structural_temporal_boundary"]["audit"],
        "artifacts/results/issue_creation_cutoff_audit_20260719.json",
        "manifest issue-cutoff audit",
    )
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
        if name == "human_window_exact_instances_20260719.tsv":
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
    check_issue_creation_cutoff()
    targets = check_targets()
    check_localization()
    check_stratified_findings()
    check_frozen_rankings(targets)
    check_architecture_and_line_coverage()
    check_token_budgets()
    check_controls_and_budgets()
    check_external()
    check_prompts_and_human()
    check_human_evidence_audit()
    check_repair()
    check_java_and_cost()
    check_removed_terms()
    check_manifest()
    print("MURAL paper artifact verification passed.")


if __name__ == "__main__":
    main()
