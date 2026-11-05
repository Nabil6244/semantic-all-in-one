"""python3 host/wrap_board2.py c1: comparison and expression boards for a head candidate."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build"); t = sys.argv[1]
H, W_ = os.path.join(R, "concepts", "h10", "H"), os.path.join(R, "wrap", t)
BG = (232, 228, 224); INK = (60, 54, 50); F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)
def im(p, s):
    a = Image.open(p).convert("RGBA"); b = Image.new("RGBA", a.size, BG + (255,)); b.alpha_composite(a); return b.convert("RGB").resize(s, Image.LANCZOS)
def grid(path, title, cells, cols, size):
    M, g = 30, 14; rows = (len(cells) + cols - 1) // cols
    c = Image.new("RGB", (M * 2 + cols * size[0] + (cols - 1) * g, 84 + rows * (size[1] + 44) + 16), BG); d = ImageDraw.Draw(c)
    d.text((M, 22), title, font=F(30), fill=INK)
    for i, (p, l) in enumerate(cells):
        x = M + (i % cols) * (size[0] + g); y = 80 + (i // cols) * (size[1] + 44)
        d.text((x + size[0] / 2, y + 6), l, font=F(21), fill=INK, anchor="mt"); c.paste(im(p, size), (x, y + 36))
    c.save(path, quality=90)
v = (("front_neutral", "Front"), ("q_neutral", "3/4"), ("side_neutral", "Side"), ("front_smile", "Front smile"), ("q_smile", "3/4 smile"), ("side_smile", "Side smile"))
cells = [(os.path.join(H, n + ".png"), "h10 " + l) for n, l in v[:3]] + [(os.path.join(W_, n + ".png"), "Candidate " + l) for n, l in v[:3]] + [(os.path.join(H, n + ".png"), "h10 " + l) for n, l in v[3:]] + [(os.path.join(W_, n + ".png"), "Candidate " + l) for n, l in v[3:]]
grid(os.path.join(R, "wrap", f"{t}_compare.jpg"), f"Candidate {t} against approved h10", cells, 3, (520, 618))
e = (("blink_half", "Blink 50%"), ("blink_full", "Blink 100%"), ("jaw", "Jaw open"), ("laugh", "Laugh"), ("aa", "aa"), ("E", "E"), ("I", "I"), ("O", "O"), ("U", "U"), ("PP", "PP"), ("FF", "FF"), ("SS", "SS"), ("TH", "TH"), ("smile_blink", "Smile + blink"), ("smile_aa", "Smile + aa"))
grid(os.path.join(R, "wrap", f"{t}_expressions.jpg"), f"Candidate {t}: expressions", [(os.path.join(W_, n + ".png"), l) for n, l in e], 5, (340, 404))
d = (("eyes", "Eyes open"), ("eyes_closed", "Eyes closed"), ("mouth_neutral", "Mouth neutral"), ("mouth_smile", "Mouth smile"))
grid(os.path.join(R, "wrap", f"{t}_detail.jpg"), f"Candidate {t}: lid and lip detail", [(os.path.join(W_, n + ".png"), l) for n, l in d], 2, (760, 420))
