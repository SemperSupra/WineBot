#!/usr/bin/env bash
# Shared WineBot runtime profile catalog (use-case + performance).

wb_profile_alias_target() {
  case "${1:-}" in
    human-desktop) echo "human-interactive" ;;
    assisted-desktop) echo "supervised-agent" ;;
    unattended-runner) echo "agent-batch" ;;
    ci-oneshot) echo "ci-gate" ;;
    support-session) echo "incident-supervision" ;;
    *) echo "${1:-}" ;;
  esac
}

wb_profile_use_case_names() {
  cat <<'EOF'
human-interactive
human-exploratory
human-debug-input
agent-batch
agent-timing-critical
agent-forensic
supervised-agent
incident-supervision
demo-training
ci-gate
EOF
}

wb_profile_legacy_aliases() {
  cat <<'EOF'
human-desktop -> human-interactive
assisted-desktop -> supervised-agent
unattended-runner -> agent-batch
ci-oneshot -> ci-gate
support-session -> incident-supervision
EOF
}

wb_profile_performance_names() {
  cat <<'EOF'
low-latency
balanced
max-quality
diagnostic
EOF
}

wb_profile_use_case_default_performance() {
  case "$(wb_profile_alias_target "${1:-}")" in
    human-interactive) echo "low-latency" ;;
    human-exploratory) echo "balanced" ;;
    human-debug-input) echo "diagnostic" ;;
    agent-batch) echo "balanced" ;;
    agent-timing-critical) echo "low-latency" ;;
    agent-forensic) echo "diagnostic" ;;
    supervised-agent) echo "balanced" ;;
    incident-supervision) echo "diagnostic" ;;
    demo-training) echo "max-quality" ;;
    ci-gate) echo "balanced" ;;
    *) return 1 ;;
  esac
}

wb_profile_use_case_allowed_performance() {
  case "$(wb_profile_alias_target "${1:-}")" in
    human-interactive) echo "low-latency balanced max-quality diagnostic" ;;
    human-exploratory) echo "balanced low-latency max-quality diagnostic" ;;
    human-debug-input) echo "diagnostic balanced" ;;
    agent-batch) echo "balanced low-latency diagnostic" ;;
    agent-timing-critical) echo "low-latency balanced" ;;
    agent-forensic) echo "diagnostic balanced" ;;
    supervised-agent) echo "balanced low-latency diagnostic max-quality" ;;
    incident-supervision) echo "diagnostic balanced" ;;
    demo-training) echo "max-quality balanced" ;;
    ci-gate) echo "balanced" ;;
    *) return 1 ;;
  esac
}

wb_profile_use_case_values() {
  local use_case
  use_case="$(wb_profile_alias_target "${1:-}")"
  case "$use_case" in
    human-interactive|human-exploratory|human-debug-input)
      cat <<EOF
MODE=interactive
WINEBOT_INSTANCE_MODE=persistent
WINEBOT_SESSION_MODE=persistent
WINEBOT_INSTANCE_CONTROL_MODE=human-only
WINEBOT_SESSION_CONTROL_MODE=human-only
WINEBOT_USE_CASE_PROFILE=$use_case
EOF
      ;;
    agent-batch|agent-timing-critical|agent-forensic)
      cat <<EOF
MODE=headless
WINEBOT_INSTANCE_MODE=persistent
WINEBOT_SESSION_MODE=persistent
WINEBOT_INSTANCE_CONTROL_MODE=agent-only
WINEBOT_SESSION_CONTROL_MODE=agent-only
WINEBOT_USE_CASE_PROFILE=$use_case
EOF
      ;;
    supervised-agent|incident-supervision|demo-training)
      cat <<EOF
MODE=interactive
WINEBOT_INSTANCE_MODE=persistent
WINEBOT_SESSION_MODE=persistent
WINEBOT_INSTANCE_CONTROL_MODE=hybrid
WINEBOT_SESSION_CONTROL_MODE=hybrid
WINEBOT_USE_CASE_PROFILE=$use_case
EOF
      ;;
    ci-gate)
      cat <<EOF
MODE=headless
WINEBOT_INSTANCE_MODE=oneshot
WINEBOT_SESSION_MODE=oneshot
WINEBOT_INSTANCE_CONTROL_MODE=agent-only
WINEBOT_SESSION_CONTROL_MODE=agent-only
APP_EXE=cmd.exe
APP_ARGS=/c exit /b 0
WINEBOT_USE_CASE_PROFILE=$use_case
EOF
      ;;
    *)
      return 1
      ;;
  esac
}

wb_profile_performance_values() {
  local perf="${1:-}"
  case "$perf" in
    low-latency)
      cat <<'EOF'
WINEBOT_RECORD=0
WINEBOT_INPUT_TRACE=0
WINEBOT_INPUT_TRACE_WINDOWS=0
WINEBOT_INPUT_TRACE_NETWORK=0
WINEBOT_INPUT_TRACE_NETWORK_SAMPLE_MS=100
ENABLE_WINEDBG=0
WINEBOT_SUPPORT_MODE=0
WINEBOT_PERFORMANCE_PROFILE=low-latency
EOF
      ;;
    balanced)
      cat <<'EOF'
WINEBOT_RECORD=0
WINEBOT_INPUT_TRACE=1
WINEBOT_INPUT_TRACE_WINDOWS=1
WINEBOT_INPUT_TRACE_NETWORK=0
WINEBOT_INPUT_TRACE_NETWORK_SAMPLE_MS=20
ENABLE_WINEDBG=0
WINEBOT_SUPPORT_MODE=0
WINEBOT_PERFORMANCE_PROFILE=balanced
EOF
      ;;
    max-quality)
      cat <<'EOF'
WINEBOT_RECORD=1
WINEBOT_INPUT_TRACE=1
WINEBOT_INPUT_TRACE_WINDOWS=1
WINEBOT_INPUT_TRACE_NETWORK=1
WINEBOT_INPUT_TRACE_NETWORK_SAMPLE_MS=10
ENABLE_WINEDBG=0
WINEBOT_SUPPORT_MODE=0
WINEBOT_PERFORMANCE_PROFILE=max-quality
EOF
      ;;
    diagnostic)
      cat <<'EOF'
WINEBOT_RECORD=1
WINEBOT_INPUT_TRACE=1
WINEBOT_INPUT_TRACE_WINDOWS=1
WINEBOT_INPUT_TRACE_NETWORK=1
WINEBOT_INPUT_TRACE_NETWORK_SAMPLE_MS=5
ENABLE_WINEDBG=1
WINEBOT_SUPPORT_MODE=1
WINEBOT_SUPPORT_MODE_MINUTES=120
WINEBOT_PERFORMANCE_PROFILE=diagnostic
EOF
      ;;
    *)
      return 1
      ;;
  esac
}

wb_profile_validate_combo() {
  local use_case perf allowed p
  use_case="$(wb_profile_alias_target "${1:-}")"
  perf="${2:-}"
  [ -n "$use_case" ] || return 1
  [ -n "$perf" ] || return 1

  allowed="$(wb_profile_use_case_allowed_performance "$use_case")" || return 1
  for p in $allowed; do
    if [ "$p" = "$perf" ]; then
      return 0
    fi
  done
  return 1
}

wb_profile_render_values() {
  local use_case perf
  use_case="$(wb_profile_alias_target "${1:-}")"
  perf="${2:-}"
  [ -n "$use_case" ] || return 1

  if [ -z "$perf" ]; then
    perf="$(wb_profile_use_case_default_performance "$use_case")" || return 1
  fi

  wb_profile_use_case_values "$use_case" >/dev/null || return 1
  wb_profile_performance_values "$perf" >/dev/null || return 1
  wb_profile_validate_combo "$use_case" "$perf" || return 1

  wb_profile_use_case_values "$use_case"
  wb_profile_performance_values "$perf"
}
