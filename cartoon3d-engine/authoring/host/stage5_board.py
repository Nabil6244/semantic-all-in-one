"""python3 host/stage5_board.py f1: h10 vs Gate 4 Three.js vs Stage 5 Three.js (compressed), plus close-ups and full body."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(os.path.dirname(HERE), "build"); t = sys.argv[1]; R = os.path.join(B, "stage5")
H = os.path.join(B, "concepts", "h10", "H"); G4 = os.path.join(R, "k3ref", "three"); S5 = os.path.join(R, t, "three")
BG = (232, 228, 224); INK = (60, 54, 50); F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)
def im(p, s):
    a = Image.open(p).convert("RGBA"); b = Image.new("RGBA", a.size, BG + (255,)); b.alpha_composite(a); return b.convert("RGB").resize(s, Image.LANCZOS)
def board(cols, rows, title, out, size):
    M, g = 30, 12; c = Image.new("RGB", (M * 2 + 150 + len(cols) * (size[0] + g), 120 + len(rows) * (size[1] + 8)), BG); d = ImageDraw.Draw(c); d.text((M, 22), title, font=F(28), fill=INK)
    for j, lab in enumerate(cols):
        d.text((M + 150 + j * (size[0] + g) + size[0] / 2, 84), lab, font=F(19), fill=INK, anchor="mt")
    for i, (rl, paths) in enumerate(rows):
        y = 112 + i * (size[1] + 8); d.text((M, y + size[1] / 2), rl, font=F(18), fill=INK, anchor="lm")
        for j, p in enumerate(paths):
            c.paste(im(p, size), (M + 150 + j * (size[0] + g), y))
    c.save(out, quality=90)
v = ["front_neutral", "q_neutral", "side_neutral", "front_smile", "q_smile"]
board([n.replace("_", " ") for n in v], [("h10 approved", [os.path.join(H, n + ".png") for n in v]), ("Gate 4 (26.9 MB)", [os.path.join(G4, n + ".png") for n in v]), ("Stage 5 (7.1 MB)", [os.path.join(S5, n + ".png") for n in v])],
      f"Stage 5 {t}: h10 vs the app's Three.js, before and after compression", os.path.join(R, f"{t}_compare.jpg"), (300, 356))
c = [x["name"] for x in json.load(open(os.path.join(HERE, "stage5_shots.json"))) if x["name"].startswith(("c_", "body"))]
board([n.replace("c_", "").replace("_", " ") for n in c], [("Gate 4", [os.path.join(G4, n + ".png") for n in c]), ("Stage 5", [os.path.join(S5, n + ".png") for n in c])],
      f"Stage 5 {t}: close-ups and full body, Three.js", os.path.join(R, f"{t}_detail.jpg"), (230, 273))
