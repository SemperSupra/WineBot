#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 - "$work/good.zip" <<'PY'
import sys
import zipfile
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("sample.txt", "synthetic fixture\n")
PY
good="$(sha256sum "$work/good.zip" | cut -d' ' -f1)"
bash "$root/windows-tools/download_tool.sh" Synthetic "file://$work/good.zip" "$good" "$work/valid" >/dev/null
test "$(cat "$work/valid/sample.txt")" = "synthetic fixture"
echo 'PASS: verified_original_zip'
set +e
missing="$(bash "$root/windows-tools/download_tool.sh" Missing "file://$work/absent.zip" "$good" "$work/no-dest" 2>&1)"
missing_status=$?
set -e
test "$missing_status" -ne 0
echo "$missing" | grep -Fq 'ERROR: download failed for Missing'
if echo "$missing" | grep -Fq 'Checksum mismatch'; then exit 1; fi
test ! -e "$work/no-dest"
echo 'PASS: nonexistent_asset_is_transport_error'
set +e
wrong="$(bash "$root/windows-tools/download_tool.sh" Wrong "file://$work/good.zip" "$(printf '%064d' 0)" "$work/no-dest-2" 2>&1)"
wrong_status=$?
set -e
test "$wrong_status" -ne 0
echo "$wrong" | grep -Fq 'ERROR: Checksum mismatch for Wrong'
test ! -e "$work/no-dest-2"
echo 'PASS: mismatching_sha_denied'
set +e
bash "$root/windows-tools/download_tool.sh" Invalid "file://$work/good.zip" invalid "$work/no-dest-3" >/dev/null 2>&1
invalid_status=$?
set -e
test "$invalid_status" -ne 0
test ! -e "$work/no-dest-3"
echo 'PASS: invalid_sha_rejected'
