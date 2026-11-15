"""Thumbnails from real frames: a frame of the episode + one big rainbow word, 1280x720 JPEG (YouTube's size).

python3 cartoon2d/thumbnail.py <story_render.json> "COLORS!" t1 [t2 ...]     -> <build>/thumb_<n>.jpg
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402

story, word, *times = sys.argv[1:]
render.load(story)
build = render.ROOT / render.G["story"]["build"]
font = ImageFont.truetype(render.FONT, 190)
cols = [(255, 70, 70), (255, 160, 30), (250, 205, 20), (60, 180, 90), (50, 140, 240), (160, 90, 230)]
for n, t in enumerate(times, 1):
    fr = render.graded(render.episode_frame(float(t))).convert("RGBA")       # episode time, same colours as the video
    d = ImageDraw.Draw(fr)
    x, y = 70, 150
    for i, ch in enumerate(word):                       # big rainbow letters with a thick white edge and a soft shadow
        d.text((x + 8, y + 10), ch, font=font, fill=(0, 0, 0, 90), anchor="lm")
        d.text((x, y), ch, font=font, fill=cols[i % len(cols)] + (255,), anchor="lm", stroke_width=14, stroke_fill=(255, 255, 255, 255))
        x += font.getlength(ch) + 4
    out = build / f"thumb_{n}.jpg"
    fr.convert("RGB").resize((1280, 720), Image.LANCZOS).save(out, quality=92)
    print("THUMB", out)
