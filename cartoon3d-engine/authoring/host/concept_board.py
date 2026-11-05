"""python3 host/concept_board.py v2: the three concepts side by side, one row per concept, same camera and light."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
B = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "concepts"); tag = sys.argv[1]
BG = (232, 228, 224); INK = (60, 54, 50); F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)
views = (("front_neutral", "Front neutral"), ("q_neutral", "3/4 neutral"), ("front_smile", "Front smile"), ("q_smile", "3/4 smile"))
rows = (("A", "A: Soft Cartoon Presenter"), ("B", "B: Expressive Preschool Host"), ("C", "C: Premium Animated Character"))
w, h = 480, 570; M = 30
c = Image.new("RGB", (M * 2 + 4 * w + 3 * 14, 70 + 3 * (h + 58) + M), BG); d = ImageDraw.Draw(c)
for j, (_, l) in enumerate(views):
    d.text((M + j * (w + 14) + w / 2, 30), l, font=F(24), fill=INK, anchor="mt")
for i, (k, l) in enumerate(rows):
    y = 70 + i * (h + 58)
    d.text((M, y + 10), l, font=F(28), fill=INK)
    for j, (n, _) in enumerate(views):
        p = os.path.join(B, tag, k, n + ".png")
        if os.path.exists(p):
            a = Image.open(p).convert("RGBA"); b = Image.new("RGBA", a.size, BG + (255,)); b.alpha_composite(a)
            c.paste(b.convert("RGB").resize((w, h), Image.LANCZOS), (M + j * (w + 14), y + 50))
c.save(os.path.join(B, f"{tag}_board.jpg"), quality=90)
