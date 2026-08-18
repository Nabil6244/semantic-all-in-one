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
if [[ ! -x .venv/bin/python ]]; then
  echo "    Creating .venv..."
  python3 -m venv .venv
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
