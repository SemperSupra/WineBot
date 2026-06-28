#!/usr/bin/env python3
"""Test Florence-2 LoRA adapter on a few GT test images."""
import os

import torch
from peft import PeftModel
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

device = "cuda"
base = "microsoft/Florence-2-base"
lora_path = "/models/florence2/wine-caption-lora"

print("Loading processor...")
processor = AutoProcessor.from_pretrained(base, trust_remote_code=True)
processor.tokenizer.model_max_length = 512

print("Loading base model...")
model = AutoModelForCausalLM.from_pretrained(
    base, trust_remote_code=True,
    torch_dtype=torch.bfloat16,
    attn_implementation="eager",
).to(device)

print("Loading LoRA adapter...")
model = PeftModel.from_pretrained(model, lora_path)
model = model.merge_and_unload()
print(f"Model loaded: {sum(p.numel() for p in model.parameters())/1e6:.1f}M params")

# Test a few images from test split
test_dir = "/models/wine-dataset-10k/test/images"
imgs = sorted(os.listdir(test_dir))[:5]
print(f"\n--- Testing {len(imgs)} images ---\n")

for img_name in imgs:
    img_path = os.path.join(test_dir, img_name)
    image = Image.open(img_path).convert("RGB").resize((768, 768), Image.LANCZOS)
    prompt = "<CAPTION>"
    inputs = processor(text=prompt, images=image, return_tensors="pt", padding=True, truncation=True)
    pixel_values = inputs["pixel_values"].to(device).to(torch.bfloat16)
    input_ids = inputs["input_ids"].to(device)
    attention_mask = inputs["attention_mask"].to(device)

    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids,
            pixel_values=pixel_values,
            attention_mask=attention_mask,
            max_new_tokens=100,
            do_sample=False,
            num_beams=1,
        )
    caption = processor.tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"[{img_name}] {caption[:200]}")
    print()

print("Done!")
