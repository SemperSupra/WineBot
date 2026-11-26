#!/usr/bin/env bash
# Layered runtime version floor; not an artifact signature or compatibility proof.
set -euo pipefail
export LC_ALL=C
fail() {
    printf 'WINEBOT_RUNTIME_ADMISSION stage=%s\n' "$1" >&2
    exit 2
}
version="$(timeout --kill-after=1s 5s wine --version 2>/dev/null)" ||
    fail version_unavailable
# Only a stable numeric Wine version is admitted. Distribution annotations
# are optional; prerelease and malformed versions require explicit qualification.
pattern='^wine-([1-9][0-9]{0,2})\.[0-9]{1,5}(\.[0-9]{1,5})?( \([^[:cntrl:]]{1,64}\))?$'
[[ "$version" =~ $pattern ]] || fail invalid_version
(( BASH_REMATCH[1] >= 11 )) || fail below_minimum
printf 'WINEBOT_RUNTIME_ADMISSION stage=version_floor_pass\n'
