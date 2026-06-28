#!/bin/bash
# Cross-validation — data gen + training in isolated phases.
set -e

FOLDS=5
IMAGES_PER_SCENE=200
EPOCHS=30
OUTPUT="/models/cross-validation"

SCENES=("save_dialog" "settings" "error_dialog" "notepad" "control_panel"
        "file_manager" "multi_window" "browser" "terminal" "context_menu"
        "wizard" "find_replace" "print_dialog" "about_dialog" "file_properties"
        "system_tray" "form_fill" "login" "toast" "data_table" "drag_drop"
        "loading")

echo "============================================================"
echo "  K-FOLD CROSS-VALIDATION"
echo "  Folds: $FOLDS   Scenes: ${#SCENES[@]}"
echo "  Images/scene: $IMAGES_PER_SCENE   Epochs: $EPOCHS"
echo "============================================================"

mkdir -p "$OUTPUT"
N_VAL=$(( ${#SCENES[@]} / FOLDS ))

# ── Phase 1: Generate data for all folds ──────────────────────────
echo ""
echo "━━━ Phase 1: Generating data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for fold in $(seq 0 $((FOLDS - 1))); do
    VAL_START=$(( fold * N_VAL ))
    VAL_END=$(( VAL_START + N_VAL - 1 ))
    VAL_SCENES=()
    TRAIN_SCENES=()
    for i in $(seq 0 $((${#SCENES[@]} - 1))); do
        if [ "$i" -ge "$VAL_START" ] && [ "$i" -le "$VAL_END" ]; then
            VAL_SCENES+=("${SCENES[$i]}")
        else
            TRAIN_SCENES+=("${SCENES[$i]}")
        fi
    done

    FOLD_DIR="$OUTPUT/fold-$fold"
    mkdir -p "$FOLD_DIR/train/images" "$FOLD_DIR/train/labels"
    mkdir -p "$FOLD_DIR/val/images" "$FOLD_DIR/val/labels"

    echo "  Fold $((fold + 1)): train=${#TRAIN_SCENES[@]} val=${#VAL_SCENES[@]} (${VAL_SCENES[*]})"

    # Write data.yaml
    cat > "$FOLD_DIR/data.yaml" << YAMLEOF
path: $FOLD_DIR
train: train/images
val: val/images
nc: 22
names:
  0: title_bar
  1: title_text
  2: button
  3: close_button
  4: text_field
  5: dropdown
  6: checkbox
  7: radio
  8: menu_bar
  9: menu_item
  10: taskbar
  11: dialog
  12: text_area
  13: scrollbar
  14: list_item
  15: tab
  16: progress_bar
  17: toolbar
  18: status_bar
  19: link
  20: icon
  21: spinner_button
YAMLEOF

    # Generate data — subprocess with importlib, no PyTorch
    python3 /tmp/gen_fold.py "$fold" "$FOLD_DIR" "$IMAGES_PER_SCENE" \
        "${#TRAIN_SCENES[@]}" "${TRAIN_SCENES[@]}" "${VAL_SCENES[@]}" \
        2>&1 | sed 's/^/    /'

    echo "  Fold $((fold + 1)) data done"
done

# ── Phase 2: Train each fold ──────────────────────────────────────
echo ""
echo "━━━ Phase 2: Training ─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for fold in $(seq 0 $((FOLDS - 1))); do
    FOLD_DIR="$OUTPUT/fold-$fold"
    echo "  Fold $((fold + 1)): training $EPOCHS epochs..."
    T0=$(date +%s)

    # Training in a subprocess — only imports YOLO, clean from generator.
    python3 /tmp/train_fold.py "$FOLD_DIR" "$EPOCHS" 2>&1 | sed 's/^/    /'

    TRAIN_TIME=$(( $(date +%s) - T0 ))
    R=$(cat "$FOLD_DIR/result.json" 2>/dev/null || echo '{"best_mAP50":0}')
    MAP50=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('best_mAP50', 0))")
    echo "  Fold $((fold + 1)): mAP50=$MAP50 (${TRAIN_TIME}s)"
done

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  CROSS-VALIDATION RESULTS"
echo "============================================================"
python3 << SUMMARYEOF
import json, os
import numpy as np

results = []
for fold in range($FOLDS):
    rpath = f"$OUTPUT/fold-{fold}/result.json"
    if os.path.isfile(rpath):
        with open(rpath) as f:
            r = json.load(f)
            r["fold"] = fold
            results.append(r)

if results:
    map50s = [r["best_mAP50"] for r in results]
    print(f"  Mean mAP50: {np.mean(map50s):.4f} +/- {np.std(map50s):.4f}")
    for r in results:
        print(f"    Fold {r['fold']}: mAP50={r['best_mAP50']:.4f}")
    with open(f"$OUTPUT/results.json", "w") as f:
        json.dump({"n_folds": $FOLDS, "mean_mAP50": round(float(np.mean(map50s)),4),
                   "std_mAP50": round(float(np.std(map50s)),4), "per_fold": results}, f, indent=2)
    print(f"\n  Saved: $OUTPUT/results.json")
else:
    print("  No results found")
SUMMARYEOF
