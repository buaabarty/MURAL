#!/usr/bin/env python3
"""Resolve ranked entities against base snapshots for repair generation."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--localization-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--round-tag", default="_base")
    parser.add_argument("--dataset-file", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_ids(path: Path) -> list[str]:
    instance_ids: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            line = str(json.loads(line)["instance_id"])
        instance_ids.append(line)
    if not instance_ids:
        raise ValueError(f"No instance ids in {path}")
    return list(dict.fromkeys(instance_ids))


def validate_resolved_context(path: Path, instance_id: str) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    methods = (payload.get("related_entities") or {}).get("methods") or []
    resolved = [
        method
        for method in methods
        if str(method.get("source_code") or "").strip()
    ]
    if len(resolved) != len(methods):
        payload["related_entities"]["methods"] = resolved
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        methods = resolved
    return {
        "resolved_entity_count": len(methods),
        "resolved_file_count": len(
            {str(method.get("file_path")) for method in methods if method.get("file_path")}
        ),
    }


def materialize_one(
    instance_id: str,
    *,
    localization_dir: Path,
    output_root: Path,
    variant: str,
    preset: str,
    round_tag: str,
    dataset_file: Path,
    source_root: Path,
    force: bool,
) -> tuple[str, str, int, int]:
    source = localization_dir / f"{instance_id}.json"
    if not source.exists():
        raise FileNotFoundError(source)

    run_dir = output_root / variant / preset / round_tag / instance_id
    source_dir = run_dir / "source_locations"
    final_dir = run_dir / "final_locations"
    meta_dir = run_dir / "meta"
    source_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    staged_source = source_dir / source.name
    destination = final_dir / source.name

    if destination.exists() and not force:
        counts = validate_resolved_context(destination, instance_id)
        return instance_id, "cached", counts["resolved_entity_count"], counts["resolved_file_count"]

    shutil.copy2(source, staged_source)
    resolver = source_root / "kgcompass" / "fix_fl_line.py"
    environment = {**os.environ, "SWE_BENCH_LOCAL_FILE": str(dataset_file)}
    result = subprocess.run(
        [
            sys.executable,
            str(resolver),
            str(source_dir),
            str(final_dir),
            "--instance_id",
            instance_id,
        ],
        cwd=source_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    (meta_dir / "resolve.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    if result.returncode != 0 or not destination.exists():
        raise RuntimeError(
            f"{instance_id}: context resolution failed with code {result.returncode}"
        )

    counts = validate_resolved_context(destination, instance_id)
    metadata = {
        "dataset_jsonl": str(dataset_file),
        "instance_id": instance_id,
        "localization_source": str(source),
        "preset": preset,
        "resolved_entity_count": counts["resolved_entity_count"],
        "resolved_file_count": counts["resolved_file_count"],
        "source_mode": "ranked_entity_context",
        "variant": variant,
    }
    (meta_dir / "base_run_config.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return instance_id, "written", counts["resolved_entity_count"], counts["resolved_file_count"]


def main() -> int:
    args = parse_args()
    if args.workers <= 0:
        raise ValueError("--workers must be positive")
    localization_dir = args.localization_dir.resolve()
    output_root = args.output_root.resolve()
    dataset_file = args.dataset_file.resolve()
    source_root = args.source_root.resolve()
    instance_ids = load_ids(args.ids_file.resolve())

    rows: list[tuple[str, str, int, int]] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                materialize_one,
                instance_id,
                localization_dir=localization_dir,
                output_root=output_root,
                variant=args.variant,
                preset=args.preset,
                round_tag=args.round_tag,
                dataset_file=dataset_file,
                source_root=source_root,
                force=args.force,
            ): instance_id
            for instance_id in instance_ids
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            instance_id = futures[future]
            try:
                rows.append(future.result())
            except Exception as error:
                failures.append(f"{instance_id}\t{error}")
            if completed % 25 == 0 or completed == len(futures):
                print(
                    f"[repair-context] {completed}/{len(futures)} complete; "
                    f"failures={len(failures)}",
                    flush=True,
                )

    manifest = output_root / f"{args.variant}_context_manifest.tsv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines = ["instance_id\tstatus\tresolved_entity_count\tresolved_file_count"]
    lines.extend("\t".join(map(str, row)) for row in sorted(rows))
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if failures:
        failure_path = output_root / f"{args.variant}_context_failures.tsv"
        failure_path.write_text(
            "instance_id\treason\n" + "\n".join(failures) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {failure_path}", file=sys.stderr)
        return 1
    print(f"wrote {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
