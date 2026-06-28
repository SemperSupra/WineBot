#!/usr/bin/env python3
"""Fine-tune Florence-2-base with LoRA on Wine desktop caption data.

Generates structured captions from the 10K GT dataset (via
generate_caption_training_data.py) and fine-tunes the language decoder
with LoRA adapters.

Usage:
  # Step 1: Generate training data (CPU, run anytime)
  python3 generate_caption_training_data.py \\
    --dataset /models/wine-dataset-10k \\
    --output /models/florence2-training/captions.jsonl \\
    --split all --max-samples 5000

  # Step 2: Fine-tune (GPU, ~2-3 hours on RTX 3090)
  python3 fine_tune_florence2.py \\
    --data /models/florence2-training/captions.jsonl \\
    --output /models/florence2/wine-caption-lora \\
    --epochs 5 --batch 8 --lr 2e-4

  # Step 3: Evaluate
  python3 -c "
    from florence2_captioner import Florence2TransformersCaptioner
    cap = Florence2TransformersCaptioner()
    print(cap.caption('test.png', style='wine'))
  "
"""

import argparse
import json
import os
import time

import torch


def load_training_data(data_path: str, max_samples: int = None):
    """Load caption training pairs from JSONL.

    Returns:
        List of {"image_path": str, "caption": str, ...}
    """
    records = []
    with open(data_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    if max_samples and len(records) > max_samples:
        records = records[:max_samples]

    return records


def fine_tune(data_path: str, output_dir: str,
              base_model: str = "microsoft/Florence-2-base",
              epochs: int = 5, batch_size: int = 8, lr: float = 2e-4,
              lora_rank: int = 16, lora_alpha: int = 32,
              max_samples: int = None, resume: bool = False):
    """Fine-tune Florence-2-base with LoRA on caption data.

    Args:
        data_path: Path to JSONL with {"image_path", "caption"} pairs.
        output_dir: Where to save LoRA adapter weights.
        base_model: HuggingFace model ID for Florence-2.
        epochs: Training epochs (5 for focused fine-tuning).
        batch_size: Batch size (8 for RTX 3090 at 224px).
        lr: Learning rate for LoRA params (2e-4 typical).
        lora_rank: LoRA rank (16 = good quality/speed tradeoff).
        lora_alpha: LoRA alpha scaling (2× rank = 32).
        max_samples: Limit training samples for testing.
        resume: Resume from existing LoRA adapter.
    """
    print("=" * 60)
    print("Florence-2 LoRA Fine-Tuning")
    print(f"  Base model: {base_model}")
    print(f"  Data: {data_path}")
    print(f"  Output: {output_dir}")
    print(f"  Epochs: {epochs}")
    print(f"  Batch: {batch_size}")
    print(f"  LR: {lr}")
    print(f"  LoRA rank: {lora_rank}, alpha: {lora_alpha}")
    print("=" * 60)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  Device: {device} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")
    print()

    # Load training data
    print("Loading training data...")
    records = load_training_data(data_path, max_samples)
    print(f"  Loaded {len(records)} training pairs")

    # Import model and processor
    print("Loading Florence-2 model...")
    from transformers import AutoConfig, AutoModelForCausalLM, AutoProcessor

    # Force eager attention to avoid _supports_sdpa / flash_attn issues with
    # transformers 5.x (Florence-2's custom modeling code was written for 4.x)
    config = AutoConfig.from_pretrained(base_model, trust_remote_code=True)
    config._attn_implementation = "eager"

    processor = AutoProcessor.from_pretrained(base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        config=config,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
        attn_implementation="eager",
    ).to(device)

    # Freeze vision encoder (we only fine-tune the language decoder)
    for param in model.vision_tower.parameters():
        param.requires_grad = False
    print("  Vision encoder frozen")

    # Apply LoRA
    print(f"Applying LoRA (rank={lora_rank}, alpha={lora_alpha})...")
    from peft import LoraConfig, PeftModel, TaskType, get_peft_model

    if resume and os.path.exists(output_dir):
        print(f"  Resuming from {output_dir}")
        model = PeftModel.from_pretrained(model, output_dir)
    else:
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=lora_rank,
            lora_alpha=lora_alpha,
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
            lora_dropout=0.05,
            bias="none",
        )
        model = get_peft_model(model, lora_config)

    model.print_trainable_parameters()

    # Prepare dataset
    from PIL import Image
    from torch.utils.data import DataLoader, Dataset

    class CaptionDataset(Dataset):
        def __init__(self, records, processor):
            self.records = records
            self.processor = processor
            # Override tokenizer's model_max_length — Florence-2's processor
            # sets this incorrectly on some transformers versions
            if hasattr(processor, 'tokenizer'):
                processor.tokenizer.model_max_length = 512
                processor.tokenizer.max_length = 512

        def __len__(self):
            return len(self.records)

        def __getitem__(self, idx):
            rec = self.records[idx]
            try:
                image = Image.open(rec["image_path"]).convert("RGB")
            except Exception as e:
                print(f"  WARNING: Cannot load {rec['image_path']}: {e}")
                # Return a placeholder
                image = Image.new("RGB", (224, 224))

            caption = rec["caption"]

            # Florence-2 uses a specific prompt format
            # Florence-2's DaViT encoder requires square inputs. Our GT dataset
            # images are 1280x720, so resize explicitly to 768x768 first.
            image = image.resize((768, 768), Image.LANCZOS)

            prompt = "<CAPTION>"
            # processor subtracts image_seq_length (~577) from max_length,
            # so pass a total that leaves room for text tokens
            inputs = self.processor(
                text=prompt,
                images=image,
                return_tensors="pt",
                padding="max_length",
                max_length=1024,
                truncation=True,
            )

            # Tokenize target caption (no image tokens here, so 512 is fine)
            target = self.processor.tokenizer(
                caption,
                return_tensors="pt",
                padding="max_length",
                max_length=512,
                truncation=True,
            )

            # Remove batch dims and set labels
            for k, v in inputs.items():
                inputs[k] = v.squeeze(0)
            inputs["labels"] = target["input_ids"].squeeze(0)

            return inputs

    train_dataset = CaptionDataset(records, processor)
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=4,
        pin_memory=True,
    )

    # Training
    from transformers import get_scheduler

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    num_training_steps = epochs * len(train_loader)
    scheduler = get_scheduler(
        "cosine",
        optimizer=optimizer,
        num_warmup_steps=int(0.05 * num_training_steps),
        num_training_steps=num_training_steps,
    )

    os.makedirs(output_dir, exist_ok=True)
    model.train()

    global_step = 0
    best_loss = float("inf")

    for epoch in range(epochs):
        print(f"\nEpoch {epoch + 1}/{epochs}")
        epoch_loss = 0.0
        epoch_start = time.time()

        for step, batch in enumerate(train_loader):
            # Move batch to device
            batch = {k: v.to(device) for k, v in batch.items()}

            # Cast pixel_values to model dtype (image processor returns float32
            # but model may be bfloat16)
            if "pixel_values" in batch and batch["pixel_values"].dtype != next(model.parameters()).dtype:
                batch["pixel_values"] = batch["pixel_values"].to(dtype=next(model.parameters()).dtype)

            outputs = model(**batch)
            loss = outputs.loss

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            epoch_loss += loss.item()
            global_step += 1

            if step % 50 == 0:
                elapsed = time.time() - epoch_start
                rate = (step + 1) / max(elapsed, 1e-6)
                print(f"  Step {step}/{len(train_loader)} | "
                      f"Loss: {loss.item():.4f} | "
                      f"LR: {scheduler.get_last_lr()[0]:.2e} | "
                      f"{rate:.1f} steps/s")

        avg_loss = epoch_loss / len(train_loader)
        epoch_time = time.time() - epoch_start
        print(f"  Epoch {epoch + 1} complete: avg_loss={avg_loss:.4f}, "
              f"time={epoch_time:.0f}s")

        # Save checkpoint
        if avg_loss < best_loss:
            best_loss = avg_loss
            model.save_pretrained(output_dir)
            processor.save_pretrained(output_dir)
            print(f"  ✓ Best model saved to {output_dir} (loss={avg_loss:.4f})")

        # Save epoch checkpoint
        epoch_dir = os.path.join(output_dir, f"epoch-{epoch + 1}")
        model.save_pretrained(epoch_dir)

    print(f"\n{'=' * 60}")
    print("Training complete!")
    print(f"Best loss: {best_loss:.4f}")
    print(f"LoRA adapter saved: {output_dir}")
    print(f"Size: {sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(output_dir) for f in fn) / 1024 / 1024:.1f} MB")
    print(f"{'=' * 60}")

    # Save training metadata
    metadata = {
        "base_model": base_model,
        "lora_rank": lora_rank,
        "lora_alpha": lora_alpha,
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "best_loss": best_loss,
        "num_samples": len(records),
        "device": device,
    }
    meta_path = os.path.join(output_dir, "training_metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Training metadata saved: {meta_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune Florence-2 with LoRA on Wine caption data"
    )
    parser.add_argument("--data", required=True,
                        help="Path to caption training JSONL")
    parser.add_argument("--output", default="/models/florence2/wine-caption-lora",
                        help="Output directory for LoRA adapter")
    parser.add_argument("--base-model", default="microsoft/Florence-2-base",
                        help="HuggingFace model ID")
    parser.add_argument("--epochs", type=int, default=5,
                        help="Training epochs")
    parser.add_argument("--batch", type=int, default=8,
                        help="Batch size")
    parser.add_argument("--lr", type=float, default=2e-4,
                        help="Learning rate")
    parser.add_argument("--lora-rank", type=int, default=16,
                        help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32,
                        help="LoRA alpha")
    parser.add_argument("--max-samples", type=int, default=None,
                        help="Limit training samples")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing LoRA adapter")
    args = parser.parse_args()

    fine_tune(
        data_path=args.data,
        output_dir=args.output,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch,
        lr=args.lr,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
        max_samples=args.max_samples,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
