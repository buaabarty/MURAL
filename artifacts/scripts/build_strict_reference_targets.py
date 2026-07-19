#!/usr/bin/env python3
"""Build strict base-snapshot repair targets from official patches.

The evaluator ranks source entities that exist at the base commit. This builder
therefore maps removed lines through an independent standard-library AST and
maps added lines through the patched AST only when the same qualified candidate
unit already exists in the base snapshot. Changes outside the candidate-unit
contract, including newly introduced definitions, become exact file targets.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from unidiff import PatchSet


@dataclass(frozen=True)
class Entity:
    file_path: str
    kind: str
    qualified_name: str
    start_line: int
    end_line: int

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.file_path, self.kind, self.qualified_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--dataset-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def normalized_path(value: str | None) -> str | None:
    if not value or value == "/dev/null":
        return None
    value = value.replace("\\", "/")
    if value.startswith(("a/", "b/")):
        value = value[2:]
    while value.startswith("./"):
        value = value[2:]
    return value


def load_ids(path: Path) -> list[str]:
    result: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        result.append(str(json.loads(line)["instance_id"]) if line.startswith("{") else line)
    return result


def discover_arrow() -> Path:
    root = Path.home() / ".cache/huggingface/datasets/princeton-nlp___swe-bench_verified/default/0.0.0"
    candidates = sorted(root.glob("*/swe-bench_verified-test.arrow"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError("SWE-bench Verified Arrow cache was not found")
    return candidates[-1]


def load_dataset(ids: Iterable[str], dataset_file: Path | None) -> dict[str, dict]:
    wanted = set(ids)
    if dataset_file is not None:
        rows: dict[str, dict] = {}
        for raw in dataset_file.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            instance_id = row.get("instance_id")
            if instance_id in wanted:
                rows[instance_id] = row
        return rows

    from datasets import Dataset

    return {
        row["instance_id"]: dict(row)
        for row in Dataset.from_file(str(discover_arrow()))
        if row.get("instance_id") in wanted
    }


def repository_roots(workspace_root: Path, repo_full_name: str) -> Iterable[Path]:
    repo_id = repo_full_name.replace("/", "__")
    repo_name = repo_full_name.rsplit("/", 1)[-1]
    for root in (
        workspace_root / "playground" / repo_id,
        workspace_root / "playground" / repo_name,
    ):
        if (root / ".git").exists():
            yield root


def read_commit_file(
    workspace_root: Path,
    repo_full_name: str,
    commit: str,
    file_path: str,
) -> str | None:
    for repo_root in repository_roots(workspace_root, repo_full_name):
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{commit}:{file_path}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
    return None


def target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    return []


def function_entity(node: ast.FunctionDef, file_path: str, prefix: str = "") -> Entity:
    qualified_name = f"{prefix}.{node.name}" if prefix else node.name
    return Entity(
        file_path=file_path,
        kind="function",
        qualified_name=qualified_name,
        start_line=node.lineno,
        end_line=int(getattr(node, "end_lineno", node.lineno)),
    )


def assignment_entities(node: ast.Assign, file_path: str, prefix: str = "") -> list[Entity]:
    entities: list[Entity] = []
    for target in node.targets:
        for name in target_names(target):
            qualified_name = f"{prefix}.{name}" if prefix else name
            entities.append(
                Entity(
                    file_path=file_path,
                    kind="assignment",
                    qualified_name=qualified_name,
                    start_line=node.lineno,
                    end_line=int(getattr(node, "end_lineno", node.lineno)),
                )
            )
    return entities


def parse_entities(source: str, file_path: str) -> tuple[list[Entity], str | None]:
    try:
        tree = ast.parse(source, filename=file_path, type_comments=True)
    except (SyntaxError, ValueError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    entities: list[Entity] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            entities.append(function_entity(node, file_path))
        elif isinstance(node, ast.Assign):
            entities.extend(assignment_entities(node, file_path))

    # MURAL materializes direct synchronous methods and simple assignments for
    # every class in the file. The target builder mirrors that unit contract
    # while remaining independent of MURAL's parser and ranking code.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for member in node.body:
            if isinstance(member, ast.FunctionDef):
                entities.append(function_entity(member, file_path, node.name))
            elif isinstance(member, ast.Assign):
                entities.extend(assignment_entities(member, file_path, node.name))
    return entities, None


def containing_entity(entities: Iterable[Entity], line_number: int) -> Entity | None:
    matches = [e for e in entities if e.start_line <= line_number <= e.end_line]
    if not matches:
        return None
    return min(matches, key=lambda e: (e.end_line - e.start_line, -e.start_line, e.qualified_name))


def apply_file_patch(base_source: str, patched_file) -> tuple[str | None, str | None]:
    source_lines = base_source.splitlines(keepends=True)
    output: list[str] = []
    cursor = 0
    try:
        for hunk in patched_file:
            hunk_start = max(0, int(hunk.source_start) - 1)
            if hunk_start < cursor:
                return None, "overlapping hunks"
            output.extend(source_lines[cursor:hunk_start])
            cursor = hunk_start
            for line in hunk:
                if line.is_context:
                    if cursor >= len(source_lines):
                        return None, "context exceeds base source"
                    output.append(source_lines[cursor])
                    cursor += 1
                elif line.is_removed:
                    if cursor >= len(source_lines):
                        return None, "removal exceeds base source"
                    cursor += 1
                elif line.is_added:
                    output.append(line.value)
        output.extend(source_lines[cursor:])
    except (AttributeError, TypeError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return "".join(output), None


def target_record(entity: Entity, evidence: str) -> dict:
    result = asdict(entity)
    result["target_type"] = result.pop("kind")
    result["evidence"] = evidence
    return result


def file_target(file_path: str, evidence: str) -> dict:
    return {
        "file_path": file_path,
        "target_type": "file",
        "qualified_name": "",
        "start_line": None,
        "end_line": None,
        "evidence": evidence,
    }


def deduplicate_targets(targets: Iterable[dict]) -> list[dict]:
    by_identity: dict[tuple[str, str, str], dict] = {}
    for target in targets:
        key = (
            str(target["file_path"]),
            str(target["target_type"]),
            str(target.get("qualified_name") or ""),
        )
        previous = by_identity.get(key)
        if previous is None:
            by_identity[key] = target
        elif target["evidence"] not in previous["evidence"].split("+"):
            previous["evidence"] += "+" + target["evidence"]
    return sorted(
        by_identity.values(),
        key=lambda x: (
            x["file_path"],
            x["target_type"],
            int(x.get("start_line") or 0),
            x.get("qualified_name") or "",
        ),
    )


def build_instance_targets(workspace_root: Path, item: dict) -> tuple[dict, dict]:
    patch = PatchSet(item["patch"])
    all_targets: list[dict] = []
    patch_files: list[str] = []
    diagnostics = {
        "python_files": 0,
        "non_python_files": 0,
        "missing_base_files": 0,
        "base_parse_failures": 0,
        "patched_parse_failures": 0,
        "patch_apply_failures": 0,
    }

    for patched_file in patch:
        source_path = normalized_path(patched_file.source_file)
        target_path = normalized_path(patched_file.target_file)
        base_path = source_path or target_path
        output_path = target_path or source_path
        if base_path is None or output_path is None:
            continue
        if output_path not in patch_files:
            patch_files.append(output_path)

        if not base_path.endswith(".py"):
            diagnostics["non_python_files"] += 1
            all_targets.append(file_target(base_path, "non_python_change"))
            continue
        diagnostics["python_files"] += 1

        base_source = read_commit_file(
            workspace_root, item["repo"], item["base_commit"], base_path
        )
        if base_source is None:
            diagnostics["missing_base_files"] += 1
            all_targets.append(file_target(base_path, "new_or_missing_base_file"))
            continue

        base_entities, base_error = parse_entities(base_source, base_path)
        if base_error:
            diagnostics["base_parse_failures"] += 1
            all_targets.append(file_target(base_path, "base_parse_failure"))
            continue

        base_by_identity = {entity.identity: entity for entity in base_entities}
        mapped_line = False
        for hunk in patched_file:
            for line in hunk:
                if line.is_removed and line.source_line_no is not None:
                    entity = containing_entity(base_entities, int(line.source_line_no))
                    if entity is not None:
                        all_targets.append(target_record(entity, "removed_line"))
                    else:
                        all_targets.append(file_target(base_path, "base_scope_change"))
                    mapped_line = True

        patched_source, apply_error = apply_file_patch(base_source, patched_file)
        if apply_error or patched_source is None:
            diagnostics["patch_apply_failures"] += 1
            if any(line.is_added for hunk in patched_file for line in hunk):
                all_targets.append(file_target(base_path, "unmapped_added_line"))
            continue

        patched_entities, patched_error = parse_entities(patched_source, output_path)
        if patched_error:
            diagnostics["patched_parse_failures"] += 1
            if any(line.is_added for hunk in patched_file for line in hunk):
                all_targets.append(file_target(base_path, "patched_parse_failure"))
            continue

        patched_to_base: dict[tuple[str, str, str], Entity] = {}
        for entity in patched_entities:
            key = (base_path, entity.kind, entity.qualified_name)
            if key in base_by_identity:
                patched_to_base[entity.identity] = base_by_identity[key]

        for hunk in patched_file:
            for line in hunk:
                if not line.is_added or line.target_line_no is None:
                    continue
                entity = containing_entity(patched_entities, int(line.target_line_no))
                base_entity = patched_to_base.get(entity.identity) if entity is not None else None
                if base_entity is not None:
                    all_targets.append(target_record(base_entity, "added_line_existing_entity"))
                else:
                    all_targets.append(file_target(base_path, "added_or_outer_scope_change"))
                mapped_line = True

        if not mapped_line:
            all_targets.append(file_target(base_path, "unmapped_patch"))

    targets = deduplicate_targets(all_targets)
    if not targets:
        for path in patch_files:
            targets.append(file_target(path, "empty_target_guard"))
    return {
        "repo": item["repo"],
        "base_commit": item["base_commit"],
        "patch_files": patch_files,
        "targets": targets,
        "target_count": len(targets),
        "entity_target_count": sum(t["target_type"] != "file" for t in targets),
        "file_target_count": sum(t["target_type"] == "file" for t in targets),
    }, diagnostics


def main() -> int:
    args = parse_args()
    ids = load_ids(args.ids_file)
    dataset = load_dataset(ids, args.dataset_file)
    missing = [instance_id for instance_id in ids if instance_id not in dataset]
    if missing:
        raise ValueError(f"Dataset is missing {len(missing)} requested instances")

    items: dict[str, dict] = {}
    totals: dict[str, int] = {}
    for index, instance_id in enumerate(ids, 1):
        result, diagnostics = build_instance_targets(args.workspace_root, dataset[instance_id])
        items[instance_id] = result
        for key, value in diagnostics.items():
            totals[key] = totals.get(key, 0) + int(value)
        if index % 50 == 0:
            print(f"mapped {index}/{len(ids)}")

    type_counts: dict[str, int] = {}
    for item in items.values():
        for target in item["targets"]:
            kind = target["target_type"]
            type_counts[kind] = type_counts.get(kind, 0) + 1

    payload = {
        "_meta": {
            "schema_version": 1,
            "population": len(items),
            "ranking_unit": (
                "base-snapshot synchronous module function, direct class method, "
                "or simple module/class assignment"
            ),
            "matching": "exact normalized file path, target kind, and qualified name",
            "file_target_policy": (
                "one exact patched-file fallback for every changed path containing "
                "a region outside the candidate-unit contract; retained with entity targets"
            ),
            "target_type_counts": type_counts,
            "diagnostics": totals,
        },
        "items": items,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["_meta"], indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
