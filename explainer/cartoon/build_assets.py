"""ONE-TIME asset builder for the Explainer cartoon kit. Run by hand, never during a render:

    python3 -B explainer/cartoon/build_assets.py            # writes explainer/assets/cartoon/ (PNG files + manifest.json)
    python3 -B explainer/cartoon/build_assets.py --check    # rebuilds in memory, compares bytes with the files on disk, writes nothing

Sets (5, each by day and at dusk; flat colour, no outline, as the style guide says), cast (one body in four colour roles, poses idle / point / surprise / think, and two more idle looks for
crowds) and props (7). The cast body is the narrator's drawing code with different colours (`explainer/narrator/build_assets.py`), so the two share one style; nothing is copied from the
reference. Everything is drawn with Pillow at 2x or 4x and reduced with LANCZOS, saved with fixed PNG settings: the same Pillow gives the same bytes."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

import PIL
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from explainer.narrator import build_assets as NB          # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "assets" / "cartoon"
ASSET_ID = "cartoon_kit_v1"
W, H = 1920, 1080
SS = 2
ROLES = {"blue": (60, 100, 200), "green": (46, 140, 92), "red": (204, 66, 64), "gold": (226, 170, 40)}
POSES = ("idle", "point", "surprise", "think")
KITS = {"a": ((86, 56, 36, 255), (250, 222, 190, 255)), "b": ((40, 36, 40, 255), (214, 160, 120, 255)), "c": ((150, 70, 40, 255), (240, 200, 170, 255))}
SETS = ("town", "field", "city", "harbour", "room")
TODS = ("day", "dusk")
PROPS = ("house", "tree", "cactus", "fence", "flag", "sign", "crate")
STAGE = {"town": 880, "field": 880, "city": 880, "harbour": 880, "room": 880}        # y of the feet line figures stand on (above the caption band that starts at y 900)
PAL = {
    "day": {"sky": (186, 222, 244), "sun": (255, 224, 120), "sand": (226, 200, 150), "grass": (122, 178, 98), "far": (150, 190, 160), "mesa": (206, 160, 120), "sea": (96, 160, 206), "wall": (238, 228, 208),
            "floor": (176, 132, 92), "road": (150, 150, 156), "building": (120, 150, 190), "building2": (150, 170, 196), "window": (240, 232, 160)},
    "dusk": {"sky": (246, 186, 146), "sun": (255, 150, 80), "sand": (200, 150, 110), "grass": (92, 134, 84), "far": (120, 130, 130), "mesa": (166, 110, 90), "sea": (80, 110, 160), "wall": (210, 190, 170),
             "floor": (140, 96, 70), "road": (110, 104, 116), "building": (90, 100, 140), "building2": (110, 112, 150), "window": (255, 214, 120)},
}
WALL, ROOF, DOOR, WOOD, DARKWOOD, LEAF, TRUNK, CACT, RED, WHITE = (236, 224, 200), (190, 90, 70), (110, 76, 52), (170, 124, 80), (120, 84, 56), (74, 140, 80), (120, 84, 56), (96, 152, 96), (196, 70, 64), (248, 248, 244)


class C:
    """Flat-colour drawing surface at SS x."""

    def __init__(self, w: int, h: int, bg=None):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w * SS, h * SS), bg if bg else (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def rect(self, x0, y0, x1, y1, fill, r=0):
        b = [x0 * SS, y0 * SS, x1 * SS, y1 * SS]
        (self.d.rounded_rectangle(b, radius=r * SS, fill=fill) if r else self.d.rectangle(b, fill=fill))

    def poly(self, pts, fill):
        self.d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)

    def ell(self, x0, y0, x1, y1, fill):
        self.d.ellipse([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=fill)

    def done(self) -> Image.Image:
        return self.im.resize((self.w, self.h), Image.LANCZOS)


def house(c: C, x, y, w, h, wall, roof, door=DOOR, win=(150, 190, 220)):
    c.rect(x, y - h, x + w, y, wall)
    c.poly([(x - w * 0.08, y - h), (x + w * 0.5, y - h - h * 0.55), (x + w * 1.08, y - h)], roof)
    c.rect(x + w * 0.42, y - h * 0.6, x + w * 0.62, y, door)
    c.rect(x + w * 0.12, y - h * 0.72, x + w * 0.3, y - h * 0.45, win)
    c.rect(x + w * 0.72, y - h * 0.72, x + w * 0.9, y - h * 0.45, win)


def pine(c: C, x, y, h, col):
    c.rect(x - h * 0.05, y - h * 0.2, x + h * 0.05, y, TRUNK)
    for k in range(3):
        top, base, half = y - h + k * h * 0.22, y - h * 0.18 - (2 - k) * h * 0.2, h * (0.2 + 0.07 * k)
        c.poly([(x, top), (x - half, base), (x + half, base)], col)


def cactus(c: C, x, y, h, col):
    c.rect(x - h * 0.09, y - h, x + h * 0.09, y, col, int(h * 0.09))
    c.rect(x - h * 0.34, y - h * 0.62, x - h * 0.2, y - h * 0.3, col, int(h * 0.07))
    c.rect(x - h * 0.34, y - h * 0.34, x - h * 0.05, y - h * 0.26, col)
    c.rect(x + h * 0.2, y - h * 0.72, x + h * 0.34, y - h * 0.4, col, int(h * 0.07))
    c.rect(x + h * 0.05, y - h * 0.44, x + h * 0.34, y - h * 0.36, col)


def sky(c: C, p, sun_xy):
    c.rect(0, 0, W, H, p["sky"])
    c.ell(sun_xy[0] - 90, sun_xy[1] - 90, sun_xy[0] + 90, sun_xy[1] + 90, p["sun"])


def draw_set(name: str, tod: str) -> Image.Image:
    p = PAL[tod]
    c = C(W, H)
    low = tod == "dusk"
    sky(c, p, (1500, 300 if not low else 520))
    g = STAGE[name]
    if name == "town":
        c.poly([(0, 640), (260, 520), (520, 520), (700, 640)], p["mesa"])
        c.poly([(1250, 640), (1480, 540), (1700, 540), (1920, 640)], p["mesa"])
        c.rect(0, 640, W, H, p["sand"])
        c.rect(0, g - 40, W, g + 40, tuple(max(0, v - 18) for v in p["sand"]))
        for x, wl, rf in ((140, 220, ROOF), (520, 260, (176, 120, 80)), (1160, 240, ROOF), (1560, 250, (176, 120, 80))):
            house(c, x, 700, wl, 150, tuple(min(255, v) for v in (p["wall"])), rf)
        for x in (420, 1010, 1460, 1840):
            cactus(c, x, 770, 170, CACT if not low else (70, 120, 80))
    elif name == "field":
        c.poly([(0, 600), (480, 480), (980, 590), (1460, 470), (1920, 580), (1920, 700), (0, 700)], p["far"])
        c.rect(0, 640, W, H, p["grass"])
        for k in range(9):
            y = 700 + k * 40
            c.poly([(0, y), (W, y - 30), (W, y + 4), (0, y + 34)], tuple(max(0, v - 22) for v in p["grass"]))
        house(c, 1380, 760, 300, 200, RED if not low else (150, 60, 56), (130, 70, 56))
        pine(c, 260, 740, 300, (60, 120, 72) if not low else (50, 90, 64))
        pine(c, 380, 756, 240, (60, 120, 72) if not low else (50, 90, 64))
        for x in range(80, 1000, 70):
            c.rect(x, 790, x + 10, 850, WOOD)
        c.rect(70, 806, 1010, 816, WOOD)
        c.rect(70, 830, 1010, 840, WOOD)
    elif name == "city":
        c.rect(0, 700, W, H, p["road"])
        c.rect(0, 960, W, 972, (230, 230, 220))
        x = -20
        k = 0
        while x < W:
            bw, bh = 150 + (k * 37) % 90, 300 + (k * 71) % 280
            col = p["building"] if k % 2 == 0 else p["building2"]
            c.rect(x, 700 - bh, x + bw, 700, col)
            for yy in range(700 - bh + 30, 680, 50):
                for xx in range(x + 20, x + bw - 30, 44):
                    c.rect(xx, yy, xx + 22, yy + 28, p["window"])
            x += bw + 14
            k += 1
    elif name == "harbour":
        c.rect(0, 560, W, 760, p["sea"])
        for k in range(12):
            c.rect((k * 190) % W, 600 + (k * 53) % 140, (k * 190) % W + 90, 608 + (k * 53) % 140, tuple(min(255, v + 30) for v in p["sea"]))
        c.rect(0, 760, W, H, p["sand"])
        c.rect(0, g - 30, W, H, WOOD)
        for x in range(0, W, 120):
            c.rect(x, g - 30, x + 6, H, DARKWOOD)
        c.poly([(1200, 640), (1700, 640), (1620, 740), (1280, 740)], (110, 70, 52))
        c.rect(1440, 380, 1452, 640, (90, 60, 44))
        c.poly([(1456, 400), (1640, 600), (1456, 600)], WHITE)
        c.poly([(1436, 430), (1300, 600), (1436, 600)], (236, 230, 214))
    else:   # room
        c.rect(0, 0, W, H, p["wall"])
        c.rect(0, 800, W, H, p["floor"])
        c.rect(120, 160, 560, 560, (96, 70, 52))
        c.rect(140, 180, 540, 540, p["sky"])
        c.rect(336, 180, 344, 540, (96, 70, 52))
        c.rect(140, 356, 540, 364, (96, 70, 52))
        c.rect(1380, 140, 1800, 760, DARKWOOD)
        for k in range(4):
            y = 180 + k * 150
            c.rect(1400, y, 1780, y + 120, (150, 110, 78))
            for j in range(9):
                c.rect(1412 + j * 40, y + 10, 1442 + j * 40, y + 118, [(176, 70, 66), (66, 110, 170), (80, 140, 90), (220, 180, 80)][(j + k) % 4])
        c.rect(700, 700, 1160, 730, WOOD)
        c.rect(724, 730, 744, 880, DARKWOOD)
        c.rect(1116, 730, 1136, 880, DARKWOOD)
    return c.done().convert("RGB")


def draw_prop(name: str) -> Image.Image:
    sizes = {"house": (340, 300), "tree": (220, 340), "cactus": (160, 280), "fence": (420, 150), "flag": (160, 320), "sign": (240, 320), "crate": (180, 160)}
    w, h = sizes[name]
    c = C(w, h)
    if name == "house":
        house(c, 20, h - 6, w - 40, 150, WALL, ROOF)
    elif name == "tree":
        c.rect(w / 2 - 14, h - 120, w / 2 + 14, h - 4, TRUNK)
        c.ell(20, 10, w - 20, h - 90, LEAF)
        c.ell(50, 60, w - 50, h - 60, (88, 156, 92))
    elif name == "cactus":
        cactus(c, w / 2, h - 4, 250, CACT)
    elif name == "fence":
        for x in range(10, w - 20, 70):
            c.rect(x, 20, x + 16, h - 4, WOOD)
        c.rect(0, 44, w, 60, WOOD)
        c.rect(0, 92, w, 108, WOOD)
    elif name == "flag":
        c.rect(26, 8, 36, h - 4, DARKWOOD)
        c.poly([(36, 14), (150, 40), (36, 120)], RED)
    elif name == "sign":
        c.rect(w / 2 - 8, 150, w / 2 + 8, h - 4, DARKWOOD)
        c.rect(14, 10, w - 14, 170, WOOD, 14)
        c.rect(30, 26, w - 30, 154, (244, 232, 200), 8)
    else:
        c.rect(6, 6, w - 6, h - 6, WOOD)
        c.rect(6, 6, w - 6, 34, DARKWOOD)
        c.rect(6, h - 34, w - 6, h - 6, DARKWOOD)
        c.rect(w / 2 - 8, 6, w / 2 + 8, h - 6, DARKWOOD)
    return c.done()


def draw_cast(role: str, pose: str, kit: str) -> Image.Image:
    hair, skin = KITS[kit]
    shirt = ROLES[role] + (255,)
    saved = dict(NB.P)
    try:
        NB.P.update(shirt=shirt, scarf=tuple(int(v * 0.72) for v in ROLES[role]) + (255,), hair=hair, skin=skin)
        body = NB.draw_body(pose)
        for name, im in (("eyes", NB.draw_eyes("open")), ("mouth", NB.draw_mouth("o" if pose == "surprise" else "closed"))):
            body.alpha_composite(im, tuple(NB.FACE_ORIGIN[name]))
    finally:
        NB.P.clear()
        NB.P.update(saved)
    return body


def png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False, compress_level=9)
    return buf.getvalue()


def build() -> Dict[str, bytes]:
    files: Dict[str, bytes] = {}
    meta: Dict = {"sets": {}, "cast": {}, "props": {}}

    def put(name: str, im: Image.Image, slot: dict, bbox: bool) -> None:
        b = png_bytes(im)
        files[name] = b
        slot.update({"file": name, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "size": list(im.size)})
        if bbox:
            slot["bbox"] = list(im.getchannel("A").getbbox())

    for s in SETS:
        meta["sets"][s] = {"ground_y": STAGE[s], "tod": {}}
        for t in TODS:
            slot: dict = {}
            put(f"set_{s}_{t}.png", draw_set(s, t), slot, False)
            meta["sets"][s]["tod"][t] = slot
    for role in ROLES:
        meta["cast"][role] = {}
        for pose in POSES:
            for kit in (KITS if pose == "idle" else ("a",)):
                slot = {}
                put(f"cast_{role}_{pose}_{kit}.png", draw_cast(role, pose, kit), slot, True)
                meta["cast"][role].setdefault(pose, {})[kit] = slot
    for pr in PROPS:
        slot = {}
        put(f"prop_{pr}.png", draw_prop(pr), slot, True)
        meta["props"][pr] = slot
    digest = hashlib.sha256("".join(hashlib.sha256(files[n]).hexdigest() for n in sorted(files)).encode()).hexdigest()
    manifest = {"asset_id": ASSET_ID, "version": 1, "canvas": [NB.CW, NB.CH], "feet_y": NB.FEET_Y, "pillow_version": PIL.__version__, "built_by": "explainer/cartoon/build_assets.py",
                "roles": list(ROLES), "poses": list(POSES), "kits": list(KITS), "layers_digest": digest, **meta}
    files["manifest.json"] = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    return files


def main(argv) -> int:
    files = build()
    if "--check" in argv:
        bad = [n for n, b in files.items() if not (OUT / n).is_file() or (OUT / n).read_bytes() != b]
        extra = sorted(p.name for p in OUT.glob("*") if p.name not in files) if OUT.exists() else []
        print(json.dumps({"files": len(files), "differ_or_missing": bad, "extra_on_disk": extra}, indent=1))
        return 0 if not bad and not extra else 1
    OUT.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (OUT / n).write_bytes(b)
    print(f"wrote {len(files)} files to {OUT}; manifest sha256 {hashlib.sha256(files['manifest.json']).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
