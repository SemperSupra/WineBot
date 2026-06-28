# WineBot Architecture & Gap Analysis

**Date:** 2026-06-28
**Context:** Architecture review following cross-validation setup, credential management policy implementation, and annotation tool creation.

---

## Architecture Overview

### Three-Tier Deployment

```
┌───────────────────────────────────────────────────────────────┐
│                    DOCKER HOST (Windows/Linux)                 │
│                                                               │
│  ┌─────────────────────┐    ┌─────────────────────────────┐   │
│  │  winebot (Wine)      │    │  winebot-cv (GPU Sidecar)   │   │
│  │  ──────────────────  │    │  ────────────────────────  │   │
│  │  Port 8000: FastAPI  │    │  Port 8001: FastAPI         │   │
│  │  Port 5900: VNC      │◄──►│  YOLO26-S v3 (22 class)    │   │
│  │  Port 6080: noVNC    │    │  PP-OCRv6 tiny + Tesseract  │   │
│  │  Wine 10.0 + X11     │    │  SigLIP2 CLIP embeddings    │   │
│  │  AHK/AutoIt scripting │    │  ML State Classifier (22)   │   │
│  │  mDNS discovery      │    │  Temporal element tracking  │   │
│  └─────────────────────┘    └──────────┬──────────────────┘   │
│                                        │ HTTP                  │
│                                        ▼                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              TrueNAS GPU Server (remote)                 │   │
│  │  ┌──────────────────┐  ┌──────────────────────────┐    │   │
│  │  │  A5000 #0         │  │  A5000 #1               │    │   │
│  │  │  Ollama (19 mod.) │  │  Captioning Sidecar     │    │   │
│  │  │  KV-Ground-8B     │  │  Florence-2 base        │    │   │
│  │  │  (4-bit GGUF)     │  │  ~135ms inference       │    │   │
│  │  └──────────────────┘  └──────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

### Containers & Services

| Container | Base | GPU | Entrypoint | Ports |
|-----------|------|-----|------------|-------|
| `winebot` (rel) | winebot-base (`intent-rel`) | CPU only | `/entrypoint.sh` → X11+VNC+API | 8000, 5900, 6080, 5354 |
| `winebot` (slim) | winebot-base (`intent-slim`) | CPU only | `/entrypoint.sh` → headless | — |
| `winebot-cv:gpu` | `nvidia/cuda:12.6.3-runtime` | RTX 3090 | `cv-sidecar-server.py --serve` | 8001 |
| `winebot-cv` (CPU) | `nvidia/cuda:12.6.3-runtime` | CPU | `cv-sidecar-server.py --serve` | 8001 |
| Captioning sidecar | Custom Dockerfile | A5000 #1 | `florence2_captioner.py` | 8002 |
| Test runner | Playwright-based | CPU | pytest | — |

### CI/CD Pipeline (GitHub Actions)

```
PR/Push to main
    │
    ▼
┌─────────────┐   ┌──────────────────┐   ┌───────────────┐
│ Pre-flight   │──►│ Integration       │──►│ Gates         │
│ Lint + Unit  │   │ Smoke test +      │   │ License check │
│ + E2E subset │   │ Trust pack gen    │   │ SBOM verify   │
└─────────────┘   └──────────────────┘   └───────┬───────┘
                                                  │
                                                  ▼
                                         ┌───────────────┐
                                         │ Release        │
                                         │ Build + push   │
                                         │ GHCR publish   │
                                         └───────────────┘
```

### Build Intents (Docker multi-stage)

| Intent | Size | Use Case |
|--------|------|----------|
| `intent-slim` | ~1.1GB | Minimal production, no pre-warmed prefix |
| `intent-rel-runner` | ~2.5GB | Headless automation runner |
| `intent-rel` | ~3.2GB | Interactive desktop with VNC |
| `intent-test` | ~3.8GB | Test runner with pytest + Playwright |
| `intent-dev` | ~4.0GB | Development with strace/lsof/nano |

---

## Gap Analysis

### ✅ Best Practices Met

| Practice | Implementation |
|----------|---------------|
| Multi-stage builds | 8 build stages, 7 intents — excellent layer optimization |
| Pinned base images | Digest-pinned (`base-2026-05-04`) for reproducibility |
| Health checks | Every service has Docker healthcheck with retry/interval/start-period |
| Read-only mounts | `apps:ro`, `automation/assets:ro` — defense in depth |
| CI/CD gating | Pre-flight → integration → gate → release |
| Test isolation | Containerized test runners, deterministic E2E |
| Deterministic ML | Seeded training, deterministic algorithms |
| Security scanning | Trivy in CI, pre-commit hooks |
| Model provenance | Registry tracks source, hash, deployment metadata |
| Fallback architecture | Every pipeline stage has automatic degradation |
| Structured config | Pydantic config with env var injection |
| Credential management | `INFRA_*` env vars, `.env.example`, deploy template |
| Container signing | Cosign in release workflow |
| SBOM generation | Syft in release workflow |

### 🟡 Medium Priority Gaps

| # | Gap | Current | Target | Effort |
|---|-----|---------|--------|--------|
| 1 | **No resource limits** | No `mem_limit`/`cpus` in compose | Add per-service limits to prevent GPU memory contention | 1h |
| 2 | **No metrics endpoint** | No Prometheus metrics | Add `/metrics` to FastAPI with `prometheus-client` | 2h |
| 3 | **No centralized logging** | Sidecar + wine log separately | Add Loki/Promtail or fluentd sidecar | 4h |
| 4 | **No rate limiting** | API unprotected against abuse | Add `slowapi` rate limiter per IP/token | 1h |
| 5 | **API token sync fragile** | Auto-generated per container, shared via file | Switch to deterministic token or Vault | 3h |
| 6 | **No canary/rollback** | Single image tag deploy | Add release tagging strategy (semver + git sha) | 2h |
| 7 | **No K8s manifests** | Docker Compose only | Add basic Helm chart or kustomize overlay | 4h |

### 🔴 High Priority Gaps

| # | Gap | Current | Target | Effort |
|---|-----|---------|--------|--------|
| 8 | **GPU container runs as root** | Container defaults to root for GPU access | Non-root Docker + `--gpus` with user namespace | 3h |
| 9 | **State classifier synthetic-only** | 100% synthetic training → ~60% real accuracy | Active learning loop: annotate real frames → retrain → deploy | 1-2 sessions |
| 10 | **Cross-validation incomplete** | Only 2/5 folds done | Ensure full 5-fold CV runs for publication | ~8h GPU |
| 11 | **No annotation backup/versioning** | Annotations as local `.txt` files | Git-track or sync to cloud storage | 2h |
| 12 | **No experiment tracking** | Best mAP50 tracked manually | MLflow or HuggingFace for training run history | 4h |

### 🟢 Future / Nice-to-Have

| # | Gap | Reasoning |
|---|-----|-----------|
| 13 | **WebSocket for live CV streaming** | Real-time analysis for interactive automation |
| 14 | **DVC/HF Datasets for GT versioning** | Dataset lineage for scientific reproducibility |
| 15 | **Model registry API (MLflow)** | Compare experiment results systematically |
| 16 | **A/B test framework for CV engines** | Side-by-side model comparison in production |
| 17 | **Vault/cloud secrets for deploy** | Replace file-based `/etc/winebot-credentials` |
| 18 | **Prometheus + Grafana dashboards** | Real-time GPU utilization, inference latency, error rates |
| 19 | **Automated real→synthetic retrain loop** | When real annotations reach threshold, auto-retrain YOLO |

---

## Cross-Validation Status (in-progress)

| Fold | Val Scenes | mAP50 | Status |
|------|-----------|-------|--------|
| 0 | save_dialog, settings, error_dialog, notepad | **0.693** | ✅ Complete |
| 1 | control_panel, file_manager, multi_window, browser | **0.711** | ✅ Complete |
| 2 | terminal, context_menu, wizard, find_replace | — | 🔄 Running |
| 3 | print_dialog, about_dialog, file_properties, system_tray | — | ⏳ |
| 4 | form_fill, login, toast, data_table | — | ⏳ |

---

## Key Metrics (Current)

| Metric | Value |
|--------|-------|
| YOLO inference | 40ms (RTX 3090) |
| Pipeline latency | 330ms (324-339 95% CI) |
| Detection F1 (v3) | **0.970** (held-out, 22 classes) |
| OCR char-F1 | 0.41 (PP-OCRv6 tiny) |
| State classifier | 100% synthetic, ~60% real |
| GPU config | 24GB RTX 3090 + 2× A5000 |
| Total model registry | 18 models, 15 active |
| Annotation tool | 15/30 real frames annotated |

---

## References

- `docker/Dockerfile` — Multi-stage build definition
- `compose/docker-compose.yml` — Service orchestration
- `docker/Dockerfile.cv-analyzer-gpu` — GPU sidecar build
- `api/server.py` — FastAPI application entrypoint
- `api/utils/config.py` — Pydantic configuration model
- `scripts/diagnostics/cv-sidecar-server.py` — CV pipeline server
- `scripts/diagnostics/model_registry.py` — Model provenance tracking
- `.github/workflows/` — CI/CD pipeline definitions
