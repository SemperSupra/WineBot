#!/bin/bash
# Shared smart-trim helper for all demo scripts.
# Finds the first chapter marker in the recording and trims the blank
# container-boot intro before it.
#
# Usage:  source _trim.sh; smart_trim "$SESSDIR"

[ -z "${_TRIM_LOADED:-}" ] || return 0
_TRIM_LOADED=1

smart_trim() {
  local sessdir="${1:-}"
  if [ -z "$sessdir" ]; then
    echo "WARNING: smart_trim called with empty sessdir" >&2
    return
  fi
  local container="${WB_CONTAINER:-compose-winebot-interactive-1}"

  # Find the LATEST video segment (not always video_001 — recording stop/start
  # within a persistent session creates video_002, video_003, etc.)
  local video
  video=$(MSYS_NO_PATHCONV=1 docker exec "$container" sh -c \
    "ls -t '${sessdir}/video_'*.mkv 2>/dev/null | grep -v part | head -1" 2>/dev/null)
  video="${video:-${sessdir}/video_001.mkv}"
  echo "  Smart trim: using $video"

  # Read first chapter time
  local first
  first=$(MSYS_NO_PATHCONV=1 docker exec "$container" sh -c \
    "ffprobe -v quiet -show_chapters -print_format flat '$video' 2>/dev/null | grep 'chapter.1.start_time' | sed 's/.*=\"\([0-9.]*\)\"/\1/' | head -1" 2>/dev/null)
  first="${first:-0}"

  # Trim to 2 seconds before first content (minimum 0)
  local trim_start=0
  trim_start=$(python3 -c "print(max(0, int(float(${first})) - 2))" 2>/dev/null || echo "0")
  echo "  Smart trim: first content at ${first}s → trimming ${trim_start}s from start"

  MSYS_NO_PATHCONV=1 docker exec "$container" sh -c "
    rm -f /tmp/trimmed.mkv /tmp/trimmed.gif
    ffmpeg -y -ss ${trim_start} -i '$video' -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null && \
    ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null && \
    echo \"  Trimmed: \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') GIF: \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')\"
  "
}
