#!/usr/bin/env bash
# ── Start Annotation Server ────────────────────────────────────────────────
# Usage:
#   scripts/start-annotation.sh                          # inside container
#   MSYS_NO_PATHCONV=1 bash scripts/start-annotation.sh   # from Windows host
#
# When run from the host (Git Bash), MSYS_NO_PATHCONV=1 is required to
# prevent Git Bash from translating container paths like /scripts to
# Windows paths like C:/Program Files/Git/scripts.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source structured logging
source "$SCRIPT_DIR/logging_utils.sh" 2>/dev/null || true

# ── Config ─────────────────────────────────────────────────────────────────
CONTAINER="${WB_CONTAINER:-winebot-cv}"
ANNOTATION_DIR="${ANNOTATION_DIR:-/artifacts/annotations/images}"
SERVER_PORT="${ANNOTATION_PORT:-8080}"
SIDECAR_URL="${CV_SIDECAR_URL:-http://localhost:8001}"
LOG_FILE="/tmp/annotation-server.log"

log_start "Starting annotation server"

# ── Check if running inside container ──────────────────────────────────────
if [ -f /.dockerenv ] || [ -f /run/.containerenv ]; then
    INSIDE_CONTAINER=1
else
    INSIDE_CONTAINER=0
fi

# ── Find annotation server script ──────────────────────────────────────────
if [ "$INSIDE_CONTAINER" = "1" ]; then
    SERVER_SCRIPT="/scripts/annotation_server.py"
elif MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" test -f /scripts/annotation_server.py 2>/dev/null; then
    # Running from host — server lives inside container
    :
else
    log_error "setup" "annotation_server.py not found in container $CONTAINER"
    log_step "fix" "docker cp scripts/annotation_server.py $CONTAINER:/scripts/annotation_server.py"
    exit 1
fi

# ── Ensure annotation directory exists with images ─────────────────────────
if [ "$INSIDE_CONTAINER" = "1" ]; then
    mkdir -p "$ANNOTATION_DIR"
else
    MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" mkdir -p "$ANNOTATION_DIR" 2>/dev/null || true
fi

# ── Kill any previous annotation server ────────────────────────────────────
log_step "cleanup" "Stopping any previous annotation server..."
if [ "$INSIDE_CONTAINER" = "1" ]; then
    pkill -f "annotation_server.py" 2>/dev/null || true
    sleep 1
else
    MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
        "pkill -f annotation_server.py 2>/dev/null; sleep 1" 2>/dev/null || true
fi

# ── Start annotation server ────────────────────────────────────────────────
# NOTE: On Windows (Git Bash), MSYS_NO_PATHCONV=1 is REQUIRED for all
# docker commands that include Unix-style paths. Without it, Git Bash
# translates /scripts → C:/Program Files/Git/scripts, causing "file not found".
# See docs/debugging.md#git-bash-path-translation for details.
log_step "start" "Starting annotation server on port $SERVER_PORT..."
log_step "config" "Images: $ANNOTATION_DIR | Sidecar: $SIDECAR_URL | Log: $LOG_FILE"

if [ "$INSIDE_CONTAINER" = "1" ]; then
    # Direct launch inside container
    nohup python3 /scripts/annotation_server.py \
        --dir "$ANNOTATION_DIR" \
        --port "$SERVER_PORT" \
        --sidecar "$SIDECAR_URL" \
        --log-file "$LOG_FILE" \
        > /dev/null 2>&1 &
    PID=$!
else
    # Remote launch via docker exec (note MSYS_NO_PATHCONV to prevent path mangling)
    MSYS_NO_PATHCONV=1 docker exec -d "$CONTAINER" python3 /scripts/annotation_server.py \
        --dir "$ANNOTATION_DIR" \
        --port "$SERVER_PORT" \
        --sidecar "$SIDECAR_URL" \
        --log-file "$LOG_FILE"
    PID="container-process"
fi

# ── Wait for server to respond ────────────────────────────────────────────
sleep 2
for i in $(seq 1 15); do
    if [ "$INSIDE_CONTAINER" = "1" ]; then
        if curl -sf "http://127.0.0.1:$SERVER_PORT/api/images" > /dev/null 2>&1; then
            log_complete "Annotation server ready on http://127.0.0.1:$SERVER_PORT"
            echo ""
            echo "  Open http://localhost:$SERVER_PORT in your browser."
            echo "  Logs: $LOG_FILE"
            exit 0
        fi
    else
        CONTAINER_IP=$(docker inspect "$CONTAINER" --format '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
        if curl -sf "http://$CONTAINER_IP:$SERVER_PORT/api/images" > /dev/null 2>&1; then
            log_complete "Annotation server ready on http://localhost:$SERVER_PORT"
            echo ""
            echo "  Open http://localhost:$SERVER_PORT in your browser."
            echo "  Logs (in container): $LOG_FILE"
            exit 0
        fi
    fi
    sleep 1
done

log_error "startup" "Annotation server did not become ready within 15s"
log_step "diagnose" "docker exec $CONTAINER cat $LOG_FILE"
exit 1
