#!/usr/bin/env python3
"""Evaluate retrieval, entity projection, and fusion on SWE-bench-Java Verified.

The script rebuilds base-commit Java entities, runs BM25 file retrieval, projects
ranked files into Java entities, adapts archived structural ranked-file seeds to
the same contract, and fuses the completed rankings with equal-weight RRF.
Official patches are read only after rankings are produced for patch-to-entity
evaluation.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import subprocess
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from tree_sitter_language_pack import get_parser

from evaluate_strict_reference_context import cluster_bootstrap_ci


CACHE_VERSION = 1
SELECTOR_VERSION = "compact_title_exact_file_rank_ast_v1"
RRF_K = 60
TOP_K = 20
SOURCE_DEPTH = 50
FILE_FALLBACK_TARGET = "__file_fallback__"
CLASS_NODE_TYPES = {
    "annotation_type_declaration",
    "class_declaration",
    "enum_declaration",
    "interface_declaration",
    "record_declaration",
}
METHOD_NODE_TYPES = {"constructor_declaration", "method_declaration"}
EXCLUDED_PATH_PARTS = {
    ".gradle",
    ".idea",
    "build",
    "generated",
    "node_modules",
    "target",
}
STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "and",
    "are",
    "because",
    "before",
    "between",
    "but",
    "can",
    "cannot",
    "could",
    "does",
    "during",
    "else",
    "expected",
    "false",
    "file",
    "files",
    "for",
    "from",
    "had",
    "has",
    "have",
    "if",
    "into",
    "issue",
    "its",
    "line",
    "may",
    "more",
    "most",
    "none",
    "only",
    "out",
    "over",
    "problem",
    "return",
    "same",
    "should",
    "some",
    "such",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "too",
    "traceback",
    "true",
    "under",
    "very",
    "when",
    "where",
    "while",
    "will",
    "with",
    "within",
    "without",
    "would",
    "you",
    "your",
}


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def normalize_path(value: object, repo_id: str = "") -> str:
    path = str(value or "").replace("\\", "/").lstrip("./")
    markers = [f"playground/{repo_id}/", f"{repo_id}/"] if repo_id else []
    for marker in markers:
        index = path.find(marker)
        if index >= 0:
            return path[index + len(marker) :]
    return path


def split_identifier(value: object) -> list[str]:
    if not value:
        return []
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    output: list[str] = []

    def add(token: str) -> None:
        if len(token) >= 3 and token not in STOPWORDS:
            output.append(token)

    for raw in re.split(r"[^A-Za-z0-9]+", spaced):
        token = raw.lower()
        if len(token) < 3 or token in STOPWORDS:
            continue
        add(token)
        if token.endswith("ing") and len(token) > 5:
            add(token[:-3])
        if token.endswith("ies") and len(token) > 5:
            add(token[:-3] + "y")
        if token.endswith("s") and len(token) > 4:
            add(token[:-1])
    return output


def exact_terms(value: object) -> set[str]:
    output: set[str] = set()
    for raw in re.findall(
        r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*",
        str(value or ""),
    ):
        token = raw.lower()
        if len(token) < 3 or token in STOPWORDS:
            continue
        output.add(token)
        for part in re.split(r"[._]+", token):
            if len(part) >= 3 and part not in STOPWORDS:
                output.add(part)
    return output


def field_terms(*values: object) -> tuple[set[str], set[str]]:
    exact: set[str] = set()
    lexical: set[str] = set()
    for value in values:
        exact.update(exact_terms(value))
        lexical.update(split_identifier(value))
    return exact, lexical


def issue_sections(title: str, body: str) -> dict[str, set[str]]:
    diagnostic_lines: list[str] = []
    narrative_lines: list[str] = []
    in_traceback = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("Traceback") or stripped == "Traceback:":
            in_traceback = True
        is_stack_line = bool(
            re.match(r'File ["\'].*["\'], line \d+', stripped)
            or re.match(r"[A-Za-z_][A-Za-z0-9_.]*Error:", stripped)
        )
        if in_traceback or is_stack_line:
            diagnostic_lines.append(line)
        else:
            narrative_lines.append(line)

    narrative = "\n".join(narrative_lines)
    diagnostic = "\n".join(diagnostic_lines)
    code_spans = " ".join(re.findall(r"`([^`]+)`", f"{title}\n{body}"))
    quoted = " ".join(re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_.-]+)['\"]", body))
    title_terms = set(split_identifier(title))
    narrative_terms = set(split_identifier(narrative))
    title_exact = exact_terms(title)
    exact = (
        title_exact
        | exact_terms(code_spans)
        | exact_terms(quoted)
        | {term for term in exact_terms(narrative) if "_" in term or "." in term}
    )
    return {
        "title_terms": title_terms,
        "narrative_terms": narrative_terms,
        "issue_terms": title_terms
        | narrative_terms
        | set(split_identifier(code_spans))
        | set(split_identifier(quoted)),
        "exact_terms": exact,
        "diagnostic_terms": exact_terms(diagnostic),
    }


def is_boilerplate(item: dict[str, Any]) -> bool:
    base = str(item.get("name") or "").lower().rsplit(".", 1)[-1]
    if base in {"__all__", "__version__", "__doc__", "__bibtex__", "__citation__"}:
        return True
    return base.startswith("__") and base.endswith("__") and base != "__init__"


def source_path_is_candidate(path: str) -> bool:
    lowered = f"/{path.lower().strip('/')}/"
    parts = set(lowered.strip("/").split("/"))
    if not path.endswith(".java") or parts & EXCLUDED_PATH_PARTS:
        return False
    return not any(
        marker in lowered
        for marker in ("/src/test/", "/src/it/", "/test/", "/tests/", "/testdata/")
    )


def node_text(source: bytes, node: Any) -> str:
    return source[node.start_byte() : node.end_byte()].decode("utf-8", errors="replace")


def node_name(source: bytes, node: Any) -> str:
    child = node.child_by_field_name("name")
    return node_text(source, child).strip() if child is not None else ""


def preceding_doc(source: bytes, start_byte: int) -> str:
    prefix = source[max(0, start_byte - 6000) : start_byte].decode("utf-8", errors="replace")
    match = re.search(r"(/\*\*.*?\*/)[ \t\r\n]*$", prefix, flags=re.DOTALL)
    return match.group(1) if match else ""


def entity_record(
    source: bytes,
    node: Any,
    path: str,
    package: str,
    owners: list[str],
    entity_type: str,
    name: str,
    signature_suffix: str = "",
) -> dict[str, Any]:
    qualified = ".".join(part for part in [package, *owners, name] if part)
    start_line = node.start_position().row + 1
    end_line = node.end_position().row + 1
    snippet = node_text(source, node)
    signature = qualified + signature_suffix
    identifier = f"{entity_type}|{path}|{start_line}|{end_line}|{qualified}"
    return {
        "id": identifier,
        "entity_type": entity_type,
        "name": qualified,
        "short_name": name,
        "signature": signature,
        "file_path": path,
        "start_line": start_line,
        "end_line": end_line,
        "source_code": snippet[:12000],
        "doc_string": preceding_doc(source, node.start_byte()),
    }


def parse_java_file(parser: Any, path: str, source: bytes) -> tuple[list[dict[str, Any]], bool]:
    tree = parser.parse(source.decode("utf-8", errors="replace"))
    root = tree.root_node()
    package_match = re.search(rb"(?m)^\s*package\s+([A-Za-z_][\w.]*)\s*;", source[:20000])
    package = package_match.group(1).decode() if package_match else ""
    entities: list[dict[str, Any]] = []

    def visit(node: Any, owners: list[str]) -> None:
        child_owners = owners
        node_type = node.kind()
        if node_type in CLASS_NODE_TYPES:
            name = node_name(source, node)
            if name:
                entities.append(entity_record(source, node, path, package, owners, "class", name))
                child_owners = [*owners, name]
        elif node_type in METHOD_NODE_TYPES:
            name = node_name(source, node)
            if name:
                params = node.child_by_field_name("parameters")
                suffix = node_text(source, params).strip() if params is not None else "()"
                entities.append(
                    entity_record(source, node, path, package, owners, "method", name, suffix)
                )
        elif node_type == "field_declaration":
            for child_index in range(node.named_child_count()):
                child = node.named_child(child_index)
                if child.kind() != "variable_declarator":
                    continue
                name = node_name(source, child)
                if name:
                    entities.append(entity_record(source, node, path, package, owners, "field", name))

        for child_index in range(node.named_child_count()):
            visit(node.named_child(child_index), child_owners)

    visit(root, [])
    unique: dict[str, dict[str, Any]] = {}
    for entity in entities:
        unique.setdefault(entity["id"], entity)
    return list(unique.values()), bool(root.has_error())


def ensure_repo(repo_full_name: str, repos_dir: Path) -> Path:
    repo_id = repo_full_name.replace("/", "__")
    destination = repos_dir / repo_id
    if not destination.exists():
        repos_dir.mkdir(parents=True, exist_ok=True)
        run(
            [
                "git",
                "clone",
                "--no-checkout",
                "--filter=blob:none",
                f"https://github.com/{repo_full_name}.git",
                str(destination),
            ]
        )
    return destination


def ensure_commit(repo: Path, sha: str) -> None:
    probe = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode != 0:
        run(["git", "-C", str(repo), "fetch", "origin", sha])


def corpus_cache_path(cache_dir: Path, repo_id: str, sha: str) -> Path:
    return cache_dir / repo_id / f"{sha}.v{CACHE_VERSION}.json.gz"


def build_corpus(repo: Path, repo_id: str, sha: str, cache_dir: Path) -> dict[str, Any]:
    cache = corpus_cache_path(cache_dir, repo_id, sha)
    if cache.exists():
        with gzip.open(cache, "rt", encoding="utf-8") as handle:
            return json.load(handle)

    parser = get_parser("java")
    entities: list[dict[str, Any]] = []
    java_files = 0
    parse_error_files = 0
    process = subprocess.Popen(
        ["git", "-C", str(repo), "archive", "--format=tar", sha],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
        for member in archive:
            path = normalize_path(member.name)
            if not member.isfile() or not source_path_is_candidate(path) or member.size > 2_000_000:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            source = extracted.read()
            java_files += 1
            parsed, has_error = parse_java_file(parser, path, source)
            parse_error_files += int(has_error)
            entities.extend(parsed)
    if process.wait() != 0:
        raise RuntimeError(f"git archive failed for {repo_id}@{sha}")

    payload = {
        "cache_version": CACHE_VERSION,
        "repo_id": repo_id,
        "sha": sha,
        "java_files": java_files,
        "parse_error_files": parse_error_files,
        "entities": entities,
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache, "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))
    return payload


def bm25_rank(entities: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    query_terms = set(split_identifier(query))
    if not query_terms or not entities:
        return []
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    document_lengths = np.zeros(len(entities), dtype=np.float64)
    for index, entity in enumerate(entities):
        text = "\n".join(
            [
                entity["signature"],
                entity["file_path"],
                entity.get("doc_string") or "",
                (entity.get("source_code") or "")[:3000],
            ]
        )
        tokens = split_identifier(text)
        document_lengths[index] = len(tokens)
        counts = Counter(tokens)
        for term in query_terms:
            if counts.get(term):
                postings[term].append((index, counts[term]))

    average_length = float(document_lengths.mean()) if len(document_lengths) else 0.0
    scores = np.zeros(len(entities), dtype=np.float64)
    k1, b = 1.5, 0.75
    for term, posting in postings.items():
        document_frequency = len(posting)
        inverse = math.log(1.0 + (len(entities) - document_frequency + 0.5) / (document_frequency + 0.5))
        for index, frequency in posting:
            denominator = frequency + k1 * (
                1.0 - b + b * document_lengths[index] / max(average_length, 1e-8)
            )
            scores[index] += inverse * frequency * (k1 + 1.0) / max(denominator, 1e-8)

    ranked_indices = [index for index in np.argsort(-scores, kind="stable") if scores[index] > 0]
    return [entities[int(index)] for index in ranked_indices]


def ranked_file_evidence(ranking: list[dict[str, Any]], depth: int = SOURCE_DEPTH) -> dict[str, dict[str, Any]]:
    pool = ranking[:depth]
    support = Counter(item["file_path"] for item in pool)
    output: dict[str, dict[str, Any]] = {}
    for entity_rank, item in enumerate(pool, start=1):
        path = item["file_path"]
        if path in output:
            continue
        output[path] = {
            "file_path": path,
            "best_rank": len(output) + 1,
            "support": support[path],
            "distance": entity_rank,
            "anchor_match": False,
        }
        if len(output) >= TOP_K:
            break
    return output


def selector_key(
    item: dict[str, Any],
    file_evidence: dict[str, Any],
    sections: dict[str, set[str]],
    original_rank: int | None,
) -> tuple[Any, ...]:
    symbol_exact, symbol_terms = field_terms(item["name"], item["signature"], item["file_path"])
    _, source_terms = field_terms(item.get("source_code"), item.get("doc_string"))
    title_symbol = sections["title_terms"] & symbol_terms
    title_source = sections["title_terms"] & source_terms
    narrative_symbol = sections["narrative_terms"] & symbol_terms
    exact_symbol = sections["exact_terms"] & symbol_exact
    exact_source = sections["exact_terms"] & exact_terms(
        f"{item.get('source_code') or ''}\n{item.get('doc_string') or ''}"
    )
    source_only = (sections["issue_terms"] & source_terms) - (sections["issue_terms"] & symbol_terms)
    diagnostic_symbol = sections["diagnostic_terms"] & symbol_exact
    penalty = int(is_boilerplate(item))
    if diagnostic_symbol and not (title_symbol or exact_symbol or narrative_symbol or source_only):
        penalty += 1
    return (
        -len(title_symbol),
        -len(title_source),
        -len(exact_symbol),
        -len(exact_source),
        penalty,
        int(file_evidence.get("best_rank") or 999),
        int(item.get("start_line") or 0),
        item.get("name") or "",
    )


def localize_files(
    entities: list[dict[str, Any]],
    file_evidence: dict[str, dict[str, Any]],
    sections: dict[str, set[str]],
    original_ranks: dict[str, int],
) -> list[dict[str, Any]]:
    rows = [
        (
            selector_key(item, file_evidence[item["file_path"]], sections, original_ranks.get(item["id"])),
            item,
        )
        for item in entities
        if item["file_path"] in file_evidence
    ]
    rows.sort(key=lambda row: row[0])
    return [item for _, item in rows[:SOURCE_DEPTH]]


def rrf_fuse(*rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scores: dict[str, float] = defaultdict(float)
    copies: dict[str, dict[str, Any]] = {}
    source_count: Counter[str] = Counter()
    best_rank: dict[str, int] = {}
    first_source: dict[str, int] = {}
    for source_index, ranking in enumerate(rankings):
        seen: set[str] = set()
        for rank, item in enumerate(ranking[:SOURCE_DEPTH], start=1):
            identifier = item["id"]
            if identifier in seen:
                continue
            seen.add(identifier)
            scores[identifier] += 1.0 / (RRF_K + rank)
            copies.setdefault(identifier, item)
            source_count[identifier] += 1
            best_rank[identifier] = min(best_rank.get(identifier, rank), rank)
            first_source.setdefault(identifier, source_index)
    identifiers = sorted(
        scores,
        key=lambda identifier: (
            -scores[identifier],
            -source_count[identifier],
            best_rank[identifier],
            first_source[identifier],
            copies[identifier]["file_path"],
            copies[identifier]["start_line"],
            identifier,
        ),
    )
    return [copies[identifier] for identifier in identifiers[:SOURCE_DEPTH]]


def normalize_dataset_record(item: dict[str, Any], source: Path, line_number: int) -> dict[str, Any]:
    """Map either official or repository-exported SWE-bench-Java rows to one schema."""
    if item.get("base_commit"):
        repo_full_name = str(item.get("repo") or "")
        if "/" not in repo_full_name:
            raise ValueError(f"Invalid official repo field in {source}:{line_number}: {repo_full_name!r}")
        org, repo = repo_full_name.split("/", 1)
        problem_statement = str(item.get("problem_statement") or "").strip()
        lines = problem_statement.splitlines()
        title = lines[0].lstrip("# ").strip() if lines else ""
        body = "\n".join(lines[1:]).strip()
        return {
            **item,
            "org": org,
            "repo": repo,
            "base": {"sha": str(item["base_commit"])},
            "title": title,
            "body": body,
            "fix_patch": str(item.get("patch") or ""),
        }

    required = ("instance_id", "org", "repo", "base", "fix_patch")
    missing = [field for field in required if field not in item]
    if missing:
        raise ValueError(f"Missing fields {missing} in {source}:{line_number}")
    return item


def load_dataset(directory: Path) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*_dataset.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                item = normalize_dataset_record(json.loads(line), path, line_number)
                output[item["instance_id"]] = item
    return output


def load_ranked_file_seeds(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            instance_id = str(item.get("instance_id") or "")
            if not instance_id:
                raise ValueError(f"Missing instance_id in {path}:{line_number}")
            files: dict[str, dict[str, Any]] = {}
            for position, record in enumerate(item.get("ranked_files") or [], start=1):
                file_path = normalize_path(record.get("file_path"))
                if not file_path or file_path in files:
                    continue
                files[file_path] = {
                    "file_path": file_path,
                    "best_rank": int(record.get("rank") or position),
                    "support": int(record.get("support") or 1),
                    "distance": int(
                        record.get("graph_distance")
                        or record.get("first_entity_rank")
                        or position
                    ),
                    "anchor_match": bool(record.get("direct_anchor")),
                }
            output[instance_id] = files
    return output


def entity_indexes(entities: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_id: dict[str, dict[str, Any]] = {}
    for item in entities:
        by_file[item["file_path"]].append(item)
        by_id[item["id"]] = item
    for rows in by_file.values():
        rows.sort(key=lambda item: (item["start_line"], item["end_line"] - item["start_line"]))
    return by_file, by_id


def patch_changed_lines(patch: str) -> dict[str, set[int]]:
    output: dict[str, set[int]] = defaultdict(set)
    current_file = ""
    old_line: int | None = None
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.*?) b/(.*)", line)
            current_file = normalize_path(match.group(2)) if match else ""
            old_line = None
        elif line.startswith("@@"):
            match = re.search(r"-(\d+)(?:,(\d+))?", line)
            old_line = int(match.group(1)) if match else None
        elif not current_file or old_line is None:
            continue
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith(" "):
            old_line += 1
        elif line.startswith("-"):
            output[current_file].add(max(1, old_line))
            old_line += 1
        elif line.startswith("+"):
            output[current_file].add(max(1, old_line))
    return output


def map_targets(
    patch: str,
    entities_by_file: dict[str, list[dict[str, Any]]],
) -> tuple[set[str], set[str], bool, int]:
    changed = patch_changed_lines(patch)
    targets: set[str] = set()
    patched_files = set(changed)
    unmapped_patched_files = 0
    for path, lines in changed.items():
        file_entities = entities_by_file.get(path) or []
        mapped_for_file = False
        for line in lines:
            containing = [
                item for item in file_entities if item["start_line"] <= line <= item["end_line"]
            ]
            if not containing:
                continue
            chosen = min(
                containing,
                key=lambda item: (
                    item["entity_type"] == "class",
                    item["end_line"] - item["start_line"],
                    item["start_line"],
                ),
            )
            targets.add(chosen["id"])
            mapped_for_file = True
        if not mapped_for_file:
            unmapped_patched_files += 1

    # Match the Python evaluation contract: auxiliary files and entities that
    # do not exist at the base commit do not enlarge an otherwise valid target
    # set. Use one file-level target only when the whole patch is unmappable.
    file_fallback = not targets
    if file_fallback:
        targets.add(FILE_FALLBACK_TARGET)
    return targets, patched_files, file_fallback, unmapped_patched_files


def candidate_target_ids(item: dict[str, Any]) -> set[str]:
    return {item["id"]}


def instance_metrics(
    ranking: list[dict[str, Any]],
    targets: set[str],
    patched_files: set[str],
    file_fallback: bool = False,
) -> dict[str, float]:
    window = ranking[:TOP_K]
    represented_files = {item["file_path"] for item in window}
    covered_targets: set[str] = set()
    first_rank: int | None = None
    for rank, item in enumerate(window, start=1):
        overlap = (
            {FILE_FALLBACK_TARGET}
            if file_fallback and item["file_path"] in patched_files
            else targets & candidate_target_ids(item)
        )
        if overlap:
            covered_targets.update(overlap)
            if first_rank is None:
                first_rank = rank
    return {
        "file": float(bool(represented_files & patched_files)),
        "method": len(covered_targets) / max(1, len(targets)),
        "mrr": 0.0 if first_rank is None else 1.0 / first_rank,
        "hit": float(first_rank is not None),
    }


def exact_mcnemar(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def bootstrap_interval(differences: np.ndarray, seed: int, iterations: int) -> tuple[float, float]:
    generator = np.random.default_rng(seed)
    sample_indices = generator.integers(0, len(differences), size=(iterations, len(differences)))
    means = differences[sample_indices].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def write_tsv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--kg-seeds", required=True, type=Path)
    parser.add_argument("--repos-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-paired", required=True, type=Path)
    parser.add_argument("--output-instances", required=True, type=Path)
    parser.add_argument("--output-targets", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--bootstrap-iters", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = load_dataset(args.dataset_dir)
    kg_seed_rows = load_ranked_file_seeds(args.kg_seeds)
    instance_ids = sorted(set(dataset) & set(kg_seed_rows))
    if args.limit > 0:
        instance_ids = instance_ids[: args.limit]
    if not instance_ids:
        raise ValueError("No shared Java instances between dataset and structural results")

    per_instance: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for index, instance_id in enumerate(instance_ids, start=1):
        item = dataset[instance_id]
        repo_full_name = f"{item['org']}/{item['repo']}"
        repo_id = repo_full_name.replace("/", "__")
        sha = item["base"]["sha"]
        try:
            repo = ensure_repo(repo_full_name, args.repos_dir)
            ensure_commit(repo, sha)
            corpus = build_corpus(repo, repo_id, sha, args.cache_dir)
            entities = corpus["entities"]
            by_file, _ = entity_indexes(entities)
            query = f"{item.get('title') or ''}\n{item.get('body') or ''}".strip()
            sections = issue_sections(str(item.get("title") or ""), str(item.get("body") or ""))

            bm25_full = bm25_rank(entities, query)
            bm25_ranking = bm25_full[:SOURCE_DEPTH]
            bm25_files = ranked_file_evidence(bm25_ranking)
            bm25_original = {entity["id"]: rank for rank, entity in enumerate(bm25_ranking, start=1)}
            bm25_local = localize_files(entities, bm25_files, sections, bm25_original)

            kg_files = {
                path: evidence
                for path, evidence in kg_seed_rows[instance_id].items()
                if path in by_file
            }
            kg_local = localize_files(entities, kg_files, sections, {})
            mural = rrf_fuse(bm25_local, kg_local)

            targets, patched_files, file_fallback, unmapped_patched_files = map_targets(
                str(item.get("fix_patch") or ""), by_file
            )
            rows = {
                "Raw_BM25_entities": bm25_ranking,
                "BM25_projection": bm25_local,
                "Structural_projection": kg_local,
                "Lexical_structural_fusion": mural,
            }
            metrics = {
                name: instance_metrics(
                    ranking,
                    targets,
                    patched_files,
                    file_fallback=file_fallback,
                )
                for name, ranking in rows.items()
            }
            per_instance.append(
                {
                    "instance_id": instance_id,
                    "repo": repo_full_name,
                    "base_commit": sha,
                    "entity_count": len(entities),
                    "java_file_count": corpus["java_files"],
                    "parse_error_files": corpus["parse_error_files"],
                    "target_count": len(targets),
                    "patched_file_count": len(patched_files),
                    "file_fallbacks": int(file_fallback),
                    "unmapped_patched_files": unmapped_patched_files,
                    "bm25_source_files": len(bm25_files),
                    "kg_source_files": len(kg_files),
                    "metrics": metrics,
                    "top20": {
                        name: [entity["id"] for entity in ranking[:TOP_K]]
                        for name, ranking in rows.items()
                    },
                }
            )
            target_records.append(
                {
                    "instance_id": instance_id,
                    "targets": sorted(targets),
                    "patched_files": sorted(patched_files),
                    "file_fallbacks": int(file_fallback),
                    "unmapped_patched_files": unmapped_patched_files,
                }
            )
            print(
                f"[java] {index}/{len(instance_ids)} {instance_id}: "
                f"entities={len(entities)} targets={len(targets)} "
                f"hits=" + ",".join(f"{name}:{int(value['hit'])}" for name, value in metrics.items()),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - retain a complete failure ledger.
            failures.append({"instance_id": instance_id, "error": repr(exc)})
            print(f"[java] FAILED {instance_id}: {exc!r}", flush=True)

    if not per_instance:
        raise RuntimeError(f"Every Java instance failed: {failures[:3]}")

    names = [
        "Raw_BM25_entities",
        "BM25_projection",
        "Structural_projection",
        "Lexical_structural_fusion",
    ]
    summary_rows: list[dict[str, Any]] = []
    for name in names:
        summary_rows.append(
            {
                "name": name,
                "N": len(per_instance),
                "top_k": TOP_K,
                "file_rate": np.mean([row["metrics"][name]["file"] for row in per_instance]),
                "method_or_entity_rate": np.mean(
                    [row["metrics"][name]["method"] for row in per_instance]
                ),
                "mrr": np.mean([row["metrics"][name]["mrr"] for row in per_instance]),
                "hit_rate": np.mean([row["metrics"][name]["hit"] for row in per_instance]),
            }
        )

    comparisons = [
        ("Raw_BM25_entities", "BM25_projection"),
        ("BM25_projection", "Structural_projection"),
        ("BM25_projection", "Lexical_structural_fusion"),
        ("Structural_projection", "Lexical_structural_fusion"),
    ]
    paired_rows: list[dict[str, Any]] = []
    for baseline, treatment in comparisons:
        for metric in ("file", "method", "mrr", "hit"):
            baseline_values = np.asarray(
                [row["metrics"][baseline][metric] for row in per_instance], dtype=float
            )
            treatment_values = np.asarray(
                [row["metrics"][treatment][metric] for row in per_instance], dtype=float
            )
            differences = treatment_values - baseline_values
            triples = [
                (row["repo"], float(base), float(treatment))
                for row, base, treatment in zip(
                    per_instance, baseline_values, treatment_values
                )
            ]
            low, high = cluster_bootstrap_ci(triples, args.bootstrap_iters, args.seed)
            wins = int(np.sum(differences > 0))
            losses = int(np.sum(differences < 0))
            paired_rows.append(
                {
                    "baseline": baseline,
                    "treatment": treatment,
                    "top_k": TOP_K,
                    "metric": metric,
                    "N": len(per_instance),
                    "baseline_value": float(baseline_values.mean()),
                    "treatment_value": float(treatment_values.mean()),
                    "delta": float(differences.mean()),
                    "ci95_low": low,
                    "ci95_high": high,
                    "wins": wins,
                    "losses": losses,
                    "ties": len(per_instance) - wins - losses,
                    "exact_mcnemar_p": exact_mcnemar(wins, losses)
                    if metric in {"file", "hit"}
                    else "NA",
                }
            )

    write_tsv(
        args.output_summary,
        summary_rows,
        ["name", "N", "top_k", "file_rate", "method_or_entity_rate", "mrr", "hit_rate"],
    )
    write_tsv(
        args.output_paired,
        paired_rows,
        [
            "baseline",
            "treatment",
            "top_k",
            "metric",
            "N",
            "baseline_value",
            "treatment_value",
            "delta",
            "ci95_low",
            "ci95_high",
            "wins",
            "losses",
            "ties",
            "exact_mcnemar_p",
        ],
    )
    args.output_instances.parent.mkdir(parents=True, exist_ok=True)
    args.output_instances.write_text(
        "\n".join(json.dumps(row, ensure_ascii=True, separators=(",", ":")) for row in per_instance)
        + "\n",
        encoding="utf-8",
    )
    target_payload = {
        "meta": {
            "cache_version": CACHE_VERSION,
            "selector_version": SELECTOR_VERSION,
            "N": len(per_instance),
            "requested_N": len(instance_ids),
            "failure_count": len(failures),
            "failures": failures,
            "dataset_sha256": hashlib.sha256(
                "\n".join(sorted(instance_ids)).encode("utf-8")
            ).hexdigest(),
            "top_k": TOP_K,
            "source_depth": SOURCE_DEPTH,
            "rrf_k": RRF_K,
            "bootstrap_iterations": args.bootstrap_iters,
            "seed": args.seed,
        },
        "items": target_records,
    }
    args.output_targets.write_text(json.dumps(target_payload, indent=2), encoding="utf-8")
    print(f"wrote {args.output_summary}")
    print(f"wrote {args.output_paired}")
    print(f"completed={len(per_instance)} failures={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
