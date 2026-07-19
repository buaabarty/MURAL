import argparse
import ast
import gc
import json
import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from heapq import nlargest
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pyarrow.ipc as pa_ipc
import torch
from transformers import AutoModel


DEFAULT_IDS_FILE = "SWE-bench_Verified_ids.jsonl"
DEFAULT_OUTPUT_ROOT = "runs/text_baselines"
DEFAULT_REPOS_DIR = "playground"
DEFAULT_TOP_K = 50
DEFAULT_BM25_TAG = "2000"
DEFAULT_DENSE_TAG = "2001"
DEFAULT_HYBRID_TAG = "2002"
DENSE_MODEL_REVISION = "516f4baf13dec4ddddda8631e019b5737c8bc250"


def run_cmd(cmd: Sequence[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def discover_verified_arrow() -> Path:
    pattern = (
        Path.home()
        / ".cache/huggingface/datasets/princeton-nlp___swe-bench_verified/default/0.0.0"
    )
    candidates = sorted(pattern.glob("*/swe-bench_verified-test.arrow"), key=os.path.getmtime)
    if not candidates:
        raise FileNotFoundError(
            "Cannot find SWE-bench Verified arrow file under ~/.cache/huggingface/datasets/"
        )
    return candidates[-1]


def load_instances_from_arrow(arrow_path: Path) -> List[dict]:
    with pa_ipc.open_stream(str(arrow_path)) as reader:
        table = reader.read_all()
    return table.to_pylist()


def load_target_instance_ids(ids_file: Optional[Path]) -> Optional[set]:
    if ids_file is None:
        return None
    target_ids = set()
    with open(ids_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                obj = json.loads(line)
                instance_id = obj.get("instance_id")
                if instance_id:
                    target_ids.add(instance_id)
            else:
                target_ids.add(line)
    return target_ids


def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", (text or "").lower())


def safe_literal_or_source(value_node, source_code: str) -> str:
    try:
        return str(ast.literal_eval(value_node))
    except Exception:
        snippet = ast.get_source_segment(source_code, value_node)
        return snippet if snippet is not None else ""


@dataclass
class MethodDoc:
    name: str
    signature: str
    file_path: str
    source_code: str
    doc_string: str
    start_line: int
    end_line: Optional[int]

    def to_result(self, score: float) -> dict:
        return {
            "type": "method",
            "name": self.name,
            "signature": self.signature,
            "file_path": self.file_path,
            "documentation": self.doc_string,
            "source_code": self.source_code,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "issue_id": None,
            "title": None,
            "content": None,
            "distance": None,
            "path": [],
            "similarity": float(score),
        }


def extract_methods_from_python_file(file_path: Path, rel_path: str) -> List[MethodDoc]:
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    try:
        tree = ast.parse(source)
    except Exception:
        return []

    module_path = rel_path.replace(os.sep, ".").replace("/", ".").removesuffix(".py")
    methods: List[MethodDoc] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = ", ".join(arg.arg for arg in node.args.args)
            full_name = f"{module_path}.{node.name}"
            signature = f"{full_name}({params})"
            methods.append(
                MethodDoc(
                    name=full_name,
                    signature=signature,
                    file_path=rel_path.replace("\\", "/"),
                    source_code=ast.get_source_segment(source, node) or "",
                    doc_string=ast.get_docstring(node) or "",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                )
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                full_name = f"{module_path}.{target.id}"
                value = safe_literal_or_source(node.value, source)
                signature = f"{full_name} = {value}"
                methods.append(
                    MethodDoc(
                        name=full_name,
                        signature=signature,
                        file_path=rel_path.replace("\\", "/"),
                        source_code=ast.get_source_segment(source, node) or "",
                        doc_string="",
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", None),
                    )
                )

    for class_node in ast.walk(tree):
        if not isinstance(class_node, ast.ClassDef):
            continue
        full_class_name = f"{module_path}.{class_node.name}"
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = ", ".join(arg.arg for arg in item.args.args)
                full_name = f"{full_class_name}.{item.name}"
                signature = f"{full_name}({params})"
                methods.append(
                    MethodDoc(
                        name=full_name,
                        signature=signature,
                        file_path=rel_path.replace("\\", "/"),
                        source_code=ast.get_source_segment(source, item) or "",
                        doc_string=ast.get_docstring(item) or "",
                        start_line=item.lineno,
                        end_line=getattr(item, "end_lineno", None),
                    )
                )
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    full_name = f"{full_class_name}.{target.id}"
                    value = safe_literal_or_source(item.value, source)
                    signature = f"{full_name} = {value}"
                    methods.append(
                        MethodDoc(
                            name=full_name,
                            signature=signature,
                            file_path=rel_path.replace("\\", "/"),
                            source_code=ast.get_source_segment(source, item) or "",
                            doc_string="",
                            start_line=item.lineno,
                            end_line=getattr(item, "end_lineno", None),
                        )
                    )

    filtered = []
    for method in methods:
        name_lower = method.name.lower()
        if "test" in name_lower and "pytest" not in name_lower:
            continue
        filtered.append(method)
    return filtered


def build_method_corpus(repo_path: Path) -> List[MethodDoc]:
    methods: List[MethodDoc] = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d != ".git"]
        for file_name in files:
            if not file_name.endswith(".py"):
                continue
            full_path = Path(root) / file_name
            rel_path = str(full_path.relative_to(repo_path))
            methods.extend(extract_methods_from_python_file(full_path, rel_path))
    return methods


class BM25Index:
    def __init__(self, docs_tokens: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.n_docs = len(docs_tokens)
        self.doc_len = np.array([len(tokens) for tokens in docs_tokens], dtype=np.float32)
        self.avgdl = float(np.mean(self.doc_len)) if self.n_docs else 0.0
        self.postings: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        self.df: Dict[str, int] = {}

        for i, tokens in enumerate(docs_tokens):
            freqs = Counter(tokens)
            for term, tf in freqs.items():
                self.postings[term].append((i, tf))
        for term, posting in self.postings.items():
            self.df[term] = len(posting)

    def score(self, query_tokens: List[str]) -> Dict[int, float]:
        scores: Dict[int, float] = defaultdict(float)
        if not query_tokens or self.n_docs == 0:
            return scores
        seen = set(query_tokens)
        for term in seen:
            posting = self.postings.get(term)
            if not posting:
                continue
            df = self.df[term]
            idf = math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))
            for doc_id, tf in posting:
                dl = self.doc_len[doc_id]
                denom = tf + self.k1 * (1.0 - self.b + self.b * dl / max(1e-8, self.avgdl))
                scores[doc_id] += idf * (tf * (self.k1 + 1.0)) / max(1e-8, denom)
        return scores

    def top_k(self, query_tokens: List[str], k: int) -> List[Tuple[int, float]]:
        scores = self.score(query_tokens)
        if not scores:
            return []
        return nlargest(k, scores.items(), key=lambda x: x[1])


class DenseIndex:
    def __init__(self, docs_text: List[str], batch_size: int = 64):
        self.model = self._load_jina_model()
        self.batch_size = max(1, batch_size)
        self.matrix = self._encode_docs(docs_text)

    @staticmethod
    def _load_jina_model():
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        model = AutoModel.from_pretrained(
            "jinaai/jina-embeddings-v2-base-code",
            revision=DENSE_MODEL_REVISION,
            trust_remote_code=True,
            local_files_only=True,
        )
        if torch.cuda.is_available():
            try:
                # Optional hard cap for this process GPU memory usage (in GB).
                # Example: KG_TEXTBASELINE_GPU_MEMORY_GB=20
                mem_cap_gb = os.environ.get("KG_TEXTBASELINE_GPU_MEMORY_GB")
                if mem_cap_gb:
                    try:
                        cap_bytes = float(mem_cap_gb) * (1024 ** 3)
                        total_bytes = float(torch.cuda.get_device_properties(0).total_memory)
                        fraction = min(1.0, max(0.01, cap_bytes / max(1.0, total_bytes)))
                        torch.cuda.set_per_process_memory_fraction(fraction, device=0)
                        print(
                            f"🧠 GPU memory cap enabled: {mem_cap_gb}GB "
                            f"(fraction={fraction:.4f})",
                            flush=True,
                        )
                    except Exception as exc:
                        print(f"⚠️ Failed to set GPU memory cap: {exc}", flush=True)
                return model.to("cuda:0")
            except Exception:
                return model.to("cpu")
        return model.to("cpu")

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

    def _encode_docs(self, docs_text: List[str]) -> np.ndarray:
        vectors = []
        start = 0
        dynamic_batch = self.batch_size
        total = len(docs_text)
        reported = 0
        print(
            f"🔢 Dense encoding start: docs={total}, initial_batch={dynamic_batch}, device={'cuda' if self._is_cuda_model() else 'cpu'}",
            flush=True,
        )
        while start < total:
            end = min(total, start + dynamic_batch)
            batch = docs_text[start:end]
            try:
                emb = self.model.encode(batch)
                vectors.append(np.asarray(emb, dtype=np.float32))
                start = end
                if start >= reported + 500 or start == total:
                    reported = start
                    print(
                        f"  ↳ dense encoded {start}/{total} docs (batch={dynamic_batch}, device={'cuda' if self._is_cuda_model() else 'cpu'})",
                        flush=True,
                    )
            except RuntimeError as exc:
                if not self._is_oom_error(exc):
                    raise

                if self._is_cuda_model() and dynamic_batch > 1:
                    dynamic_batch = max(1, dynamic_batch // 2)
                    self._clear_cuda_cache()
                    print(
                        f"⚠️ Dense OOM: reduce embed batch size to {dynamic_batch} and retry",
                        flush=True,
                    )
                    continue

                if self._is_cuda_model():
                    print("⚠️ Dense OOM at batch_size=1: switch dense encoding to CPU", flush=True)
                    dynamic_batch = 1
                    self._switch_to_cpu()
                    continue

                raise

        mat = np.vstack(vectors) if vectors else np.zeros((0, 1), dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    def query_scores(self, query: str) -> np.ndarray:
        if self.matrix.shape[0] == 0:
            return np.zeros((0,), dtype=np.float32)
        try:
            q = np.asarray(self.model.encode([query])[0], dtype=np.float32)
        except RuntimeError as exc:
            if not self._is_oom_error(exc) or not self._is_cuda_model():
                raise
            print("⚠️ Dense query OOM: switch dense query encoding to CPU")
            self._switch_to_cpu()
            q = np.asarray(self.model.encode([query])[0], dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return np.zeros((self.matrix.shape[0],), dtype=np.float32)
        q = q / q_norm
        return self.matrix @ q

    def top_k(self, query: str, k: int) -> List[Tuple[int, float]]:
        scores = self.query_scores(query)
        n = scores.shape[0]
        if n == 0:
            return []
        k = min(k, n)
        idx = np.argpartition(-scores, k - 1)[:k]
        ordered = idx[np.argsort(-scores[idx])]
        return [(int(i), float(scores[i])) for i in ordered]


def rrf_fuse(
    bm25_ranked: List[Tuple[int, float]],
    dense_ranked: List[Tuple[int, float]],
    top_k: int,
    rrf_k: int = 60,
) -> List[Tuple[int, float]]:
    fused: Dict[int, float] = defaultdict(float)
    for rank, (doc_id, _) in enumerate(bm25_ranked, start=1):
        fused[doc_id] += 1.0 / (rrf_k + rank)
    for rank, (doc_id, _) in enumerate(dense_ranked, start=1):
        fused[doc_id] += 1.0 / (rrf_k + rank)
    if not fused:
        return []
    return nlargest(top_k, fused.items(), key=lambda x: x[1])


def ensure_repo(repo_identifier: str, repos_dir: Path, fetch_remote: bool):
    repo_path = repos_dir / repo_identifier
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository not found locally: {repo_path}")
    if fetch_remote:
        run_cmd(["git", "-C", str(repo_path), "fetch", "--all", "--tags"], check=True)
    return repo_path


def checkout_commit(repo_path: Path, commit: str):
    run_cmd(["git", "-C", str(repo_path), "checkout", "--detach", "--quiet", commit], check=True)


def build_doc_text(method: MethodDoc) -> str:
    source_prefix = method.source_code[:3000] if method.source_code else ""
    return "\n".join(
        [
            method.signature or "",
            method.file_path or "",
            method.doc_string or "",
            source_prefix,
        ]
    )


def write_result(
    output_file: Path,
    instance_id: str,
    baseline_name: str,
    methods: List[MethodDoc],
    ranked: List[Tuple[int, float]],
):
    payload_methods = [methods[idx].to_result(score) for idx, score in ranked]
    payload = {
        "related_entities": {
            "methods": payload_methods,
            "classes": [],
            "issues": [],
        },
        "artifact_stats": {},
        "kg_params": {"baseline": baseline_name},
        "run_meta": {
            "instance_id": instance_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "baseline": baseline_name,
        },
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(payload, f, separators=(",", ":"))


def compose_query_text(item: dict, include_hints: bool = False) -> str:
    problem = item.get("problem_statement") or ""
    if not include_hints:
        return problem.strip()
    hints = item.get("hints_text") or ""
    return (problem + "\n" + hints).strip()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Export three non-KG retrieval baselines over repository code: "
            "BM25, Jina embedding cosine, and BM25+Dense hybrid (RRF)."
        )
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT_ROOT, help="Output root directory")
    parser.add_argument("--repos-dir", default=DEFAULT_REPOS_DIR, help="Local repos root")
    parser.add_argument(
        "--instance-ids",
        default=DEFAULT_IDS_FILE,
        help="JSONL with instance_id entries (default: SWE-bench_Verified_ids.jsonl)",
    )
    parser.add_argument(
        "--dataset-arrow",
        default=None,
        help="Optional SWE-bench Verified test arrow path; auto-discover if omitted.",
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Top-k methods per baseline")
    parser.add_argument(
        "--fusion-depth",
        type=int,
        default=200,
        help="How many docs from each ranker to fuse for hybrid RRF",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only process first N instances")
    parser.add_argument("--fetch-remote", action="store_true", help="Fetch before checkout")
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--embed-batch-size", type=int, default=1, help="Dense embedding batch size")
    hint_group = parser.add_mutually_exclusive_group()
    hint_group.add_argument(
        "--include-hints",
        action="store_true",
        help="Append hints_text to the problem_statement query.",
    )
    hint_group.add_argument("--exclude-hints", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--bm25-tag", default=DEFAULT_BM25_TAG, help="Run-id dir for BM25")
    parser.add_argument("--dense-tag", default=DEFAULT_DENSE_TAG, help="Run-id dir for Dense")
    parser.add_argument("--hybrid-tag", default=DEFAULT_HYBRID_TAG, help="Run-id dir for Hybrid")
    args = parser.parse_args()

    output_root = Path(args.output)
    repos_dir = Path(args.repos_dir)
    target_ids = load_target_instance_ids(Path(args.instance_ids) if args.instance_ids else None)
    arrow_path = Path(args.dataset_arrow) if args.dataset_arrow else discover_verified_arrow()
    print(f"Using dataset arrow: {arrow_path}")

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

    print(f"Total instances to process: {len(items)}")
    if not items:
        return

    run_tags = {
        "bm25": args.bm25_tag,
        "dense": args.dense_tag,
        "hybrid": args.hybrid_tag,
    }
    for tag in run_tags.values():
        (output_root / tag).mkdir(parents=True, exist_ok=True)

    grouped: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for item in items:
        instance_id = item["instance_id"]
        repo_identifier = instance_id.rsplit("-", 1)[0]
        base_commit = item.get("base_commit")
        if not base_commit:
            print(f"⚠️ Missing base_commit, skip {instance_id}")
            continue
        grouped[(repo_identifier, base_commit)].append(item)

    total_groups = len(grouped)
    for group_idx, ((repo_identifier, base_commit), group_items) in enumerate(grouped.items(), start=1):
        pending_items = []
        for item in group_items:
            instance_id = item["instance_id"]
            targets = [
                output_root / run_tags["bm25"] / f"{instance_id}.json",
                output_root / run_tags["dense"] / f"{instance_id}.json",
                output_root / run_tags["hybrid"] / f"{instance_id}.json",
            ]
            if args.force or any(not p.exists() for p in targets):
                pending_items.append(item)
        if not pending_items:
            print(f"[{group_idx}/{total_groups}] ✅ Skip {repo_identifier}@{base_commit[:8]} (all done)")
            continue

        print(
            f"[{group_idx}/{total_groups}] 🚀 Building corpus for {repo_identifier}@{base_commit[:8]} "
            f"(instances: {len(pending_items)})"
        )
        repo_path = ensure_repo(repo_identifier, repos_dir, args.fetch_remote)
        try:
            checkout_commit(repo_path, base_commit)
        except subprocess.CalledProcessError:
            print(f"❌ Checkout failed for {repo_identifier}@{base_commit}, skipping group")
            continue

        methods = build_method_corpus(repo_path)
        if not methods:
            print(f"⚠️ No methods parsed for {repo_identifier}@{base_commit[:8]}, writing empty outputs")
            for item in pending_items:
                instance_id = item["instance_id"]
                for baseline_name, tag in run_tags.items():
                    out = output_root / tag / f"{instance_id}.json"
                    if out.exists() and not args.force:
                        continue
                    write_result(out, instance_id, baseline_name, [], [])
            continue

        docs_tokens = [tokenize(build_doc_text(m)) for m in methods]
        bm25_index = BM25Index(docs_tokens)
        dense_index = DenseIndex([build_doc_text(m) for m in methods], batch_size=args.embed_batch_size)

        for item in pending_items:
            instance_id = item["instance_id"]
            query = compose_query_text(item, include_hints=args.include_hints)
            if not query:
                query = instance_id

            bm25_top = bm25_index.top_k(tokenize(query), args.top_k)
            dense_top = dense_index.top_k(query, args.top_k)
            bm25_fuse = bm25_index.top_k(tokenize(query), args.fusion_depth)
            dense_fuse = dense_index.top_k(query, args.fusion_depth)
            hybrid_top = rrf_fuse(bm25_fuse, dense_fuse, args.top_k)

            outputs = {
                "bm25": (output_root / run_tags["bm25"] / f"{instance_id}.json", bm25_top),
                "dense": (output_root / run_tags["dense"] / f"{instance_id}.json", dense_top),
                "hybrid": (output_root / run_tags["hybrid"] / f"{instance_id}.json", hybrid_top),
            }
            for baseline_name, (out_file, ranked) in outputs.items():
                if out_file.exists() and not args.force:
                    continue
                write_result(out_file, instance_id, baseline_name, methods, ranked)
            print(
                f"  ✅ {instance_id}: bm25={len(bm25_top)} dense={len(dense_top)} hybrid={len(hybrid_top)}"
            )

    print("===========================================")
    print("🎉 Baseline export finished")
    print(f"Output root: {output_root}")
    print(
        f"Run tags: bm25={run_tags['bm25']} dense={run_tags['dense']} hybrid={run_tags['hybrid']}"
    )
    print("===========================================")


if __name__ == "__main__":
    main()
