"""python3 host/stage3_board.py g2: Gate 3 boards, Blender above Three.js for every pose in stage3_shots.json."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); t = sys.argv[1]; SHOTFILE = sys.argv[2] if len(sys.argv) > 2 else "stage3_shots.json"; STAGE = sys.argv[3] if len(sys.argv) > 3 else "stage3"
R = os.path.join(os.path.dirname(HERE), "build", STAGE)
D = os.path.join(R, t); BG = (232, 228, 224); INK = (60, 54, 50); F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)
SH = [s["name"] for s in json.load(open(os.path.join(HERE, SHOTFILE)))]
def im(p, s):
    a = Image.open(p).convert("RGBA"); b = Image.new("RGBA", a.size, BG + (255,)); b.alpha_composite(a); return b.convert("RGB").resize(s, Image.LANCZOS)
def board(names, cols, title, out, size=(250, 297)):
    M, g = 30, 12; blocks = (len(names) + cols - 1) // cols
    c = Image.new("RGB", (M * 2 + 110 + cols * (size[0] + g), 84 + blocks * (2 * size[1] + 60) + 10), BG); d = ImageDraw.Draw(c); d.text((M, 22), title, font=F(28), fill=INK)
    for i, n in enumerate(names):
        x = M + 110 + (i % cols) * (size[0] + g); y = 80 + (i // cols) * (2 * size[1] + 60)
        d.text((x + size[0] / 2, y + 4), n.replace("_", " "), font=F(19), fill=INK, anchor="mt")
        c.paste(im(os.path.join(D, n + ".png"), size), (x, y + 30)); c.paste(im(os.path.join(D, "three", n + ".png"), size), (x, y + 30 + size[1] + 4))
        if i % cols == 0:
            d.text((M, y + 30 + size[1] / 2), "Blender", font=F(18), fill=INK, anchor="lm"); d.text((M, y + 34 + size[1] * 1.5), "Three.js", font=F(18), fill=INK, anchor="lm")
    c.save(out, quality=90)
body = [n for n in SH if n.startswith("body")]
board([n for n in SH if n not in body], 7, f"Stage 3 {t}: Gate 3 poses, Blender and Three.js", os.path.join(R, f"{t}_poses.jpg"))
board(body, 3, f"Stage 3 {t}: full body", os.path.join(R, f"{t}_body.jpg"), size=(330, 392))
