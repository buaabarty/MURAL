#!/usr/bin/env python3
"""Revalidate archived LLM attempts and select the first applicable patch."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kgcompass"))

from repair_claude import CodeRepair  # noqa: E402


RAW_OUTPUT = re.compile(
    r"--- LLM raw output ---\n(.*?)\n--- End of LLM raw output ---",
    re.DOTALL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--playground-root", type=Path, required=True)
    parser.add_argument("--dataset-file", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--preset", default="local_qwen3coder30b")
    parser.add_argument("--round-tag", default="_base")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    parser.add_argument("--output-predictions", type=Path, required=True)
    return parser.parse_args()


def load_ids(path: Path) -> list[str]:
    result = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            result.append(str(json.loads(line)["instance_id"]) if line.startswith("{") else line)
    return result


def load_dataset(path: Path) -> dict[str, dict]:
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            item = json.loads(raw)
            result[str(item["instance_id"])] = item
    return result


def main() -> int:
    args = parse_args()
    ids = load_ids(args.ids_file)
    dataset = load_dataset(args.dataset_file)
    os.environ.setdefault("OPENAI_API_KEY", "offline-reprocessing")
    repairer = CodeRepair(
        language="python",
        api_type="openai_compat",
        temperature=0.0,
        model_name_override="glm-5.2",
        base_url_override="http://127.0.0.1:1/v1",
        api_key_env="OPENAI_API_KEY",
    )

    ledger = []
    predictions = []
    for instance_id in ids:
        item = dataset[instance_id]
        repo_identifier = instance_id.rsplit("-", 1)[0]
        log_path = args.run_root / args.variant / instance_id / "repair.log"
        locations_dir = (
            args.input_root
            / args.variant
            / args.preset
            / args.round_tag
            / instance_id
            / "final_locations"
        )
        attempts = RAW_OUTPUT.findall(log_path.read_text(encoding="utf-8", errors="replace"))
        instance_out = args.output_root / args.variant / instance_id
        instance_out.mkdir(parents=True, exist_ok=True)

        selected_patch = ""
        selected_attempt = None
        attempted = []
        for index, raw_output in enumerate(attempts, start=1):
            raw_path = instance_out / f"attempt_{index}.txt"
            raw_path.write_text(raw_output.strip() + "\n", encoding="utf-8")
            result = repairer.post_process_and_apply_patch(
                instance_id,
                str(raw_path),
                str(locations_dir),
                playground_dir=str(args.playground_root),
                repo_identifier=repo_identifier,
                repo_name=str(item["repo"]),
                commit_id=str(item["base_commit"]),
            )
            patch = repairer._combine_applied_patches(
                result["processed_patches"],
                result["applied_files"],
            )
            attempted.append(
                {
                    "attempt": index,
                    "applied_files": result["applied_files"],
                    "failed_files": result["failed_files"],
                    "applicable": bool(patch.strip()),
                }
            )
            if patch.strip():
                selected_patch = patch.rstrip() + "\n"
                selected_attempt = index
                break

        audit = {
            "instance_id": instance_id,
            "variant": args.variant,
            "raw_attempt_count": len(attempts),
            "selected_attempt": selected_attempt,
            "applicable": bool(selected_patch),
            "attempts": attempted,
        }
        (instance_out / "reprocess_audit.json").write_text(
            json.dumps(audit, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger.append(
            {
                "instance_id": instance_id,
                "variant": args.variant,
                "raw_attempt_count": len(attempts),
                "selected_attempt": "" if selected_attempt is None else selected_attempt,
                "applicable": int(bool(selected_patch)),
            }
        )
        predictions.append(
            {
                "instance_id": instance_id,
                "model_name_or_path": "glm-5.2",
                "model_patch": selected_patch,
            }
        )

    args.output_ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.output_ledger.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(ledger[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(ledger)
    args.output_predictions.parent.mkdir(parents=True, exist_ok=True)
    args.output_predictions.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    print(
        f"wrote {args.output_ledger} and {args.output_predictions}; "
        f"applicable={sum(row['applicable'] for row in ledger)}/{len(ledger)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
