#!/usr/bin/env python3
"""Audit whether time-ineligible issue/PR paths affect frozen MURAL windows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from entity_identity import canonical_entity_key  # noqa: E402
from export_multi_source_rrf_fusion import fuse_entities  # noqa: E402


HISTORICAL_LABELS = {"issue", "pullrequest", "pull_request", "pr"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    ).timestamp()


def entities(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return list((payload.get("related_entities") or {}).get(key) or [])


def historical_nodes(item: dict[str, Any]) -> set[str]:
    output: set[str] = set()
    for edge in item.get("path_details") or []:
        for side in ("start", "end"):
            node = str(edge.get(f"{side}_node") or "")
            labels = {
                str(label).replace(" ", "").lower()
                for label in (edge.get(f"{side}_labels") or [])
            }
            node_type = str(edge.get(f"{side}_type") or "").lower()
            looks_historical = bool(
                labels & HISTORICAL_LABELS
                or node_type in HISTORICAL_LABELS
                or re.match(r"^(?:issue|pr|pullrequest)#", node, re.IGNORECASE)
            )
            if looks_historical and node.lower() != "root":
                output.add(node)
    return output


def ranked_methods(payload: dict[str, Any]) -> list[dict[str, Any]]:
    methods = entities(payload, "methods")
    if any(isinstance(item.get("similarity"), (int, float)) for item in methods):
        methods.sort(
            key=lambda item: (
                float(item.get("similarity"))
                if isinstance(item.get("similarity"), (int, float))
                else float("-inf")
            ),
            reverse=True,
        )
    return methods


def identity_sequence(rows: list[dict[str, Any]], limit: int) -> list[str]:
    return [canonical_entity_key(item) for item in rows[:limit]]


def content_sequence(rows: list[dict[str, Any]], limit: int) -> list[str]:
    output: list[str] = []
    for item in rows[:limit]:
        source_hash = hashlib.sha256(
            str(item.get("source_code") or "").encode("utf-8")
        ).hexdigest()
        output.append(f"{canonical_entity_key(item)}:{source_hash}")
    return output


def sequence_hash(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def load_selected_counts(path: Path, source: str, budget: int) -> dict[str, int]:
    output: dict[str, int] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("source") == source and int(row["token_budget"]) == budget:
                output[row["instance_id"]] = int(row["selected_entities"])
    return output


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structural-dir", required=True, type=Path)
    parser.add_argument("--bm25-dir", required=True, type=Path)
    parser.add_argument("--dense-dir", required=True, type=Path)
    parser.add_argument("--mural-dir", required=True, type=Path)
    parser.add_argument("--artifact-metadata", required=True, type=Path)
    parser.add_argument("--packing-instances", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--token-budget", type=int, default=4000)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-tsv", required=True, type=Path)
    parser.add_argument("--fail-on-window-change", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    instance_ids = sorted(path.stem for path in args.structural_dir.glob("*.json"))
    selected_counts = load_selected_counts(
        args.packing_instances, "MURAL", args.token_budget
    )
    metadata_rows = load(args.artifact_metadata)["artifacts"]
    metadata = {row["artifact"]: row for row in metadata_rows}
    artifact_instances: dict[str, set[str]] = defaultdict(set)
    instance_rows: list[dict[str, Any]] = []
    observed_history_rows = 0
    filtered_history_rows = 0
    filtered_history_only_identities = 0
    changed_top20 = 0
    changed_top50 = 0
    changed_packed = 0

    for instance_id in instance_ids:
        structural = load(args.structural_dir / f"{instance_id}.json")
        bm25 = load(args.bm25_dir / f"{instance_id}.json")
        dense = load(args.dense_dir / f"{instance_id}.json")
        current = load(args.mural_dir / f"{instance_id}.json")
        cutoff = float(
            ((structural.get("run_meta") or {}).get("active_root") or {})[
                "created_at"
            ]
        )
        filtered: dict[str, list[dict[str, Any]]] = {}
        history_rows = 0
        invalid_rows = 0
        invalid_flags: dict[str, set[bool]] = defaultdict(set)
        instance_artifacts: set[str] = set()
        invalid_artifacts: set[str] = set()

        for key in ("methods", "classes"):
            kept: list[dict[str, Any]] = []
            for item in entities(structural, key):
                nodes = historical_nodes(item)
                history_rows += int(bool(nodes))
                instance_artifacts.update(nodes)
                for node in nodes:
                    artifact_instances[node].add(instance_id)
                invalid_nodes = {
                    node
                    for node in nodes
                    if node not in metadata
                    or timestamp(metadata[node]["created_at"]) > cutoff
                    or timestamp(metadata[node]["last_modified_at"]) > cutoff
                }
                identifier = canonical_entity_key(item)
                invalid_flags[identifier].add(bool(invalid_nodes))
                if invalid_nodes:
                    invalid_rows += 1
                    invalid_artifacts.update(invalid_nodes)
                else:
                    kept.append(item)
            filtered[key] = kept

        history_only = sum(flags == {True} for flags in invalid_flags.values())
        observed_history_rows += history_rows
        filtered_history_rows += invalid_rows
        filtered_history_only_identities += history_only
        strict_methods = fuse_entities(
            [
                ("BM25", entities(bm25, "methods")),
                ("Structural", filtered["methods"]),
                ("Dense", entities(dense, "methods")),
            ],
            {"BM25": 1.0, "Structural": 1.0, "Dense": 1.0},
            60,
            50,
        )
        current_methods = ranked_methods(current)
        top20_equal = identity_sequence(current_methods, args.top_k) == identity_sequence(
            strict_methods, args.top_k
        )
        top50_equal = identity_sequence(current_methods, 50) == identity_sequence(
            strict_methods, 50
        )
        selected = selected_counts.get(instance_id, 0)
        packed_equal = content_sequence(current_methods, selected) == content_sequence(
            strict_methods, selected
        )
        changed_top20 += int(not top20_equal)
        changed_top50 += int(not top50_equal)
        changed_packed += int(not packed_equal)
        instance_rows.append(
            {
                "instance_id": instance_id,
                "cutoff_epoch": cutoff,
                "historical_path_rows": history_rows,
                "time_ineligible_path_rows": invalid_rows,
                "historical_artifacts": ";".join(sorted(instance_artifacts)),
                "time_ineligible_artifacts": ";".join(sorted(invalid_artifacts)),
                "top20_equal_after_strict_filter": int(top20_equal),
                "top50_equal_after_strict_filter": int(top50_equal),
                "packed_entities_4000": selected,
                "packed_4000_equal_after_strict_filter": int(packed_equal),
                "current_top20_sha256": sequence_hash(identity_sequence(current_methods, args.top_k)),
                "strict_top20_sha256": sequence_hash(identity_sequence(strict_methods, args.top_k)),
            }
        )

    artifacts = []
    for artifact, instances in sorted(artifact_instances.items()):
        row = dict(metadata.get(artifact) or {})
        row.update(
            {
                "artifact": artifact,
                "kind": "pull_request" if re.match(r"^(?:pr|pullrequest)#", artifact, re.I) else "issue",
                "instances": sorted(instances),
                "metadata_present": artifact in metadata,
            }
        )
        artifacts.append(row)

    report = {
        "audit": "strict_structural_artifact_time_boundary",
        "policy": (
            "Retain a historical issue or pull request only when both creation and "
            "last-modification times are no later than the target issue cutoff."
        ),
        "configuration": {
            "instances": len(instance_ids),
            "top_k": args.top_k,
            "token_budget": args.token_budget,
            "rrf_k": 60,
            "source_order": ["BM25", "Structural", "Dense"],
        },
        "summary": {
            "instances_with_historical_paths": sum(
                int(row["historical_path_rows"] > 0) for row in instance_rows
            ),
            "unique_historical_artifacts": len(artifacts),
            "historical_issue_artifacts": sum(a["kind"] == "issue" for a in artifacts),
            "historical_pull_request_artifacts": sum(
                a["kind"] == "pull_request" for a in artifacts
            ),
            "artifacts_with_verified_timestamps": sum(
                bool(a["metadata_present"]) for a in artifacts
            ),
            "historical_path_rows_observed": observed_history_rows,
            "time_ineligible_path_rows_removed": filtered_history_rows,
            "time_ineligible_only_entity_identities": filtered_history_only_identities,
            "top20_changed_instances": changed_top20,
            "top50_changed_instances": changed_top50,
            "packed_4000_changed_instances": changed_packed,
        },
        "historical_artifacts": artifacts,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_tsv(args.output_tsv, instance_rows)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    if args.fail_on_window_change and (changed_top20 or changed_packed):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
