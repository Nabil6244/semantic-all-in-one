#!/usr/bin/env bash
# Setup (skip if already present) then run default video generation.
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Checking ffmpeg..."
if command -v ffmpeg >/dev/null 2>&1; then
  echo "    ffmpeg already installed: $(ffmpeg -version 2>&1 | head -1)"
else
  echo "    ffmpeg not found — installing via Homebrew..."
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew is required to install ffmpeg on Mac."
    echo "Install it from https://brew.sh then re-run this script."
    exit 1
  fi
  brew install ffmpeg
fi

echo "==> Checking Python deps..."
# The code needs Python 3.10+ (macOS's /usr/bin/python3 is 3.9). An old .venv
# is set aside (renamed, not deleted) and rebuilt with a new enough Python.
py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
if [[ -x .venv/bin/python ]] && ! py_ok .venv/bin/python; then
  OLD=".venv-py-old-$(date +%Y%m%d%H%M%S)"
  echo "    .venv uses Python < 3.10; moving it to $OLD"
  mv .venv "$OLD"
fi
if [[ ! -x .venv/bin/python ]]; then
  BASE=""
  for cand in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1 && py_ok "$(command -v "$cand")"; then BASE="$(command -v "$cand")"; break; fi
  done
  if [[ -z "$BASE" ]]; then
    echo "ERROR: Python 3.10 or newer is required (found none on PATH)."
    exit 1
  fi
  echo "    Creating .venv with $BASE..."
  "$BASE" -m venv .venv
fi
PYTHON=".venv/bin/python"

# Skip pip install if faster-whisper is already importable
if "$PYTHON" -c "import faster_whisper" >/dev/null 2>&1; then
  echo "    requirements already satisfied (faster-whisper found)"
else
  echo "    Installing from requirements.txt..."
  "$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$PYTHON" -m pip install -r requirements.txt
fi

# Default inputs for this project
CSV="script.csv"
AUDIO="voiceover.mp3"
IMAGES="Images"
OUTPUT="final.mp4"

for f in "$CSV" "$AUDIO"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing required file: $f"
    exit 1
  fi
done
if [[ ! -d "$IMAGES" ]]; then
  echo "ERROR: missing images folder: $IMAGES"
  exit 1
fi

echo "==> Starting video generation (default: Ken Burns zoom)..."
CMD=(
  "$PYTHON" video_generator.py
  --csv "$CSV"
  --audio "$AUDIO"
  --images-dir "$IMAGES"
  --output "$OUTPUT"
)

# Optional: drop a file at assets/bg_audio.mp3 to mix under the voiceover
if [[ -f assets/bg_audio.mp3 ]]; then
  CMD+=(--bg-audio assets/bg_audio.mp3 --bg-volume 0.15)
  echo "    background audio: assets/bg_audio.mp3"
fi

echo "    command: ${CMD[*]}"
"${CMD[@]}"

echo "==> Done. Output: $OUTPUT"
