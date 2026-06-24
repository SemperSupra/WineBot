#!/usr/bin/env python3
# EXECUTION: EITHER — pure Python, no GPU needed
"""
Model provenance fingerprinting for reproducible CV/OCR research.

Every inference result includes a provenance record capturing:
  - Model identity: name, tag, family, parameter count
  - Content fingerprint: SHA256 hash of model weights (guarantees bit-exact reproducibility)
  - Quantization: format + level (e.g., GGUF Q4_K_M, BF16 safetensors)
  - Runtime: git commit, Python packages, Docker image digest
  - Pipeline: which backends were used at each stage

Usage:
  from provenance import fingerprint_ollama_model, get_runtime_provenance
  prov = fingerprint_ollama_model("http://host:30068", "qwen3.5:35b")
  runtime = get_runtime_provenance()
"""

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ModelProvenance:
    """Complete identity and integrity record for one model."""
    # Model identity
    model_name: str                    # e.g., "qwen3.5:35b"
    model_family: str = ""             # e.g., "qwen35moe"
    parameter_size: str = ""           # e.g., "36.0B"

    # Content integrity
    content_sha256: str = ""           # SHA256 of model weights (bit-exact fingerprint)
    model_format: str = ""             # "gguf", "safetensors", "onnx"
    quantization: str = ""             # "Q4_K_M", "BF16", "none"

    # Source
    ollama_host: str = ""              # Where the model lives

    # Fingerprinting timestamp
    fingerprinted_at: str = ""         # ISO 8601

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        """Unique identifier: family + sha256[:12] + quant."""
        short_hash = self.content_sha256[:12] if self.content_sha256 else "unknown"
        return f"{self.model_family}-{self.quantization}-{short_hash}"


@dataclass
class RuntimeProvenance:
    """Version fingerprint of the runtime environment."""
    git_commit: str = ""
    git_branch: str = ""
    docker_image: str = ""
    python_version: str = ""
    key_packages: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineProvenance:
    """Complete provenance for one inference result."""
    # What model was used
    model: Optional[ModelProvenance] = None

    # What runtime
    runtime: Optional[RuntimeProvenance] = None

    # Which backends were active
    pipeline_backends: Dict[str, str] = field(default_factory=dict)
    # e.g., {"ui_detector": "wine", "ocr_backend": "tesseract",
    #        "vlm_backend": "ollama", "captioner": "florence2"}

    # Timing
    inference_ms: float = 0.0
    timestamp_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "model": self.model.to_dict() if self.model else None,
            "runtime": self.runtime.to_dict() if self.runtime else None,
            "pipeline_backends": self.pipeline_backends,
            "inference_ms": self.inference_ms,
            "timestamp_utc": self.timestamp_utc,
        }
        return d

    def reproducibility_spec(self) -> str:
        """One-line spec that can be pasted into a paper methods section."""
        parts = []
        if self.model:
            parts.append(f"{self.model.model_name}")
            if self.model.quantization:
                parts.append(f"({self.model.quantization})")
            parts.append(f"[SHA256:{self.model.content_sha256[:16]}]")
        if self.runtime and self.runtime.git_commit:
            parts.append(f"winebot@{self.runtime.git_commit[:8]}")
        return " ".join(parts)


# ── Fingerprinting functions ──────────────────────────────────────────────────


def fingerprint_ollama_model(host: str, model_name: str,
                              timeout: int = 10) -> Optional[ModelProvenance]:
    """Query an Ollama server for model identity and content hash.

    Uses POST /api/show to get the model's modelfile, parameters,
    and details including quantization and content SHA256.

    Args:
        host: Ollama API base URL (e.g., "http://localhost:11434").
        model_name: Model name + tag (e.g., "qwen3.5:35b").
        timeout: Request timeout in seconds.

    Returns:
        ModelProvenance, or None if the server is unreachable or
        the model doesn't exist.
    """
    import urllib.request
    import urllib.error
    import re

    try:
        body = json.dumps({"name": model_name}).encode("utf-8")
        req = urllib.request.Request(
            f"{host}/api/show",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())

        # Extract SHA256 from the FROM line in the modelfile
        modelfile = data.get("modelfile", "")
        sha_match = re.search(r"sha256-([a-f0-9]{64})", modelfile)
        content_sha256 = sha_match.group(1) if sha_match else ""

        details = data.get("details", {})

        return ModelProvenance(
            model_name=model_name,
            model_family=details.get("family", ""),
            parameter_size=details.get("parameter_size", ""),
            content_sha256=content_sha256,
            model_format=details.get("format", ""),
            quantization=details.get("quantization_level", "BF16"),
            ollama_host=host,
            fingerprinted_at=datetime.now(timezone.utc).isoformat(),
        )

    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"[provenance] Model '{model_name}' not found on {host}",
                  file=sys.stderr)
        else:
            body = e.read().decode()[:200] if e.fp else ""
            print(f"[provenance] HTTP {e.code} from {host}: {body}",
                  file=sys.stderr)
        return None
    except Exception as e:
        print(f"[provenance] Cannot reach {host}: {e}", file=sys.stderr)
        return None


def get_git_commit(repo_path: Optional[str] = None) -> str:
    """Get the current git commit hash.

    Tries: env var WINEBOT_GIT_COMMIT > git rev-parse > "unknown".
    """
    # Allow explicit override via env var (for Docker builds)
    explicit = os.environ.get("WINEBOT_GIT_COMMIT", "")
    if explicit:
        return explicit

    try:
        cwd = repo_path or os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def get_runtime_provenance() -> RuntimeProvenance:
    """Capture the current runtime environment fingerprint."""
    rp = RuntimeProvenance(
        git_commit=get_git_commit(),
        docker_image=os.environ.get("DOCKER_IMAGE", ""),
        python_version=sys.version.split()[0],
    )

    # Key packages — only the ones relevant to reproducibility
    for pkg in ["torch", "torchvision", "ultralytics", "opencv-python",
                 "onnxruntime", "transformers", "open_clip_torch", "numpy",
                 "pytesseract", "rfdetr"]:
        try:
            import importlib
            mod = importlib.import_module(pkg.replace("-", "_"))
            version = getattr(mod, "__version__", "unknown")
            rp.key_packages[pkg] = version
        except ImportError:
            pass

    return rp


def hash_string(s: str) -> str:
    """SHA256 of a string, for quick content hashing."""
    return hashlib.sha256(s.encode()).hexdigest()
