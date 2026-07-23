#!/usr/bin/env python3
"""Relate source-visible target completeness to official repair outcomes."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_entity_only_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        instance_id
        for instance_id, item in payload["items"].items()
        if int(item["file_target_count"]) == 0
    }


def summarize(
    prompt_rows: list[dict[str, str]],
    outcome_rows: list[dict[str, str]],
    entity_only_ids: set[str],
) -> list[dict[str, Any]]:
    prompts = {
        (row["instance_id"], row["variant"]): row for row in prompt_rows
    }
    outcomes = {
        (row["instance_id"], row["variant"]): row for row in outcome_rows
    }
    if set(prompts) != set(outcomes):
        missing_prompts = sorted(set(outcomes) - set(prompts))
        missing_outcomes = sorted(set(prompts) - set(outcomes))
        raise ValueError(
            "Prompt/outcome keys differ: "
            f"missing prompts={missing_prompts[:3]}, "
            f"missing outcomes={missing_outcomes[:3]}"
        )

    rows: list[dict[str, Any]] = []
    for variant in sorted({variant for _, variant in prompts}):
        variant_keys = [key for key in prompts if key[1] == variant]
        strata = {
            "all": variant_keys,
            "entity_only": [key for key in variant_keys if key[0] in entity_only_ids],
        }
        for stratum, selected in strata.items():
            for complete in (0, 1):
                keys = [
                    key
                    for key in selected
                    if int(prompts[key]["source_complete"]) == complete
                ]
                resolved = sum(int(outcomes[key]["resolved"]) for key in keys)
                rows.append(
                    {
                        "stratum": stratum,
                        "variant": variant,
                        "source_complete": complete,
                        "N": len(keys),
                        "resolved": resolved,
                        "resolved_rate": 100.0 * resolved / len(keys) if keys else 0.0,
                    }
                )
    return rows


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", required=True, type=Path)
    parser.add_argument("--outcomes", required=True, type=Path)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = summarize(
        read_tsv(args.prompts),
        read_tsv(args.outcomes),
        read_entity_only_ids(args.targets),
    )
    write_tsv(args.output, rows)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
