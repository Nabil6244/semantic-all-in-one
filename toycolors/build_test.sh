#!/bin/bash
# 30 s paint-board test: song + Blender frames + mux. Usage: toycolors/build_test.sh [--fast]
set -e
cd "$(dirname "$0")/.."
OUT=toycolors/out
python3 -m toycolors.song $OUT/audio
rm -rf $OUT/frames
/Applications/Blender.app/Contents/MacOS/Blender -b -P toycolors/scene_paint.py -- $OUT/frames "$@" > $OUT/blender.log 2>&1
ffmpeg -loglevel error -y -framerate 24 -i $OUT/frames/f_%04d.png -i $OUT/audio/mix.wav \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
  -c:a aac -b:a 192k -shortest -movflags +faststart $OUT/paint_board_test.mp4
echo "$OUT/paint_board_test.mp4"
