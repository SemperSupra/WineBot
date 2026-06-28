#!/usr/bin/env bash
# ── Shared logging utilities for WineBot shell scripts ──────────────────────
# Source this file:  source "$(dirname "$0")/logging_utils.sh"
#
# Usage:
#   log_start "Processing widgets"
#   log_step "load" "Loading data..."
#   log_complete "Processed ${n} widgets"
#   log_error "Failed" "Something went wrong"

SCRIPT_NAME="$(basename "${BASH_SOURCE[1]:-$0}")"
SCRIPT_START_TIME=""

log_start() {
  SCRIPT_START_TIME=$(date +%s)
  local msg="${1:-Started}"
  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"level\":\"info\",\"logger\":\"${SCRIPT_NAME}\",\"message\":\"${msg}\"}" >&2
}

log_step() {
  local step="$1"
  local msg="${2:-}"
  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"level\":\"info\",\"logger\":\"${SCRIPT_NAME}\",\"message\":\"[${step}] ${msg}\"}" >&2
}

log_complete() {
  local msg="${1:-Completed}"
  local elapsed=""
  if [ -n "$SCRIPT_START_TIME" ]; then
    local now
    now=$(date +%s)
    elapsed=$((now - SCRIPT_START_TIME))
  fi
  if [ -n "$elapsed" ]; then
    echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"level\":\"info\",\"logger\":\"${SCRIPT_NAME}\",\"message\":\"${msg}\",\"elapsed_s\":${elapsed}}" >&2
  else
    echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"level\":\"info\",\"logger\":\"${SCRIPT_NAME}\",\"message\":\"${msg}\"}" >&2
  fi
}

log_error() {
  local context="${1:-}"
  local msg="${2:-Error}"
  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"level\":\"error\",\"logger\":\"${SCRIPT_NAME}\",\"message\":\"${msg}\",\"context\":\"${context}\"}" >&2
}

log_warn() {
  local msg="${1:-Warning}"
  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"level\":\"warn\",\"logger\":\"${SCRIPT_NAME}\",\"message\":\"${msg}\"}" >&2
}
