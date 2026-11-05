"""python3 host/stage4_board.py k1: Gate 4 boards, Blender above Three.js."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); t = sys.argv[1]; R = os.path.join(os.path.dirname(HERE), "build", "stage4"); D = os.path.join(R, t)
BG = (232, 228, 224); INK = (60, 54, 50); F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)
SH = [x["name"] for x in json.load(open(os.path.join(HERE, "stage4_shots.json")))]
def im(p, s):
    a = Image.open(p).convert("RGBA"); b = Image.new("RGBA", a.size, BG + (255,)); b.alpha_composite(a); return b.convert("RGB").resize(s, Image.LANCZOS)
def board(cells, cols, title, out, size, rows=("Blender", "Three.js")):
    """cells: (label, [image per row])"""
    M, g = 30, 12; nr = len(rows); blocks = (len(cells) + cols - 1) // cols
    c = Image.new("RGB", (M * 2 + 110 + cols * (size[0] + g), 84 + blocks * (nr * (size[1] + 4) + 40) + 10), BG); d = ImageDraw.Draw(c); d.text((M, 22), title, font=F(28), fill=INK)
    for i, (lab, ims) in enumerate(cells):
        x = M + 110 + (i % cols) * (size[0] + g); y = 80 + (i // cols) * (nr * (size[1] + 4) + 40)
        d.text((x + size[0] / 2, y + 4), lab, font=F(19), fill=INK, anchor="mt")
        for r, p in enumerate(ims):
            c.paste(im(p, size), (x, y + 30 + r * (size[1] + 4)))
            if i % cols == 0:
                d.text((M, y + 30 + r * (size[1] + 4) + size[1] / 2), rows[r], font=F(18), fill=INK, anchor="lm")
    c.save(out, quality=90)
both = lambda n: [os.path.join(D, n + ".png"), os.path.join(D, "three", n + ".png")]
lab = lambda n: n[2:].replace("_", " ")
board([(lab(n), both(n)) for n in SH if n.startswith("v_")], 5, f"Stage 4 {t}: expressions at video size", os.path.join(R, f"{t}_video.jpg"), (250, 297))
board([(lab(n), both(n)) for n in SH if n.startswith("c_")], 7, f"Stage 4 {t}: close-ups (visemes, expressions, brows)", os.path.join(R, f"{t}_closeup.jpg"), (230, 273))
ba = [(f"{v} {w}", [os.path.join(D, f"before_{v}_{n}.png" if False else f"before_{w}_{n}.png"), os.path.join(D, f"{w}_{n}.png"), os.path.join(D, "three", f"{w}_{n}.png")]) for n in ("FF", "TH") for w in ("c", "q") for v in [n]]
board(ba, 4, f"Stage 4 {t}: FF and TH, Gate 3 vs now", os.path.join(R, f"{t}_ff_th.jpg"), (280, 332), rows=("Before", "Blender", "Three.js"))
