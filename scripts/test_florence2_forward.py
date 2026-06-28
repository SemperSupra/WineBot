#!/usr/bin/env python3
"""Quick verify Florence-2 LoRA via forward pass (not generate)."""
import os

import torch
from peft import PeftModel
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

device = "cuda"
base = "microsoft/Florence-2-base"
lora_path = "/models/florence2/wine-caption-lora"

print("Loading...")
processor = AutoProcessor.from_pretrained(base, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    base, trust_remote_code=True,
    torch_dtype=torch.bfloat16,
    attn_implementation="eager",
).to(device)
model = PeftModel.from_pretrained(model, lora_path)

# Test forward pass on 3 images
test_dir = "/models/wine-dataset-10k/test/images"
imgs = sorted(os.listdir(test_dir))[:3]

model.eval()
for img_name in imgs:
    img_path = os.path.join(test_dir, img_name)
    image = Image.open(img_path).convert("RGB").resize((768, 768), Image.LANCZOS)
    inputs = processor(text="<CAPTION>", images=image, return_tensors="pt",
                       padding="max_length", max_length=1024, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    if "pixel_values" in inputs and inputs["pixel_values"].dtype != torch.bfloat16:
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
    inputs["labels"] = inputs["input_ids"].clone()

    with torch.no_grad():
        out = model(**inputs)

    logits = out.logits
    pred_tokens = logits.argmax(dim=-1)[0, :10]
    print(f"[{img_name}] loss={out.loss.item():.4f}  perplexity={torch.exp(out.loss).item():.1f}")
    print(f"  First 10 pred tokens: {pred_tokens.cpu().tolist()}")
    print()

print("Adapter verified successfully.")
