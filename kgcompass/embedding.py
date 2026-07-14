import hashlib
import os
import sqlite3
import threading
import traceback
from transformers import AutoConfig, AutoModel
import numpy as np

MODEL_NAME = "jinaai/jina-embeddings-v2-base-code"
DEFAULT_MODEL_REVISION = "516f4baf13dec4ddddda8631e019b5737c8bc250"
MODEL_REVISION = os.getenv(
    "KGCOMPASS_EMBEDDING_REVISION",
    DEFAULT_MODEL_REVISION,
)


def _patch_transformers_pruning_helper():
    """Keep cached Jina remote code compatible with newer transformers."""
    import transformers.pytorch_utils as pytorch_utils

    if hasattr(pytorch_utils, "find_pruneable_heads_and_indices"):
        return

    def find_pruneable_heads_and_indices(heads, n_heads, head_size, already_pruned_heads):
        import torch

        mask = torch.ones(n_heads, head_size)
        heads = set(heads) - already_pruned_heads
        for head in heads:
            head = head - sum(1 if h < head else 0 for h in already_pruned_heads)
            mask[head] = 0
        mask = mask.view(-1).contiguous().eq(1)
        index = torch.arange(len(mask), dtype=torch.long)[mask].long()
        return heads, index

    pytorch_utils.find_pruneable_heads_and_indices = find_pruneable_heads_and_indices


def _patch_model_runtime_helpers(model):
    import torch

    if hasattr(model, "embeddings") and hasattr(model.embeddings, "position_ids"):
        max_positions = model.embeddings.position_ids.shape[1]
        device = model.embeddings.position_ids.device
        model.embeddings.position_ids = torch.arange(max_positions, device=device).expand((1, -1))
        model.embeddings.token_type_ids = torch.zeros((1, max_positions), dtype=torch.long, device=device)

    if hasattr(model, "get_head_mask"):
        return model

    def get_head_mask(head_mask, num_hidden_layers, is_attention_chunked=False):
        if head_mask is None:
            return [None] * num_hidden_layers

        if head_mask.dim() == 1:
            head_mask_5d = head_mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1).unsqueeze(-1)
            head_mask_5d = head_mask_5d.expand(num_hidden_layers, -1, -1, -1, -1)
        elif head_mask.dim() == 2:
            head_mask_5d = head_mask.unsqueeze(1).unsqueeze(-1).unsqueeze(-1)
        else:
            head_mask_5d = head_mask

        if head_mask_5d.dim() != 5:
            raise ValueError(f"head_mask.dim != 5, got {head_mask_5d.dim()}")
        if is_attention_chunked:
            head_mask_5d = head_mask_5d.unsqueeze(-1)

        dtype = next(model.parameters()).dtype
        return head_mask_5d.to(dtype=dtype)

    model.get_head_mask = get_head_mask
    return model


class Embedding:
    _instance = None
    _model = None
    _cache = None
    _cache_lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            print("创建新的 Embedding 实例")
            cls._instance = super().__new__(cls)
            
            try:
                print("初始化 pipeline...")
                # 打印缓存路径信息，帮助调试
                cache_dir = os.environ.get('HF_HOME') or os.path.expanduser('~/.cache/huggingface')
                print(f"HuggingFace 缓存目录: {cache_dir}")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                os.environ.setdefault("HF_HUB_OFFLINE", "1")

                # 严格从本地缓存加载，禁止联网探测
                _patch_transformers_pruning_helper()
                config = AutoConfig.from_pretrained(
                    MODEL_NAME,
                    revision=MODEL_REVISION,
                    trust_remote_code=True,
                    local_files_only=True,
                )
                for name, value in {
                    "is_decoder": False,
                    "add_cross_attention": False,
                    "pruned_heads": {},
                }.items():
                    if not hasattr(config, name):
                        setattr(config, name, value)
                device = os.environ.get("KGCOMPASS_EMBEDDING_DEVICE", "cuda:0")
                cls._model = _patch_model_runtime_helpers(AutoModel.from_pretrained(
                    MODEL_NAME,
                    revision=MODEL_REVISION,
                    config=config,
                    trust_remote_code=True,
                    local_files_only=True,
                )).to(device)
                print(f"embedding model 初始化成功（仅本地缓存，device={device}）")

                cache_path = os.getenv("KGCOMPASS_EMBEDDING_CACHE", "").strip()
                if cache_path:
                    cache_path = os.path.abspath(os.path.expanduser(cache_path))
                    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
                    cls._cache = sqlite3.connect(
                        cache_path,
                        check_same_thread=False,
                        isolation_level=None,
                        timeout=60,
                    )
                    cls._cache.execute("PRAGMA journal_mode=WAL")
                    cls._cache.execute("PRAGMA synchronous=NORMAL")
                    cls._cache.execute("PRAGMA busy_timeout=60000")
                    cls._cache.execute(
                        "CREATE TABLE IF NOT EXISTS embeddings "
                        "(cache_key TEXT PRIMARY KEY, vector BLOB NOT NULL)"
                    )
                    print(f"embedding cache 已启用: {cache_path}")
                        
            except Exception as e:
                print(f"pipeline 初始化失败: {e}")
                cache_dir = os.environ.get('HF_HOME') or os.path.expanduser('~/.cache/huggingface')
                model_cache_path = os.path.join(cache_dir, "hub", "models--jinaai--jina-embeddings-v2-base-code")
                print(f"提示: 请确保模型已下载到本地缓存目录")
                print(f"预期模型路径: {model_cache_path}")
                print(f"如果路径不存在，请检查模型是否正确下载")
                raise
        return cls._instance
    
    def __init__(self):
        pass

    def get_embedding(self, text):
        """获取文本的 embedding"""
        try:
            if text is None:
                print("警告: 输入文本为 None")
                return None
                
            if not isinstance(text, str):
                print(f"警告: 输入文本类型不是字符串，而是 {type(text)}")
                text = str(text)
                
            if not text.strip():
                print("警告: 输入文本为空")
                return None
            
            cache_key = hashlib.sha256(
                (
                    MODEL_NAME
                    + "@"
                    + MODEL_REVISION
                    + "\0"
                    + text
                ).encode("utf-8")
            ).hexdigest()
            legacy_cache_key = hashlib.sha256(
                (MODEL_NAME + "\0" + text).encode("utf-8")
            ).hexdigest()
            if self._cache is not None:
                try:
                    with self._cache_lock:
                        if MODEL_REVISION == DEFAULT_MODEL_REVISION:
                            row = self._cache.execute(
                                "SELECT vector FROM embeddings WHERE cache_key IN (?, ?) "
                                "ORDER BY cache_key = ? DESC LIMIT 1",
                                (cache_key, legacy_cache_key, cache_key),
                            ).fetchone()
                        else:
                            row = self._cache.execute(
                                "SELECT vector FROM embeddings WHERE cache_key = ?",
                                (cache_key,),
                            ).fetchone()
                except sqlite3.Error as error:
                    print(f"embedding cache 读取失败，将重新计算: {error}")
                    row = None
                if row is not None:
                    return np.frombuffer(row[0], dtype="<f4").tolist()

            embedding = self._model.encode([text])[0].tolist()
            if self._cache is not None:
                vector = np.asarray(embedding, dtype="<f4").tobytes()
                try:
                    with self._cache_lock:
                        self._cache.execute(
                            "INSERT OR IGNORE INTO embeddings(cache_key, vector) VALUES (?, ?)",
                            (cache_key, vector),
                        )
                except sqlite3.Error as error:
                    print(f"embedding cache 写入失败，已保留当前结果: {error}")
            return embedding
            
        except Exception as e:
            print(f"获取 embedding 时出错: {e}")
            print(f"model 状态: {self._model}")
            print(traceback.format_exc())
            return None

    def _cos_similarity(self, vec1, vec2):
        """计算两个向量的余弦相似度"""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return np.dot(vec1, vec2) / (norm1 * norm2)

    def text_similarity(self, text1, text2):
        """计算两个文本的相似度"""
        vec1 = self.get_embedding(text1)
        vec2 = self.get_embedding(text2)
        if vec1 is None or vec2 is None:
            return 0.0
        return self._cos_similarity(vec1, vec2)
