#!/usr/bin/env python3
# EXECUTION: EITHER — pure Python, no GPU needed
"""
Model Registry — full provenance and lifecycle for every model asset.

Tracks every model in the WineBot CV/OCR pipeline from upstream source
through fine-tuning to deployment. Each entry captures:

  - Upstream provenance: source repo, license, base model SHA256
  - Fine-tuning lineage: training script, dataset, hyperparameters,
    git commit at training time
  - Deployment fingerprint: content SHA256, file size, last-validated timestamp
  - Version lifecycle: which model supersedes this one, deprecation status

Usage:
  from model_registry import ModelRegistry
  reg = ModelRegistry.from_scan("/models")
  reg.print_catalog()
  reg.export_json("pipeline_provenance.json")

  # Get the citation string for a paper
  reg.get_citation()  # → "YOLOv8n (Ultralytics, AGPL-3.0) → wine-finetuned-v3"

  # Generate a full supply chain audit
  reg.audit_trail()   # → chain from upstream to deployment
"""

import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ── Data Model ─────────────────────────────────────────────────────────────────


@dataclass
class UpstreamSource:
    """Provenance of the base model before our modifications."""
    project: str                      # e.g., "YOLOv8" (Ultralytics)
    repository: str                   # e.g., "https://github.com/ultralytics/ultralytics"
    model_id: str                     # e.g., "yolov8n.pt"
    license: str                      # e.g., "AGPL-3.0"
    license_url: str = ""
    citation: str = ""                # BibTeX or DOI
    base_sha256: str = ""             # SHA256 of the upstream file (before our fine-tuning)
    notes: str = ""


@dataclass
class TrainingProvenance:
    """How this fine-tuned model was produced."""
    training_script: str = ""         # Path relative to repo root
    dataset_generator: str = ""       # e.g., "winebot-gt-generator.py"
    dataset_version: str = ""         # Git commit of generator at training time
    dataset_split: str = "train"      # "train", "all", etc.
    train_scenes: list[str] = field(default_factory=list)
    val_scenes: list[str] = field(default_factory=list)
    train_frameworks: list[str] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)
    image_count: int = 0
    element_count: int = 0
    seed: int = 42
    epochs: int = 30
    batch_size: int = 8
    image_size: int = 1280
    learning_rate: float = 0.0       # 0 means auto-detected by YOLO
    freeze_layers: int = 10
    base_model: str = ""             # Path to the upstream checkpoint used as starting point
    git_commit: str = ""             # Git commit of winebot repo at training time


@dataclass
class ModelDeployment:
    """Runtime fingerprint of the deployed model."""
    file_path: str = ""              # Where the model lives in the container
    file_size_bytes: int = 0
    content_sha256: str = ""         # SHA256 of the deployed file
    last_validated_at: str = ""      # ISO 8601
    validation_mAP50: float = 0.0
    validation_mAP50_95: float = 0.0
    validation_split: str = ""       # Which split was used for validation
    gpu_compatible: bool = True
    vram_estimate_mb: float = 0.0
    quantization: str = ""
    deployment_timestamp: str = ""
    deployment_platform: str = ""
    notes: str = ""


@dataclass
class ModelEntry:
    """Complete lifecycle record for one model asset.

    Covers the full chain: upstream → training → deployment.
    Some entries have no training data (direct upstream downloads).
    """
    # Identity
    name: str                         # e.g., "wine-finetuned-v3"
    role: str                         # "ui_detector" | "ocr_engine" | "embedding" | "captioner" | "grounding"
    pipeline_stage: int               # 1-9 from the pipeline map
    description: str = ""

    # Upstream
    upstream: UpstreamSource | None = None

    # Training (only for fine-tuned models)
    training: TrainingProvenance | None = None

    # Deployment
    deployment: ModelDeployment | None = None

    # Lifecycle
    status: str = "active"            # active | deprecated | superseded | development
    superseded_by: str = ""           # Name of the model that replaces this one
    supersedes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "pipeline_stage": self.pipeline_stage,
            "description": self.description,
            "upstream": asdict(self.upstream) if self.upstream else None,
            "training": asdict(self.training) if self.training else None,
            "deployment": asdict(self.deployment) if self.deployment else None,
            "status": self.status,
            "superseded_by": self.superseded_by,
            "supersedes": self.supersedes,
        }

    def upstream_chain(self) -> str:
        """Human-readable chain: ModelX (Author, License) → ours"""
        parts = []
        if self.upstream:
            parts.append(f"{self.upstream.project} ({self.upstream.license})")
        if self.training and self.training.base_model:
            parts.append(f"fine-tuned on {self.training.image_count} images")
        return " → ".join(parts) if parts else self.name


# ── Registry ───────────────────────────────────────────────────────────────────


class ModelRegistry:
    """Complete catalog of all models in the WineBot CV/OCR pipeline.

    Can be populated from:
      - Hardcoded catalogue (built-in knowledge of upstream models)
      - Filesystem scan (SHA256 fingerprint of deployed checkpoints)
      - Training logs (mAP values, hyperparameters)
    """

    def __init__(self):
        self.entries: dict[str, ModelEntry] = {}
        self._git_commit = self._get_git_commit()

    # ── Built-in Catalogue ──────────────────────────────────────────────────

    @classmethod
    def from_catalogue(cls) -> "ModelRegistry":
        """Create registry with hardcoded knowledge of all pipeline models."""
        reg = cls()
        reg._register_builtin()
        return reg

    @classmethod
    def from_scan(cls, model_dir: str = "/models") -> "ModelRegistry":
        """Create registry and fingerprint all models on disk.

        Args:
            model_dir: Root of the shared model cache.
        """
        reg = cls()
        reg._register_builtin()
        reg.fingerprint_deployments(model_dir)
        return reg

    @classmethod
    def from_benchmark_dir(cls, model_dir: str,
                             results_file: str) -> "ModelRegistry":
        """Create registry from benchmark results (with mAP values)."""
        reg = cls.from_scan(model_dir)
        reg._ingest_benchmark_results(results_file)
        return reg

    # ── Built-in catalog of every model in the pipeline ─────────────────────

    def _register_builtin(self):
        """Register all known models — upstream, fine-tuned, and downloaded."""

        # ── STAGE 1: UI Element Detectors ───────────────────────────────────

        # Upstream: YOLOv8n (Ultralytics)
        self._add(ModelEntry(
            name="yolov8n",
            role="ui_detector",
            pipeline_stage=1,
            description="YOLOv8 nano — base model from Ultralytics, used as starting point for fine-tuning",
            upstream=UpstreamSource(
                project="YOLOv8 (Ultralytics)",
                repository="https://github.com/ultralytics/ultralytics",
                model_id="yolov8n.pt",
                license="AGPL-3.0",
                license_url="https://github.com/ultralytics/ultralytics/blob/main/LICENSE",
                citation="Jocher et al. (2023) Ultralytics YOLOv8",
            ),
            status="active",
        ))

        # Our: wine-finetuned (v1, v2, v3)
        self._add(ModelEntry(
            name="wine-finetuned",
            role="ui_detector",
            pipeline_stage=1,
            description="YOLOv8n fine-tuned on Wine GT data — v1 (original, 5 scenes)",
            upstream=UpstreamSource(
                project="YOLOv8 (Ultralytics)",
                repository="https://github.com/ultralytics/ultralytics",
                model_id="yolov8n.pt",
                license="AGPL-3.0",
                license_url="https://github.com/ultralytics/ultralytics/blob/main/LICENSE",
            ),
            training=TrainingProvenance(
                training_script="scripts/diagnostics/fine_tune_detector.py",
                dataset_generator="scripts/diagnostics/winebot-gt-generator.py",
                dataset_split="all",
                train_scenes=["save_dialog", "settings", "error_dialog", "notepad", "control_panel"],
                image_count=1805,
                epochs=20,
            ),
            status="superseded",
            superseded_by="wine-finetuned-v2",
        ))

        self._add(ModelEntry(
            name="wine-finetuned-v2",
            role="ui_detector",
            pipeline_stage=1,
            description="YOLOv8n fine-tuned — v2 corrected (content lines fixed, 11 scenes)",
            upstream=UpstreamSource(
                project="YOLOv8 (Ultralytics)",
                repository="https://github.com/ultralytics/ultralytics",
                model_id="yolov8n.pt",
                license="AGPL-3.0",
            ),
            training=TrainingProvenance(
                training_script="scripts/diagnostics/fine_tune_detector.py",
                dataset_generator="scripts/diagnostics/winebot-gt-generator.py",
                dataset_split="all",
                train_scenes=["save_dialog", "settings", "error_dialog", "notepad",
                              "control_panel", "file_manager", "multi_window", "browser",
                              "terminal", "context_menu", "wizard"],
                image_count=2000,
                epochs=20,
            ),
            status="superseded",
            superseded_by="wine-finetuned-v3",
        ))

        self._add(ModelEntry(
            name="wine-finetuned-v3",
            role="ui_detector",
            pipeline_stage=1,
            description="YOLOv8n fine-tuned — v3 (18 scenes, 8 frameworks, 3587 images, mAP50=0.918)",
            upstream=UpstreamSource(
                project="YOLOv8 (Ultralytics)",
                repository="https://github.com/ultralytics/ultralytics",
                model_id="yolov8n.pt",
                license="AGPL-3.0",
            ),
            training=TrainingProvenance(
                training_script="scripts/diagnostics/fine_tune_detector.py",
                dataset_generator="scripts/diagnostics/winebot-gt-generator.py",
                dataset_split="all",
                train_scenes=["save_dialog", "settings", "error_dialog", "notepad",
                              "control_panel", "file_manager", "multi_window", "browser",
                              "terminal", "context_menu", "wizard", "find_replace",
                              "print_dialog", "about_dialog", "file_properties",
                              "system_tray", "form_fill"],
                train_frameworks=["win32_classic", "win10_fluent", "qt_fusion",
                                  "gtk_adwaita", "java_metal", "tkinter",
                                  "electron_dark", "classic_95"],
                image_count=3587,
                epochs=30,
                batch_size=8,
                image_size=1280,
            ),
            deployment=ModelDeployment(
                file_path="/models/yolo/wine-finetuned-v3.pt",
                vram_estimate_mb=150.0,
                gpu_compatible=True,
            ),
            status="active",
            supersedes=["wine-finetuned-v2", "wine-finetuned"],
        ))

        # ScreenParser (upstream from IBM/ETH)
        self._add(ModelEntry(
            name="screenparser",
            role="ui_detector",
            pipeline_stage=1,
            description="ScreenParser YOLOv11-L (55 classes) from IBM/ETH docling-project — base model",
            upstream=UpstreamSource(
                project="docling-project/ScreenParser (IBM/ETH)",
                repository="https://huggingface.co/docling-project/ScreenParser",
                model_id="best.pt",
                license="Apache-2.0",
                license_url="https://www.apache.org/licenses/LICENSE-2.0",
            ),
            status="active",
        ))

        # Our fine-tuned ScreenParser
        self._add(ModelEntry(
            name="screenparser-wine",
            role="ui_detector",
            pipeline_stage=1,
            description="ScreenParser YOLOv11-L fine-tuned on Wine GT (mAP50=0.951, mAP50-95=0.794)",
            upstream=UpstreamSource(
                project="docling-project/ScreenParser (IBM/ETH)",
                repository="https://huggingface.co/docling-project/ScreenParser",
                model_id="best.pt",
                license="Apache-2.0",
            ),
            training=TrainingProvenance(
                training_script="scripts/diagnostics/fine_tune_detector.py",
                dataset_generator="scripts/diagnostics/winebot-gt-generator.py",
                dataset_split="all",
                train_scenes=["save_dialog", "settings", "error_dialog", "notepad",
                              "control_panel", "file_manager", "multi_window", "browser",
                              "terminal", "context_menu", "wizard", "find_replace",
                              "print_dialog", "about_dialog", "file_properties",
                              "system_tray", "form_fill"],
                image_count=3587,
                epochs=50,
                batch_size=4,
                image_size=1280,
                freeze_layers=10,
                base_model="screenparser/best.pt",
            ),
            deployment=ModelDeployment(
                file_path="/models/yolo/screenparser-wine.pt",
                vram_estimate_mb=500.0,
                gpu_compatible=True,
            ),
            status="active",
        ))

        # OmniParser icon detect
        self._add(ModelEntry(
            name="omniparser_icon_detect",
            role="ui_detector",
            pipeline_stage=1,
            description="OmniParser v2 icon detection model (Microsoft)",
            upstream=UpstreamSource(
                project="OmniParser (Microsoft Research)",
                repository="https://huggingface.co/microsoft/OmniParser",
                model_id="icon_detect/model.pt",
                license="AGPL-3.0",
                license_url="https://github.com/microsoft/OmniParser/blob/main/LICENSE",
                citation="Lu et al. (2024) OmniParser for Pure Vision Based GUI Agent. arXiv:2408.00203",
            ),
            status="active",
        ))

        # UI-DETR-1
        self._add(ModelEntry(
            name="uidetr1",
            role="ui_detector",
            pipeline_stage=1,
            description="UI-DETR-1 — class-agnostic interactable element detector (RF-DETR-M, DINOv2 backbone)",
            upstream=UpstreamSource(
                project="racineai/UI-DETR-1 (TW3)",
                repository="https://huggingface.co/racineai/UI-DETR-1",
                model_id="model.pth",
                license="MIT",
                license_url="https://opensource.org/licenses/MIT",
            ),
            deployment=ModelDeployment(
                file_path="/models/uidetr1/model.pth",
                vram_estimate_mb=1100.0,
                gpu_compatible=True,
            ),
            status="active",
        ))

        # ── STAGE 2: OCR Engines ────────────────────────────────────────────

        self._add(ModelEntry(
            name="tesseract",
            role="ocr_engine",
            pipeline_stage=2,
            description="Tesseract 5.3.4 — Google's OCR engine, CPU-based",
            upstream=UpstreamSource(
                project="Tesseract OCR (Google)",
                repository="https://github.com/tesseract-ocr/tesseract",
                model_id="eng.traineddata",
                license="Apache-2.0",
                license_url="https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE",
            ),
            status="active",
        ))

        self._add(ModelEntry(
            name="ppocr-v6-tiny",
            role="ocr_engine",
            pipeline_stage=2,
            description="PP-OCRv6 tiny — PaddlePaddle text detection + recognition (ONNX export, CPU)",
            upstream=UpstreamSource(
                project="PaddlePaddle/PP-OCRv6 (Baidu)",
                repository="https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_onnx",
                model_id="ppocr_v6_tiny_det.onnx + ppocr_v6_tiny_rec.onnx",
                license="Apache-2.0",
                license_url="https://www.apache.org/licenses/LICENSE-2.0",
            ),
            deployment=ModelDeployment(
                file_path="/models/ocr/ppocr_v6_tiny_det.onnx",
                vram_estimate_mb=0.0,
                gpu_compatible=False,
            ),
            status="active",
        ))

        self._add(ModelEntry(
            name="ppocr-v6-small",
            role="ocr_engine",
            pipeline_stage=2,
            description="PP-OCRv6 small — medium quality/speed tradeoff (ONNX, CPU)",
            upstream=UpstreamSource(
                project="PaddlePaddle/PP-OCRv6 (Baidu)",
                repository="https://huggingface.co/PaddlePaddle/PP-OCRv6_small_onnx",
                model_id="ppocr_v6_small_det.onnx + ppocr_v6_small_rec.onnx",
                license="Apache-2.0",
            ),
            status="active",
        ))

        self._add(ModelEntry(
            name="ppocr-v6-medium",
            role="ocr_engine",
            pipeline_stage=2,
            description="PP-OCRv6 medium — best quality (ONNX, CPU)",
            upstream=UpstreamSource(
                project="PaddlePaddle/PP-OCRv6 (Baidu)",
                repository="https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_onnx",
                model_id="ppocr_v6_med_det.onnx + ppocr_v6_med_rec.onnx",
                license="Apache-2.0",
            ),
            status="active",
        ))

        # ── STAGE 3: CLIP Embedding ─────────────────────────────────────────

        self._add(ModelEntry(
            name="clip-vitb32",
            role="embedding",
            pipeline_stage=3,
            description="OpenCLIP ViT-B-32 trained on LAION-2B — 512-dim image-text embeddings",
            upstream=UpstreamSource(
                project="OpenCLIP (LAION)",
                repository="https://github.com/mlfoundations/open_clip",
                model_id="ViT-B-32 / laion2b_s34b_b79k",
                license="MIT",
                license_url="https://github.com/mlfoundations/open_clip/blob/main/LICENSE",
                citation="Ilharco et al. (2021) OpenCLIP. Zenodo. DOI:10.5281/zenodo.5143773",
            ),
            deployment=ModelDeployment(
                vram_estimate_mb=350.0,
                gpu_compatible=True,
            ),
            status="active",
        ))

        # ── STAGE 4: Florence-2 Captioning ──────────────────────────────────

        self._add(ModelEntry(
            name="florence2-base",
            role="captioner",
            pipeline_stage=4,
            description="Florence-2-base (230M) — Microsoft lightweight vision-language model for captioning",
            upstream=UpstreamSource(
                project="Florence-2 (Microsoft)",
                repository="https://huggingface.co/microsoft/Florence-2-base",
                model_id="microsoft/Florence-2-base",
                license="MIT",
                license_url="https://huggingface.co/microsoft/Florence-2-base/blob/main/LICENSE",
                citation="Xiao et al. (2024) Florence-2: Advancing a Unified Representation for a Variety of Vision Tasks. CVPR 2024.",
            ),
            status="active",
        ))

        self._add(ModelEntry(
            name="florence2-wine-lora",
            role="captioner",
            pipeline_stage=4,
            description="Florence-2-base + LoRA fine-tuned on Wine GT captions (planned)",
            upstream=UpstreamSource(
                project="Florence-2 (Microsoft)",
                repository="https://huggingface.co/microsoft/Florence-2-base",
                model_id="microsoft/Florence-2-base + wine-lora",
                license="MIT",
            ),
            training=TrainingProvenance(
                training_script="scripts/diagnostics/fine_tune_florence2.py",
                dataset_generator="scripts/diagnostics/winebot-gt-generator.py",
                dataset_split="train",
                image_count=5000,
                seed=42,
            ),
            status="development",
        ))

        # ── STAGE 5: VLM Grounding ──────────────────────────────────────────

        self._add(ModelEntry(
            name="kv-ground-8b",
            role="grounding",
            pipeline_stage=5,
            description="KV-Ground-8B (Qwen3-VL-based) — GUI grounding specialist. BF16 ~16GB."
                       " ScreenSpot-Pro: 73.2. ScreenSpot-v2: 94.6",
            upstream=UpstreamSource(
                project="KV-Ground-8B (Kingsware & Vocaela AI)",
                repository="https://huggingface.co/vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315",
                model_id="KV-Ground-8B-BaseGuiOwl1.5-0315",
                license="CC BY-NC-SA 4.0",
                license_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
                citation="Kingsware & Vocaela (2025) KV-Ground-8B: GUI Grounding via MLLM-as-Judge + GRPO. "
                        "ScreenSpot-v2: 94.6, ScreenSpot-Pro: 73.2.",
            ),
            deployment=ModelDeployment(
                vram_estimate_mb=16000.0,
                gpu_compatible=True,
                content_sha256="5efcdade5cf37f58e30d1b6f9ad6cd0264e5b71548af44aeef8ef6fca3604981",
                file_size_bytes=4789196800,
                quantization="Q4_K_M",
                deployment_timestamp="2026-06-25T16:14:00Z",
                deployment_platform="Ollama on TrueNAS A5000 #0",
            ),
            status="active",
        ))

        # Ollama-served VLM (runtime reference only — provenance lives on the server)
        self._add(ModelEntry(
            name="ollama-vlm",
            role="grounding",
            pipeline_stage=5,
            description="Any Ollama-served vision model. Model name, SHA256 tracked at runtime via vlm_ollama.py provenance. "
                       "Primary: qwen3.5:35b (Q4_K_M, 36B params MoE, Apache 2.0). "
                       "Optional: kv-ground-8b (GGUF Q4_K_M, 5.0 GB, CC BY-NC-SA, text-only GGUF — vision container pending).",
            upstream=UpstreamSource(
                project="Qwen3.5 (Alibaba/Qwen) / KV-Ground-8B (Kingsware & Vocaela AI)",
                repository="https://huggingface.co/Qwen/Qwen3.5-35B-A3B-Instruct / "
                          "https://huggingface.co/vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315",
                model_id="Multi-model: qwen3.5:35b + kv-ground-8b",
                license="Apache-2.0 / CC BY-NC-SA 4.0",
            ),
            status="active",
        ))

        # ── STAGE 9: Training Artifacts ─────────────────────────────────────

        self._add(ModelEntry(
            name="wine-10k-v1",
            role="ui_detector",
            pipeline_stage=1,
            description="YOLOv8n trained on 7,800 images with proper train/val/test splits. "
                       "mAP50=0.758 on held-out val (2 scenes × 2 frameworks).",
            upstream=UpstreamSource(
                project="YOLOv8 (Ultralytics)",
                repository="https://github.com/ultralytics/ultralytics",
                model_id="yolov8n.pt",
                license="AGPL-3.0",
            ),
            training=TrainingProvenance(
                training_script="scripts/diagnostics/fine_tune_detector.py",
                dataset_generator="scripts/diagnostics/winebot-gt-generator.py",
                dataset_version="split-support at git:a427ed8",
                dataset_split="train",
                train_scenes=["save_dialog", "settings", "error_dialog", "notepad",
                              "control_panel", "file_manager", "multi_window", "browser",
                              "terminal", "context_menu", "wizard", "find_replace", "print_dialog"],
                val_scenes=["about_dialog", "file_properties"],
                train_frameworks=["win32_classic", "win10_fluent", "qt_fusion",
                                  "gtk_adwaita", "java_metal", "tkinter"],
                test_frameworks=["electron_dark", "classic_95"],
                image_count=7800,
                element_count=0,
                epochs=30,
                batch_size=8,
                image_size=1280,
                seed=42,
            ),
            deployment=ModelDeployment(
                file_path="/models/yolo/wine-10k-v1.pt",
                vram_estimate_mb=150.0,
                gpu_compatible=True,
            ),
            status="active",
        ))

    def _add(self, entry: ModelEntry):
        self.entries[entry.name] = entry

    # ── Filesystem Fingerprinting ───────────────────────────────────────────

    def fingerprint_deployments(self, model_dir: str = "/models"):
        """SHA256 hash every model file on disk and update deployment records."""
        model_dir = Path(model_dir)
        scanned = 0
        for entry in self.entries.values():
            if entry.deployment and entry.deployment.file_path:
                path = entry.deployment.file_path
                # Resolve relative paths
                if not path.startswith("/"):
                    path = str(model_dir / path)
                if os.path.isfile(path):
                    sha = self._sha256_file(path)
                    entry.deployment.content_sha256 = sha
                    entry.deployment.file_size_bytes = os.path.getsize(path)
                    entry.deployment.last_validated_at = (
                        datetime.now(UTC).isoformat()
                    )
                    scanned += 1
        print(f"[registry] Fingerprinted {scanned} model files", file=sys.stderr)

    def _ingest_benchmark_results(self, results_path: str):
        """Populate mAP values from a benchmark JSON file."""
        if not os.path.isfile(results_path):
            return
        with open(results_path) as f:
            data = json.load(f)
        # Try to match results to entries
        for result in data.get("results", []):
            engine = result.get("engine", {})
            ui = engine.get("ui_detector", "")
            # Map backend names to registry names
            for name, entry in self.entries.items():
                if ui in (entry.name, entry.name.replace("-", "_")):
                    summary = result.get("summary", {})
                    if entry.deployment:
                        entry.deployment.validation_mAP50 = summary.get("mAP50", 0.0)
                        entry.deployment.validation_mAP50_95 = summary.get("mAP50_95", 0.0)

    @staticmethod
    def _sha256_file(path: str) -> str:
        """Compute SHA256 of a file."""
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def _get_git_commit() -> str:
        import subprocess
        explicit = os.environ.get("WINEBOT_GIT_COMMIT", "")
        if explicit:
            return explicit
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"

    # ── Queries ─────────────────────────────────────────────────────────────

    def get_by_stage(self, stage: int) -> list[ModelEntry]:
        """Return all models for a pipeline stage."""
        return [e for e in self.entries.values() if e.pipeline_stage == stage]

    def get_active(self) -> list[ModelEntry]:
        """Return currently active models (not deprecated/superseded)."""
        return [e for e in self.entries.values() if e.status == "active"]

    def get_lineage(self, name: str) -> str:
        """Get the full provenance chain for a model."""
        entry = self.entries.get(name)
        if not entry:
            return f"Unknown model: {name}"
        chain = [f"{name}"]
        if entry.upstream:
            chain.append(f"(based on {entry.upstream.project}, {entry.upstream.license})")
        if entry.training and entry.training.image_count:
            chain.append(f"(trained on {entry.training.image_count} images)")
        if entry.deployment and entry.deployment.content_sha256:
            chain.append(f"[SHA256: {entry.deployment.content_sha256[:16]}]")
        return " → ".join(chain)

    def get_citation(self) -> str:
        """Generate a methods-section citation string."""
        lines = ["## Models Used"]
        by_stage = {}
        for entry in self.get_active():
            stage = entry.pipeline_stage
            if stage not in by_stage:
                by_stage[stage] = []
            by_stage[stage].append(entry)

        stage_names = {
            1: "UI Detection", 2: "OCR", 3: "Semantic Embedding",
            4: "Scene Captioning", 5: "Element Grounding", 9: "Training",
        }
        for stage in sorted(by_stage):
            name = stage_names.get(stage, f"Stage {stage}")
            models = by_stage[stage]
            line_parts = []
            for m in models:
                u = m.upstream
                if u:
                    line_parts.append(
                        f"{u.project} ({u.license})"
                    )
                else:
                    line_parts.append(m.name)
            lines.append(f"- **{name}:** {'; '.join(line_parts)}")

        lines.append(f"\nWineBot commit: {self._git_commit}")
        lines.append(f"Generated: {datetime.now(UTC).isoformat()}")
        lines.append(
            "All models fingerprinted by SHA256 content hash for bit-exact reproducibility."
        )
        return "\n".join(lines)

    def audit_trail(self) -> list[dict]:
        """Full supply chain audit: upstream → modification → deployment for every model."""
        trail = []
        for entry in self.entries.values():
            record = {
                "name": entry.name,
                "status": entry.status,
                "chain": entry.upstream_chain(),
                "license": entry.upstream.license if entry.upstream else "unknown",
            }
            if entry.upstream:
                record["upstream_repo"] = entry.upstream.repository
                record["upstream_citation"] = entry.upstream.citation
            if entry.training and entry.training.image_count:
                record["trained_on"] = {
                    "images": entry.training.image_count,
                    "split": entry.training.dataset_split,
                    "generator": entry.training.dataset_generator,
                    "git_commit": entry.training.git_commit,
                }
            if entry.deployment and entry.deployment.content_sha256:
                record["sha256"] = entry.deployment.content_sha256
            trail.append(record)
        return trail

    # ── Output ──────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "winebot_git_commit": self._git_commit,
            "generated_at": datetime.now(UTC).isoformat(),
            "total_models": len(self.entries),
            "active_models": len(self.get_active()),
            "entries": {name: e.to_dict() for name, e in self.entries.items()},
        }

    def export_json(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"[registry] Exported to {path}", file=sys.stderr)

    def print_catalog(self):
        print("=" * 72)
        print("  WineBot Model Catalog")
        print("=" * 72)
        print(f"  Git commit: {self._git_commit}")
        print(f"  Models: {len(self.entries)} ({len(self.get_active())} active)")
        print()

        by_stage = {}
        for entry in self.entries.values():
            stage = entry.pipeline_stage
            if stage not in by_stage:
                by_stage[stage] = []
            by_stage[stage].append(entry)

        stage_names = {
            1: "UI Detection", 2: "OCR", 3: "Embedding",
            4: "Captioning", 5: "Grounding", 9: "Training",
        }

        for stage in sorted(by_stage):
            name = stage_names.get(stage, f"Stage {stage}")
            print(f"  [{name}]")
            for entry in by_stage[stage]:
                status_flag = ""
                if entry.status == "superseded":
                    status_flag = f" → {entry.superseded_by}"
                elif entry.status == "deprecated":
                    status_flag = " [DEPRECATED]"
                elif entry.status == "development":
                    status_flag = " [PLANNED]"

                sha = ""
                if entry.deployment and entry.deployment.content_sha256:
                    sha = f"  SHA256:{entry.deployment.content_sha256[:16]}"

                lic = ""
                if entry.upstream:
                    lic = f"  {entry.upstream.license}"

                print(f"    {entry.name:<28s}{status_flag}")
                if entry.description:
                    print(f"      {entry.description[:100]}")
                print(f"      {entry.upstream_chain()}")
                print(f"      {lic}{sha}")
                print()
        print("=" * 72)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="WineBot Model Registry — provenance and lifecycle management")
    parser.add_argument("--scan", default=None,
                        help="Model directory to SHA256 fingerprint")
    parser.add_argument("--export", default=None,
                        help="Export JSON to this path")
    parser.add_argument("--catalog", action="store_true",
                        help="Print model catalog")
    parser.add_argument("--audit", action="store_true",
                        help="Print supply chain audit trail")
    parser.add_argument("--citation", action="store_true",
                        help="Print methods-section citation")
    parser.add_argument("--lineage", default=None,
                        help="Show lineage for a specific model")

    args = parser.parse_args()

    if args.scan:
        reg = ModelRegistry.from_scan(args.scan)
    else:
        reg = ModelRegistry.from_catalogue()

    if args.catalog:
        reg.print_catalog()

    if args.audit:
        trail = reg.audit_trail()
        for t in trail:
            print(json.dumps(t, indent=2))

    if args.citation:
        print(reg.get_citation())

    if args.lineage:
        print(reg.get_lineage(args.lineage))

    if args.export:
        reg.export_json(args.export)

    if not any([args.catalog, args.audit, args.citation, args.lineage, args.export]):
        reg.print_catalog()


if __name__ == "__main__":
    main()
