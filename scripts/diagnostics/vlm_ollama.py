#!/usr/bin/env python3
# EXECUTION: EITHER — runs in sidecar container or on host with network access
"""
Ollama VLM backend for WineBot GUI grounding and scene description.

Offloads VLM inference to a remote Ollama server (e.g., TrueNAS with A5000 GPUs).
All configuration via environment variables — no hostnames or models are
hardcoded or committed to the repo.

Env vars:
  VLM_PROVIDER=ollama              Set to enable Ollama backend
  OLLAMA_HOST=http://host:port      Ollama API URL (default: http://localhost:11434)
  OLLAMA_VLM_MODEL=name             Model name in Ollama (default: qwen3.5:35b)
  OLLAMA_TIMEOUT=60                 Request timeout in seconds
  OLLAMA_KEEP_ALIVE=3600            Keep model in GPU memory (seconds, 0=unload)
  OLLAMA_AUTO_PULL=false            Auto-pull model if not found (true/false)
  WINEBOT_GIT_COMMIT=abc123         Git commit override for provenance
"""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np


class OllamaVLM:
    """Client for Ollama's chat API with vision support.

    Tracks model provenance (SHA256 content hash, quantization, family)
    for reproducible research. Can auto-pull missing models when
    OLLAMA_AUTO_PULL=true is set.
    """

    def __init__(self,
                 host: str | None = None,
                 model: str | None = None,
                 timeout: int = 60,
                 keep_alive: int = 3600,
                 auto_pull: bool | None = None):
        """
        Args:
            host: Ollama API host URL (reads OLLAMA_HOST env var if None).
            model: Model name (reads OLLAMA_VLM_MODEL env var if None).
            timeout: Request timeout in seconds.
            keep_alive: Keep model loaded for this many seconds after request.
            auto_pull: Auto-pull model if not found (reads OLLAMA_AUTO_PULL env var).
        """
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_VLM_MODEL", "qwen3.5:35b")
        self.timeout = timeout or int(os.environ.get("OLLAMA_TIMEOUT", "60"))
        self.keep_alive = keep_alive or int(os.environ.get("OLLAMA_KEEP_ALIVE", "3600"))
        if auto_pull is None:
            auto_pull = os.environ.get("OLLAMA_AUTO_PULL", "").lower() == "true"
        self.auto_pull = auto_pull
        self._available = None  # cached on first check
        self._provenance = None  # ModelProvenance from /api/show

    # ── Availability ───────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """Check if Ollama server is reachable and model is available."""
        if self._available is None:
            self._available = self._check()
        return self._available

    @property
    def provenance(self) -> dict | None:
        """Return the model's provenance record (cached after first check)."""
        if self._provenance is None and self.available:
            self._provenance = self._fingerprint()
        return self._provenance

    def _check(self) -> bool:
        """Probe the Ollama server and verify model exists."""
        if not self._server_reachable():
            return False

        if self._model_exists():
            return True

        if self.auto_pull:
            print(f"[ollama] Model '{self.model}' not found — auto-pulling...",
                  file=sys.stderr)
            if self._pull_model():
                print(f"[ollama] Pulled '{self.model}' successfully", file=sys.stderr)
                return True
            print(f"[ollama] Pull failed for '{self.model}'", file=sys.stderr)
            return False

        # List available models for debugging
        try:
            available = self._list_models()
            print(f"[ollama] Model '{self.model}' not found. "
                  f"Available: {available[:6]}...", file=sys.stderr)
        except Exception:
            pass
        return False

    def _server_reachable(self) -> bool:
        """Check if the Ollama server responds."""
        try:
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                headers={"User-Agent": "WineBot/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as _:
                return True
        except Exception as e:
            print(f"[ollama] Server unreachable at {self.host}: {e}", file=sys.stderr)
            return False

    def _model_exists(self) -> bool:
        """Check if the configured model is on the server."""
        models = self._list_models()
        base = self.model.split(":")[0]
        for m in models:
            if self.model in m or base in m:
                print(f"[ollama] Model '{m}' matches '{self.model}'",
                      file=sys.stderr)
                return True
        return False

    def _list_models(self) -> list[str]:
        """Return list of model names on the server."""
        try:
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                headers={"User-Agent": "WineBot/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    def _pull_model(self) -> bool:
        """Pull the configured model from Ollama registry.

        Uses POST /api/pull with streaming progress.
        Returns True if pull succeeded.
        """
        try:
            body = json.dumps({
                "name": self.model,
                "stream": True,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/pull",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                # Stream progress lines
                last_status = ""
                for line in resp:
                    try:
                        entry = json.loads(line.decode().strip())
                        status = entry.get("status", "")
                        if status and status != last_status:
                            digest = entry.get("digest", "")[:12]
                            total = entry.get("total", 0)
                            completed = entry.get("completed", 0)
                            if total > 0:
                                pct = int(100 * completed / total)
                                print(f"[ollama] Pulling {self.model}: "
                                      f"{pct}% {status} {digest}", file=sys.stderr)
                            else:
                                print(f"[ollama] Pulling: {status}", file=sys.stderr)
                            last_status = status
                    except json.JSONDecodeError:
                        pass
            return self._model_exists()
        except Exception as e:
            print(f"[ollama] Pull error: {e}", file=sys.stderr)
            return False

    def _fingerprint(self) -> dict | None:
        """Get model provenance via POST /api/show.

        Returns:
            Dict with model_name, model_family, parameter_size,
            content_sha256, model_format, quantization, ollama_host,
            fingerprinted_at.
        """
        try:
            body = json.dumps({"name": self.model}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/show",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            modelfile = data.get("modelfile", "")
            sha_match = re.search(r"sha256-([a-f0-9]{64})", modelfile)
            sha256 = sha_match.group(1) if sha_match else ""
            details = data.get("details", {})

            prov = {
                "model_name": self.model,
                "model_family": details.get("family", ""),
                "parameter_size": details.get("parameter_size", ""),
                "content_sha256": sha256,
                "model_format": details.get("format", ""),
                "quantization": details.get("quantization_level", "BF16"),
                "ollama_host": self.host,
                "fingerprinted_at": datetime.now(UTC).isoformat(),
            }

            if sha256:
                short = sha256[:12]
                print(f"[ollama] Provenance: {prov['model_family']} "
                      f"{prov['parameter_size']} {prov['quantization']} "
                      f"sha256:{short}", file=sys.stderr)
            return prov

        except Exception as e:
            print(f"[ollama] Provenance unavailable: {e}", file=sys.stderr)
            return {
                "model_name": self.model,
                "ollama_host": self.host,
                "fingerprinted_at": datetime.now(UTC).isoformat(),
            }

    # ── Inference ──────────────────────────────────────────────────────────

    def chat(self, messages: list[dict], image: np.ndarray | None = None,
             system_prompt: str | None = None) -> str | None:
        """Send a chat completion request, optionally with an image.

        Args:
            messages: List of chat message dicts {role, content}.
            image: BGR numpy array to include as a vision attachment.
            system_prompt: Optional system message.

        Returns:
            Response text, or None on failure.
        """
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 512,
            },
            "keep_alive": f"{self.keep_alive}s",
        }

        if system_prompt:
            body["messages"].append({"role": "system", "content": system_prompt})

        for msg in messages:
            if image is not None and msg == messages[0]:
                _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                img_b64 = base64.b64encode(buf).decode("utf-8")
                body["messages"].append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                    "images": [img_b64],
                })
            else:
                body["messages"].append(msg)

        try:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/chat",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "WineBot/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode())
                content = result.get("message", {}).get("content", "")
                if not content:
                    print(f"[ollama] Empty response from {self.model}", file=sys.stderr)
                    return None
                return content

        except urllib.error.HTTPError as e:
            body_text = e.read().decode()[:500] if e.fp else ""
            print(f"[ollama] HTTP {e.code}: {body_text}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"[ollama] Request failed: {e}", file=sys.stderr)
            return None

    def ground(self, image: np.ndarray, query: str) -> dict | None:
        """Ground a natural language query to a specific UI element."""
        h, w = image.shape[:2]
        prompt = (
            f"Point to {query}. Output ONLY the bounding box as "
            f"[x1, y1, x2, y2] where each coordinate is normalized "
            f"to 0-1000 (0=left/top, 1000=right/bottom). "
            f"Do not explain — output only the four numbers in brackets."
        )

        response = self.chat(
            messages=[{"role": "user", "content": prompt}],
            image=image,
        )

        if not response:
            return None

        return self._parse_coordinates(response, query, image, normalized=True)

    def describe(self, image: np.ndarray, style: str = "detailed") -> str | None:
        """Describe a UI screenshot in natural language."""
        if style == "brief":
            prompt = "Describe this UI screenshot in one sentence. Focus on what the user sees: dialog titles, button labels, text fields, checkboxes. Be specific about visible text."
        else:
            prompt = (
                "Describe this UI screenshot in detail. Include:\n"
                "1. What type of window or dialog is shown\n"
                "2. The title bar text\n"
                "3. All visible UI elements: buttons (with their labels), "
                "text fields, checkboxes, dropdowns, menus, tabs\n"
                "4. Any visible text content\n"
                "5. The overall purpose of this screen\n"
                "Be specific about visible label text. Describe what you see."
            )

        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            image=image,
        )

    def _parse_coordinates(self, text: str, query: str,
                            image: np.ndarray,
                            normalized: bool = False) -> dict | None:
        """Parse model output for bounding box coordinates."""
        m = re.search(
            r'\[\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*\]',
            text
        )
        if m:
            coords = [int(m.group(i)) for i in range(1, 5)]
            x1, y1, x2, y2 = coords
            h, w = image.shape[:2]

            if normalized:
                x1 = int(x1 * w / 1000)
                y1 = int(y1 * h / 1000)
                x2 = int(x2 * w / 1000)
                y2 = int(y2 * h / 1000)

            x1 = max(0, min(w, x1))
            y1 = max(0, min(h, y1))
            x2 = max(0, min(w, x2))
            y2 = max(0, min(h, y2))

            if x2 - x1 < 2: x2 = x1 + 2
            if y2 - y1 < 2: y2 = y1 + 2

            return {
                "bbox": [x1, y1, x2 - x1, y2 - y1],
                "label": query,
                "confidence": 0.85,
                "raw_response": text,
            }

        print(f"[ollama] Could not parse coordinates from: {text[:200]}",
              file=sys.stderr)
        return {"label": query, "confidence": 0.3, "raw_response": text}


# ── Factory ────────────────────────────────────────────────────────────────────

_ollama_vlm: OllamaVLM | None = None


def get_ollama_vlm(host: str | None = None,
                    model: str | None = None) -> OllamaVLM | None:
    """Get or create the Ollama VLM client.

    Only activates when VLM_PROVIDER env var is set to "ollama".
    Returns None if Ollama is not configured or unreachable.

    Args:
        host: Override OLLAMA_HOST env var.
        model: Override OLLAMA_VLM_MODEL env var.

    Returns:
        OllamaVLM instance, or None if not configured.
    """
    global _ollama_vlm

    provider = os.environ.get("VLM_PROVIDER", "").lower()
    if provider != "ollama":
        return None

    if _ollama_vlm is not None:
        return _ollama_vlm

    client = OllamaVLM(host=host, model=model)
    if client.available:
        _ollama_vlm = client
        print(f"[vlm] Ollama VLM configured: {client.model} @ {client.host}",
              file=sys.stderr)
        # Trigger provenance fingerprint
        _ = client.provenance
        return client

    print(f"[vlm] Ollama VLM unavailable at {client.host}", file=sys.stderr)
    return None
