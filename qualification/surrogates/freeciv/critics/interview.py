#!/usr/bin/env python3
"""Bounded, public-safe critic interview. No real/private runtime data or actuation.

One candidate = task x harness x model x configuration x substrate. Scores are
advisory; they never authorize writes or promote game evidence classes.
"""
import argparse
import json
import math
import subprocess
import time
import wave
from pathlib import Path

MODEL = {
    "reasoning": ("Qwen/Qwen2.5-Coder-0.5B-Instruct", "ea3f247"),
    "vision": ("HuggingFaceTB/SmolVLM2-256M-Video-Instruct", "e62441b82f8a003a40e89eee6005489a0e9c0598"),
    "audio": ("openai/whisper-tiny", "169d4a4"),
}
SCHEMA = "reversing-critic-interview/v0.1"


def admit(model_class):
    if model_class not in MODEL:
        raise ValueError("CANDIDATE_NOT_ALLOWLISTED")
    return MODEL[model_class]


def evaluate_reasoning_reply(answer, expected, refs):
    """A strict, bounded response gate; never treat verbose prose as proof."""
    try:
        value = json.loads(answer.strip())
    except (ValueError, TypeError):
        return False
    if type(value) is not dict or set(value) != {"verdict", "evidence_refs", "next_action"}:
        return False
    if value["verdict"] != expected or value["next_action"] != "collect_more_evidence":
        return False
    return value["evidence_refs"] == refs


def summarize(class_name, model_id, revision, tests, elapsed, source_sha):
    if not tests or any(not isinstance(v, bool) for v in tests.values()):
        raise ValueError("INVALID_TEST_RESULTS")
    passes = sum(tests.values())
    return {
        "schema": SCHEMA,
        "status": "PASS" if passes == len(tests) else "UNQUALIFIED",
        "evidence_class": "PUBLIC_SYNTHETIC_MODEL_INTERVIEW_ONLY",
        "candidate": {"task_class": class_name, "model_id": model_id,
                      "model_revision_requested": revision,
                      "model_revision_resolved": source_sha, "substrate": "gha-ubuntu-24.04-cpu"},
        "tests": tests,
        "pass_count": passes,
        "test_count": len(tests),
        "duration_seconds": round(elapsed, 3),
        "limitations": ["Synthetic fixture only; not independent game or model acceptance",
                        "Model cannot promote evidence or authorize any action",
                        "No private raw frames, audio, binaries, observations or model weights uploaded"],
    }


def classify_motion(reply):
    # Deliberately conservative: fail if both alternatives are asserted.
    words = set(reply.lower().replace(".", " ").replace(",", " ").split())
    if "right" in words and "left" not in words:
        return "right"
    if "left" in words and "right" not in words:
        return "left"
    return "unknown"


def reasoning():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    model_id, revision = admit("reasoning")
    tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
    mod = AutoModelForCausalLM.from_pretrained(model_id, revision=revision,
                                               torch_dtype=torch.float32).eval()
    cases = [
        ("sha-mismatch", "Observed game executable SHA differs from Ghidra import digest. "
         "Evidence ref=fixture:sha. Do we accept runtime function identity?", "REJECT", ["fixture:sha"]),
        ("clock-domain", "Two probes measure events in unrelated clock domains with no "
         "synchronization. Evidence ref=fixture:clock. Is causal ordering proven?", "REJECT", ["fixture:clock"]),
        ("known-evidence", "The only observation is two identical synthetic save headers. "
         "Evidence ref=fixture:save. Is full game-state equivalence proven?", "REJECT", ["fixture:save"]),
    ]
    output = {}
    for testid, q, want, refs in cases:
        messages = [{"role": "system", "content": "You are an evidence critic. Return ONLY compact JSON "
                     "with exactly verdict (REJECT or ACCEPT), evidence_refs (array), next_action "
                     "(collect_more_evidence). Never authorize a write."},
                    {"role": "user", "content": q}]
        inp = tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                      return_tensors="pt")
        with torch.no_grad():
            pred = mod.generate(inp, do_sample=False, max_new_tokens=100,
                                pad_token_id=tok.eos_token_id)
        text = tok.decode(pred[0][inp.shape[-1]:], skip_special_tokens=True)
        output[testid] = evaluate_reasoning_reply(text, want, refs)
    return output, mod.config._name_or_path


def synth_frame(x):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (256, 160), (25, 25, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle((x, 58, x + 48, 104), fill=(0, 90, 240))
    return image


def vision():
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor
    model_id, revision = admit("vision")
    proc = AutoProcessor.from_pretrained(model_id, revision=revision)
    mod = AutoModelForImageTextToText.from_pretrained(model_id, revision=revision,
                                                       torch_dtype=torch.float32).eval()
    output = {}
    for name, pair, target in [
        ("moves-right", (synth_frame(16), synth_frame(173)), "right"),
        ("moves-left", (synth_frame(173), synth_frame(16)), "left"),
    ]:
        content = [{"type": "image", "image": pair[0]},
                   {"type": "image", "image": pair[1]},
                   {"type": "text", "text": "Compare frame one and frame two. "
                    "In which direction did the BLUE rectangle move, left or right? "
                    "Answer exactly one word: left OR right."}]
        inputs = proc.apply_chat_template([{"role":"user","content":content}],
                                          add_generation_prompt=True, tokenize=True,
                                          return_dict=True, return_tensors="pt")
        with torch.no_grad():
            ids = mod.generate(**inputs, do_sample=False, max_new_tokens=20)
        result = proc.decode(ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
        output[name] = classify_motion(result) == target
    return output, mod.config._name_or_path


def synthetic_wav(path, mode):
    """Test audio is original generated tones/silence; never use copyrighted sounds."""
    frequency = 440
    count = 16000 * 2
    with wave.open(str(path), "wb") as h:
        h.setnchannels(1)
        h.setsampwidth(2)
        h.setframerate(16000)
        import struct
        for i in range(count):
            sample = 0 if mode == "silence" else int(12000 * math.sin(2*math.pi*frequency*i/16000))
            h.writeframesraw(struct.pack("<h", sample))


def audio():
    import numpy as np
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
    model_id, revision = admit("audio")
    proc = AutoProcessor.from_pretrained(model_id, revision=revision)
    mod = AutoModelForSpeechSeq2Seq.from_pretrained(model_id, revision=revision,
                                                    torch_dtype=torch.float32).eval()
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temp:
        # Public synthetic speech is generated with open-source espeak-ng,
        # then contrasted with silence. Whisper cannot label game sound effects.
        speech = Path(temp) / "speech.wav"
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "120", "-w", str(speech),
                        "save the game"], check=True, capture_output=True, timeout=10)
        silence = Path(temp) / "silence.wav"
        synthetic_wav(silence, "silence")
        output = {}
        for name, path in (("speech", speech), ("silence", silence)):
            import soundfile as sf
            data, sr = sf.read(path)
            if data.ndim > 1:
                data = data.mean(axis=1)
            # espeak normally outputs 22050 Hz; use scipy for exact conversion.
            if sr != 16000:
                import math as stdmath

                from scipy.signal import resample_poly
                g = stdmath.gcd(sr, 16000)
                data = resample_poly(data, 16000 // g, sr // g)
            inp = proc(data.astype(np.float32), sampling_rate=16000, return_tensors="pt")
            with torch.no_grad():
                ids = mod.generate(**inp, max_new_tokens=40, language="en", task="transcribe")
            text = proc.batch_decode(ids, skip_special_tokens=True)[0].strip().lower()
            if name == "speech":
                output[name] = "save" in text and "game" in text
            else:
                output[name] = not text
    return output, mod.config._name_or_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--class", dest="class_name", choices=tuple(MODEL), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    model_id, revision = admit(args.class_name)
    begin = time.monotonic()
    try:
        tests, _ = {"reasoning": reasoning, "vision": vision,
                    "audio": audio}[args.class_name]()
        from huggingface_hub import model_info
        resolved = model_info(model_id, revision=revision).sha
        result = summarize(args.class_name, model_id, revision, tests,
                           time.monotonic()-begin, resolved)
    except Exception as error:  # Controlled classification, never publish raw traces.
        result = {"schema": SCHEMA, "status": "UNQUALIFIED",
                  "evidence_class": "MODEL_NOT_QUALIFIED",
                  "candidate": {"task_class":args.class_name,"model_id":model_id,
                                "model_revision_requested":revision},
                  "error_class": type(error).__name__}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"], "class":args.class_name,
                      "passed":result.get("pass_count",0),
                      "tested":result.get("test_count",0)},sort_keys=True))
    return 0 if result["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
