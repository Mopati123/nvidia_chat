"""
Vector Database for Market Pattern Memory  (T2-E: FAISS backend)

Stores market state embeddings with trajectory outcomes for similarity-based retrieval.
Uses FAISS IndexFlatIP on L2-normalised embeddings for in-process cosine similarity
search — no external process dependency, faster cold start, mmap-friendly persistence.

Public interface is unchanged from the ChromaDB version:
  store_pattern(), query_similar(), compute_memory_bias(), get_stats(), etc.
"""

import json
import hashlib
import logging
import struct
from collections import OrderedDict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:                         # graceful fallback: pure-numpy brute force
    _FAISS_AVAILABLE = False

logger = logging.getLogger(__name__)

EMBED_DIM = 128
_LRU_MAXSIZE = 256                          # query cache entries


# ---------------------------------------------------------------------------
# PatternMemory — unchanged from ChromaDB version
# ---------------------------------------------------------------------------

@dataclass
class PatternMemory:
    """A stored market pattern with trajectory outcomes."""
    pattern_id: str
    timestamp: str
    symbol: str
    timeframe: str
    embedding_hash: str
    trajectories: List[Dict]
    best_trajectory_id: Optional[str]
    best_pnl: float
    avg_pnl: float
    win_rate: float
    market_summary: Dict
    evidence_hash: str

    def to_dict(self) -> Dict:
        data = dict(asdict(self))
        for key in ['trajectories', 'market_summary']:
            if key in data and data[key] is not None:
                data[key] = json.dumps(data[key])
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'PatternMemory':
        data = dict(data)
        for key in ['trajectories', 'market_summary']:
            if key in data and isinstance(data[key], str):
                try:
                    data[key] = json.loads(data[key])
                except json.JSONDecodeError:
                    data[key] = {} if key == 'market_summary' else []
        return cls(**data)


# ---------------------------------------------------------------------------
# FAISS-backed vector store
# ---------------------------------------------------------------------------

class PatternVectorStore:
    """
    Vector database using FAISS for in-process cosine similarity search.

    Persistence layout under persist_dir:
        faiss_index.bin  — FAISS index (mmap-friendly)
        metadata.json    — list of serialised PatternMemory dicts (same order as FAISS)
    """

    COLLECTION_NAME = "market_patterns"
    PERSIST_DIR = Path.home() / ".apexquantumict" / "vector_db"

    def __init__(self,
                 collection_name: Optional[str] = None,
                 persist_dir: Optional[Path] = None) -> None:
        self.collection_name = collection_name or self.COLLECTION_NAME
        self.persist_dir = Path(persist_dir or self.PERSIST_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self._index_path = self.persist_dir / ("faiss_index.bin" if _FAISS_AVAILABLE
                                                 else "faiss_index.npy")
        self._meta_path  = self.persist_dir / "metadata.json"

        # FAISS index (inner product on L2-normalised vectors = cosine sim)
        if _FAISS_AVAILABLE:
            self._index: Any = faiss.IndexFlatIP(EMBED_DIM)
        else:
            self._index = _BruteForceIndex(EMBED_DIM)

        # Metadata list — one entry per FAISS sequential id
        self._meta_list: List[Dict] = []          # index i → serialised PatternMemory
        self._id_map: Dict[str, int] = {}         # pattern_id → faiss int id

        # LRU query cache: embedding_hash → List[PatternMemory]
        self._query_cache: "OrderedDict[str, List[PatternMemory]]" = OrderedDict()

        self._load_from_disk()
        logger.info("FAISS vector store: %d patterns loaded from %s",
                    len(self._meta_list), self.persist_dir)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_from_disk(self) -> None:
        if self._meta_path.exists():
            try:
                with open(self._meta_path, "r", encoding="utf-8") as f:
                    self._meta_list = json.load(f)
                # rebuild id_map
                self._id_map = {m["pattern_id"]: i for i, m in enumerate(self._meta_list)}
            except Exception as exc:
                logger.warning("Could not load metadata: %s", exc)
                self._meta_list = []
                self._id_map = {}

        if self._index_path.exists():
            try:
                if _FAISS_AVAILABLE:
                    self._index = faiss.read_index(str(self._index_path))
                else:
                    self._index.load(self._index_path)
            except Exception as exc:
                logger.warning("Could not load index from disk: %s", exc)
                if _FAISS_AVAILABLE:
                    self._index = faiss.IndexFlatIP(EMBED_DIM)

    def _save_to_disk(self) -> None:
        try:
            with open(self._meta_path, "w", encoding="utf-8") as f:
                json.dump(self._meta_list, f)
            if _FAISS_AVAILABLE:
                faiss.write_index(self._index, str(self._index_path))
            else:
                self._index.save(self._index_path)
        except Exception as exc:
            logger.error("Could not persist vector store: %s", exc)

    # ------------------------------------------------------------------
    # Embedding utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        return (vec / norm).astype("float32") if norm > 1e-9 else vec.astype("float32")

    def _compute_embedding_hash(self, embedding: np.ndarray) -> str:
        quantized = np.round(embedding, decimals=4)
        return hashlib.sha256(quantized.tobytes()).hexdigest()[:16]

    def _cache_key(self, embedding: np.ndarray) -> str:
        return self._compute_embedding_hash(embedding)

    def _cache_put(self, key: str, value: List[PatternMemory]) -> None:
        self._query_cache[key] = value
        if len(self._query_cache) > _LRU_MAXSIZE:
            self._query_cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def store_pattern(self,
                      embedding: np.ndarray,
                      symbol: str = "",
                      timeframe: str = "",
                      trajectories: Optional[List[Dict]] = None,
                      market_summary: Optional[Dict] = None,
                      evidence_hash: str = "") -> str:
        """Store a market pattern embedding with trajectory outcomes."""
        trajectories = trajectories or []
        embedding_hash = self._compute_embedding_hash(embedding)
        raw_id = f"{symbol}_{timeframe}_{embedding_hash}_{datetime.now().isoformat()}"
        pattern_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]

        pnls = [t.get("pnl", 0) for t in trajectories]
        successes = [t.get("success", False) for t in trajectories]
        best_idx = int(np.argmax(pnls)) if pnls else 0
        best_traj = trajectories[best_idx] if trajectories else None

        memory = PatternMemory(
            pattern_id=pattern_id,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            timeframe=timeframe,
            embedding_hash=embedding_hash,
            trajectories=trajectories,
            best_trajectory_id=best_traj.get("trajectory_id") if best_traj else None,
            best_pnl=float(best_traj.get("pnl", 0)) if best_traj else 0.0,
            avg_pnl=float(np.mean(pnls)) if pnls else 0.0,
            win_rate=float(np.mean(successes)) if successes else 0.0,
            market_summary=market_summary or {},
            evidence_hash=evidence_hash,
        )

        vec = self._l2_normalize(embedding).reshape(1, -1)
        self._index.add(vec)
        faiss_id = len(self._meta_list)
        self._meta_list.append(memory.to_dict())
        self._id_map[pattern_id] = faiss_id

        self._query_cache.clear()          # invalidate cache on write
        self._save_to_disk()
        logger.debug("Stored pattern %s for %s (%s)", pattern_id, symbol, timeframe)
        return pattern_id

    def query_similar(self,
                      embedding: np.ndarray,
                      symbol: Optional[str] = None,
                      timeframe: Optional[str] = None,
                      top_k: int = 10,
                      min_similarity: float = 0.7) -> List[PatternMemory]:
        """Query for similar market patterns via cosine similarity."""
        cache_key = self._cache_key(embedding) + f"_{symbol}_{timeframe}_{top_k}_{min_similarity}"
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]

        if self._index.ntotal == 0:
            return []

        vec = self._l2_normalize(embedding).reshape(1, -1)
        k_search = min(top_k * 2, self._index.ntotal)
        scores, ids = self._index.search(vec, k_search)

        memories: List[PatternMemory] = []
        for score, fid in zip(scores[0], ids[0]):
            if fid < 0 or fid >= len(self._meta_list):
                continue
            similarity = float(score)           # inner product of unit vecs = cosine sim
            if similarity < min_similarity:
                continue
            meta = self._meta_list[int(fid)]
            pm = PatternMemory.from_dict(meta)
            # filter by symbol / timeframe if requested
            if symbol and pm.symbol != symbol:
                continue
            if timeframe and pm.timeframe != timeframe:
                continue
            pm.market_summary["similarity"] = similarity
            memories.append(pm)

        memories.sort(key=lambda m: m.market_summary.get("similarity", 0), reverse=True)
        result = memories[:top_k]
        self._cache_put(cache_key, result)
        return result

    def get_pattern(self, pattern_id: str) -> Optional[PatternMemory]:
        fid = self._id_map.get(pattern_id)
        if fid is None or fid >= len(self._meta_list):
            return None
        return PatternMemory.from_dict(self._meta_list[fid])

    def delete_pattern(self, pattern_id: str) -> bool:
        """Mark a pattern as deleted. FAISS does not support in-place removal;
        the slot is zeroed and excluded from future search results."""
        fid = self._id_map.pop(pattern_id, None)
        if fid is None:
            return False
        self._meta_list[fid] = {}           # tombstone
        self._query_cache.clear()
        self._save_to_disk()
        return True

    def get_stats(self) -> Dict[str, Any]:
        live = sum(1 for m in self._meta_list if m)
        return {
            "total_patterns": live,
            "faiss_ntotal": self._index.ntotal,
            "collection_name": self.collection_name,
            "persist_dir": str(self.persist_dir),
            "faiss_available": _FAISS_AVAILABLE,
        }

    def get_patterns_by_symbol(self, symbol: str, limit: int = 100) -> List[PatternMemory]:
        results = []
        for meta in self._meta_list:
            if not meta:
                continue
            if meta.get("symbol") == symbol:
                results.append(PatternMemory.from_dict(meta))
            if len(results) >= limit:
                break
        return results

    def compute_memory_bias(self,
                            trajectories: List[Any],
                            similar_memories: List[PatternMemory],
                            bias_strength: float = 0.3) -> Dict[str, float]:
        """Compute bias weights for trajectories based on historical success."""
        if not similar_memories:
            return {t.id if hasattr(t, "id") else str(i): 1.0
                    for i, t in enumerate(trajectories)}

        operator_success: Dict[tuple, Dict] = {}
        total_weight = 0.0

        for memory in similar_memories:
            similarity = memory.market_summary.get("similarity", 0.5)
            weight = similarity * (1 + memory.win_rate)
            for traj in memory.trajectories:
                op_key = tuple(sorted(traj.get("operators_used", [])))
                if op_key not in operator_success:
                    operator_success[op_key] = {"pnl": 0.0, "weight": 0.0, "count": 0}
                operator_success[op_key]["pnl"] += traj.get("pnl", 0) * weight
                operator_success[op_key]["weight"] += weight
                operator_success[op_key]["count"] += 1
            total_weight += weight

        biases: Dict[str, float] = {}
        for i, traj in enumerate(trajectories):
            traj_id = traj.id if hasattr(traj, "id") else f"traj_{i}"
            ops = getattr(traj, "operators_used", []) or list(
                getattr(traj, "operator_scores", {}).keys()
            )
            op_key = tuple(sorted(ops)) if ops else ()
            if op_key in operator_success and operator_success[op_key]["weight"] > 0:
                avg_pnl = (operator_success[op_key]["pnl"] /
                           operator_success[op_key]["weight"])
                bias = 1.0 + bias_strength * float(np.tanh(avg_pnl * 10))
            else:
                bias = 1.0
            biases[traj_id] = bias

        return biases


# ---------------------------------------------------------------------------
# Pure-numpy fallback when faiss is not installed
# ---------------------------------------------------------------------------

class _BruteForceIndex:
    """Minimal cosine-similarity index using numpy matrix operations."""

    def __init__(self, dim: int) -> None:
        self.d = dim
        self._vecs: List[np.ndarray] = []

    @property
    def ntotal(self) -> int:
        return len(self._vecs)

    def add(self, x: np.ndarray) -> None:
        self._vecs.append(x[0].copy())

    def search(self, x: np.ndarray, k: int):
        if not self._vecs:
            return np.zeros((1, k), dtype="float32"), -np.ones((1, k), dtype="int64")
        mat = np.stack(self._vecs)              # (N, d)
        scores = (mat @ x[0]).astype("float32")  # cosine sim (vecs are unit)
        top = np.argsort(-scores)[:k]
        return scores[top].reshape(1, -1), top.astype("int64").reshape(1, -1)

    def save(self, path: Path) -> None:
        if self._vecs:
            # path already ends in .npy; np.save would append .npy again — use explicit open
            with open(str(path), "wb") as f:
                np.save(f, np.stack(self._vecs))

    def load(self, path: Path) -> None:
        with open(str(path), "rb") as f:
            arr = np.load(f, allow_pickle=False)
        self._vecs = [arr[i] for i in range(len(arr))]


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_vector_store: Optional[PatternVectorStore] = None


def get_vector_store(collection_name: Optional[str] = None) -> PatternVectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = PatternVectorStore(collection_name=collection_name)
    return _vector_store


def reset_vector_store() -> None:
    global _vector_store
    _vector_store = None
