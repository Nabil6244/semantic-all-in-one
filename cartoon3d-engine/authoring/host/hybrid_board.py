"""python3 host/hybrid_board.py h1: the Hybrid review board."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
B = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "concepts"); tag = sys.argv[1]; D = os.path.join(B, tag, "H")
BG = (232, 228, 224); INK = (60, 54, 50); F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)
def im(n, s):
    a = Image.open(os.path.join(D, n + ".png")).convert("RGBA"); b = Image.new("RGBA", a.size, BG + (255,)); b.alpha_composite(a); return b.convert("RGB").resize(s, Image.LANCZOS)
w, h = 500, 594; M = 30; g = 14
c = Image.new("RGB", (M * 2 + 3 * w + 2 * g, 90 + 2 * (h + 44) + 44 + 380 + 44 + 300 + M), BG); d = ImageDraw.Draw(c)
d.text((M, 24), "Hybrid A+B+C: design review (" + tag + ")", font=F(34), fill=INK)
y = 84
for row in ((("front_neutral", "Front neutral"), ("q_neutral", "3/4 neutral"), ("side_neutral", "Side neutral")), (("front_smile", "Front smile"), ("q_smile", "3/4 smile"), ("side_smile", "Side smile"))):
    for j, (n, l) in enumerate(row):
        x = M + j * (w + g); d.text((x + w / 2, y + 6), l, font=F(23), fill=INK, anchor="mt"); c.paste(im(n, (w, h)), (x, y + 38))
    y += h + 44
W = 3 * w + 2 * g
d.text((M + W / 2, y + 6), "Eyes close-up", font=F(23), fill=INK, anchor="mt"); c.paste(im("eyes", (int(380 * 1200 / 640), 380)), (M + (W - int(380 * 1200 / 640)) // 2, y + 38)); y += 380 + 44
for j, (n, l) in enumerate((("mouth_neutral", "Mouth neutral"), ("mouth_smile", "Mouth smile"))):
    x = M + j * (W // 2 + 7); d.text((x + 380, y + 6), l, font=F(23), fill=INK, anchor="mt"); c.paste(im(n, (760, 300 if False else 300)), (x, y + 38))
c.save(os.path.join(B, f"hybrid_{tag}_board.jpg"), quality=90)
