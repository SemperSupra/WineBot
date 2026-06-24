#!/usr/bin/env python3
# EXECUTION: IN_CONTAINER — requires GPU (or CPU fallback)
"""
CLIP-based scene embedding engine for WineBot.

Produces 512-dimensional semantic embeddings of UI screenshots,
enabling natural-language search, zero-shot scene classification,
and similarity matching across the frame archive.

Embedder selection via CLIP_BACKEND env var:
  CLIP_BACKEND=open_clip     (default, ViT-B-32, GPU, ~12ms)
  CLIP_BACKEND=onnx          (ONNX Runtime, CPU, ~50ms, no torch dependency)
  CLIP_BACKEND=none          (disabled)

Usage:
  from clip_embedder import get_clip_embedder
  clip = get_clip_embedder()
  embedding = clip.embed_image(image)         # → np.ndarray[512]
  similarity = clip.similarity(image, "text") # → float
  labels = clip.classify(image, ["a", "b"])   # → Dict[str, float]
"""

import os
import sys
from typing import Dict, List, Optional

import cv2
import numpy as np


class CLIPSceneEmbedder:
    """Base class for CLIP-based scene embedding backends."""

    name: str = "base"
    available: bool = False
    uses_gpu: bool = False
    dim: int = 512
    model_size_mb: float = 0.0

    def embed_image(self, image: np.ndarray) -> np.ndarray:
        """Embed a BGR screenshot into a semantic vector.

        Args:
            image: BGR image as numpy array (any resolution).

        Returns:
            512-dimensional normalized embedding vector.
        """
        raise NotImplementedError

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a text description into the same vector space.

        Args:
            text: Natural language description.

        Returns:
            512-dimensional normalized embedding vector.
        """
        raise NotImplementedError

    def similarity(self, image: np.ndarray, text: str) -> float:
        """Cosine similarity between an image and a text description.

        Args:
            image: BGR screenshot.
            text: Natural language query.

        Returns:
            Cosine similarity in [-1, 1]. Higher = better match.
        """
        img_emb = self.embed_image(image)
        txt_emb = self.embed_text(text)
        return float(np.dot(img_emb, txt_emb))

    def classify(self, image: np.ndarray, labels: List[str]) -> Dict[str, float]:
        """Zero-shot classification: which label best describes this image?

        Args:
            image: BGR screenshot.
            labels: List of candidate descriptions
                    (e.g. ["save dialog", "settings window", "error dialog"]).

        Returns:
            Dict mapping each label to its probability (softmax over similarities).
        """
        img_emb = self.embed_image(image)
        similarities = []
        for label in labels:
            txt_emb = self.embed_text(label)
            sim = float(np.dot(img_emb, txt_emb))
            similarities.append(sim)

        # Softmax for probability distribution
        sims = np.array(similarities)
        sims = sims - sims.max()  # Numerical stability
        probs = np.exp(sims * 100.0)  # Temperature-scaled (CLIP likes 100)
        probs = probs / probs.sum()

        return {label: round(float(p), 4) for label, p in zip(labels, probs)}

    def embed_batch(self, images: List[np.ndarray]) -> np.ndarray:
        """Embed multiple images efficiently.

        Args:
            images: List of BGR screenshots.

        Returns:
            (N, 512) array of normalized embeddings.
        """
        # Default: process one at a time. Backends can override with batched inference.
        return np.stack([self.embed_image(img) for img in images])


# ── OpenCLIP Backend ───────────────────────────────────────────────────────────

class OpenCLIPEmbedder(CLIPSceneEmbedder):
    """OpenCLIP ViT-B-32 via open_clip_torch. GPU-accelerated, ~12ms/image.

    Model: ViT-B-32 trained on LAION-2B (laion2b_s34b_b79k).
    88M params, 340MB image encoder + 160MB text encoder.
    512-dim embeddings, MIT license.
    """

    name = "open_clip"
    dim = 512
    model_size_mb = 500.0

    # Canonical model identifier
    MODEL_NAME = "ViT-B-32"
    PRETRAINED = "laion2b_s34b_b79k"

    def __init__(self):
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device = "cpu"

        try:
            import torch  # noqa: F401
            self._has_torch = True
        except ImportError:
            self._has_torch = False

        try:
            import open_clip  # noqa: F401
            self._has_open_clip = True
        except ImportError:
            self._has_open_clip = False

        self.available = self._has_torch and self._has_open_clip

    def _load_model(self):
        """Lazy-load the OpenCLIP model on first use."""
        if self._model is not None:
            return

        import torch
        import open_clip

        # Determine device
        if torch.cuda.is_available():
            self._device = "cuda"
            self.uses_gpu = True
        else:
            self._device = "cpu"

        print(f"[clip] Loading OpenCLIP {self.MODEL_NAME} "
              f"(pretrained={self.PRETRAINED}) on {self._device}...",
              file=sys.stderr)

        self._model, self._preprocess, self._tokenizer = (
            open_clip.create_model_and_transforms(
                self.MODEL_NAME, pretrained=self.PRETRAINED
            )
        )
        self._model = self._model.to(self._device)
        self._model.eval()

        # Count params for logging
        total_params = sum(p.numel() for p in self._model.parameters())
        print(f"[clip] Loaded: {total_params/1e6:.0f}M params, "
              f"dim={self.dim}, device={self._device}", file=sys.stderr)

    def embed_image(self, image: np.ndarray) -> np.ndarray:
        """Embed a BGR image using OpenCLIP."""
        self._load_model()
        if self._model is None:
            return np.zeros(self.dim, dtype=np.float32)

        import torch

        # Convert BGR to RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # OpenCLIP preprocess handles resize, center crop, normalize
        img_tensor = self._preprocess(Image.fromarray(rgb)).unsqueeze(0)
        img_tensor = img_tensor.to(self._device)

        with torch.no_grad(), torch.amp.autocast('cuda' if self._device == 'cuda' else 'cpu'):
            features = self._model.encode_image(img_tensor)
            features = features / features.norm(dim=-1, keepdim=True)

        return features.cpu().numpy().flatten().astype(np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        """Embed text using OpenCLIP tokenizer + text encoder."""
        self._load_model()
        if self._model is None:
            return np.zeros(self.dim, dtype=np.float32)

        import torch
        import open_clip

        tokens = open_clip.tokenize([text])
        tokens = tokens.to(self._device)

        with torch.no_grad(), torch.amp.autocast('cuda' if self._device == 'cuda' else 'cpu'):
            features = self._model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)

        return features.cpu().numpy().flatten().astype(np.float32)

    def embed_batch(self, images: List[np.ndarray]) -> np.ndarray:
        """Batch image embedding (GPU-efficient)."""
        self._load_model()
        if self._model is None or not images:
            return np.zeros((len(images), self.dim), dtype=np.float32)

        import torch
        from PIL import Image as PILImage

        batch = []
        for img in images:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            batch.append(self._preprocess(PILImage.fromarray(rgb)))
        batch_tensor = torch.stack(batch).to(self._device)

        with torch.no_grad(), torch.amp.autocast('cuda' if self._device == 'cuda' else 'cpu'):
            features = self._model.encode_image(batch_tensor)
            features = features / features.norm(dim=-1, keepdim=True)

        return features.cpu().numpy().astype(np.float32)


# Lazy import for PIL (used in preprocess path) — done at module level for OpenCLIP
try:
    from PIL import Image  # noqa: F401 (used by OpenCLIPEmbedder)
except ImportError:
    pass


# ── ONNX Backend ───────────────────────────────────────────────────────────────

class ONNXCLIPEmbedder(CLIPSceneEmbedder):
    """CLIP via ONNX Runtime — no PyTorch dependency, CPU-friendly.

    Requires pre-exported ONNX models in /models/clip/:
      - clip_vitb32_image.onnx  (340 MB)
      - clip_vitb32_text.onnx   (160 MB)

    Slower than OpenCLIP (~50ms vs ~12ms) but works without PyTorch
    and without a discrete GPU. Good for testing or CPU-only deployments.
    """

    name = "onnx_clip"
    dim = 512
    model_size_mb = 500.0

    def __init__(self):
        self._img_session = None
        self._txt_session = None
        self._available = False

        try:
            import onnxruntime  # noqa: F401
            self._has_onnx = True
        except ImportError:
            self._has_onnx = False

        if self._has_onnx:
            # Check if ONNX models exist
            img_path = os.path.join(
                os.environ.get("CLIP_MODEL_DIR", "/models/clip"),
                "clip_vitb32_image.onnx"
            )
            txt_path = os.path.join(
                os.environ.get("CLIP_MODEL_DIR", "/models/clip"),
                "clip_vitb32_text.onnx"
            )
            self._available = os.path.isfile(img_path) and os.path.isfile(txt_path)

        self.available = self._available

    def _load_model(self):
        if self._img_session is not None:
            return

        import onnxruntime as ort

        model_dir = os.environ.get("CLIP_MODEL_DIR", "/models/clip")
        img_path = os.path.join(model_dir, "clip_vitb32_image.onnx")
        txt_path = os.path.join(model_dir, "clip_vitb32_text.onnx")

        try:
            # Try GPU provider first, fall back to CPU
            providers = [
                ("CUDAExecutionProvider", {"device_id": 0}),
                "CPUExecutionProvider",
            ]
            self._img_session = ort.InferenceSession(img_path, providers=providers)
            self._txt_session = ort.InferenceSession(txt_path, providers=providers)

            actual_provider = self._img_session.get_providers()[0]
            self.uses_gpu = "CUDA" in actual_provider
            print(f"[clip_onnx] Loaded from {model_dir} "
                  f"(provider: {actual_provider})", file=sys.stderr)
        except Exception as e:
            print(f"[clip_onnx] Failed to load ONNX models: {e}", file=sys.stderr)
            self.available = False

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """CLIP-standard preprocessing: resize to 224×224, normalize."""
        # CLIP expects 224×224 RGB with mean/std normalization
        img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (224, 224))
        img = img.astype(np.float32) / 255.0

        # CLIP normalization constants
        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
        img = (img - mean) / std

        # CHW format
        img = np.transpose(img, (2, 0, 1))
        return np.expand_dims(img, axis=0).astype(np.float32)

    def embed_image(self, image: np.ndarray) -> np.ndarray:
        self._load_model()
        if self._img_session is None:
            return np.zeros(self.dim, dtype=np.float32)

        input_data = self._preprocess_image(image)
        output = self._img_session.run(None, {"pixel_values": input_data})[0]
        features = output.flatten()
        # Normalize
        features = features / (np.linalg.norm(features) + 1e-8)
        return features.astype(np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        self._load_model()
        if self._txt_session is None:
            return np.zeros(self.dim, dtype=np.float32)

        # Simple tokenized input — ONNX text model expects token IDs
        # Fall back to a zero vector if tokenizer not available
        try:
            import open_clip
            tokens = open_clip.tokenize([text]).numpy()
        except ImportError:
            return np.zeros(self.dim, dtype=np.float32)

        output = self._txt_session.run(None, {"input_ids": tokens})[0]
        features = output.flatten()
        features = features / (np.linalg.norm(features) + 1e-8)
        return features.astype(np.float32)


# ── Factory ────────────────────────────────────────────────────────────────────

_clip_embedder: Optional[CLIPSceneEmbedder] = None


def get_clip_embedder(backend: Optional[str] = None) -> CLIPSceneEmbedder:
    """Get or create the configured CLIP scene embedder.

    Args:
        backend: "open_clip", "onnx", "none", or None (reads CLIP_BACKEND env var
                 or auto-selects best available).

    Returns:
        CLIPSceneEmbedder instance, or a no-op placeholder if no backend available.
    """
    global _clip_embedder

    if backend is None:
        backend = os.environ.get("CLIP_BACKEND", "").lower()
        if not backend:
            # Auto-select: prefer OpenCLIP (GPU), fall back to ONNX (CPU)
            if OpenCLIPEmbedder().available:
                backend = "open_clip"
            elif ONNXCLIPEmbedder().available:
                backend = "onnx"
            else:
                backend = "none"

    if _clip_embedder is not None and _clip_embedder.name == backend:
        return _clip_embedder

    if backend == "open_clip":
        emb = OpenCLIPEmbedder()
        if emb.available:
            _clip_embedder = emb
        else:
            print("[clip] OpenCLIP not available, falling back", file=sys.stderr)
            _clip_embedder = ONNXCLIPEmbedder() if ONNXCLIPEmbedder().available else CLIPSceneEmbedder()
    elif backend == "onnx":
        emb = ONNXCLIPEmbedder()
        _clip_embedder = emb if emb.available else CLIPSceneEmbedder()
    else:
        _clip_embedder = CLIPSceneEmbedder()

    return _clip_embedder


def clip_available() -> bool:
    """Check if any CLIP backend is operational."""
    emb = get_clip_embedder()
    return emb.available
