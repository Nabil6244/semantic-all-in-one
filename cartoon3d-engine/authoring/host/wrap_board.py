"""python3 host/wrap_board.py t1: wrapped head beside approved h10."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build"); t = sys.argv[1]
BG = (232, 228, 224); INK = (60, 54, 50); F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)
def im(p, s):
    a = Image.open(p).convert("RGBA"); b = Image.new("RGBA", a.size, BG + (255,)); b.alpha_composite(a); return b.convert("RGB").resize(s, Image.LANCZOS)
H, W_ = os.path.join(R, "concepts", "h10", "H"), os.path.join(R, "wrap", t)
w, h = 440, 522; M = 30; g = 14
c = Image.new("RGB", (M * 2 + 4 * w + 3 * g, 90 + 2 * (h + 44) + 440), BG); d = ImageDraw.Draw(c)
d.text((M, 24), f"Wrap test {t}: MPFB head on approved h10", font=F(32), fill=INK)
rows = (((H, "front_neutral", "h10 front"), (H, "q_neutral", "h10 3/4"), (H, "side_neutral", "h10 side"), (H, "front_smile", "h10 smile")),
        ((W_, "front_neutral", "Wrap front"), (W_, "q_neutral", "Wrap 3/4"), (W_, "side_neutral", "Wrap side"), (W_, "h10smile", "Wrap: approved h10 smile")))
y = 80
for r in rows:
    for j, (dr, n, l) in enumerate(r):
        x = M + j * (w + g); d.text((x + w / 2, y + 6), l, font=F(22), fill=INK, anchor="mt"); c.paste(im(os.path.join(dr, n + ".png"), (w, h)), (x, y + 36))
    y += h + 44
for j, (dr, n, l) in enumerate(((W_, "blink", "Wrap: blink key"), (W_, "smile", "Wrap: old MPFB smile key"))):
    x = M + j * (w + g); d.text((x + w / 2, y + 6), l, font=F(22), fill=INK, anchor="mt"); c.paste(im(os.path.join(dr, n + ".png"), (w, 380)), (x, y + 36))
x = M + 2 * (w + g); d.text((x + w, y + 6), "Wrap: eyes", font=F(22), fill=INK, anchor="mt"); c.paste(im(os.path.join(W_, "eyes.png"), (2 * w + g, 380)), (x, y + 36))
c.save(os.path.join(R, "wrap", f"{t}_board.jpg"), quality=90)
