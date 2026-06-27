# Real Desktop Validation Plan

## Problem

All pipeline metrics are measured on synthetic data. We don't know real-world performance.

**Previous attempt:** MKV extraction from demo recordings produced near-black frames (mean pixel=3).
**Root cause:** The demo recordings use Wine's virtual desktop which doesn't render correctly when extracted via ffmpeg without the running container.

## Approach: Live Capture from WineBot Container

The only reliable way to get real desktop frames is to capture them from a **running WineBot container** with real applications.

### Step 1: Start WineBot with Recording

```bash
# Start WineBot with recording enabled
docker compose -f compose/docker-compose.yml --profile headless up -d
WINEBOT_RECORD=1 ./scripts/run-app.sh notepad.exe

# While running, capture screenshots via the API
./scripts/winebotctl screenshot --output /tmp/real_frames/
```

This produces real rendered frames with actual font rendering, window decorations, and compositing effects.

### Step 2: Collect Diverse Scenes

Run multiple applications and capture their dialogs:

| App | Scenes Expected |
|:---|:---|
| Notepad | Notepad window, save dialog, find/replace, about dialog |
| 7-Zip | File manager, context menu, properties, extraction wizard |
| VLC | Browser-like open dialog, settings, about |
| Wine control panel | Settings, control panel, system tray |

Target: **200-500 real desktop screenshots** across 10-15 scene types.

### Step 3: Manual Labeling

Each screenshot needs manual labeling for evaluation. Two approaches:

**Option A: Quick qualitative (1 session)**
- Capture 50 screenshots
- Run pipeline on each
- Manually inspect: "are detected elements correct?"
- Report: precision@human (what fraction of detections look right?)

**Option B: Full quantitative (2-3 sessions)**
- Capture 200 screenshots
- Manual bounding box labels for 22 classes
- Run pipeline_evaluator.py on labeled set
- Report: full metrics with synthetic→real performance gap

### Step 4: Measure the Gap

| Metric | Synthetic | Real | Gap |
|:---|---:|---:|---:|
| Per-frame F1 | 0.91 | ? | +? |
| State accuracy | 100% | ? | +? |
| Mean latency | 330ms | ? | +? |

### Success Criteria

- Real per-frame F1 > 0.70 (acceptable transfer)
- Real per-frame F1 > 0.80 (good transfer)
- State accuracy > 80% on real screenshots

### Prerequisites

1. Running WineBot container (Docker not crashed)
2. Wine apps installed (notepad, 7-Zip, VLC)
3. Human evaluator (you) for labeling
