# WineBot Ecosystem Architecture

> **Last updated:** 2026-07-08  
> **Audit reference:** REC-GH-009 (docs/audits/GITHUB_AUDIT.md)

## Overview

The WineBot ecosystem spans **10 repositories across 2 GitHub organizations** (SemperSupra and mark-e-deyoung).
It provides a containerized harness for running Windows GUI applications under Wine with headless/interactive modes,
automation tooling, and computer vision capabilities.

## Repository Map

```
SemperSupra/WineBot ────────── Core harness (Python/Docker/Wine)
    │
    ├── Personal Fork
    │   └── mark-e-deyoung/WineBot-1 ── Development fork for personal experiments
    │
    ├── Windows Counterpart
    │   └── mark-e-deyoung/WinBot ── Windows-native automation (PowerShell)
    │
    ├── API Contracts
    │   └── mark-e-deyoung/winebot-contracts ── Shared API spec between WinBot and WineBot
    │
    ├── Build Toolchain
    │   └── SemperSupra/WineBotAppBuilder ── CI/CD pipeline (9 workflows, CMake/NSIS)
    │
    ├── Core Dependency
    │   └── SemperSupra/WinInspect ── Window inspector (C++, UIAutomation/Wine support)
    │
    ├── Computer Vision Pipeline
    │   ├── SemperSupra/desktop-ui-cv ── UI element detection, OCR, state classification
    │   ├── SemperSupra/ui-captioning ── Florence-2 model for natural language UI descriptions
    │   └── SemperSupra/kv-ground-server ── KV-Ground-8B VLM for GUI element grounding
    │
    └── Research
        └── mark-e-deyoung/winebot-research ── Publication strategy and competitive analysis
```

## Data Flow

```
User Input / Script
    │
    ▼
WineBot (harness) ───► WinInspect (window queries)
    │                       │
    │                       ▼
    │               desktop-ui-cv (element detection)
    │                       │
    │               ┌───────┴───────┐
    │               ▼               ▼
    │         ui-captioning    kv-ground-server
    │         (Florence-2)     (KV-Ground-8B)
    │               │               │
    │               └───────┬───────┘
    │                       ▼
    │               Structured output
    │              (elements + captions + locations)
    │
    ▼
WinBot (Windows) ◄─── winebot-contracts (API spec) ───► WineBot (Wine/Linux)
```

## CI/CD Pipeline

| Repo | Workflows | Status |
|------|-----------|--------|
| WineBotAppBuilder | 9 | Full CI/CD pipeline (lint, build, test, package, release) |
| WineBot | 8 | Core harness CI (Docker build, integration tests, security scan) |
| WinInspect | 6 | Multi-platform build (Windows/Linux/Wine), static analysis |
| desktop-ui-cv | 1 | Basic CI |
| ui-captioning | 1 | Basic CI |
| kv-ground-server | 1 | Basic CI |
| winebot-contracts | 3 | Conformance tests |
| WinBot | 1 | Basic CI |

## Deployment

- WineBot runs as a Docker container on Linux hosts (VPS or local)
- WinBot runs natively on Windows
- CV model servers (kv-ground-server, ui-captioning) run as sidecar containers or on GPU hosts
- WineBotAppBuilder produces Windows installers via CMake/NSIS cross-compilation

## Key Technologies

| Technology | Used In |
|------------|---------|
| Docker | WineBot, WineBotAppBuilder |
| Wine | WineBot, WinInspect |
| Python | WineBot, CV pipeline, contracts |
| C++ | WinInspect |
| PowerShell | WinBot, deployment scripts |
| TLA+ | WineBotAppBuilder (formal models) |
| Florence-2 | ui-captioning |
| KV-Ground-8B | kv-ground-server |
| CMake/NSIS | WineBotAppBuilder (build toolchain) |

## Related Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines
- [GOVERNANCE.md](GOVERNANCE.md) — Project governance model
- [AGENTS.md](AGENTS.md) — AI agent collaboration patterns
