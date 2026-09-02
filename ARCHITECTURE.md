# WineBot Ecosystem Architecture

> **Last updated:** 2026-09-02  
> **Audit reference:** REC-GH-009 (docs/audits/GITHUB_AUDIT.md)

## Overview

The WineBot ecosystem spans repositories across the SemperSupra and mark-e-deyoung GitHub organizations.
It provides a containerized harness for running Windows GUI applications under Wine with headless/interactive modes,
automation tooling, native-Windows counterparts, and computer vision capabilities.

WineBotAppBuilder (WBAB) is **retiring and feature-frozen**. It remains part of the historical architecture record but is not a recommended dependency for new work. Native product builds should remain in the product repository; reusable Windows release/trust/distribution mechanics belong in Windows Package Foundry; native Windows interactive automation belongs in WinBot; Wine runtime/compatibility validation belongs in WineBot.

## Repository Map

```
SemperSupra/WineBot ────────── Core harness (Python/Docker/Wine)
    │
    ├── Personal Fork
    │   └── mark-e-deyoung/WineBot-1 ── Development fork for personal experiments
    │
    ├── Windows Counterpart
    │   └── mark-e-deyoung/WinBot ── Windows-native automation (PowerShell/Hyper-V)
    │
    ├── API Contracts
    │   └── mark-e-deyoung/winebot-contracts ── Shared API spec between WinBot and WineBot
    │
    ├── Windows Build / Release
    │   ├── product-local GitHub Actions ── native product build/test/package
    │   ├── SemperSupra/windows-package-foundry ── reusable release/trust/distribution infrastructure
    │   └── SemperSupra/WineBotAppBuilder ── RETIRING historical cross-build toolchain; no new adoption
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

## Build, Qualification, and Distribution Ownership

| Concern | Preferred owner |
|---|---|
| Product-specific Windows build/test/package | Product-local GitHub Actions on native Windows runners |
| Reusable Windows release/trust/distribution | `SemperSupra/windows-package-foundry` |
| Native Windows interactive/GUI automation | `mark-e-deyoung/WinBot` |
| Wine runtime/compatibility qualification | `SemperSupra/WineBot` |
| Shared WineBot/WinBot API conformance | `mark-e-deyoung/winebot-contracts` |
| Historical Linux-hosted MinGW/NSIS cross-build orchestration | `SemperSupra/WineBotAppBuilder` — retiring/reference only |

## Deployment

- WineBot runs as a Docker container on Linux hosts (VPS or local).
- WinBot runs natively on Windows and provides the portfolio path for native Windows interactive automation.
- CV model servers (kv-ground-server, ui-captioning) run as sidecar containers or on GPU hosts.
- Windows applications should normally build/package in their own native Windows GitHub Actions workflows.
- Windows Package Foundry wraps completed product builds with reusable release/trust/distribution machinery where appropriate.
- WBAB historically supplied Linux-hosted CMake/MinGW/NSIS cross-build orchestration; it is being retired and should not be introduced into new workflows.

## Key Technologies

| Technology | Used In |
|------------|---------|
| Docker | WineBot; historical WBAB implementation |
| Wine | WineBot, WinInspect |
| Python | WineBot, CV pipeline, contracts |
| C++ | WinInspect |
| PowerShell | WinBot, deployment scripts |
| TLA+ | Historical WBAB formal models |
| Florence-2 | ui-captioning |
| KV-Ground-8B | kv-ground-server |
| CMake/NSIS | Product-native Windows build/package paths; historical WBAB toolchain |

## Related Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines
- [GOVERNANCE.md](GOVERNANCE.md) — Project governance model
- [AGENTS.md](AGENTS.md) — AI agent collaboration patterns
- [WBAB retirement tracker](https://github.com/SemperSupra/WineBotAppBuilder/issues/61) — authoritative retirement decision and migration status
