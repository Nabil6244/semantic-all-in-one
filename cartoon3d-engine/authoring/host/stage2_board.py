"""python3 host/stage2_board.py s1: h10, Blender low mesh and Three.js side by side."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build"); t = sys.argv[1]
H, Bd, Th = os.path.join(R, "concepts", "h10", "H"), os.path.join(R, "stage2", t), os.path.join(R, "stage2", t, "three")
BG = (232, 228, 224); INK = (60, 54, 50); F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)
def im(p, s):
    a = Image.open(p).convert("RGBA"); b = Image.new("RGBA", a.size, BG + (255,)); b.alpha_composite(a); return b.convert("RGB").resize(s, Image.LANCZOS)
def grid(path, title, cells, cols, size):
    M, g = 30, 14; rows = (len(cells) + cols - 1) // cols
    c = Image.new("RGB", (M * 2 + cols * size[0] + (cols - 1) * g, 84 + rows * (size[1] + 44) + 16), BG); d = ImageDraw.Draw(c); d.text((M, 22), title, font=F(30), fill=INK)
    for i, (p, l) in enumerate(cells):
        x = M + (i % cols) * (size[0] + g); y = 80 + (i // cols) * (size[1] + 44)
        d.text((x + size[0] / 2, y + 6), l, font=F(21), fill=INK, anchor="mt"); c.paste(im(p, size), (x, y + 36))
    c.save(path, quality=90)
v = (("front_neutral", "front"), ("q_neutral", "3/4"), ("side_neutral", "side"), ("front_smile", "smile"), ("q_smile", "3/4 smile"))
cells = [(os.path.join(H, n + ".png"), "h10 " + l) for n, l in v] + [(os.path.join(Bd, n + ".png"), "Blender low " + l) for n, l in v] + [(os.path.join(Th, n + ".png"), "Three.js " + l) for n, l in v]
grid(os.path.join(R, "stage2", f"{t}_compare.jpg"), f"Stage 2 {t}: h10, optimised Blender, Three.js", cells, 5, (340, 404))
e = ("blink_half", "blink", "jaw", "aa", "O", "SS", "laugh")
grid(os.path.join(R, "stage2", f"{t}_three_expr.jpg"), f"Stage 2 {t}: expressions in Three.js", [(os.path.join(Th, n + ".png"), n) for n in e], 4, (340, 404))
