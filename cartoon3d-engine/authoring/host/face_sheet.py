"""python3 host/face_sheet.py <tag> [before_tag]: labelled review board; with a before tag, also a before/after board."""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

B = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "face")
BG = (232, 228, 224); INK = (60, 54, 50)
F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)


def card(tag, name, size):
    p = os.path.join(B, tag, name + ".png")
    im = Image.open(p).convert("RGBA"); bg = Image.new("RGBA", im.size, BG + (255,)); bg.alpha_composite(im)
    im = bg.convert("RGB"); W, H = im.size
    r = size[0] / size[1]; cw, ch = (W, int(W / r)) if W / H < r else (int(H * r), H)
    x, y = (W - cw) // 2, (H - ch) // 2
    return im.crop((x, y, x + cw, y + ch)).resize(size, Image.LANCZOS)


def board(path, title, items, cols, size):
    rows = (len(items) + cols - 1) // cols; M = 30
    c = Image.new("RGB", (cols * (size[0] + 16) + 2 * M, 90 + rows * (size[1] + 52) + M), BG); d = ImageDraw.Draw(c)
    d.text((M, 26), title, font=F(34), fill=INK)
    for i, (tag, name, label) in enumerate(items):
        x = M + (i % cols) * (size[0] + 16); y = 90 + (i // cols) * (size[1] + 52)
        d.text((x + size[0] / 2, y + 8), label, font=F(22), fill=INK, anchor="mt")
        if os.path.exists(os.path.join(B, tag, name + ".png")):
            c.paste(card(tag, name, size), (x, y + 40))
    c.save(path, quality=92)


tag = sys.argv[1]
N = [("front_neutral", "Front neutral"), ("front_smile", "Front smile"), ("q_neutral", "3/4 neutral"), ("q_smile", "3/4 smile"), ("side", "Side profile"),
     ("eyes", "Close-up eyes"), ("laugh", "Laugh"), ("talk", "Talking"), ("surprise", "Surprised"), ("curious", "Curious"), ("smile45_arkit", "45% smile test")]
board(os.path.join(B, f"{tag}_board.jpg"), f"Face review: {tag}", [(tag, n, l) for n, l in N], 4, (440, 528))
if len(sys.argv) > 2:
    before = sys.argv[2]; pick = [N[0], N[1], N[2], N[5], N[6], N[10]]
    items = []
    for n, l in pick:
        items += [(before, n, f"Before: {l}"), (tag, n, f"After: {l}")]
    board(os.path.join(B, f"{tag}_before_after.jpg"), f"Before and after: {before} to {tag}", items, 4, (440, 528))
