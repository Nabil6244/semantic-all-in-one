"""Lays the renders out as one labelled character sheet (python3 host/make_sheet.py). Writes build/host_character_sheet.png and host_pose_tests.png."""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

B = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build"); S = os.path.join(B, "sheet")
BG = (243, 241, 236); INK = (70, 62, 58)
F = lambda n: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", n)


def card(name, size, shadow=True):
    im = Image.open(os.path.join(S, name + ".png")).convert("RGBA")
    box = im.getbbox(); W, H = im.size
    bg = Image.new("RGBA", im.size, BG + (255,))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse((box[0] + 20, box[3] - 26, box[2] - 20, box[3] + 14), fill=(60, 50, 45, 80))
        bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize(size, Image.LANCZOS)


def sheet(path, title, rows):
    M, gap = 40, 26
    width = max(sum(w for _, _, (w, _), _ in r) + gap * (len(r) - 1) for r in rows) + 2 * M
    height = 110 + sum(r[0][2][1] + 60 for r in rows) + M
    c = Image.new("RGB", (width, height), BG); d = ImageDraw.Draw(c)
    d.text((M, 34), title, font=F(40), fill=INK)
    y = 110
    for r in rows:
        x = M
        for name, label, size, sh in r:
            c.paste(card(name, size, sh), (x, y + 40))
            d.text((x + size[0] / 2, y + 10), label, font=F(24), fill=INK, anchor="mt")
            x += size[0] + gap
        y += r[0][2][1] + 60
    c.save(path)


FB, FC = (432, 675), (540, 641)
sheet(os.path.join(B, "host_character_sheet.png"), "Preschool host: appearance review", [
    [("front", "Front / neutral", FB, True), ("three_quarter", "Three-quarter", FB, True), ("side", "Side", FB, True), ("back", "Back", FB, True), ("wave", "Waving", FB, True)],
    [("face", "Face close-up", FC, False), ("smile", "Friendly smile", FC, False), ("laugh", "Laugh", FC, False), ("surprise", "Surprise", FC, False)]])
sheet(os.path.join(B, "host_pose_tests.png"), "Clothing deformation tests", [
    [("t_arms_up", "Arms overhead", FB, True), ("t_arms_front", "Arms across, head turned", FB, True), ("t_stride", "Stride", FB, True), ("t_sit", "Deep knee bend", FB, True)]])
