#!/usr/bin/env python3
"""Assemble complete SWE-bench predictions from audited repair-profile runs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--variants", nargs="+", default=["issue", "bm25", "mural"]
    )
    parser.add_argument("--model-prefix", default="glm5_corrected")
    parser.add_argument(
        "--nested-variant",
        action="store_true",
        help="Expect RUN_ROOT/VARIANT/VARIANT/INSTANCE rather than one variant level",
    )
    parser.add_argument(
        "--shards",
        nargs="+",
        help="Optional shard names below each variant; implies a nested variant level",
    )
    parser.add_argument("--expected-dataset-source")
    parser.add_argument(
        "--dataset-label",
        help="Stable ledger label written after validating the real dataset path",
    )
    parser.add_argument("--expected-context-profile")
    parser.add_argument("--expected-max-retries", type=int)
    parser.add_argument("--max-prompt-tokens", type=int)
    parser.add_argument("--require-no-prefill", action="store_true")
    parser.add_argument("--require-thinking-disabled", action="store_true")
    return parser.parse_args()


def load_ids(path: Path) -> list[str]:
    values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    values = [value for value in values if value and not value.startswith("#")]
    if not values:
        raise ValueError(f"No instance ids in {path}")
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate instance ids in {path}")
    return values


def read_last_jsonl(path: Path) -> tuple[dict[str, object], int]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"No rows in {path}")
    return rows[-1], len(rows)


def validate_audit(
    audit: dict[str, object], variant: str, instance_id: str, args: argparse.Namespace
) -> None:
    label = f"{variant}/{instance_id}"
    problem_tokens = int(audit.get("problem_statement_tokens") or 0)
    dataset_source = str(audit.get("dataset_source") or "")
    prompt_tokens = int(audit.get("first_prompt_tokens") or 0)
    candidate_count = int(audit.get("candidate_entity_count") or 0)
    rendered_count = int(audit.get("first_prompt_rendered_entity_count") or 0)
    source_count = int(audit.get("first_prompt_source_entity_count") or 0)
    if problem_tokens <= 0 or not dataset_source:
        raise ValueError(f"Missing frozen issue provenance for {label}")
    if prompt_tokens <= 0:
        raise ValueError(f"Missing first-prompt token audit for {label}")
    if min(candidate_count, rendered_count, source_count) < 0:
        raise ValueError(f"Negative context count for {label}")
    if rendered_count > candidate_count or source_count > rendered_count:
        raise ValueError(f"Inconsistent context rendering counts for {label}")

    expected_dataset = getattr(args, "expected_dataset_source", None)
    if expected_dataset and Path(dataset_source).resolve() != Path(expected_dataset).resolve():
        raise ValueError(
            f"Unexpected dataset source for {label}: {dataset_source}"
        )
    expected_profile = getattr(args, "expected_context_profile", None)
    if expected_profile and audit.get("context_profile_version") != expected_profile:
        raise ValueError(
            f"Unexpected context profile for {label}: "
            f"{audit.get('context_profile_version')!r}"
        )
    expected_retries = getattr(args, "expected_max_retries", None)
    if expected_retries is not None and int(audit.get("max_retries") or 0) != expected_retries:
        raise ValueError(
            f"Unexpected retry limit for {label}: {audit.get('max_retries')!r}"
        )
    max_prompt_tokens = getattr(args, "max_prompt_tokens", None)
    if max_prompt_tokens is not None and prompt_tokens > max_prompt_tokens:
        raise ValueError(
            f"Prompt token limit exceeded for {label}: {prompt_tokens}"
        )
    if getattr(args, "require_no_prefill", False) and audit.get("response_prefill"):
        raise ValueError(f"Response prefill enabled for {label}")
    if getattr(args, "require_thinking_disabled", False):
        extra_body = audit.get("generation_extra_body")
        if not isinstance(extra_body, dict) or extra_body.get("enable_thinking") is not False:
            raise ValueError(f"Thinking was not explicitly disabled for {label}")


def main() -> int:
    args = parse_args()
    run_root = args.run_root.resolve()
    output_root = args.output_root.resolve()
    instance_ids = load_ids(args.ids_file.resolve())
    output_root.mkdir(parents=True, exist_ok=True)
    ledger_rows: list[dict[str, object]] = []

    for variant in args.variants:
        predictions: list[dict[str, str]] = []
        for instance_id in instance_ids:
            if args.shards:
                candidates = [
                    run_root / variant / shard / variant / instance_id
                    for shard in args.shards
                ]
                matches = [candidate for candidate in candidates if candidate.exists()]
                if len(matches) != 1:
                    raise ValueError(
                        f"Expected one shard for {variant}/{instance_id}, found {matches}"
                    )
                run_dir = matches[0].parent
            else:
                run_dir = run_root / variant
                if args.nested_variant:
                    run_dir /= variant
            patches_dir = run_dir / instance_id / "patches"
            result_path = patches_dir / "patch_results.jsonl"
            audit_path = patches_dir / f"{instance_id}.run.json"
            if not result_path.exists() or not audit_path.exists():
                raise FileNotFoundError(
                    f"Incomplete {variant}/{instance_id}: {result_path}, {audit_path}"
                )

            result, result_rows = read_last_jsonl(result_path)
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            validate_audit(audit, variant, instance_id, args)
            patch = str(result.get("fix_patch") or "").strip()
            predictions.append(
                {
                    "model_name_or_path": f"{args.model_prefix}_{variant}",
                    "instance_id": instance_id,
                    "model_patch": patch,
                }
            )
            problem_tokens = int(audit.get("problem_statement_tokens") or 0)
            dataset_source = str(audit.get("dataset_source") or "")
            ledger_rows.append(
                {
                    "instance_id": instance_id,
                    "variant": variant,
                    "nonempty": int(bool(patch)),
                    "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest()
                    if patch
                    else "",
                    "result_rows": result_rows,
                    "dataset_source": args.dataset_label or dataset_source,
                    "problem_statement_tokens": problem_tokens,
                    "first_prompt_profile": audit.get("first_prompt_profile", ""),
                    "context_profile_version": audit.get(
                        "context_profile_version", ""
                    ),
                    "response_prefill": int(bool(audit.get("response_prefill"))),
                    "max_retries": audit.get("max_retries", ""),
                    "generation_extra_body": json.dumps(
                        audit.get("generation_extra_body") or {}, sort_keys=True
                    ),
                    "candidate_entity_count": audit.get("candidate_entity_count", 0),
                    "candidate_file_count": audit.get("candidate_file_count", 0),
                    "candidate_class_scope_count": audit.get(
                        "candidate_class_scope_count", 0
                    ),
                    "first_prompt_rendered_entity_count": audit.get(
                        "first_prompt_rendered_entity_count", 0
                    ),
                    "first_prompt_source_entity_count": audit.get(
                        "first_prompt_source_entity_count", 0
                    ),
                    "first_prompt_tokens": audit.get("first_prompt_tokens", 0),
                    "retry_count": len(audit.get("retry_attempts", [])),
                    "final_status": audit.get("final_status", ""),
                    "applied_file_count": len(audit.get("applied_files", [])),
                }
            )

        variant_dir = output_root / variant
        variant_dir.mkdir(parents=True, exist_ok=True)
        prediction_path = variant_dir / "predictions_all.jsonl"
        prediction_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=True) for row in predictions) + "\n",
            encoding="utf-8",
        )

    ledger_path = output_root / "assembly.tsv"
    fields = list(ledger_rows[0])
    with ledger_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(ledger_rows)
    print(f"wrote {ledger_path} ({len(ledger_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
