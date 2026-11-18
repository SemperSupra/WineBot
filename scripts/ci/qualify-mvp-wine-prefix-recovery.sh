#!/usr/bin/env bash
# REAL Wine-generated synthetic prefix, archive, tamper rejection and replay.
# Public runner only. This is distro Wine infrastructure proof, not yet
# full state-volume / pinned layered Wine11 recovery acceptance.
set -euo pipefail
fail() { printf 'MVP_PREFIX_RECOVERY stage=%s\n' "$1" >&2; exit 1; }
[ "${GITHUB_ACTIONS:-}" = true ] &&
  [ "${GITHUB_EVENT_NAME:-}" = pull_request ] || fail unqualified_venue
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]] ||
  fail invalid_runner_id
command -v wineboot >/dev/null 2>&1 || fail wine_unavailable
command -v xvfb-run >/dev/null 2>&1 || fail xvfb_unavailable
umask 077
work="$(mktemp -d "${RUNNER_TEMP:-/tmp}/mvp-wineprefix.XXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT
export WINEPREFIX="$work/live"
export WINEARCH=win64
export WINEDEBUG=-all
export WINEDLLOVERRIDES=mscoree,mshtml=
mkdir -p "$WINEPREFIX"
# Invented user profile and registry, never existing user state.
if ! xvfb-run -a /bin/bash -euo pipefail -c '
  timeout 180 wineboot -u >/dev/null 2>&1
  wine reg add "HKCU\\Software\\WineBotMVPIC1" /v State \
    /t REG_SZ /d SyntheticReady /f >/dev/null 2>&1
  wine reg query "HKCU\\Software\\WineBotMVPIC1" /v State \
    >/dev/null 2>&1
  wineserver -k >/dev/null 2>&1 || true
' >"$work/wine-first.log" 2>&1; then
  fail initial_wine_prefix_failed
fi
test -s "$WINEPREFIX/user.reg" || fail source_registry_missing
mkdir -p "$WINEPREFIX/drive_c/ic1-docs"
printf 'IC1_WINE_CREATED_PREFIX_PROOF\n' \
  >"$WINEPREFIX/drive_c/ic1-docs/verified.txt"
file_sha="$(sha256sum "$WINEPREFIX/drive_c/ic1-docs/verified.txt" | cut -d' ' -f1)"
[[ "$file_sha" =~ ^[0-9a-f]{64}$ ]] || fail file_hash_failed
tar -C "$WINEPREFIX" -cf "$work/prefix.tar" . \
  >"$work/tar-first.log" 2>&1 || fail archive_failed
archive_sha="$(sha256sum "$work/prefix.tar" | cut -d' ' -f1)"
[[ "$archive_sha" =~ ^[0-9a-f]{64}$ ]] || fail archive_hash_failed
echo 'MVP_PREFIX_RECOVERY stage=real_wine_prefix_archived'

# Tampered archive must be rejected before extraction.
cp "$work/prefix.tar" "$work/tampered.tar"
printf tamper >>"$work/tampered.tar"
if printf '%s  %s\n' "$archive_sha" "$work/tampered.tar" |
    sha256sum -c --status - >/dev/null 2>&1; then
  fail corruption_accepted
fi
rm -f -- "$work/tampered.tar"
printf '%s  %s\n' "$archive_sha" "$work/prefix.tar" |
  sha256sum -c --status - >/dev/null 2>&1 ||
  fail archive_integrity
echo 'MVP_PREFIX_RECOVERY stage=tamper_negative_pass'

# A different empty directory simulates loss/replacement of the user volume.
# Extraction is always unprivileged and refuses to overlay previous state.
mkdir -p "$work/restored"
[ -z "$(find "$work/restored" -mindepth 1 -print -quit)" ] ||
  fail restore_target_not_empty
tar --no-same-owner --no-same-permissions -C "$work/restored" \
  -xf "$work/prefix.tar" >"$work/tar-restore.log" 2>&1 ||
  fail restore_failed
restored_sha="$(sha256sum "$work/restored/drive_c/ic1-docs/verified.txt" |
  cut -d' ' -f1)"
[ "$restored_sha" = "$file_sha" ] || fail file_postcondition_mismatch
test -s "$work/restored/user.reg" || fail restored_registry_missing
export WINEPREFIX="$work/restored"
if ! xvfb-run -a /bin/bash -euo pipefail -c '
  timeout 120 wine reg query "HKCU\\Software\\WineBotMVPIC1" /v State \
    >"$WINEPREFIX/ic1-query-local.log" 2>&1
  grep -q SyntheticReady "$WINEPREFIX/ic1-query-local.log"
  rm -f -- "$WINEPREFIX/ic1-query-local.log"
  wineserver -k >/dev/null 2>&1 || true
' >"$work/wine-restore.log" 2>&1; then
  fail restored_wine_registry_unreadable
fi
echo 'MVP_PREFIX_RECOVERY stage=real_wine_prefix_restored_and_queried'
echo 'MVP_PREFIX_RECOVERY stage=bounded_infrastructure_pass'
