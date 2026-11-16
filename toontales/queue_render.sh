#!/bin/zsh
# Toon Tales batch: wait until the kids-video renders (cartoon2d / cartoon3d, other sessions) have been idle for IDLE_MIN
# minutes, then render each story in turn and copy the finished Shorts into DEST with a titles list.
# Usage: toontales/queue_render.sh story_id [story_id ...]
cd "${0:A:h}/.." || exit 1
DEST="$HOME/Downloads/Toon Tales Shorts"
IDLE_MIN=${IDLE_MIN:-15}
mkdir -p "$DEST"
busy() { pgrep -f "cartoon2d/(render|voice|mix|hook)\.py|cartoon3d-engine|lesson\.mjs" >/dev/null; }
idle=0; waited=0
while (( idle < IDLE_MIN && waited < 360 )); do
  if busy; then idle=0; else idle=$((idle + 1)); fi
  sleep 60; waited=$((waited + 1))
done
echo "START $(date '+%H:%M') (waited ${waited} min)"
n=$(ls "$DEST"/*.mp4 2>/dev/null | wc -l | tr -d ' ')
for s in "$@"; do
  plan="toontales/stories/$s/plan.json"
  title=$(python3 -c "import json;print(json.load(open('$plan'))['title'])")
  if python3 -m toontales.shots.build_story "$plan" > "toontales/build/queue_$s.log" 2>&1 \
     && python3 -m toontales.edit.edit "$plan" >> "toontales/build/queue_$s.log" 2>&1; then
    n=$((n + 1))
    name=$(printf "%02d - %s.mp4" $n "${title//[\/:?\"]/}")
    cp "out/toontales_$s.mp4" "$DEST/$name"
    echo "$name" >> "$DEST/titles.txt"
    echo "DONE $s -> $name $(date '+%H:%M')"
  else
    echo "FAILED $s (see toontales/build/queue_$s.log)"
  fi
done
echo "ALL DONE $(date '+%H:%M')"
