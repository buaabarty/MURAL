#!/usr/bin/env python3
"""Audit which ranked candidates receive source-bearing repair context."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path


ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ARTIFACT_ROOT / "kgcompass"))

from repair_claude import CodeRepair, load_instance_from_dataset  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--dataset-file", required=True, type=Path)
    parser.add_argument("--playground-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--variants", nargs="+", default=["issue", "bm25", "mural"])
    parser.add_argument("--preset", required=True)
    parser.add_argument("--round-tag", default="_base")
    parser.add_argument("--prompt-token-limit", type=int, default=5000)
    return parser.parse_args()


def parse_rendered_blocks(content: str) -> list[tuple[str, bool]]:
    rendered: list[tuple[str, bool]] = []
    for block in re.split(r"(?=^- signature : )", content, flags=re.MULTILINE):
        match = re.match(r"^- signature : (.*)$", block, flags=re.MULTILINE)
        if not match:
            continue
        rendered.append(
            (match.group(1).strip(), "- source_authority :" in block)
        )
    return rendered


def main() -> int:
    args = parse_args()
    ids = []
    for raw_line in args.ids_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            line = str(json.loads(line)["instance_id"])
        ids.append(line)
    os.environ["SWE_BENCH_LOCAL_FILE"] = str(args.dataset_file.resolve())
    os.environ["MURAL_REPAIR_FIRST_PROMPT_PROFILE"] = "compact"
    os.environ["MURAL_REPAIR_PROMPT_TOKEN_LIMIT"] = str(args.prompt_token_limit)
    os.environ["MURAL_REPAIR_RESPONSE_PREFILL"] = "off"
    os.environ.setdefault("OPENAI_API_KEY", "offline-audit")
    repairer = CodeRepair(
        language="python",
        api_type="openai_compat",
        temperature=0.0,
        model_name_override="glm-5.2",
        base_url_override="http://127.0.0.1:1/v1",
        api_key_env="OPENAI_API_KEY",
    )

    rows = []
    for variant in args.variants:
        for instance_id in ids:
            location_path = (
                args.input_root
                / variant
                / args.preset
                / args.round_tag
                / instance_id
                / "final_locations"
                / f"{instance_id}.json"
            )
            location = json.loads(location_path.read_text(encoding="utf-8"))
            dataset = load_instance_from_dataset(instance_id, "swe-bench")
            problem = repairer._build_issue_context(location, dataset).replace("\r", "")
            methods = (location.get("related_entities") or {}).get("methods") or []
            repo_id = instance_id.rsplit("-", 1)[0]
            repo_path = args.playground_root / variant / repo_id
            methods = repairer._enrich_methods_with_file_context(
                methods, str(repo_path), dataset["commit_id"]
            )
            content = repairer._build_compact_repair_context(problem, methods)
            prompt = repairer._get_prompt_template().format(
                problem_statement=problem,
                content=content or "No related code snippets found.",
                file_path_example=repairer.file_path_example,
                language_name=repairer.language_name,
                code_example=repairer.code_example,
                code_block_lang=repairer.code_block_lang,
            )
            rendered = parse_rendered_blocks(content)
            rows.append(
                {
                    "instance_id": instance_id,
                    "variant": variant,
                    "candidate_entities": len(methods),
                    "rendered_entities": len(rendered),
                    "source_entities": sum(source for _, source in rendered),
                    "prefix_source_entities": sum(
                        source for _, source in rendered[:10]
                    ),
                    "tail_source_entities": sum(
                        source for _, source in rendered[10:20]
                    ),
                    "prompt_tokens": repairer.count_tokens(prompt),
                    "context_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.output} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
