import argparse
import gc
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import torch
import transformers.tokenization_utils_base as tokenization_utils_base
import transformers.utils.hub as transformers_hub

from export_text_baselines import (
    DenseIndex,
    build_method_corpus,
    checkout_commit,
    compose_query_text,
    discover_verified_arrow,
    ensure_repo,
    load_instances_from_arrow,
    load_target_instance_ids,
    write_result,
)


DEFAULT_IDS_FILE = "SWE-bench_Verified_ids.jsonl"
DEFAULT_OUTPUT_ROOT = "runs/text_baselines_dense_filefirst"
DEFAULT_REPOS_DIR = "playground_text_baselines"
DEFAULT_DENSE_TAG = "2201"
DEFAULT_TOP_K = 50
DEFAULT_MIN_FILES = 2


@dataclass
class FileDoc:
    file_path: str
    text: str


def _disable_remote_template_lookup():
    def _offline_list_repo_templates(*args, **kwargs):
        return []

    transformers_hub.list_repo_templates = _offline_list_repo_templates
    tokenization_utils_base.list_repo_templates = _offline_list_repo_templates


def build_kgmatched_method_text(method) -> str:
    text = "\n".join(
        [
            method.name or "",
            method.doc_string or "",
            method.source_code or "",
        ]
    ).strip()
    return text[:4000]


def build_file_text(rel_path: str, content: str) -> str:
    return "\n".join([rel_path or "", (content or "")[:4000]]).strip()


def build_file_and_method_corpora(repo_path: Path):
    methods = build_method_corpus(repo_path)
    methods_by_file: Dict[str, List] = defaultdict(list)
    for method in methods:
        methods_by_file[method.file_path].append(method)

    file_docs: List[FileDoc] = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d != ".git"]
        for file_name in files:
            if not file_name.endswith(".py"):
                continue
            full_path = Path(root) / file_name
            rel_path = str(full_path.relative_to(repo_path)).replace("\\", "/")
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                content = ""
            file_docs.append(FileDoc(file_path=rel_path, text=build_file_text(rel_path, content)))
    return file_docs, methods_by_file


class ReusableDenseEncoder:
    def __init__(self, batch_size: int = 1):
        self.batch_size = max(1, batch_size)
        self.model = DenseIndex._load_jina_model()

    @staticmethod
    def _is_oom_error(exc: BaseException) -> bool:
        text = str(exc).lower()
        return "out of memory" in text or "cuda error: out of memory" in text

    def _is_cuda_model(self) -> bool:
        try:
            return next(self.model.parameters()).is_cuda
        except Exception:
            return False

    def _clear_cuda_cache(self):
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        gc.collect()

    def _switch_to_cpu(self):
        try:
            self.model = self.model.to("cpu")
        except Exception:
            pass
        self._clear_cuda_cache()

    def encode_texts(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        vectors = []
        start = 0
        dynamic_batch = self.batch_size
        total = len(texts)
        while start < total:
            end = min(total, start + dynamic_batch)
            batch = list(texts[start:end])
            try:
                emb = self.model.encode(batch)
                vectors.append(np.asarray(emb, dtype=np.float32))
                start = end
            except RuntimeError as exc:
                if not self._is_oom_error(exc):
                    raise
                if self._is_cuda_model() and dynamic_batch > 1:
                    dynamic_batch = max(1, dynamic_batch // 2)
                    self._clear_cuda_cache()
                    continue
                if self._is_cuda_model():
                    dynamic_batch = 1
                    self._switch_to_cpu()
                    continue
                raise
        mat = np.vstack(vectors) if vectors else np.zeros((0, 1), dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    def encode_query(self, query: str) -> np.ndarray:
        try:
            q = np.asarray(self.model.encode([query])[0], dtype=np.float32)
        except RuntimeError as exc:
            if not self._is_oom_error(exc) or not self._is_cuda_model():
                raise
            self._switch_to_cpu()
            q = np.asarray(self.model.encode([query])[0], dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return q
        return q / q_norm


def top_k_from_matrix(matrix: np.ndarray, query_vec: np.ndarray, k: int) -> List[Tuple[int, float]]:
    if matrix.shape[0] == 0:
        return []
    scores = matrix @ query_vec
    k = min(k, scores.shape[0])
    idx = np.argpartition(-scores, k - 1)[:k]
    ordered = idx[np.argsort(-scores[idx])]
    return [(int(i), float(scores[i])) for i in ordered]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Export a file-first dense baseline: retrieve top related files first, "
            "then retrieve functions only inside those files with dense cosine."
        )
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--repos-dir", default=DEFAULT_REPOS_DIR)
    parser.add_argument("--instance-ids", default=DEFAULT_IDS_FILE)
    parser.add_argument("--dataset-arrow", default=None)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--min-files",
        type=int,
        default=DEFAULT_MIN_FILES,
        help="Always keep at least this many top-ranked files before expanding by candidate budget.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fetch-remote", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--embed-batch-size", type=int, default=1)
    parser.add_argument(
        "--include-hints",
        action="store_true",
        help="Use hints_text in the query. Default is no-hints.",
    )
    parser.add_argument("--dense-tag", default=DEFAULT_DENSE_TAG)
    return parser.parse_args()


def main():
    args = parse_args()
    _disable_remote_template_lookup()

    output_root = Path(args.output)
    repos_dir = Path(args.repos_dir)
    target_ids = load_target_instance_ids(Path(args.instance_ids) if args.instance_ids else None)
    arrow_path = Path(args.dataset_arrow) if args.dataset_arrow else discover_verified_arrow()
    print(f"Using dataset arrow: {arrow_path}", flush=True)

    all_items = load_instances_from_arrow(arrow_path)
    items = []
    for item in all_items:
        instance_id = item.get("instance_id")
        if not instance_id:
            continue
        if target_ids is not None and instance_id not in target_ids:
            continue
        items.append(item)
    items = sorted(items, key=lambda x: x["instance_id"])
    if args.limit is not None:
        items = items[: args.limit]

    print(f"Total instances to process: {len(items)}", flush=True)
    if not items:
        return

    dense_dir = output_root / args.dense_tag
    dense_dir.mkdir(parents=True, exist_ok=True)

    grouped: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for item in items:
        instance_id = item["instance_id"]
        repo_identifier = instance_id.rsplit("-", 1)[0]
        base_commit = item.get("base_commit")
        if not base_commit:
            print(f"⚠️ Missing base_commit, skip {instance_id}", flush=True)
            continue
        grouped[(repo_identifier, base_commit)].append(item)

    total_groups = len(grouped)
    encoder = ReusableDenseEncoder(batch_size=args.embed_batch_size)

    for group_idx, ((repo_identifier, base_commit), group_items) in enumerate(grouped.items(), start=1):
        pending_items = []
        for item in group_items:
            instance_id = item["instance_id"]
            target = dense_dir / f"{instance_id}.json"
            if args.force or not target.exists():
                pending_items.append(item)
        if not pending_items:
            print(f"[{group_idx}/{total_groups}] ✅ Skip {repo_identifier}@{base_commit[:8]} (all done)", flush=True)
            continue

        print(
            f"[{group_idx}/{total_groups}] 🚀 Building file-first dense corpus for "
            f"{repo_identifier}@{base_commit[:8]} (instances: {len(pending_items)})",
            flush=True,
        )
        repo_path = ensure_repo(repo_identifier, repos_dir, args.fetch_remote)
        try:
            checkout_commit(repo_path, base_commit)
        except Exception:
            print(f"❌ Checkout failed for {repo_identifier}@{base_commit}, skipping group", flush=True)
            continue

        file_docs, methods_by_file = build_file_and_method_corpora(repo_path)
        if not file_docs:
            print(f"⚠️ No python files parsed for {repo_identifier}@{base_commit[:8]}", flush=True)
            for item in pending_items:
                instance_id = item["instance_id"]
                out = dense_dir / f"{instance_id}.json"
                if out.exists() and not args.force:
                    continue
                write_result(out, instance_id, "dense_filefirst", [], [])
            continue

        file_texts = [doc.text for doc in file_docs]
        file_matrix = encoder.encode_texts(file_texts)

        for item in pending_items:
            instance_id = item["instance_id"]
            query = compose_query_text(item, include_hints=args.include_hints)
            if not query:
                query = instance_id
            query_vec = encoder.encode_query(query)
            file_ranked = top_k_from_matrix(file_matrix, query_vec, file_matrix.shape[0])

            selected_files = []
            candidate_methods = []
            seen = set()
            for rank, (file_idx, score) in enumerate(file_ranked, start=1):
                file_path = file_docs[file_idx].file_path
                selected_files.append((file_idx, score))
                for method in methods_by_file.get(file_path, []):
                    key = (method.name, method.signature, method.file_path, method.start_line)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidate_methods.append(method)
                if rank >= max(1, args.min_files) and len(candidate_methods) >= args.top_k:
                    break

            if not candidate_methods:
                out = dense_dir / f"{instance_id}.json"
                write_result(out, instance_id, "dense_filefirst", [], [])
                print(f"  ⚠️ {instance_id}: no candidate methods after file-first stage", flush=True)
                continue

            method_texts = [build_kgmatched_method_text(m) for m in candidate_methods]
            method_matrix = encoder.encode_texts(method_texts)
            dense_top_local = top_k_from_matrix(method_matrix, query_vec, args.top_k)
            out_file = dense_dir / f"{instance_id}.json"
            write_result(out_file, instance_id, "dense_filefirst", candidate_methods, dense_top_local)
            print(
                f"  ✅ {instance_id}: files={len(selected_files)} candidate_methods={len(candidate_methods)} top={len(dense_top_local)}",
                flush=True,
            )

    print("===========================================", flush=True)
    print("🎉 File-first dense baseline export finished", flush=True)
    print(f"Output root: {output_root}", flush=True)
    print(f"Run tag: dense={args.dense_tag}", flush=True)
    print("===========================================", flush=True)


if __name__ == "__main__":
    main()
