#!/usr/bin/env python3
"""Web-based bounding box annotation tool for real desktop screenshots.

Loads a directory of images, lets you draw bounding boxes and assign
class labels matching the WineGT 22-class taxonomy, saves in YOLO format.

Usage:
  # Annotate images in a directory
  python3 annotation_server.py --dir /path/to/images --port 8080

  # With auto-detection from the CV sidecar (requires sidecar on port 8001)
  python3 annotation_server.py --dir /path/to/images --sidecar http://localhost:8001

  # Open http://localhost:8080 in a browser

Keyboard shortcuts:
  ← →        Previous/Next image
  0-9         Select class
  d / q       Draw / Select mode
  Delete      Remove selected box
  Ctrl+S      Save annotations
  + / -       Zoom in/out
  Space       Auto-detect (if sidecar configured)
"""
import argparse
import base64
import glob
import logging
import os
import socket
import sys

import cv2
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ── WineGT 22-class taxonomy (must match winebot-gt-generator.py) ────────────

WINE_CLASSES = [
    "title_bar",       # 0
    "title_text",      # 1
    "button",          # 2
    "close_button",    # 3
    "text_field",      # 4
    "dropdown",        # 5
    "checkbox",        # 6
    "radio",           # 7
    "menu_bar",        # 8
    "menu_item",       # 9
    "taskbar",         # 10
    "dialog",          # 11
    "text_area",       # 12
    "scrollbar",       # 13
    "list_item",       # 14
    "tab",             # 15
    "progress_bar",    # 16
    "toolbar",         # 17
    "status_bar",      # 18
    "link",            # 19
    "icon",            # 20
    "spinner_button",  # 21
]

CLASS_COLORS = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
    "#469990", "#dcbeff", "#9a6324", "#fffac8", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#a9a9a9",
    "#e6beff", "#ff6f61",
]


# ── API Models ──────────────────────────────────────────────────────────────


class AnnotationItem(BaseModel):
    class_id: int
    x: int
    y: int
    w: int
    h: int


class SaveAnnotationsRequest(BaseModel):
    filename: str
    annotations: list[AnnotationItem]


# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="WineBot Annotation Tool")

# Runtime config
IMAGE_DIR: str = ""
ALLOW_DELETE: bool = False
SIDECAR_URL: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_image_list() -> list[str]:
    """Get sorted list of image files in IMAGE_DIR."""
    exts = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff")
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(IMAGE_DIR, ext), recursive=False))
    return sorted(files)


def _label_path(img_path: str) -> str:
    """Get corresponding YOLO label path for an image."""
    return os.path.splitext(img_path)[0] + ".txt"


def _load_yolo_labels(label_path: str, img_w: int, img_h: int) -> list[dict]:
    """Load YOLO-format labels. Returns list of {class_id, class_name, x, y, w, h} in pixels."""
    elements = []
    if not os.path.isfile(label_path):
        return elements
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cls_id = int(parts[0])
            cx_norm = float(parts[1])
            cy_norm = float(parts[2])
            w_norm = float(parts[3])
            h_norm = float(parts[4])

            x_px = int((cx_norm - w_norm / 2) * img_w)
            y_px = int((cy_norm - h_norm / 2) * img_h)
            w_px = int(w_norm * img_w)
            h_px = int(h_norm * img_h)

            elements.append({
                "class_id": cls_id,
                "class_name": WINE_CLASSES[cls_id] if cls_id < len(WINE_CLASSES) else f"class_{cls_id}",
                "x": max(0, x_px),
                "y": max(0, y_px),
                "w": min(w_px, img_w - max(0, x_px)),
                "h": min(h_px, img_h - max(0, y_px)),
            })
    return elements


def _save_yolo_labels(label_path: str, elements: list[dict], img_w: int, img_h: int):
    """Save annotations in YOLO format (class_id cx cy w h normalized)."""
    with open(label_path, "w") as f:
        for elem in elements:
            cls_id = elem.get("class_id", 0)
            cx = (elem["x"] + elem["w"] / 2) / img_w
            cy = (elem["y"] + elem["h"] / 2) / img_h
            nw = elem["w"] / img_w
            nh = elem["h"] / img_h
            cx = max(0.0, min(1.0, cx))
            cy = max(0.0, min(1.0, cy))
            nw = max(0.0, min(1.0, nw))
            nh = max(0.0, min(1.0, nh))
            f.write(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")


# ── API Endpoints ────────────────────────────────────────────────────────────


@app.get("/api/classes")
def get_classes():
    """Return the class taxonomy with colors."""
    return JSONResponse({
        "classes": [{"id": i, "name": name, "color": CLASS_COLORS[i]}
                     for i, name in enumerate(WINE_CLASSES)],
    })


@app.get("/api/images")
def list_images():
    """List all images in the annotation directory."""
    images = _get_image_list()
    result = []
    for path in images:
        rel = os.path.relpath(path, IMAGE_DIR)
        lbl_path = _label_path(path)
        lbl_exists = os.path.isfile(lbl_path)
        result.append({
            "filename": os.path.basename(path),
            "path": rel,
            "annotated": lbl_exists,
        })
    return JSONResponse({"images": result, "total": len(result), "dir": IMAGE_DIR})


@app.get("/api/image/{filename:path}")
def get_image(filename: str):
    """Get image data and existing annotations."""
    img_path = os.path.join(IMAGE_DIR, filename)
    if not os.path.isfile(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    img = cv2.imread(img_path)
    if img is None:
        raise HTTPException(status_code=400, detail="Cannot read image")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]

    _, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR),
                          [cv2.IMWRITE_JPEG_QUALITY, 92])
    img_b64 = base64.b64encode(buf).decode("utf-8")

    lbl_path = _label_path(img_path)
    annotations = _load_yolo_labels(lbl_path, w, h)

    return JSONResponse({
        "filename": filename,
        "width": w,
        "height": h,
        "image_data": f"data:image/jpeg;base64,{img_b64}",
        "annotations": annotations,
        "has_labels": os.path.isfile(lbl_path),
    })


@app.post("/api/save")
def save_annotations(req: SaveAnnotationsRequest):
    """Save annotations for an image in YOLO format."""
    img_path = os.path.join(IMAGE_DIR, req.filename)
    if not os.path.isfile(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    img = cv2.imread(img_path)
    if img is None:
        raise HTTPException(status_code=400, detail="Cannot read image")
    h, w = img.shape[:2]

    lbl_path = _label_path(img_path)
    elements = [a.model_dump() for a in req.annotations]
    _save_yolo_labels(lbl_path, elements, w, h)

    return JSONResponse({"status": "saved", "path": lbl_path, "count": len(elements)})


@app.post("/api/delete/{filename:path}")
def delete_image(filename: str):
    """Delete an image and its labels."""
    if not ALLOW_DELETE:
        raise HTTPException(status_code=400,
                            detail="Deletion not enabled (start with --allow-delete)")

    img_path = os.path.join(IMAGE_DIR, filename)
    lbl_path = _label_path(img_path)

    removed = []
    if os.path.isfile(img_path):
        os.remove(img_path)
        removed.append(filename)
    if os.path.isfile(lbl_path):
        os.remove(lbl_path)
        removed.append(os.path.basename(lbl_path))

    return JSONResponse({"status": "deleted", "removed": removed})


@app.get("/api/auto-detect/{filename:path}")
def auto_detect(filename: str):
    """Run the CV sidecar's wine detector on an image and return predictions."""
    if not SIDECAR_URL:
        raise HTTPException(status_code=400,
                            detail="No sidecar configured (start with --sidecar)")

    img_path = os.path.join(IMAGE_DIR, filename)
    if not os.path.isfile(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    # Copy image to a temp path the sidecar can read
    # (sidecar runs in Docker, so we need a path accessible to it)
    tmp_path = "/tmp/annotation-auto-detect.png"
    shutil.copy2(img_path, tmp_path)

    try:
        import requests
        r = requests.post(
            f"{SIDECAR_URL}/analyze",
            json={"image_path": tmp_path, "ui_detector": "wine"},
            timeout=15,
        )
        r.raise_for_status()
        result = r.json()
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"Sidecar error: {e}")

    # Map sidecar element types to wine class IDs
    TYPE_TO_CLASS = {
        "title_bar": 0, "title_text": 1, "button": 2, "close_button": 3,
        "text_field": 4, "dropdown": 5, "checkbox": 6, "radio": 7,
        "menu_bar": 8, "menu_item": 9, "taskbar": 10, "dialog": 11,
        "text_area": 12, "scrollbar": 13, "list_item": 14, "tab": 15,
        "progress_bar": 16, "toolbar": 17, "status_bar": 18, "link": 19,
        "icon": 20, "spinner_button": 21,
    }

    elements = result.get("element_detail", [])
    annotations = []
    for e in elements:
        bbox = e.get("bbox", [0, 0, 0, 0])
        elem_type = e.get("type", "button")
        cls_id = TYPE_TO_CLASS.get(elem_type, 2)  # default to button(2)
        if bbox[2] > 5 and bbox[3] > 5:  # min size filter
            annotations.append({
                "class_id": cls_id,
                "class_name": WINE_CLASSES[cls_id],
                "x": bbox[0],
                "y": bbox[1],
                "w": bbox[2],
                "h": bbox[3],
            })

    return JSONResponse({
        "annotations": annotations,
        "count": len(annotations),
        "detector": result.get("detector", "?"),
        "state": result.get("ui_state", "?"),
    })


@app.get("/api/stats")
def get_stats():
    """Summary statistics across all images."""
    images = _get_image_list()
    total = len(images)
    annotated = 0
    total_boxes = 0
    per_class = {}

    for path in images:
        lbl_path = _label_path(path)
        if os.path.isfile(lbl_path):
            annotated += 1
            # Read image to get dimensions
            img = cv2.imread(path)
            if img is not None:
                h, w = img.shape[:2]
                labels = _load_yolo_labels(lbl_path, w, h)
                total_boxes += len(labels)
                for lbl in labels:
                    cls_name = lbl["class_name"]
                    per_class[cls_name] = per_class.get(cls_name, 0) + 1

    return JSONResponse({
        "total_images": total,
        "annotated_images": annotated,
        "total_annotations": total_boxes,
        "per_class": dict(sorted(per_class.items())),
        "unannotated": total - annotated,
    })


# ── HTML Frontend ────────────────────────────────────────────────────────────


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WineBot Annotation Tool</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #1a1a2e; color: #e0e0e0; height: 100vh; overflow: hidden; }
.container { display: flex; flex-direction: column; height: 100vh; }

/* Top toolbar */
.toolbar { display: flex; align-items: center; gap: 8px; padding: 6px 14px;
           background: #16213e; border-bottom: 1px solid #0f3460; flex-shrink: 0; flex-wrap: wrap; }
.toolbar button { background: #0f3460; color: #e0e0e0; border: 1px solid #1a5276;
                  padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;
                  white-space: nowrap; }
.toolbar button:hover { background: #1a5276; }
.toolbar button:disabled { opacity: 0.35; cursor: default; }
.toolbar select { background: #0f3460; color: #e0e0e0; border: 1px solid #1a5276;
                  padding: 5px 8px; border-radius: 4px; font-size: 12px; }
.toolbar .nav-info { color: #a0a0b0; font-size: 12px; margin: 0 4px; white-space: nowrap; }
.toolbar .spacer { flex: 1; min-width: 8px; }

/* Main area */
.main-area { display: flex; flex: 1; overflow: hidden; }

/* Canvas wrapper */
.canvas-wrapper { flex: 1; display: flex; align-items: center; justify-content: center;
                  background: #0d0d1a; overflow: hidden; position: relative; }
.canvas-wrapper canvas { max-width: 100%; max-height: 100%; }
#annotation-canvas { cursor: crosshair; }

.side-panel { width: 260px; background: #16213e; border-left: 1px solid #0f3460;
              display: flex; flex-direction: column; flex-shrink: 0; overflow-y: auto; }
.panel-section { padding: 10px; border-bottom: 1px solid #0f3460; }
.panel-section h3 { font-size: 11px; text-transform: uppercase; color: #a0a0b0;
                    margin-bottom: 6px; letter-spacing: 0.5px; }

.class-list { display: flex; flex-direction: column; gap: 1px; max-height: 320px; overflow-y: auto; }
.class-item { display: flex; align-items: center; gap: 5px; padding: 2px 5px;
              border-radius: 3px; cursor: pointer; font-size: 11px;
              transition: background 0.1s; }
.class-item:hover { background: #1a2744; }
.class-item.active { background: #1a5276; outline: 1px solid #2a7ab0; }
.class-item .swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
.class-item .cid { color: #666; font-size: 9px; width: 16px; text-align: right; }
.class-item .cname { flex: 1; }
.class-item .shortcut { color: #444; font-size: 9px; width: 14px; text-align: center; }

.annotation-list { display: flex; flex-direction: column; gap: 3px; max-height: 200px; overflow-y: auto; }
.annotation-entry { display: flex; align-items: center; gap: 5px; padding: 3px 5px;
                    border-radius: 3px; font-size: 11px; cursor: pointer;
                    border: 1px solid transparent; }
.annotation-entry:hover { background: #1a2744; }
.annotation-entry.selected { border-color: #e94560; background: #1a2744; }
.annotation-entry .dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.annotation-entry .aname { font-weight: 600; min-width: 65px; font-size: 10px; }
.annotation-entry .asize { color: #888; font-size: 9px; }
.annotation-entry .adel { margin-left: auto; cursor: pointer; color: #e94560;
                           font-size: 13px; padding: 0 3px; cursor: pointer; }

.empty-msg { color: #555; font-size: 11px; font-style: italic; padding: 6px; }

/* Stats bar */
.stats-bar { display: flex; align-items: center; gap: 14px; padding: 4px 14px;
             background: #16213e; border-top: 1px solid #0f3460; font-size: 11px;
             color: #a0a0b0; flex-shrink: 0; }
.stats-bar .stat { display: flex; align-items: center; gap: 3px; }
.stats-bar .sv { color: #e0e0e0; font-weight: 600; }
.stats-bar .fname { flex: 1; text-align: right; color: #666; font-size: 10px; }

.unsaved-badge { background: #e94560; color: #fff; padding: 1px 7px; border-radius: 4px;
                 font-size: 10px; font-weight: bold; display: none; }

/* Image gallery */
.image-gallery { display: none; }
.image-gallery.open { display: block; }
.gallery-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; padding: 6px; }
.thumb { aspect-ratio: 16/10; background: #0d0d1a; border-radius: 3px; cursor: pointer;
         border: 2px solid transparent; overflow: hidden; position: relative; font-size: 0; }
.thumb:hover { border-color: #1a5276; }
.thumb.active { border-color: #e94560; }
.thumb .tlabel { position: absolute; bottom: 0; left: 0; right: 0;
                 background: rgba(0,0,0,0.75); padding: 1px 4px; font-size: 8px;
                 white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #ccc; }
.thumb .tbadge { position: absolute; top: 2px; right: 2px; width: 7px; height: 7px;
                 border-radius: 50%; background: #e94560; }
.thumb .tbadge.done { background: #4caf50; }

::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #0d0d1a; }
::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }

/* Toast notification */
.toast { position: fixed; bottom: 50px; left: 50%; transform: translateX(-50%);
         background: #333; color: #e0e0e0; padding: 8px 20px; border-radius: 6px;
         font-size: 13px; z-index: 999; opacity: 0; transition: opacity 0.3s;
         pointer-events: none; }
.toast.show { opacity: 1; }
</style>
</head>
<body>
<div class="container">
  <div class="toolbar">
    <button onclick="toggleGallery()">☰ Gallery</button>
    <span class="nav-info">
      <button id="btn-prev" onclick="nav(-1)" disabled>◀</button>
      <span id="nav-pos">- / -</span>
      <button id="btn-next" onclick="nav(1)" disabled>▶</button>
    </span>
    <select id="mode-sel" onchange="setMode(this.value)" title="Mode">
      <option value="draw">✏️ Draw</option>
      <option value="select">↖️ Select</option>
    </select>
    <select id="class-sel" onchange="pickClass(parseInt(this.value))" title="Current class"></select>
    <div class="spacer"></div>
    <span class="unsaved-badge" id="unsaved">UNSAVED</span>
    <button id="btn-save" onclick="saveAnn()">💾 Save</button>
    <button id="btn-auto" onclick="autoDetect()">🤖 Auto</button>
    <button onclick="clearAll()">🗑️ Clear</button>
  </div>

  <div class="main-area">
    <div class="canvas-wrapper" id="cw">
      <canvas id="ac"></canvas>
    </div>
    <div class="side-panel">
      <div class="panel-section">
        <h3>Classes <span style="color:#888;font-weight:normal;font-size:10px">(key 0-9)</span></h3>
        <div class="class-list" id="clist"></div>
      </div>
      <div class="panel-section">
        <h3>Boxes <span id="box-count" style="color:#888;font-weight:normal"></span></h3>
        <div class="annotation-list" id="alist"></div>
      </div>
      <div class="panel-section image-gallery" id="gallery">
        <h3>Gallery</h3>
        <div class="gallery-grid" id="ggrid"></div>
      </div>
    </div>
  </div>

  <div class="stats-bar">
    <div class="stat">📷 <span class="sv" id="s-total">0</span></div>
    <div class="stat">🏷️ <span class="sv" id="s-ann">0</span></div>
    <div class="stat">📦 <span class="sv" id="s-box">0</span></div>
    <div class="fname" id="s-fname"></div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
// ── State ─────────────────────────────────────────────────────────────────
const S = {
  images: [], idx: 0, data: null, anns: [], sel: -1,
  drawing: false, dStart: null, mode: 'draw', cls: 0,
  loaded: false, dirty: false, imgObj: null,
  naturalW: 0, naturalH: 0,
};

const $ = id => document.getElementById(id);
const canvas = $('ac');
const ctx = canvas.getContext('2d');

let CLASSES = [];

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  const cd = await (await fetch('/api/classes')).json();
  CLASSES = cd.classes;
  renderClassList();
  const id = await (await fetch('/api/images')).json();
  S.images = id.images;
  $('s-total').textContent = id.total;
  const ann = id.images.filter(i => i.annotated).length;
  $('s-ann').textContent = ann;
  renderGallery();
  if (id.total > 0) await loadImg(0);
}

// ── Classes ────────────────────────────────────────────────────────────────

function renderClassList() {
  const sel = $('class-sel');
  const list = $('clist');
  sel.innerHTML = '';
  list.innerHTML = '';
  CLASSES.forEach((c, i) => {
    sel.innerHTML += `<option value="${i}">${i}. ${c.name}</option>`;
    const d = document.createElement('div');
    d.className = 'class-item';
    d.dataset.idx = i;
    d.innerHTML = `<span class="swatch" style="background:${c.color}"></span>
                   <span class="cid">${i}</span>
                   <span class="cname">${c.name}</span>
                   <span class="shortcut">${i<10?i:''}</span>`;
    d.onclick = () => pickClass(i);
    list.appendChild(d);
  });
  pickClass(0);
}

function pickClass(idx) {
  S.cls = idx;
  document.querySelectorAll('.class-item').forEach(el => el.classList.remove('active'));
  const el = document.querySelector(`.class-item[data-idx="${idx}"]`);
  if (el) el.classList.add('active');
  $('class-sel').value = idx;
}

// ── Image loading ──────────────────────────────────────────────────────────

async function loadImg(idx) {
  if (idx < 0 || idx >= S.images.length) return;
  S.idx = idx;
  S.dirty = false;
  $('unsaved').style.display = 'none';
  S.sel = -1;

  const info = S.images[idx];
  const d = await (await fetch(`/api/image/${encodeURIComponent(info.path)}`)).json();
  S.data = d;
  S.anns = (d.annotations || []).map((a, i) => ({...a, _uid: i}));

  S.imgObj = new Image();
  S.imgObj.onload = () => {
    S.naturalW = S.imgObj.naturalWidth;
    S.naturalH = S.imgObj.naturalHeight;
    fitCanvas();
    render();
  };
  S.imgObj.src = d.image_data;

  $('s-fname').textContent = info.filename;
  $('s-box').textContent = S.anns.length;
  $('nav-pos').textContent = `${idx+1} / ${S.images.length}`;
  $('btn-prev').disabled = idx === 0;
  $('btn-next').disabled = idx >= S.images.length - 1;
  updateAnnList();
  renderGallery();
}

function fitCanvas() {
  const wrap = $('cw');
  const mw = wrap.clientWidth - 4;
  const mh = wrap.clientHeight - 4;
  const sc = Math.min(mw / S.naturalW, mh / S.naturalH, 1);
  canvas.width = S.naturalW * sc;
  canvas.height = S.naturalH * sc;
  canvas._scale = sc;
}

// ── Navigation ─────────────────────────────────────────────────────────────

function nav(d) {
  const i = S.idx + d;
  if (i >= 0 && i < S.images.length) {
    if (S.dirty) saveAnn().then(() => loadImg(i));
    else loadImg(i);
  }
}

// ── Mode ───────────────────────────────────────────────────────────────────

function setMode(m) {
  S.mode = m;
  $('mode-sel').value = m;
  canvas.style.cursor = m === 'draw' ? 'crosshair' : 'pointer';
}

// ── Render ─────────────────────────────────────────────────────────────────

function render() {
  if (!S.data || !S.imgObj) return;
  const sc = canvas._scale || 1;
  const w = canvas.width, h = canvas.height;

  ctx.clearRect(0, 0, w, h);
  ctx.drawImage(S.imgObj, 0, 0, w, h);

  S.anns.forEach((a, i) => {
    const cl = CLASSES[a.class_id] || CLASSES[0];
    const sx = a.x * sc, sy = a.y * sc, sw = a.w * sc, sh = a.h * sc;
    ctx.strokeStyle = i === S.sel ? '#fff' : cl.color;
    ctx.lineWidth = i === S.sel ? 3 : 2;
    ctx.strokeRect(sx, sy, sw, sh);
    if (i === S.sel) { ctx.fillStyle = 'rgba(255,255,255,0.08)'; ctx.fillRect(sx, sy, sw, sh); }
    ctx.fillStyle = cl.color;
    ctx.font = 'bold 10px sans-serif';
    const lbl = a.class_name || cl.name;
    const tw = ctx.measureText(lbl).width;
    ctx.fillRect(sx, sy - 13, tw + 5, 13);
    ctx.fillStyle = '#fff';
    ctx.fillText(lbl, sx + 3, sy - 3);
  });
}

// ── Mouse ──────────────────────────────────────────────────────────────────

canvas.addEventListener('mousedown', e => {
  const r = canvas.getBoundingClientRect();
  const mx = (e.clientX - r.left) / canvas._scale;
  const my = (e.clientY - r.top) / canvas._scale;

  if (S.mode === 'draw') {
    S.drawing = true;
    S.dStart = {x: e.clientX - r.left, y: e.clientY - r.top};
  } else {
    let hit = -1;
    for (let i = S.anns.length - 1; i >= 0; i--) {
      const a = S.anns[i];
      if (mx >= a.x && mx <= a.x + a.w && my >= a.y && my <= a.y + a.h) { hit = i; break; }
    }
    S.sel = hit;
    updateAnnList();
    render();
  }
});

canvas.addEventListener('mousemove', e => {
  if (S.drawing && S.dStart) {
    const r = canvas.getBoundingClientRect();
    const cx = e.clientX - r.left, cy = e.clientY - r.top;
    render();
    ctx.strokeStyle = CLASSES[S.cls].color;
    ctx.lineWidth = 2;
    ctx.setLineDash([5,3]);
    ctx.strokeRect(S.dStart.x, S.dStart.y, cx - S.dStart.x, cy - S.dStart.y);
    ctx.setLineDash([]);
  }
});

canvas.addEventListener('mouseup', e => {
  if (S.drawing && S.dStart) {
    const r = canvas.getBoundingClientRect();
    const ex = (e.clientX - r.left) / canvas._scale;
    const ey = (e.clientY - r.top) / canvas._scale;
    const x1 = Math.min(S.dStart.x / canvas._scale, ex);
    const y1 = Math.min(S.dStart.y / canvas._scale, ey);
    const bw = Math.abs(ex - S.dStart.x / canvas._scale);
    const bh = Math.abs(ey - S.dStart.y / canvas._scale);

    if (bw > 5 && bh > 5) {
      S.anns.push({class_id: S.cls, class_name: CLASSES[S.cls].name,
                    x: Math.round(x1), y: Math.round(y1), w: Math.round(bw), h: Math.round(bh),
                    _uid: Date.now()});
      S.dirty = true;
      $('unsaved').style.display = 'inline';
      $('s-box').textContent = S.anns.length;
      updateAnnList();
    }
    S.drawing = false; S.dStart = null;
    render();
  }
});

// ── Keyboard ───────────────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  switch (e.key) {
    case 'ArrowLeft': nav(-1); e.preventDefault(); break;
    case 'ArrowRight': nav(1); e.preventDefault(); break;
    case 's': if (e.ctrlKey) { saveAnn(); e.preventDefault(); } break;
    case 'Delete': case 'Backspace': delSel(); e.preventDefault(); break;
    case 'Escape': S.sel = -1; updateAnnList(); render(); break;
    case 'd': setMode('draw'); e.preventDefault(); break;
    case 'q': setMode('select'); e.preventDefault(); break;
    case '+': case '=': zoom(1.3); e.preventDefault(); break;
    case '-': zoom(0.7); e.preventDefault(); break;
    case ' ': autoDetect(); e.preventDefault(); break;
    default: if (e.key >= '0' && e.key <= '9') { const i=parseInt(e.key); if(i<CLASSES.length) pickClass(i); }
  }
});

function zoom(f) {
  canvas._scale = Math.max(0.1, Math.min(5, (canvas._scale||1) * f));
  canvas.width = S.naturalW * canvas._scale;
  canvas.height = S.naturalH * canvas._scale;
  render();
}

// ── Annotations ────────────────────────────────────────────────────────────

function updateAnnList() {
  const al = $('alist');
  $('box-count').textContent = `(${S.anns.length})`;
  if (!S.anns.length) { al.innerHTML = '<div class="empty-msg">Draw boxes on the image</div>'; return; }
  al.innerHTML = '';
  S.anns.forEach((a, i) => {
    const cl = CLASSES[a.class_id] || CLASSES[0];
    const d = document.createElement('div');
    d.className = 'annotation-entry' + (i===S.sel?' selected':'');
    d.innerHTML = `<span class="dot" style="background:${cl.color}"></span>
                   <span class="aname">${a.class_name||cl.name}</span>
                   <span class="asize">${a.w}×${a.h}</span>
                   <span class="adel" data-idx="${i}">×</span>`;
    d.querySelector('.adel').onclick = e => { e.stopPropagation(); rmAnn(i); };
    d.onclick = () => { S.sel = i; updateAnnList(); render(); };
    al.appendChild(d);
  });
}

function rmAnn(i) {
  S.anns.splice(i, 1);
  S.sel = -1; S.dirty = true;
  $('unsaved').style.display = 'inline';
  $('s-box').textContent = S.anns.length;
  updateAnnList(); render();
}

function delSel() { if (S.sel >= 0) rmAnn(S.sel); }

function clearAll() {
  if (S.anns.length && !confirm('Remove all annotations for this image?')) return;
  S.anns = []; S.sel = -1; S.dirty = true;
  $('unsaved').style.display = 'inline';
  $('s-box').textContent = '0';
  updateAnnList(); render();
}

// ── Save ───────────────────────────────────────────────────────────────────

async function saveAnn() {
  const info = S.images[S.idx];
  if (!info) return;
  await fetch('/api/save', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({filename: info.path,
      annotations: S.anns.map(a => ({class_id:a.class_id, x:Math.round(a.x), y:Math.round(a.y), w:Math.round(a.w), h:Math.round(a.h)}))
    })});
  S.dirty = false;
  $('unsaved').style.display = 'none';
  S.images[S.idx].annotated = true;
  $('s-ann').textContent = S.images.filter(i=>i.annotated).length;
  toast('Saved ✓');
  renderGallery();
}

// ── Auto detect ────────────────────────────────────────────────────────────

async function autoDetect() {
  const info = S.images[S.idx];
  if (!info) return;
  $('btn-auto').textContent = '⏳';
  $('btn-auto').disabled = true;
  try {
    const r = await fetch(`/api/auto-detect/${encodeURIComponent(info.path)}`);
    if (!r.ok) { const e=await r.json(); throw new Error(e.detail); }
    const d = await r.json();
    S.anns = d.annotations.map((a,i) => ({...a, _uid: Date.now()+i}));
    S.dirty = true;
    $('unsaved').style.display = 'inline';
    $('s-box').textContent = S.anns.length;
    toast(`Auto: ${d.count} boxes (${d.state})`);
    updateAnnList(); render();
  } catch(e) {
    toast('Auto failed: ' + e.message);
  }
  $('btn-auto').textContent = '🤖';
  $('btn-auto').disabled = false;
}

// ── Gallery ────────────────────────────────────────────────────────────────

function toggleGallery() { $('gallery').classList.toggle('open'); renderGallery(); }

function renderGallery() {
  const g = $('ggrid');
  if (!S.images.length) { g.innerHTML='<div class="empty-msg">No images</div>'; return; }
  g.innerHTML = '';
  S.images.forEach((img, i) => {
    const t = document.createElement('div');
    t.className = 'thumb' + (i===S.idx?' active':'');
    t.innerHTML = `<div class="tlabel">${img.filename}</div>
                   ${img.annotated ? '<div class="tbadge done"></div>' : '<div class="tbadge"></div>'}`;
    t.onclick = () => { if(S.dirty) saveAnn().then(()=>loadImg(i)); else loadImg(i); };
    g.appendChild(t);
  });
}

// ── Toast ──────────────────────────────────────────────────────────────────

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

init();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(HTML_PAGE)


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    global IMAGE_DIR, ALLOW_DELETE, SIDECAR_URL

    parser = argparse.ArgumentParser(description="WineBot Annotation Tool")
    parser.add_argument("--dir", "-d", default=".",
                        help="Directory containing images to annotate")
    parser.add_argument("--port", "-p", type=int, default=8080,
                        help="Port to serve on (tries next port if busy)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Host to bind to")
    parser.add_argument("--allow-delete", action="store_true",
                        help="Enable image deletion via UI (dangerous)")
    parser.add_argument("--sidecar", default=None,
                        help="CV sidecar URL for auto-detection (e.g. http://localhost:8001)")
    parser.add_argument("--log-file", default=None,
                        help="Path to log file (default: stderr)")
    args = parser.parse_args()

    IMAGE_DIR = os.path.abspath(args.dir)
    ALLOW_DELETE = args.allow_delete
    SIDECAR_URL = args.sidecar

    # ── Logging setup ───────────────────────────────────────────────────────────
    log_handler = logging.FileHandler(args.log_file) if args.log_file else logging.StreamHandler()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[log_handler],
    )
    log = logging.getLogger("annotation")

    if not os.path.isdir(IMAGE_DIR):
        log.error("Directory not found: %s", IMAGE_DIR)
        sys.exit(1)

    images = _get_image_list()
    log.info("Starting WineBot Annotation Tool")
    log.info("Image directory: %s (%d images)", IMAGE_DIR, len(images))
    log.info("Classes: %d (%s..%s)", len(WINE_CLASSES), WINE_CLASSES[0], WINE_CLASSES[-1])
    log.info("Sidecar: %s", SIDECAR_URL or "not configured")

    # ── Port discovery with conflict fallback ───────────────────────────────────
    port = args.port
    max_attempts = 10
    for _attempt in range(max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((args.host, port))
            sock.close()
            if result == 0:
                log.warning("Port %d is in use, trying %d", port, port + 1)
                port += 1
            else:
                break
        except OSError:
            port += 1
    else:
        log.error("Could not find free port after %d attempts (tried %d..%d)",
                   max_attempts, args.port, port)
        sys.exit(1)

    log.info("Binding to %s:%d", args.host, port)

    # ── Print banner to stdout (for interactive sessions) ────────────────────────
    banner = (
        f"\n{'='*60}\n"
        f"  WineBot Annotation Tool\n"
        f"{'='*60}\n"
        f"  Image directory: {IMAGE_DIR}\n"
        f"  Images found:    {len(images)}\n"
        f"  Classes:         {len(WINE_CLASSES)} (0-{len(WINE_CLASSES)-1})\n"
        f"  Sidecar:         {SIDECAR_URL or 'not configured'}\n"
        f"  Delete enabled:  {ALLOW_DELETE}\n"
        f"  Server:          http://{args.host}:{port}\n"
        f"{'='*60}\n"
        f"\n  Keyboard shortcuts:\n"
        f"    {'Space':13s} Auto-detect with sidecar\n" if SIDECAR_URL else ""
        f"    {'← →':13s} Previous/Next image\n"
        f"    {'0-9':13s} Select class\n"
        f"    d / q       Draw / Select mode\n"
        f"    Delete       Remove selected box\n"
        f"    Ctrl+S       Save annotations\n"
        f"    + / -         Zoom in/out\n"
        f"\n  Open http://localhost:{port} in your browser.\n"
    )
    print(banner)
    log.info("Serving on %s:%d", args.host, port)

    uvicorn.run(app, host=args.host, port=port, log_level="info",
                access_log=False)


if __name__ == "__main__":
    import shutil  # noqa: F401 — used in auto_detect endpoint
    main()
