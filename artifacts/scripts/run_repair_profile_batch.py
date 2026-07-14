#!/usr/bin/env python3
"""Run one explicit repair-context profile over frozen location files.

The runner is intentionally sequential because every invocation checks out the
same repository worktree before applying a candidate patch. It records the
exact command configuration and a per-instance audit ledger for resumable runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    artifact_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument(
        "--variants", nargs="+", default=["issue", "bm25", "mural"]
    )
    parser.add_argument("--preset", required=True)
    parser.add_argument("--round-tag", default="_base")
    parser.add_argument("--playground-dir", required=True, type=Path)
    parser.add_argument("--dataset-file", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=artifact_root)
    parser.add_argument("--model", default="glm-5")
    parser.add_argument(
        "--base-url",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    parser.add_argument("--api-key-env", default="DASHSCOPE_API_KEY")
    parser.add_argument(
        "--extra-body-json",
        help="Additional frozen OpenAI-compatible generation options as JSON.",
    )
    thinking = parser.add_mutually_exclusive_group()
    thinking.add_argument(
        "--disable-thinking",
        dest="disable_thinking",
        action="store_true",
        help="Pass enable_thinking=false without shell-quoting JSON.",
    )
    thinking.add_argument(
        "--enable-thinking",
        dest="disable_thinking",
        action="store_false",
        help="Enable provider-side thinking for non-protocol experiments.",
    )
    parser.set_defaults(disable_thinking=True)
    parser.add_argument(
        "--repetition-penalty",
        type=float,
        help="Pass a repetition penalty without shell-quoting JSON.",
    )
    parser.add_argument(
        "--first-prompt-profile",
        choices=["auto", "ultra", "compact", "breadth", "full"],
        default="compact",
    )
    parser.add_argument("--prompt-token-limit", type=int, default=5000)
    parser.add_argument("--completion-max-tokens", type=int, default=2048)
    parser.add_argument(
        "--response-prefill", choices=["on", "off"], default="off"
    )
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def load_ids(path: Path) -> list[str]:
    ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    ids = [instance_id for instance_id in ids if instance_id and not instance_id.startswith("#")]
    if not ids:
        raise ValueError(f"No instance ids in {path}")
    return list(dict.fromkeys(ids))


def build_extra_body(args: argparse.Namespace) -> dict[str, object]:
    extra_body: dict[str, object] = {}
    if args.extra_body_json:
        try:
            parsed = json.loads(args.extra_body_json)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid --extra-body-json: {error}") from error
        if not isinstance(parsed, dict):
            raise ValueError("--extra-body-json must decode to an object")
        extra_body.update(parsed)
    if args.disable_thinking:
        extra_body["enable_thinking"] = False
    if args.repetition_penalty is not None:
        extra_body["repetition_penalty"] = args.repetition_penalty
    return extra_body


def read_audit(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_summary(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "instance_id",
        "variant",
        "returncode",
        "elapsed_seconds",
        "first_prompt_profile",
        "context_profile_version",
        "candidate_entity_count",
        "candidate_file_count",
        "candidate_class_scope_count",
        "first_prompt_rendered_entity_count",
        "first_prompt_source_entity_count",
        "first_prompt_tokens",
        "first_attempt_status",
        "retry_count",
        "final_status",
        "applied_file_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    extra_body = build_extra_body(args)
    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    playground_dir = args.playground_dir.resolve()
    dataset_file = args.dataset_file.resolve()
    source_root = args.source_root.resolve()
    repair_script = source_root / "kgcompass" / "repair_claude.py"
    instance_ids = load_ids(args.ids_file.resolve())

    output_root.mkdir(parents=True, exist_ok=True)
    configuration = {
        "input_root": str(input_root),
        "ids_file": str(args.ids_file.resolve()),
        "dataset_file": str(dataset_file),
        "instance_ids": instance_ids,
        "variants": args.variants,
        "preset": args.preset,
        "round_tag": args.round_tag,
        "model": args.model,
        "base_url": args.base_url,
        "generation_extra_body": extra_body,
        "first_prompt_profile": args.first_prompt_profile,
        "prompt_token_limit": args.prompt_token_limit,
        "completion_max_tokens": args.completion_max_tokens,
        "response_prefill": args.response_prefill,
        "max_retries": args.max_retries,
        "temperature": args.temperature,
        "timeout": args.timeout,
        "sequential": True,
    }
    config_path = output_root / "run_config.json"
    if config_path.exists():
        previous = json.loads(config_path.read_text(encoding="utf-8"))
        if previous != configuration:
            raise ValueError(f"Run configuration changed: {config_path}")
    else:
        config_path.write_text(
            json.dumps(configuration, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    environment = {**os.environ}
    if not environment.get(args.api_key_env):
        hostname = (urlparse(args.base_url).hostname or "").lower()
        if hostname in {"127.0.0.1", "localhost", "::1"}:
            environment[args.api_key_env] = "local-vllm"
        else:
            raise EnvironmentError(
                f"{args.api_key_env} is required for remote base URL {args.base_url}"
            )
    if extra_body:
        environment["MURAL_REPAIR_EXTRA_BODY_JSON"] = json.dumps(
            extra_body, sort_keys=True
        )
    else:
        environment.pop("MURAL_REPAIR_EXTRA_BODY_JSON", None)
    rows: list[dict[str, object]] = []
    failures = 0
    total = len(instance_ids) * len(args.variants)
    completed = 0

    for instance_id in instance_ids:
        repo_identifier = instance_id.rsplit("-", 1)[0]
        for variant in args.variants:
            completed += 1
            source_location = (
                input_root
                / variant
                / args.preset
                / args.round_tag
                / instance_id
                / "final_locations"
                / f"{instance_id}.json"
            )
            if not source_location.exists():
                raise FileNotFoundError(source_location)

            run_dir = output_root / variant / instance_id
            locations_dir = run_dir / "final_locations"
            patches_dir = run_dir / "patches"
            locations_dir.mkdir(parents=True, exist_ok=True)
            patches_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_location, locations_dir / source_location.name)
            audit_path = patches_dir / f"{instance_id}.run.json"
            log_path = run_dir / "repair.log"

            returncode = 0
            elapsed_seconds: float | str = ""
            if not audit_path.exists():
                command = [
                    sys.executable,
                    str(repair_script),
                    str(locations_dir),
                    "--instance_id",
                    instance_id,
                    "--playground_dir",
                    str(playground_dir),
                    "--repo_identifier",
                    repo_identifier,
                    "--language",
                    "python",
                    "--api_type",
                    "openai_compat",
                    "--temperature",
                    str(args.temperature),
                    "--model",
                    args.model,
                    "--base-url",
                    args.base_url,
                    "--api-key-env",
                    args.api_key_env,
                    "--dataset-file",
                    str(dataset_file),
                    "--first-prompt-profile",
                    args.first_prompt_profile,
                    "--prompt-token-limit",
                    str(args.prompt_token_limit),
                    "--completion-max-tokens",
                    str(args.completion_max_tokens),
                    "--response-prefill",
                    args.response_prefill,
                    "--max-retries",
                    str(args.max_retries),
                ]
                print(
                    f"[repair-profile] {completed}/{total} {variant} {instance_id}",
                    flush=True,
                )
                with log_path.open("w", encoding="utf-8") as log:
                    started = time.monotonic()
                    try:
                        result = subprocess.run(
                            command,
                            cwd=source_root,
                            env=environment,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            timeout=args.timeout,
                            check=False,
                        )
                        returncode = result.returncode
                    except subprocess.TimeoutExpired:
                        returncode = 124
                        log.write(f"\nTimed out after {args.timeout} seconds.\n")
                    elapsed_seconds = round(time.monotonic() - started, 3)

            audit = read_audit(audit_path)
            if returncode != 0 or not audit:
                failures += 1
            rows.append(
                {
                    "instance_id": instance_id,
                    "variant": variant,
                    "returncode": returncode,
                    "elapsed_seconds": elapsed_seconds,
                    "first_prompt_profile": audit.get("first_prompt_profile", ""),
                    "context_profile_version": audit.get(
                        "context_profile_version", ""
                    ),
                    "candidate_entity_count": audit.get("candidate_entity_count", ""),
                    "candidate_file_count": audit.get("candidate_file_count", ""),
                    "candidate_class_scope_count": audit.get(
                        "candidate_class_scope_count", ""
                    ),
                    "first_prompt_rendered_entity_count": audit.get(
                        "first_prompt_rendered_entity_count", ""
                    ),
                    "first_prompt_source_entity_count": audit.get(
                        "first_prompt_source_entity_count", ""
                    ),
                    "first_prompt_tokens": audit.get("first_prompt_tokens", ""),
                    "first_attempt_status": audit.get("first_attempt_status", ""),
                    "retry_count": len(audit.get("retry_attempts", [])),
                    "final_status": audit.get("final_status", ""),
                    "applied_file_count": len(audit.get("applied_files", [])),
                }
            )
            write_summary(output_root / "run_summary.tsv", rows)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
