#!/usr/bin/env python3
"""KV-Ground-8B 4-bit vision API server for TrueNAS deployment."""
import os, torch, time
from PIL import Image
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
model = None
processor = None
MODEL_ID = "vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315"
DEVICE = "cuda:0"


def load_model():
    global model, processor
    if model is not None:
        return

    print(f"Loading KV-Ground-8B in 4-bit on {DEVICE}...")
    from transformers import AutoModelForCausalLM, AutoProcessor

    processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    print("Processor loaded")

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="auto",
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
    )
    print(f"Model loaded. VRAM: {torch.cuda.memory_allocated()/1024**3:.1f}GB")


@app.post("/ground")
async def ground(request: Request):
    load_model()
    data = await request.json()
    image_path = data.get("image_path", "")
    query = data.get("query", "")
    if not image_path or not os.path.exists(image_path):
        return JSONResponse({"error": "image_path required"}, status_code=400)
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)

    image = Image.open(image_path).convert("RGB")
    t0 = time.time()
    inputs = processor(text=query, images=image, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=128, do_sample=False)
    result = processor.decode(outputs[0], skip_special_tokens=True)
    elapsed = (time.time() - t0) * 1000
    return JSONResponse({
        "query": query, "result": result,
        "time_ms": round(elapsed, 1),
        "model": "KV-Ground-8B-4bit",
    })


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model": "KV-Ground-8B-4bit",
        "loaded": model is not None,
        "device": DEVICE,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
