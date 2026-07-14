#!/usr/bin/env python3
"""Generate Java structural rankings with the frozen diagnostic settings."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


def load_instances(dataset: Path) -> list[str]:
    instance_ids = [
        json.loads(line)["instance_id"]
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return list(dict.fromkeys(instance_ids))


def require_repository(workdir: Path, repos_dir: Path | None, repo_id: str) -> None:
    playground = workdir / "playground"
    playground.mkdir(parents=True, exist_ok=True)
    repository = playground / repo_id
    if repository.exists():
        return
    if repos_dir is None:
        raise FileNotFoundError(
            f"Missing {repository}; provide --repos-dir or create this checkout"
        )
    source = (repos_dir / repo_id).resolve()
    if not (source / ".git").exists():
        raise FileNotFoundError(f"Missing Git repository: {source}")
    repository.symlink_to(source, target_is_directory=True)


def service_address(environment: dict[str, str]) -> tuple[str, int]:
    uri = urlparse(environment.get("NEO4J_URI", "bolt://127.0.0.1:7687"))
    return uri.hostname or "127.0.0.1", uri.port or 7687


def wait_for_service(host: str, port: int, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError as error:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Neo4j is unavailable at {host}:{port}") from error
            time.sleep(5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    artifact_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--repos-dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--log-dir", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=artifact_root)
    parser.add_argument("--entity-depth", type=int, default=50)
    parser.add_argument("--result-limit", type=int, default=200)
    parser.add_argument("--reference-workers", type=int, default=4)
    parser.add_argument("--embedding-cache", type=Path)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--service-timeout", type=int, default=900)
    parser.add_argument("--enable-method-call-expansion", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = args.dataset.resolve()
    workdir = args.workdir.resolve()
    repos_dir = args.repos_dir.resolve() if args.repos_dir else None
    output_dir = args.output_dir.resolve()
    log_dir = args.log_dir.resolve()
    source_root = args.source_root.resolve()
    runner = Path(__file__).resolve().with_name("run_java_kg_depth.py")
    instance_ids = load_instances(dataset)
    if not instance_ids:
        raise ValueError(f"No instances found in {dataset}")

    workdir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "KGCOMPASS_MULTI_SWE_BENCH_FILE": str(dataset),
        "KGCOMPASS_RESULT_LIMIT": str(args.result_limit),
        "KGCOMPASS_ENABLE_METHOD_CALL_EXPANSION": (
            "1" if args.enable_method_call_expansion else "0"
        ),
        "KGCOMPASS_EXPAND_PATCH_LINKS": "0",
        "KGCOMPASS_USE_TIMELINE": "0",
        "KGCOMPASS_STRICT_IDENTIFIER_FILTER": "1",
        "KGCOMPASS_NAME_SEARCH_STRICT": "1",
        "KGCOMPASS_SOURCE_EXTENSIONS": ".java",
        "KGCOMPASS_REFERENCE_WORKERS": str(args.reference_workers),
        "FL_SCAN_EXCLUDE_NONPROD_CONTEXT": "1",
    }
    if args.embedding_cache:
        environment["KGCOMPASS_EMBEDDING_CACHE"] = str(args.embedding_cache.resolve())
    host, port = service_address(environment)

    failures: list[str] = []
    for index, instance_id in enumerate(instance_ids, start=1):
        output = output_dir / f"{instance_id}.json"
        if output.exists():
            print(f"[java-kg] {index}/{len(instance_ids)} skip {instance_id}", flush=True)
            continue
        repo_id = instance_id.rsplit("-", 1)[0]
        require_repository(workdir, repos_dir, repo_id)
        command = [
            sys.executable,
            str(runner),
            "--source-root",
            str(source_root),
            "--depth",
            str(args.entity_depth),
            "--instance-id",
            instance_id,
            "--repo-id",
            repo_id,
            "--output-dir",
            str(output_dir),
        ]
        succeeded = False
        for attempt in range(1, args.retries + 2):
            wait_for_service(host, port, args.service_timeout)
            print(
                f"[java-kg] {index}/{len(instance_ids)} run {instance_id} "
                f"attempt={attempt}",
                flush=True,
            )
            log_path = log_dir / f"{instance_id}.log"
            with log_path.open("w" if attempt == 1 else "a", encoding="utf-8") as log:
                completed = subprocess.run(
                    command,
                    cwd=workdir,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            succeeded = completed.returncode == 0 and output.exists()
            if succeeded:
                break
            time.sleep(10)
        if not succeeded:
            failures.append(instance_id)
            print(f"[java-kg] failed {instance_id}", flush=True)

    if failures:
        print(f"failed instances ({len(failures)}): {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
