"""Placeholder grey-board clip for the feasibility spike. NOT the board system: just enough to test that a clip made outside Hybrid can sit
in a Hybrid footage beat, and to measure what the pipeline does to it.

Every frame carries a 16-bit frame number as black/white cells in the top-left corner (read back from the render), a red border at the exact
frame edges (shows any crop or scale), a typed label, two icon circles that pop in, a placeholder narrator figure and the clip time.

usage: python3 -B -I make_board_clip.py <out.mp4> <seconds> [fps] [width] [height]
Reads one bundled font (assets/fonts/Inter-Bold.ttf); writes only the output file."""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

out = Path(sys.argv[1])
seconds = float(sys.argv[2])
fps = int(sys.argv[3]) if len(sys.argv) > 3 else 30
W = int(sys.argv[4]) if len(sys.argv) > 4 else 1920
H = int(sys.argv[5]) if len(sys.argv) > 5 else 1080
root = Path(__file__).resolve().parents[2]
FONT = str(root / "assets" / "fonts" / "Inter-Bold.ttf")
BOARD = (192, 192, 192)          # about the measured reference board grey (#C0C0C0)
CELL = 20                        # frame-number cell size in pixels at 1920 wide
n_frames = int(round(seconds * fps))


def font(px):
    return ImageFont.truetype(FONT, px)


def pop(t, t0, dur=0.25):
    """0 before t0, overshoot scale-in over dur, then 1."""
    if t < t0:
        return 0.0
    k = min(1.0, (t - t0) / dur)
    s = 1.5
    return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2


def frame(i):
    t = i / fps
    im = Image.new("RGB", (W, H), BOARD)
    d = ImageDraw.Draw(im)
    # placeholder narrator (left): hat, head, body, arm, spear
    d.line([(300, 330), (300, 860)], fill=(60, 40, 30), width=8)
    d.polygon([(240, 380), (360, 380), (300, 300)], fill=(210, 170, 90), outline=(60, 40, 30))
    d.ellipse([255, 380, 345, 470], fill=(245, 215, 190), outline=(40, 40, 40), width=4)
    d.line([(300, 470), (300, 700)], fill=(40, 40, 40), width=6)
    d.line([(300, 520), (430, 560)], fill=(40, 40, 40), width=6)
    d.line([(300, 700), (270, 830)], fill=(40, 40, 40), width=6)
    d.line([(300, 700), (330, 830)], fill=(40, 40, 40), width=6)
    # typed label
    text = "SPIKE BOARD: one idea per board"
    n = max(0, min(len(text), int((t - 0.3) * 30)))
    d.text((700, 200), text[:n], font=font(64), fill=(40, 40, 40))
    # two icon circles pop in (blue ring, green ring)
    for k, (cx, colr, t0) in enumerate(((900, (40, 80, 170), 1.5), (1400, (30, 130, 70), 2.0))):
        s = pop(t, t0)
        if s > 0:
            r = int(90 * s)
            d.ellipse([cx - r, 520 - r, cx + r, 520 + r], fill=(250, 250, 250), outline=colr, width=10)
            if s > 0.9:
                d.text((cx - 60, 650), "= test", font=font(48), fill=colr)
    # clip time and frame number
    d.text((700, 900), f"clip t={t:6.3f}s  frame {i}", font=font(44), fill=(40, 40, 40))
    # 16-bit frame number, MSB first, black = 0 / white = 1
    for b in range(16):
        bit = (i >> (15 - b)) & 1
        x0 = b * CELL
        d.rectangle([x0, 0, x0 + CELL - 1, CELL - 1], fill=(255, 255, 255) if bit else (0, 0, 0))
    # red border at the exact frame edges (below the code row)
    d.rectangle([0, CELL, W - 1, H - 1], outline=(220, 0, 0), width=6)
    return im


cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
       "-an", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", "-preset", "medium", "-movflags", "+faststart", str(out)]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
for i in range(n_frames):
    p.stdin.write(frame(i).tobytes())
p.stdin.close()
rc = p.wait()
print(f"board clip: {n_frames} frames, {seconds}s, {W}x{H}@{fps}, rc={rc}, {out}")
sys.exit(rc)
