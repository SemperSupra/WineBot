#!/usr/bin/env python3
"""Debug KV-Ground-8B processor output."""
from PIL import Image
from transformers import AutoProcessor

MODEL_ID = "vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315"
p = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
img = Image.new("RGB", (768, 768), (200, 200, 200))

# Check processor's image token config
print(f"Processor class: {type(p).__name__}")
print(f"Tokenizer class: {type(p.tokenizer).__name__}")

# Check for special token IDs
for attr in dir(p.tokenizer):
    if "image" in attr.lower() or "vision" in attr.lower() or "im_" in attr.lower():
        val = getattr(p.tokenizer, attr)
        if isinstance(val, int):
            print(f"  tokenizer.{attr} = {val}")

# Test different prompt formats
prompts = [
    "<image>what is this?",
    "what is this?",
    "<|vision_start|><|image_pad|><|vision_end|>what is this?",
]

for prompt in prompts:
    try:
        inputs = p(text=prompt, images=img, return_tensors="pt")
        ids = inputs["input_ids"][0]
        print(f"\nPrompt ({len(prompt)} chars): {prompt[:60]}")
        print(f"  input_ids shape: {inputs['input_ids'].shape}")
        print(f"  pixel_values shape: {inputs['pixel_values'].shape}")
        print(f"  First 40 tokens: {ids[:40].tolist()}")

        # Store the tokens for later matching
        if "pixel_values" in inputs:
            n_features = inputs["pixel_values"].shape[1]
            print(f"  Image features: {n_features}")
    except Exception as e:
        print(f"\nPrompt ({len(prompt)} chars): {prompt[:60]}")
        print(f"  ERROR: {e}")
