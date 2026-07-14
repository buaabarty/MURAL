#!/usr/bin/env python3
"""Partition repair instances while keeping each repository in one shard."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--shards", type=int, default=2)
    return parser.parse_args()


def repository_of(instance_id: str) -> str:
    if "-" not in instance_id:
        raise ValueError(f"Invalid SWE-bench instance id: {instance_id}")
    return instance_id.rsplit("-", 1)[0]


def partition_by_repository(
    instance_ids: list[str], shard_count: int
) -> list[list[str]]:
    if shard_count < 1:
        raise ValueError("shard_count must be positive")
    by_repository: dict[str, list[str]] = defaultdict(list)
    for instance_id in instance_ids:
        by_repository[repository_of(instance_id)].append(instance_id)

    assignments: list[list[str]] = [[] for _ in range(shard_count)]
    sizes = [0] * shard_count
    for repository, repository_ids in sorted(
        by_repository.items(), key=lambda item: (-len(item[1]), item[0])
    ):
        shard = min(range(shard_count), key=lambda index: (sizes[index], index))
        assignments[shard].extend(repository_ids)
        sizes[shard] += len(repository_ids)
    return assignments


def main() -> int:
    args = parse_args()
    instance_ids = [
        line.strip()
        for line in args.ids_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not instance_ids or len(instance_ids) != len(set(instance_ids)):
        raise ValueError("IDs must be nonempty and unique")

    shards = partition_by_repository(instance_ids, args.shards)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "source": str(args.ids_file.resolve()),
        "total_instances": len(instance_ids),
        "shards": [],
    }
    for index, shard_ids in enumerate(shards):
        path = args.output_dir / f"shard_{index}.ids"
        path.write_text("\n".join(shard_ids) + "\n", encoding="utf-8")
        repositories = sorted({repository_of(value) for value in shard_ids})
        manifest["shards"].append(
            {
                "name": f"shard_{index}",
                "path": str(path.resolve()),
                "instances": len(shard_ids),
                "repositories": repositories,
            }
        )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
