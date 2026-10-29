"""ONE-TIME asset builder for the Explainer "characters" pack: the people a story needs (soldier, officer, king, police, worker, farmer, merchant, sailor, doctor, revolutionary, royal guard, judge,
woman, priest). Run by hand, never during a render:

    python3 -B explainer/cartoon/build_characters.py            # writes explainer/assets/characters/ (PNG files + manifest.json)
    python3 -B explainer/cartoon/build_characters.py --check    # rebuilds in memory, compares bytes with the files on disk, writes nothing
    python3 -B explainer/cartoon/build_characters.py --sheet PATH.png   # contact sheet for looking at the art

Every character is the same body as the narrator and the v1 cast (explainer/narrator/build_assets.py draws it) in the neat "serious" look, with its own colours and clothing drawn on top: hats and
hair, collars, belts, robes. Four poses each (idle, point, surprise, think), 440 x 560 like the cast, feet on the bottom edge. Drawn with Pillow at 4x and reduced with LANCZOS, saved with fixed
PNG settings, so the same Pillow gives the same bytes. The v1 kit and its manifest are not touched."""

from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import PIL
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from explainer.narrator import build_assets as NB      # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "assets" / "characters"
ASSET_ID = "characters_v1"
POSES = ("idle", "point", "surprise", "think")
INK = (38, 38, 40, 255)
GOLD, GOLD2, SILVER, WHITE, BLACK = (226, 170, 40, 255), (250, 214, 100, 255), (200, 204, 212, 255), (246, 244, 236, 255), (40, 40, 46, 255)
RED, BLUE, NAVY, GREEN, BROWN, STRAW = (200, 62, 58, 255), (60, 100, 200, 255), (34, 48, 92, 255), (60, 130, 84, 255), (122, 84, 52, 255), (226, 196, 108, 255)

# colours of the body for each character: shirt (the coat), pants, shoe, scarf (the tie), hair, skin
LOOKS: Dict[str, dict] = {
    "soldier": dict(shirt=(44, 66, 128, 255), pants=(232, 228, 214, 255), shoe=BLACK, scarf=(190, 56, 52, 255), hair=(70, 46, 30, 255), skin=(240, 205, 172, 255)),
    "officer": dict(shirt=(30, 48, 104, 255), pants=(236, 232, 218, 255), shoe=BLACK, scarf=(216, 176, 60, 255), hair=(60, 40, 30, 255), skin=(238, 200, 168, 255)),
    "king": dict(shirt=(138, 40, 86, 255), pants=(70, 40, 80, 255), shoe=(60, 40, 40, 255), scarf=(226, 170, 40, 255), hair=(150, 150, 156, 255), skin=(240, 205, 175, 255)),
    "police": dict(shirt=(40, 60, 104, 255), pants=(32, 44, 80, 255), shoe=BLACK, scarf=BLACK, hair=(50, 38, 34, 255), skin=(226, 184, 150, 255)),
    "worker": dict(shirt=(104, 108, 118, 255), pants=(70, 78, 96, 255), shoe=(90, 62, 44, 255), scarf=(224, 124, 40, 255), hair=(60, 44, 34, 255), skin=(224, 182, 148, 255)),
    "farmer": dict(shirt=(190, 70, 60, 255), pants=(64, 96, 150, 255), shoe=(90, 62, 44, 255), scarf=(236, 224, 190, 255), hair=(120, 84, 52, 255), skin=(230, 190, 156, 255)),
    "merchant": dict(shirt=(92, 60, 40, 255), pants=(60, 50, 44, 255), shoe=BLACK, scarf=(226, 170, 40, 255), hair=(46, 36, 32, 255), skin=(214, 168, 132, 255)),
    "sailor": dict(shirt=(244, 242, 236, 255), pants=(244, 242, 236, 255), shoe=BLACK, scarf=(40, 60, 120, 255), hair=(96, 66, 40, 255), skin=(226, 182, 146, 255)),
    "doctor": dict(shirt=(244, 244, 242, 255), pants=(90, 100, 120, 255), shoe=(70, 60, 56, 255), scarf=(80, 150, 170, 255), hair=(60, 50, 46, 255), skin=(236, 198, 164, 255)),
    "revolutionary": dict(shirt=(232, 224, 200, 255), pants=(60, 80, 130, 255), shoe=(80, 56, 40, 255), scarf=(196, 60, 58, 255), hair=(52, 38, 30, 255), skin=(230, 190, 156, 255)),
    "guard": dict(shirt=(186, 46, 46, 255), pants=(40, 50, 90, 255), shoe=BLACK, scarf=GOLD, hair=(60, 44, 34, 255), skin=(238, 200, 168, 255)),
    "judge": dict(shirt=(36, 36, 44, 255), pants=(36, 36, 44, 255), shoe=BLACK, scarf=(246, 244, 236, 255), hair=(150, 150, 156, 255), skin=(238, 200, 168, 255)),
    "woman": dict(shirt=(146, 84, 150, 255), pants=(146, 84, 150, 255), shoe=(90, 56, 50, 255), scarf=(246, 244, 236, 255), hair=(110, 62, 40, 255), skin=(244, 212, 182, 255)),
    "priest": dict(shirt=(34, 34, 40, 255), pants=(34, 34, 40, 255), shoe=BLACK, scarf=(246, 244, 236, 255), hair=(120, 120, 126, 255), skin=(236, 198, 164, 255)),
}
TYPES = tuple(LOOKS)


def _hat_band(c, y0, y1, x0=150, x1=290, col=GOLD):
    c.rrect((x0, y0, x1, y1), 4, col)


def soldier(c):
    c.rrect((160, 6, 280, 70), 8, BLACK)                          # the shako
    _hat_band(c, 54, 66, 160, 280)
    c.circle((220, 36), 13, GOLD)
    c.ellipse((262, 4, 290, 52), RED)                             # plume
    c.rrect((150, 66, 290, 80), 5, BLACK)                         # peak
    for a, b in (((172, 248), (270, 396)), ((268, 248), (170, 396))):      # white cross belts
        c.stroke([a, b], 22, INK)
        c.stroke([a, b], 14, WHITE)
    c.circle((220, 322), 11, GOLD)


def officer(c):
    c.poly([(104, 74), (146, 38), (220, 24), (294, 38), (336, 74), (300, 86), (220, 64), (140, 86)], BLACK)      # bicorne
    c.stroke([(116, 72), (150, 44), (220, 30), (290, 44), (324, 72)], 6, GOLD)
    c.circle((220, 52), 12, RED)
    c.circle((220, 52), 6, WHITE)
    for x0 in (142, 254):                                          # gold epaulettes
        c.rrect((x0, 240, x0 + 44, 262), 5, GOLD)
        for k in range(5):
            c.stroke([(x0 + 6 + k * 8, 262), (x0 + 6 + k * 8, 276)], 4, GOLD2)
    c.stroke([(166, 252), (276, 398)], 20, INK)
    c.stroke([(166, 252), (276, 398)], 12, RED)                    # sash
    c.circle((256, 300), 11, GOLD)
    c.circle((256, 300), 5, WHITE)


def king(c):
    c.poly([(148, 70), (148, 14), (184, 42), (220, 2), (256, 42), (292, 14), (292, 70)], GOLD)
    c.rrect((148, 62, 292, 78), 4, GOLD2)
    for x, y in ((148, 12), (220, 0), (292, 12)):
        c.circle((x, y + 4), 8, RED)
    c.ellipse((140, 222, 300, 270), WHITE)                         # ermine collar
    for x, y in ((166, 248), (196, 258), (230, 258), (262, 248), (214, 236)):
        c.circle((x, y), 5, BLACK, False)
    c.stroke([(220, 268), (220, 404)], 14, INK)
    c.stroke([(220, 268), (220, 404)], 8, GOLD)
    c.circle((220, 330), 11, RED)


def police(c):
    c.rrect((150, 22, 290, 74), 24, NAVY)                          # peaked cap
    c.rrect((148, 56, 292, 70), 4, BLACK)
    c.rrect((160, 66, 280, 84), 8, BLACK)                          # the peak
    c.circle((220, 42), 12, SILVER)
    c.poly([(248, 284), (284, 284), (284, 312), (266, 326), (248, 312)], SILVER)       # badge
    c.circle((266, 300), 5, GOLD, False)
    c.stroke([(156, 376), (284, 376)], 14, BLACK)
    c.rrect((208, 366, 232, 386), 3, SILVER)


def worker(c):
    c.ellipse((142, 20, 298, 104), (246, 200, 40, 255))            # hard hat
    c.rrect((124, 78, 316, 94), 6, (246, 200, 40, 255))
    c.stroke([(220, 22), (220, 78)], 8, (214, 164, 20, 255))
    c.poly([(160, 250), (280, 250), (286, 404), (154, 404)], (236, 122, 40, 255))          # hi-vis vest
    for y in (310, 352):
        c.stroke([(156, y), (284, y)], 10, SILVER)


def farmer(c):
    c.ellipse((92, 54, 348, 104), STRAW)                           # straw hat
    c.ellipse((150, 8, 290, 86), STRAW)
    c.rrect((150, 56, 290, 70), 4, BROWN)
    for x in (186, 254):                                           # dungaree straps and bib
        c.stroke([(x, 244), (x, 400)], 14, INK)
        c.stroke([(x, 244), (x, 400)], 8, (64, 96, 150, 255))
    c.rrect((184, 330, 256, 404), 8, (64, 96, 150, 255))


def merchant(c):
    c.rrect((162, 6, 278, 66), 6, (56, 40, 34, 255))              # top hat
    c.rrect((136, 60, 304, 78), 6, (56, 40, 34, 255))
    _hat_band(c, 48, 60, 162, 278, GOLD)
    c.poly([(176, 244), (264, 244), (252, 396), (188, 396)], (70, 130, 90, 255))       # waistcoat
    c.stroke([(190, 300), (220, 330), (250, 300)], 5, GOLD)
    c.circle((220, 332), 9, GOLD)
    c.stroke([(190, 163), (220, 156), (250, 163)], 12, (46, 36, 32, 255))          # moustache


def sailor(c):
    c.ellipse((146, 28, 294, 94), WHITE)                           # sailor cap
    c.rrect((146, 72, 294, 90), 6, (40, 60, 120, 255))
    for y in (270, 304, 338, 372):                                 # striped top
        c.stroke([(160, y), (280, y)], 10, (50, 80, 160, 255))
    c.poly([(168, 232), (272, 232), (220, 318)], (40, 60, 120, 255))
    c.stroke([(184, 244), (220, 296), (256, 244)], 5, WHITE)


def doctor(c):
    for cx in (176, 264):                                          # round glasses
        c.ellipse((cx - 27, 99, cx + 27, 153), None, True, 5)
    c.stroke([(203, 126), (237, 126)], 5, INK)
    c.poly([(176, 232), (264, 232), (220, 404), (208, 404)], (236, 238, 240, 255), True, 4)
    c.stroke([(184, 246), (190, 300), (220, 330), (252, 300), (256, 246)], 6, BLACK)      # stethoscope
    c.circle((220, 336), 9, SILVER)
    c.rrect((256, 300, 276, 332), 3, WHITE)
    c.stroke([(266, 306), (266, 326)], 4, RED)
    c.stroke([(256, 316), (276, 316)], 4, RED)


def revolutionary(c):
    c.poly([(132, 90), (146, 44), (196, 16), (252, 30), (300, 18), (318, 52), (294, 56), (300, 90)], RED)     # Phrygian cap
    c.circle((176, 74), 13, WHITE)
    c.circle((176, 74), 7, BLUE)
    for k, col in enumerate((BLUE, WHITE, RED)):                    # tricolour sash at the waist
        c.stroke([(156, 360 + k * 14), (284, 360 + k * 14)], 14, col)
    c.poly([(176, 236), (264, 236), (220, 292)], (200, 192, 168, 255))


def guard(c):
    c.rrect((146, 4, 294, 74), 40, BLACK)                         # bearskin
    for x in range(160, 290, 20):
        c.stroke([(x, 8), (x + 6, 40)], 5, (70, 70, 78, 255))
    c.circle((220, 52), 10, GOLD)
    c.stroke([(168, 84), (220, 98), (272, 84)], 5, GOLD)
    for y in (282, 316, 350):
        c.circle((220, y), 8, GOLD)
    for a, b in (((172, 248), (270, 396)), ((268, 248), (170, 396))):
        c.stroke([a, b], 20, INK)
        c.stroke([a, b], 12, WHITE)


def judge(c):
    c.ellipse((112, 30, 328, 118), WHITE)                          # a curled wig
    for x in (118, 138):
        for y in (100, 140, 180):
            c.circle((x, y), 17, WHITE)
            c.circle((440 - x, y), 17, WHITE)
    c.poly([(196, 236), (244, 236), (230, 330), (210, 330)], WHITE)    # white bands
    c.stroke([(220, 236), (220, 330)], 4, INK)


def woman(c):
    c.poly([(158, 368), (282, 368), (322, 500), (118, 500)], (146, 84, 150, 255))      # dress
    c.stroke([(122, 498), (318, 498)], 8, (110, 60, 116, 255))
    c.poly([(122, 90), (152, 108), (146, 262), (110, 244)], (110, 62, 40, 255))        # long hair
    c.poly([(318, 90), (288, 108), (294, 262), (330, 244)], (110, 62, 40, 255))
    c.circle((220, 46), 30, (110, 62, 40, 255))                    # bun
    c.poly([(196, 70), (220, 62), (244, 70), (244, 84), (196, 84)], (110, 62, 40, 255), False)
    c.stroke([(176, 238), (264, 238)], 14, WHITE)                  # collar


def priest(c):
    c.poly([(150, 240), (290, 240), (316, 520), (124, 520)], (34, 34, 40, 255))        # cassock
    c.stroke([(220, 250), (220, 520)], 4, (80, 80, 90, 255))
    c.rrect((204, 234, 236, 262), 3, WHITE)
    c.stroke([(158, 384), (282, 384)], 8, GOLD)
    c.stroke([(220, 384), (220, 440)], 6, GOLD)
    c.stroke([(208, 424), (232, 424)], 6, GOLD)
    c.ellipse((172, 52, 268, 96), (236, 198, 164, 255), False)       # tonsure


DRAW: Dict[str, Callable] = {"soldier": soldier, "officer": officer, "king": king, "police": police, "worker": worker, "farmer": farmer, "merchant": merchant, "sailor": sailor,
                             "doctor": doctor, "revolutionary": revolutionary, "guard": guard, "judge": judge, "woman": woman, "priest": priest}


def draw_character(kind: str, pose: str) -> Image.Image:
    look = LOOKS[kind]
    saved, saved_style = dict(NB.P), NB.STYLE
    try:
        NB.STYLE = "serious"
        NB.P.update(look)
        body = NB.draw_body(pose)
        for name, im in (("eyes", NB.draw_eyes("open")), ("mouth", NB.draw_mouth("o" if pose == "surprise" else "closed"))):
            body.alpha_composite(im, tuple(NB.FACE_ORIGIN[name]))
        c = NB.Canvas(NB.CW, NB.CH)
        DRAW[kind](c)
        body.alpha_composite(c.done())
    finally:
        NB.P.clear()
        NB.P.update(saved)
        NB.STYLE = saved_style
    return body


def png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False, compress_level=9)
    return buf.getvalue()


def build() -> Dict[str, bytes]:
    files: Dict[str, bytes] = {}
    chars: Dict[str, dict] = {}
    for kind in TYPES:
        chars[kind] = {}
        for pose in POSES:
            im = draw_character(kind, pose)
            b = png_bytes(im)
            name = f"char_{kind}_{pose}.png"
            files[name] = b
            chars[kind][pose] = {"file": name, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "size": list(im.size), "bbox": list(im.getchannel("A").getbbox())}
    digest = hashlib.sha256("".join(hashlib.sha256(files[n]).hexdigest() for n in sorted(files)).encode()).hexdigest()
    manifest = {"asset_id": ASSET_ID, "version": 1, "canvas": [NB.CW, NB.CH], "feet_y": NB.FEET_Y, "pillow_version": PIL.__version__, "built_by": "explainer/cartoon/build_characters.py",
                "types": list(TYPES), "poses": list(POSES), "layers_digest": digest, "characters": chars}
    files["manifest.json"] = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    return files


def contact_sheet(files: Dict[str, bytes], path: str) -> None:
    cols = 7
    rows = (len(TYPES) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * 220, rows * 290), (236, 230, 214, 255))
    for k, kind in enumerate(TYPES):
        im = Image.open(io.BytesIO(files[f"char_{kind}_idle.png"])).convert("RGBA").resize((220, 280), Image.LANCZOS)
        sheet.alpha_composite(im, ((k % cols) * 220, (k // cols) * 290))
    sheet.convert("RGB").save(path)


def main(argv) -> int:
    files = build()
    if "--check" in argv:
        bad = [n for n, b in files.items() if not (OUT / n).is_file() or (OUT / n).read_bytes() != b]
        print("characters pack: " + ("matches the files on disk" if not bad else f"DIFFERS in {len(bad)} file(s): {', '.join(bad[:6])}"))
        return 1 if bad else 0
    if "--sheet" in argv:
        contact_sheet(files, argv[argv.index("--sheet") + 1])
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (OUT / n).write_bytes(b)
    print(f"wrote {len(files)} files to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
