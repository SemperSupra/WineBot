#!/usr/bin/env python3
# EXECUTION: IN_CONTAINER — requires transformers + GPU (or CPU fallback)
"""
Florence-2 scene captioning engine for WineBot.

Generates human-readable descriptions of UI screenshots. Fine-tunable
on WineBot's synthetic GT data (image → auto-generated structured caption).

Captioner selection via FLORENCE2_BACKEND env var:
  FLORENCE2_BACKEND=base     (default, microsoft/Florence-2-base, ~150ms)
  FLORENCE2_BACKEND=wine     (our fine-tuned LoRA adapter, ~150ms)
  FLORENCE2_BACKEND=none     (disabled)

Usage:
  from florence2_captioner import get_captioner
  cap = get_captioner()
  caption = cap.caption(image, style="detailed")
  # → "A save dialog titled 'Save As' with a filename text field,
  #    a file type dropdown, and Save, Cancel, Hide Folders buttons."
"""

import os
import sys

import cv2
import numpy as np


class Florence2Captioner:
    """Base class for Florence-2 captioning backends."""

    name: str = "base"
    available: bool = False
    uses_gpu: bool = False

    # Caption style prompts
    CAPTION_STYLES = {
        "brief": "<CAPTION>",
        "detailed": "<DETAILED_CAPTION>",
        "more_detailed": "<MORE_DETAILED_CAPTION>",
        "od": "<OD>",  # Object detection: region descriptions
        "ocr": "<OCR>",  # Text extraction
        "ocr_with_region": "<OCR_WITH_REGION>",
    }

    def caption(self, image: np.ndarray, style: str = "detailed") -> str:
        """Generate a human-readable description of a UI screenshot.

        Args:
            image: BGR screenshot as numpy array.
            style: Caption style — "brief", "detailed", "more_detailed",
                   "od" (object descriptions), "ocr", "ocr_with_region".

        Returns:
            Natural language description string.
        """
        raise NotImplementedError

    def caption_batch(self, images: list[np.ndarray],
                       style: str = "detailed") -> list[str]:
        """Generate captions for multiple frames."""
        return [self.caption(img, style) for img in images]


# ── Transformers Backend ──────────────────────────────────────────────────────

class Florence2TransformersCaptioner(Florence2Captioner):
    """Florence-2 via HuggingFace transformers. GPU-accelerated.

    Supports:
      - Base model: microsoft/Florence-2-base (230M params, MIT)
      - Fine-tuned: Base + LoRA adapter from our Wine GT training
      - Auto device selection (CUDA/MPS/CPU)
    """

    name = "florence2"
    available = False
    uses_gpu = False

    # Stable model identifier (Florence-2-base is the standard)
    MODEL_ID = "microsoft/Florence-2-base"

    def __init__(self, lora_adapter: str | None = None):
        """
        Args:
            lora_adapter: Path to LoRA adapter weights
                          (e.g., /models/florence2/florence2-wine-lora).
                          If None, uses base model without fine-tuning.
        """
        self._model = None
        self._processor = None
        self._device = "cpu"
        self._lora_path = lora_adapter

        # Check dependencies
        try:
            import torch  # noqa: F401
            self._has_torch = True
        except ImportError:
            self._has_torch = False

        try:
            import transformers  # noqa: F401
            self._has_transformers = True
        except ImportError:
            self._has_transformers = False

        self.available = self._has_torch and self._has_transformers

    def _load_model(self):
        """Lazy-load Florence-2 on first use."""
        if self._model is not None:
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        if torch.cuda.is_available():
            self._device = "cuda"
            self.uses_gpu = True
        else:
            self._device = "cpu"

        model_dir = os.environ.get(
            "FLORENCE2_MODEL_DIR",
            os.path.join(os.environ.get("MODEL_CACHE", "/models"),
                         "florence2")
        )

        # Determine model source
        if os.path.isdir(model_dir) and os.path.isfile(
            os.path.join(model_dir, "config.json")
        ):
            model_id = model_dir
        else:
            model_id = os.environ.get("FLORENCE2_MODEL_ID", self.MODEL_ID)

        print(f"[florence2] Loading from {model_id} on {self._device}...",
              file=sys.stderr)

        self._model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16 if self._device == "cuda" else torch.float32,
            trust_remote_code=True,
        ).to(self._device)
        self._model.eval()

        self._processor = AutoProcessor.from_pretrained(
            model_id,
            trust_remote_code=True,
        )

        # Load LoRA adapter if available
        if self._lora_path and os.path.isdir(self._lora_path):
            try:
                from peft import PeftModel
                self._model = PeftModel.from_pretrained(
                    self._model, self._lora_path
                )
                self._model = self._model.merge_and_unload()
                print(f"[florence2] LoRA adapter loaded from {self._lora_path}",
                      file=sys.stderr)
            except ImportError:
                print("[florence2] peft not available — skipping LoRA adapter",
                      file=sys.stderr)
            except Exception as e:
                print(f"[florence2] LoRA load failed: {e}", file=sys.stderr)

        total_params = sum(p.numel() for p in self._model.parameters())
        print(f"[florence2] Loaded: {total_params/1e6:.0f}M params "
              f"on {self._device}", file=sys.stderr)

    def caption(self, image: np.ndarray, style: str = "detailed") -> str:
        """Generate a caption for a UI screenshot."""
        self._load_model()
        if self._model is None:
            return ""

        import torch
        from PIL import Image

        # Convert BGR to RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        # Get the appropriate task prompt
        task_prompt = self.CAPTION_STYLES.get(
            style, self.CAPTION_STYLES["detailed"]
        )

        # Process and generate
        inputs = self._processor(
            text=task_prompt, images=pil_img,
            return_tensors="pt"
        ).to(self._device)

        try:
            with torch.no_grad():
                if self._device == "cuda":
                    with torch.amp.autocast('cuda'):
                        generated_ids = self._model.generate(
                            input_ids=inputs["input_ids"],
                            pixel_values=inputs["pixel_values"],
                            max_new_tokens=256,
                            num_beams=3,
                            do_sample=False,
                        )
                else:
                    generated_ids = self._model.generate(
                        input_ids=inputs["input_ids"],
                        pixel_values=inputs["pixel_values"],
                        max_new_tokens=256,
                        num_beams=3,
                        do_sample=False,
                    )

            # Decode, skip special tokens
            generated_text = self._processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]

            # Florence-2 returns the task prompt prefix — strip it
            result = self._processor.post_process_generation(
                generated_text,
                task=task_prompt,
                image_size=(pil_img.width, pil_img.height)
            )
            return str(result.get(task_prompt, generated_text))

        except Exception as e:
            print(f"[florence2] Inference error: {e}", file=sys.stderr)
            return ""


# ── Factory ────────────────────────────────────────────────────────────────────

_florence2_captioner: Florence2Captioner | None = None


def get_captioner(backend: str | None = None) -> Florence2Captioner:
    """Get or create the configured Florence-2 captioner.

    Args:
        backend: "base", "wine", or None (reads FLORENCE2_BACKEND env var,
                 defaults to "base").

    Returns:
        Florence2Captioner instance.
    """
    global _florence2_captioner

    if backend is None:
        backend = os.environ.get("FLORENCE2_BACKEND", "base").lower()

    if _florence2_captioner is not None and _florence2_captioner.name == backend:
        return _florence2_captioner

    if backend == "wine":
        lora_path = os.environ.get(
            "FLORENCE2_LORA_PATH",
            "/models/florence2/florence2-wine-lora"
        )
        _florence2_captioner = Florence2TransformersCaptioner(
            lora_adapter=lora_path
        )
    elif backend == "base":
        _florence2_captioner = Florence2TransformersCaptioner()
    else:
        _florence2_captioner = Florence2Captioner()

    return _florence2_captioner


def captioner_available() -> bool:
    """Check if any Florence-2 backend is operational."""
    cap = get_captioner()
    return cap.available
