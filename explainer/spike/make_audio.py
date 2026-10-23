"""Synthetic narration for the spike: a steady 330 Hz tone with a 2 kHz click on every whole second, so that dropouts, shifts and re-timing are
measurable. 48 kHz mono 16-bit WAV. Also writes a small placeholder PNG used as the beat-3 supporting photo card (local media only).

usage: python3 -B -I make_audio.py <out.wav> <seconds> <card.png>"""
import math
import struct
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw

out, seconds, card = Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3])
SR = 48000
n = int(SR * seconds)
frames = bytearray()
for i in range(n):
    t = i / SR
    v = 0.25 * math.sin(2 * math.pi * 330 * t)
    frac = t - math.floor(t)
    if frac < 0.04:                                   # 40 ms click at every whole second
        env = 0.5 * (1 - math.cos(2 * math.pi * frac / 0.04))
        v += 0.7 * env * math.sin(2 * math.pi * 2000 * t)
    frames += struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32000))
with wave.open(str(out), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(frames))

im = Image.new("RGB", (800, 500), (230, 225, 210))
d = ImageDraw.Draw(im)
d.rectangle([0, 0, 799, 499], outline=(60, 60, 60), width=8)
d.text((60, 220), "LOCAL PLACEHOLDER CARD", fill=(40, 40, 40))
im.save(card)
print(f"audio {seconds}s -> {out}; card -> {card}")
