#!/usr/bin/env python3
# EXECUTION: EITHER — runs in sidecar container or on host
"""
CLIP Frame Index — persistent vector search over WineBot frame archives.

Stores 512-dim CLIP embeddings with metadata, supports semantic search
via cosine similarity (FAISS IndexFlatIP), and persists to disk as JSONL
+ NumPy memmap for fast reload.

Usage:
  from clip_index import FrameIndex
  idx = FrameIndex("/data/frame_index")
  idx.add("frame_001.png", embedding, {"scene": "save_dialog", "workflow": "demo"})
  results = idx.search("a save dialog with a text field", k=10)
  idx.save()
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np


class FrameIndex:
    """Persistent vector index of CLIP-embedded frames.

    Stores embeddings in a NumPy memmap file for large indexes that
    don't fit in memory. Uses FAISS for accelerated search when
    available, falling back to brute-force NumPy.
    """

    DIM = 512  # CLIP ViT-B-32 embedding dimension

    def __init__(self, index_dir: str):
        """
        Args:
            index_dir: Directory for index files (created if needed).
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self._embeddings: np.ndarray | None = None  # (N, 512)
        self._metadata: list[dict] = []                 # one per frame
        self._paths: list[str] = []                     # frame file paths
        self._n: int = 0
        self._dirty: bool = False

        # Try to import FAISS for accelerated search
        try:
            import faiss  # noqa: F401
            self._has_faiss = True
        except ImportError:
            self._has_faiss = False

        self._faiss_index = None

        # Load existing index if present
        self._load()

    # ── Add ─────────────────────────────────────────────────────────────────

    def add(self, path: str, embedding: np.ndarray, metadata: dict | None = None):
        """Add a frame embedding to the index.

        Args:
            path: File path or identifier for the frame.
            embedding: 512-dim normalized CLIP embedding.
            metadata: Optional dict with scene_type, workflow_name,
                      timestamp, generator_name, etc.
        """
        emb = np.asarray(embedding, dtype=np.float32).flatten()
        if len(emb) != self.DIM:
            raise ValueError(f"Expected {self.DIM}-dim embedding, got {len(emb)}")

        # Normalize for cosine similarity
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm

        if self._embeddings is None:
            self._embeddings = np.empty((0, self.DIM), dtype=np.float32)

        self._embeddings = np.vstack([self._embeddings, emb])
        self._paths.append(str(path))
        self._metadata.append(metadata or {})
        self._n += 1
        self._dirty = True

    def add_batch(self, paths: list[str], embeddings: np.ndarray,
                   metadatas: list[dict] | None = None):
        """Add multiple frames efficiently.

        Args:
            paths: List of frame identifiers.
            embeddings: (N, 512) array of normalized embeddings.
            metadatas: Optional list of metadata dicts.
        """
        embs = np.asarray(embeddings, dtype=np.float32)
        if embs.ndim != 2 or embs.shape[1] != self.DIM:
            raise ValueError(
                f"Expected (N, {self.DIM}) embeddings, got {embs.shape}")

        # Normalize
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embs = embs / norms

        if self._embeddings is None:
            self._embeddings = np.empty((0, self.DIM), dtype=np.float32)

        self._embeddings = np.vstack([self._embeddings, embs])
        self._paths.extend(str(p) for p in paths)
        self._metadata.extend(metadatas or [{} for _ in paths])
        self._n = len(self._paths)
        self._dirty = True

    # ── Search ──────────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 10,
               clip_embedder=None) -> list[dict]:
        """Search frames by text query or embedding.

        Args:
            query: Text description to search for, OR a 512-dim
                   embedding vector (np.ndarray).
            k: Number of results to return.
            clip_embedder: CLIPSceneEmbedder instance for text embedding.
                           Required if query is a string.

        Returns:
            List of dicts: [{path, similarity, metadata, rank}, ...]
            sorted by similarity descending.
        """
        if self._n == 0:
            return []

        # Get query embedding
        if isinstance(query, str):
            if clip_embedder is None:
                raise ValueError(
                    "clip_embedder required for text queries")
            query_emb = clip_embedder.embed_text(query)
        else:
            query_emb = np.asarray(query, dtype=np.float32).flatten()

        # Normalize query
        query_emb = query_emb / (np.linalg.norm(query_emb) + 1e-8)

        if self._has_faiss and self._n > 1000:
            similarities = self._search_faiss(query_emb, k)
        else:
            similarities = self._search_numpy(query_emb, k)

        # Build results
        results = []
        for idx, sim in similarities:
            if idx < 0 or idx >= self._n:
                continue
            results.append({
                "path": self._paths[idx],
                "similarity": round(float(sim), 4),
                "metadata": self._metadata[idx],
                "rank": len(results) + 1,
            })

        return results[:k]

    def search_by_embedding(self, embedding: np.ndarray, k: int = 10) -> list[dict]:
        """Search by embedding vector instead of text."""
        return self.search(embedding, k=k)

    def _search_numpy(self, query_emb: np.ndarray,
                       k: int) -> list[tuple[int, float]]:
        """Brute-force cosine similarity search."""
        sims = np.dot(self._embeddings, query_emb)  # (N,)
        top_k = min(k, self._n)
        top_indices = np.argpartition(sims, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(sims[top_indices])[::-1]]
        return [(int(i), float(sims[i])) for i in top_indices]

    def _search_faiss(self, query_emb: np.ndarray,
                       k: int) -> list[tuple[int, float]]:
        """FAISS-accelerated search."""
        import faiss

        if self._faiss_index is None:
            self._faiss_index = faiss.IndexFlatIP(self.DIM)
            self._faiss_index.add(self._embeddings)

        query = query_emb.reshape(1, -1).astype(np.float32)
        scores, indices = self._faiss_index.search(query, k)
        return [(int(indices[0][i]), float(scores[0][i]))
                for i in range(len(scores[0])) if indices[0][i] >= 0]

    # ── Filtering ──────────────────────────────────────────────────────────

    def filter_by_scene(self, scene_type: str) -> list[int]:
        """Return indices of frames with a given scene type."""
        return [i for i, m in enumerate(self._metadata)
                if m.get("scene_type") == scene_type
                or m.get("generator") == scene_type]

    def filter_by_workflow(self, workflow_name: str) -> list[int]:
        """Return indices of frames from a given workflow."""
        return [i for i, m in enumerate(self._metadata)
                if m.get("workflow") == workflow_name]

    def filter_by_timerange(self, start_ms: float, end_ms: float) -> list[int]:
        """Return indices of frames within a time range."""
        return [i for i, m in enumerate(self._metadata)
                if start_ms <= m.get("timestamp_ms", 0) <= end_ms]

    def find_by_path(self, frame_path: str) -> dict | None:
        """Look up a frame by its path and return its embedding + metadata.

        Args:
            frame_path: Full or relative path to the frame file (matched
                        against the tail of stored paths).

        Returns:
            Dict with {"path", "embedding", "metadata"} or None if not found.
        """
        path_tail = frame_path.replace("\\", "/").split("/")[-1]
        for i in range(self._n):
            stored = self._paths[i].replace("\\", "/")
            if stored.endswith(path_tail):
                return {
                    "path": self._paths[i],
                    "embedding": self._embeddings[i].copy(),
                    "metadata": self._metadata[i],
                    "index": i,
                }
        return None

    # ── Persistence ────────────────────────────────────────────────────────

    def save(self):
        """Save the index to disk."""
        if not self._dirty:
            return

        t0 = time.time()

        # Save embeddings as NumPy memmap (fast reload for large indexes)
        emb_path = self.index_dir / "embeddings.npy"
        np.save(str(emb_path), self._embeddings)

        # Save metadata as JSONL (one entry per line)
        meta_path = self.index_dir / "metadata.jsonl"
        with open(meta_path, "w") as f:
            for i in range(self._n):
                entry = {
                    "path": self._paths[i],
                    "metadata": self._metadata[i],
                }
                f.write(json.dumps(entry) + "\n")

        self._dirty = False
        elapsed = time.time() - t0
        size_mb = os.path.getsize(emb_path) / (1024 * 1024)
        print(f"[index] Saved {self._n} frames ({size_mb:.1f}MB) "
              f"in {elapsed:.1f}s", file=sys.stderr)

    def _load(self):
        """Load index from disk if it exists."""
        emb_path = self.index_dir / "embeddings.npy"
        meta_path = self.index_dir / "metadata.jsonl"

        if not emb_path.exists() or not meta_path.exists():
            return

        t0 = time.time()
        self._embeddings = np.load(str(emb_path))
        self._paths = []
        self._metadata = []

        with open(meta_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                self._paths.append(entry["path"])
                self._metadata.append(entry.get("metadata", {}))

        self._n = len(self._paths)
        elapsed = time.time() - t0
        size_mb = os.path.getsize(emb_path) / (1024 * 1024)
        print(f"[index] Loaded {self._n} frames ({size_mb:.1f}MB) "
              f"in {elapsed:.1f}s", file=sys.stderr)

    # ── Stats ──────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return index statistics."""
        scene_counts: dict[str, int] = {}
        for m in self._metadata:
            scene = m.get("scene_type", m.get("generator", "unknown"))
            scene_counts[scene] = scene_counts.get(scene, 0) + 1

        return {
            "total_frames": self._n,
            "embedding_dim": self.DIM,
            "size_on_disk_mb": round(
                (self.index_dir / "embeddings.npy").stat().st_size
                / (1024 * 1024), 1
            ) if (self.index_dir / "embeddings.npy").exists() else 0,
            "scene_distribution": scene_counts,
            "has_faiss": self._has_faiss,
        }

    def __len__(self):
        return self._n

    def __repr__(self):
        return f"FrameIndex(n={self._n}, dim={self.DIM}, dir={self.index_dir})"
