#!/usr/bin/env python3
# EXECUTION: EITHER — runs in sidecar container or on host with network access
"""
Ollama VLM backend for WineBot GUI grounding and scene description.

Offloads VLM inference to a remote Ollama server (e.g., TrueNAS with A5000 GPUs).
All configuration via environment variables — no hostnames or models are
hardcoded or committed to the repo.

Env vars:
  VLM_PROVIDER=ollama          Set to enable Ollama backend
  OLLAMA_HOST=http://host:port  Ollama API URL (default: http://localhost:11434)
  OLLAMA_VLM_MODEL=name         Model name in Ollama (default: qwen3.5:35b)
  OLLAMA_TIMEOUT=60             Request timeout in seconds
  OLLAMA_KEEP_ALIVE=3600        Keep model in GPU memory (seconds, 0=unload)
"""

import base64
import json
import os
import sys
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import urllib.request
import urllib.error


class OllamaVLM:
    """Client for Ollama's chat API with vision support."""

    def __init__(self,
                 host: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: int = 60,
                 keep_alive: int = 3600):
        """
        Args:
            host: Ollama API host URL (reads OLLAMA_HOST env var if None).
            model: Model name (reads OLLAMA_VLM_MODEL env var if None).
            timeout: Request timeout in seconds.
            keep_alive: Keep model loaded for this many seconds after request.
        """
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_VLM_MODEL", "qwen3.5:35b")
        self.timeout = timeout or int(os.environ.get("OLLAMA_TIMEOUT", "60"))
        self.keep_alive = keep_alive or int(os.environ.get("OLLAMA_KEEP_ALIVE", "3600"))
        self._available = None  # cached on first check

    @property
    def available(self) -> bool:
        """Check if Ollama server is reachable and model is available."""
        if self._available is None:
            self._available = self._check()
        return self._available

    def _check(self) -> bool:
        """Probe the Ollama server."""
        try:
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                headers={"User-Agent": "WineBot/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name", "") for m in data.get("models", [])]
                # Check if our model or a close match exists
                base = self.model.split(":")[0]
                for m in models:
                    if base in m or self.model in m:
                        print(f"[ollama] Server OK, model '{m}' matches '{self.model}'",
                              file=sys.stderr)
                        return True
                print(f"[ollama] Server OK but model '{self.model}' not found. "
                      f"Available: {models[:6]}...", file=sys.stderr)
                return False
        except Exception as e:
            print(f"[ollama] Server unreachable at {self.host}: {e}", file=sys.stderr)
            return False

    def chat(self, messages: List[Dict], image: Optional[np.ndarray] = None,
             system_prompt: Optional[str] = None) -> Optional[str]:
        """Send a chat completion request, optionally with an image.

        Args:
            messages: List of chat message dicts {role, content}.
            image: BGR numpy array to include as a vision attachment.
            system_prompt: Optional system message.

        Returns:
            Response text, or None on failure.
        """
        # Build Ollama API request
        body: Dict[str, Any] = {
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

        # Add image if provided (Ollama supports base64 inline)
        for msg in messages:
            if image is not None and msg == messages[0]:
                # Embed image as base64 JPEG in the first user message
                _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                img_b64 = base64.b64encode(buf).decode("utf-8")
                body["messages"].append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                    "images": [img_b64],
                })
            else:
                body["messages"].append(msg)

        # Send request
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

    def ground(self, image: np.ndarray, query: str) -> Optional[Dict]:
        """Ground a natural language query to a specific UI element.

        Args:
            image: BGR screenshot.
            query: Natural language description of the element to find.

        Returns:
            Dict with bbox, label, confidence, or None.
        """
        prompt = (
            f"Point to {query}. Output ONLY the bounding box as "
            f"[x1, y1, x2, y2] in pixel coordinates. The image is "
            f"{image.shape[1]} pixels wide and {image.shape[0]} pixels tall. "
            f"Do not explain — output only the coordinates in brackets."
        )

        response = self.chat(
            messages=[{"role": "user", "content": prompt}],
            image=image,
        )

        if not response:
            return None

        return self._parse_coordinates(response, query, image)

    def describe(self, image: np.ndarray, style: str = "detailed") -> Optional[str]:
        """Describe a UI screenshot in natural language.

        Args:
            image: BGR screenshot.
            style: "brief" or "detailed".

        Returns:
            Natural language description string, or None.
        """
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
                            image: np.ndarray) -> Optional[Dict]:
        """Parse model output for bounding box coordinates."""
        import re

        # Pattern: [number, number, number, number]
        m = re.search(
            r'\[\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*\]',
            text
        )
        if m:
            coords = [int(m.group(i)) for i in range(1, 5)]
            x1, y1, x2, y2 = coords
            # Clamp to image bounds
            h, w = image.shape[:2]
            x1 = max(0, min(w, x1))
            y1 = max(0, min(h, y1))
            x2 = max(0, min(w, x2))
            y2 = max(0, min(h, y2))
            return {
                "bbox": [x1, y1, x2 - x1, y2 - y1],
                "label": query,
                "confidence": 0.85,
                "raw_response": text,
            }

        # No coordinates found
        print(f"[ollama] Could not parse coordinates from: {text[:200]}",
              file=sys.stderr)
        return {"label": query, "confidence": 0.3, "raw_response": text}


# ── Factory ────────────────────────────────────────────────────────────────────

_ollama_vlm: Optional[OllamaVLM] = None


def get_ollama_vlm(host: Optional[str] = None,
                    model: Optional[str] = None) -> Optional[OllamaVLM]:
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
        return client

    print(f"[vlm] Ollama VLM unavailable at {client.host}", file=sys.stderr)
    return None
