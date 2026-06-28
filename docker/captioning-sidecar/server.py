#!/usr/bin/env python3
"""Captioning Sidecar — dedicated Florence-2 scene description server.

Lightweight FastAPI service exposing a single endpoint. Isolated from
the main CV sidecar so dependency conflicts (Florence-2 needs specific
transformers version) don't break detection/OCR/embedding.

Env vars:
  CAPTIONER_MODEL=microsoft/Florence-2-base   Model ID or path
  CAPTIONER_LORA=/models/captioning/wine-lora  Optional LoRA adapter
  CAPTIONER_DEVICE=cuda                         cuda | cpu | auto
  CAPTIONER_HOST=0.0.0.0                       Listen address
  CAPTIONER_PORT=8002                           Listen port
"""

import base64
import os
import sys
import time

import cv2
import numpy as np

# ── FastAPI (lazy, for CLI usage) ─────────────────────────────────────────

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


def load_model():
    """Load Florence-2 with optional LoRA adapter."""
    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor

    model_id = os.environ.get("CAPTIONER_MODEL", "microsoft/Florence-2-base")
    lora_path = os.environ.get("CAPTIONER_LORA", "")
    device_str = os.environ.get("CAPTIONER_DEVICE", "auto")

    if device_str == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = device_str

    print(f"[captioning] Loading {model_id} on {device}...", file=sys.stderr)

    torch_dtype = torch.bfloat16 if device == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch_dtype,
        trust_remote_code=True,
    ).to(device)
    model.eval()

    processor = AutoProcessor.from_pretrained(
        model_id,
        trust_remote_code=True,
    )

    # Load LoRA adapter if configured
    if lora_path and os.path.isdir(lora_path):
        try:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, lora_path)
            model = model.merge_and_unload()
            model.eval()
            print(f"[captioning] LoRA adapter loaded from {lora_path}",
                  file=sys.stderr)
        except ImportError:
            print("[captioning] peft not installed — skipping LoRA",
                  file=sys.stderr)
        except Exception as e:
            print(f"[captioning] LoRA load failed: {e}", file=sys.stderr)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"[captioning] Loaded: {total_params/1e6:.0f}M params on {device}",
          file=sys.stderr)

    return model, processor, device


def caption_image(model, processor, device, image, style="detailed"):
    """Generate a caption for a UI screenshot."""
    import torch
    from PIL import Image

    task_prompts = {
        "brief": "<CAPTION>",
        "detailed": "<DETAILED_CAPTION>",
        "more_detailed": "<MORE_DETAILED_CAPTION>",
        "od": "<OD>",
        "ocr": "<OCR>",
        "ocr_with_region": "<OCR_WITH_REGION>",
    }
    task_prompt = task_prompts.get(style, task_prompts["detailed"])

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)

    inputs = processor(
        text=task_prompt, images=pil_img,
        return_tensors="pt"
    ).to(device)

    try:
        with torch.no_grad():
            if device == "cuda":
                with torch.amp.autocast("cuda"):
                    generated_ids = model.generate(
                        input_ids=inputs["input_ids"],
                        pixel_values=inputs["pixel_values"],
                        max_new_tokens=256,
                        num_beams=3,
                        do_sample=False,
                    )
            else:
                generated_ids = model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=256,
                    num_beams=3,
                    do_sample=False,
                )

        generated_text = processor.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]

        result = processor.post_process_generation(
            generated_text,
            task=task_prompt,
            image_size=(pil_img.width, pil_img.height)
        )
        return str(result.get(task_prompt, generated_text))

    except Exception as e:
        print(f"[captioning] Inference error: {e}", file=sys.stderr)
        return ""


def create_app():
    """Build the FastAPI app with model loaded at startup."""
    app = FastAPI(title="WineBot Captioning Sidecar")

    # Load model at startup
    app.state.model, app.state.processor, app.state.device = load_model()

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "model": os.environ.get("CAPTIONER_MODEL", "microsoft/Florence-2-base"),
            "device": app.state.device,
            "lora": bool(os.environ.get("CAPTIONER_LORA", "")),
        }

    @app.post("/caption")
    async def caption(request_data: dict):
        """Generate a natural language description of a UI screenshot.

        Request body:
          {"image": "<base64 PNG>", "style": "detailed"}

        Style options:
          - "brief": Short one-line caption
          - "detailed": Paragraph describing all elements
          - "more_detailed": Even more detail
          - "od": Per-region object descriptions
          - "ocr": Extracted text content
          - "ocr_with_region": Text with bounding boxes

        Returns:
          {"caption": "...", "style": "detailed", "inference_ms": 145}
        """
        img_b64 = request_data.get("image", "")
        style = request_data.get("style", "detailed")

        if not img_b64:
            raise HTTPException(status_code=400, detail="image required")

        try:
            img_bytes = base64.b64decode(img_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid base64 image")

        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail="could not decode image")

        t0 = time.perf_counter()
        caption = caption_image(
            app.state.model, app.state.processor, app.state.device,
            img, style=style
        )
        elapsed = (time.perf_counter() - t0) * 1000

        return JSONResponse(content={
            "caption": caption,
            "style": style,
            "inference_ms": round(elapsed, 1),
            "model": os.environ.get("CAPTIONER_MODEL", "microsoft/Florence-2-base"),
        })

    return app


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="WineBot Captioning Sidecar")
    parser.add_argument("--serve", action="store_true",
                        help="Start HTTP server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--cli", action="store_true",
                        help="CLI: caption a single image")
    parser.add_argument("--image", default=None,
                        help="Image path for --cli mode")
    parser.add_argument("--style", default="detailed",
                        help="Caption style for --cli mode")
    args = parser.parse_args()

    if args.cli:
        if not args.image or not os.path.isfile(args.image):
            print("ERROR: --image required for CLI mode", file=sys.stderr)
            sys.exit(1)
        model, processor, device = load_model()
        img = cv2.imread(args.image)
        t0 = time.perf_counter()
        caption = caption_image(model, processor, device, img, args.style)
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"{caption}")
        print(f"\n[{elapsed:.0f}ms on {device}]", file=sys.stderr)
        return

    if args.serve:
        if not HAS_FASTAPI:
            print("ERROR: FastAPI/uvicorn not installed. Use --cli.", file=sys.stderr)
            sys.exit(1)
        app = create_app()
        print(f"Captioning Sidecar starting on {args.host}:{args.port}", file=sys.stderr)
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    else:
        print("Usage: --serve (start HTTP) or --cli --image foo.png", file=sys.stderr)


if __name__ == "__main__":
    main()
