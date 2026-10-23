"""ONE-TIME asset builder for the Explainer narrator ("explorer": round head, tuft of hair, neckerchief). Run by hand, never during a render:

    python3 -B explainer/narrator/build_assets.py            # writes explainer/assets/narrator/ (PNG layers + manifest.json)
    python3 -B explainer/narrator/build_assets.py --check    # rebuilds in memory, compares bytes with the files on disk, writes nothing

Everything about the character's look is in PARAMS (colours, proportions); the pose functions only place arms. Layers are drawn at 4x and reduced with
LANCZOS, saved with fixed PNG settings, so a rebuild with the same Pillow gives identical bytes (the manifest records the Pillow version for information).
The character is an original design: it is deliberately not the reference's figure (no hat, no spear)."""

from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import PIL
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "assets" / "narrator"
ASSET_ID = "narrator_explorer_v1"
CW, CH = 440, 560                 # canvas in design pixels = delivered pixels at scale 1.0
SS = 4
FEET_Y = 548
HEAD = (220, 150)
POSES = ("idle", "point", "surprise", "think", "shrug", "explain")
EYES = ("open", "blink", "happy")
MOUTHS = ("closed", "open", "wide", "o")

PARAMS = {
    "ink": (38, 38, 40, 255), "line": 6,
    "skin": (250, 222, 190, 255), "hair": (86, 56, 36, 255), "shirt": (70, 150, 160, 255), "pants": (96, 84, 120, 255), "shoe": (120, 80, 50, 255),
    "scarf": (212, 70, 66, 255), "cheek": (240, 150, 140, 255), "eye_white": (255, 255, 255, 255), "mouth_in": (150, 40, 50, 255), "tongue": (236, 120, 130, 255),
    "head_r": 92, "arm_w": 24, "hand_r": 17,
}
P = PARAMS


class Canvas:
    """Draws in design units on a 4x RGBA surface."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def pt(self, p):
        return (p[0] * SS, p[1] * SS)

    def ellipse(self, box, fill, outline=True, width=None):
        x0, y0, x1, y1 = box
        self.d.ellipse([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=fill, outline=P["ink"] if outline else None, width=int((width or P["line"]) * SS) if outline else 0)

    def circle(self, c, r, fill, outline=True, width=None):
        self.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill, outline, width)

    def poly(self, pts, fill, outline=True, width=None):
        q = [self.pt(p) for p in pts]
        self.d.polygon(q, fill=fill)
        if outline:
            self.d.line(q + [q[0]], fill=P["ink"], width=int((width or P["line"]) * SS), joint="curve")
            for x, y in q:
                r = (width or P["line"]) * SS / 2
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=P["ink"])

    def rrect(self, box, radius, fill, outline=True):
        x0, y0, x1, y1 = box
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=radius * SS, fill=fill, outline=P["ink"] if outline else None, width=P["line"] * SS if outline else 0)

    def stroke(self, pts, width, color):
        q = [self.pt(p) for p in pts]
        self.d.line(q, fill=color, width=int(width * SS), joint="curve")
        r = width * SS / 2
        for x, y in (q[0], q[-1]):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    def arc(self, box, a0, a1, width, color):
        x0, y0, x1, y1 = box
        self.d.arc([x0 * SS, y0 * SS, x1 * SS, y1 * SS], a0, a1, fill=color, width=int(width * SS))

    def done(self) -> Image.Image:
        return self.im.resize((self.w, self.h), Image.LANCZOS)


def arm(c: Canvas, pts: List[Tuple[float, float]], hand: Tuple[float, float], finger: Tuple[float, float] = None):
    c.stroke(pts, P["arm_w"] + 2 * P["line"], P["ink"])
    c.stroke(pts, P["arm_w"], P["shirt"])
    if finger:
        c.stroke([hand, finger], 13 + 2 * 4, P["ink"])
        c.stroke([hand, finger], 13, P["skin"])
    c.circle(hand, P["hand_r"], P["skin"])


def leaf(c: Canvas, cx, cy, length, width, angle_deg):
    a = math.radians(angle_deg)
    ux, uy = math.sin(a), -math.cos(a)
    nx, ny = -uy, ux
    tip = (cx + ux * length, cy + uy * length)
    pts = [(cx + nx * width / 2, cy + ny * width / 2), (cx + ux * length * 0.55 + nx * width * 0.62, cy + uy * length * 0.55 + ny * width * 0.62), tip,
           (cx + ux * length * 0.55 - nx * width * 0.62, cy + uy * length * 0.55 - ny * width * 0.62), (cx - nx * width / 2, cy - ny * width / 2)]
    c.poly(pts, P["hair"], True, 5)


POSE_ARMS = {   # (left arm pts, left hand, left finger), (right arm pts, right hand, right finger); "left"/"right" are the VIEWER's left and right
    "idle": (([(160, 266), (130, 332), (128, 384)], (128, 392), None), ([(280, 266), (310, 332), (312, 384)], (312, 392), None)),
    "point": (([(160, 266), (122, 322), (160, 350)], (166, 354), None), ([(280, 266), (340, 258), (388, 250)], (394, 250), (426, 248))),
    "surprise": (([(160, 266), (114, 206), (98, 136)], (96, 126), None), ([(280, 266), (326, 206), (342, 136)], (344, 126), None)),
    "think": (([(160, 266), (148, 340), (226, 334)], (234, 334), None), ([(280, 266), (322, 304), (268, 244)], (258, 236), None)),
    "shrug": (([(160, 266), (104, 322), (94, 262)], (92, 250), None), ([(280, 266), (336, 322), (346, 262)], (348, 250), None)),
    "explain": (([(160, 266), (122, 322), (160, 350)], (166, 354), None), ([(280, 266), (344, 296), (392, 268)], (398, 262), (420, 244))),
}


def draw_body(pose: str) -> Image.Image:
    c = Canvas(CW, CH)
    # legs and shoes
    c.rrect((166, 380, 214, 538), 18, P["pants"])
    c.rrect((226, 380, 274, 538), 18, P["pants"])
    c.ellipse((142, 524, 222, FEET_Y), P["shoe"])
    c.ellipse((218, 524, 298, FEET_Y), P["shoe"])
    # torso
    c.rrect((152, 232, 288, 408), 46, P["shirt"])
    c.d.line([(160 * SS, 392 * SS), (280 * SS, 392 * SS)], fill=P["ink"], width=5 * SS)
    # arms behind the scarf and head
    (lp, lh, lf), (rp, rh, rf) = POSE_ARMS[pose]
    arm(c, lp, lh, lf)
    if pose != "think":
        arm(c, rp, rh, rf)
    # neckerchief
    c.poly([(168, 228), (272, 228), (220, 306)], P["scarf"])
    c.circle((220, 236), 15, P["scarf"])
    # head (face features are separate layers)
    c.circle(HEAD, P["head_r"], P["skin"], True, 7)
    for cx in (HEAD[0] - 56, HEAD[0] + 56):
        c.ellipse((cx - 17, 172, cx + 17, 190), P["cheek"], False)
    if pose == "think":                      # the hand at the chin is in front of the head
        arm(c, [(280, 266), (330, 300), (276, 262)], (254, 238), None)
    # tuft of hair
    leaf(c, 214, 70, 52, 26, -22)
    leaf(c, 226, 66, 62, 28, 4)
    leaf(c, 238, 70, 50, 24, 28)
    return c.done()


def draw_eyes(state: str) -> Image.Image:
    c = Canvas(200, 70)
    for cx in (60, 140):
        cy = 34
        if state == "open":
            c.ellipse((cx - 17, cy - 21, cx + 17, cy + 21), P["eye_white"], True, 5)
            c.circle((cx + 5, cy + 2), 9, P["ink"], False)
            c.circle((cx + 9, cy - 3), 3.2, P["eye_white"], False)
        elif state == "blink":
            c.arc((cx - 18, cy - 14, cx + 18, cy + 8), 20, 160, 6, P["ink"])
        else:   # happy: arcs that curve up
            c.arc((cx - 18, cy - 4, cx + 18, cy + 22), 200, 340, 6, P["ink"])
    return c.done()


def draw_mouth(state: str) -> Image.Image:
    c = Canvas(120, 70)
    cx, cy = 60, 26
    if state == "closed":
        c.arc((cx - 26, cy - 12, cx + 26, cy + 14), 25, 155, 6, P["ink"])
    elif state == "open":
        c.ellipse((cx - 22, cy - 6, cx + 22, cy + 24), P["mouth_in"], True, 5)
        c.ellipse((cx - 11, cy + 10, cx + 11, cy + 22), P["tongue"], False)
    elif state == "wide":
        c.ellipse((cx - 30, cy - 8, cx + 30, cy + 36), P["mouth_in"], True, 5)
        c.ellipse((cx - 15, cy + 18, cx + 15, cy + 33), P["tongue"], False)
    else:   # o
        c.ellipse((cx - 13, cy - 6, cx + 13, cy + 24), P["mouth_in"], True, 5)
    return c.done()


FACE_ORIGIN = {"eyes": (HEAD[0] - 100, 112), "mouth": (HEAD[0] - 60, 170)}


def png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False, compress_level=9)
    return buf.getvalue()


def build() -> Dict[str, bytes]:
    files: Dict[str, bytes] = {}
    meta = {"poses": {}, "eyes": {}, "mouths": {}}
    for pose in POSES:
        im = draw_body(pose)
        name = f"body_{pose}.png"
        files[name] = png_bytes(im)
        meta["poses"][pose] = {"file": name, "bbox": list(im.getchannel("A").getbbox())}
    for st in EYES:
        im = draw_eyes(st)
        name = f"eyes_{st}.png"
        files[name] = png_bytes(im)
        meta["eyes"][st] = {"file": name, "origin": list(FACE_ORIGIN["eyes"])}
    for st in MOUTHS:
        im = draw_mouth(st)
        name = f"mouth_{st}.png"
        files[name] = png_bytes(im)
        meta["mouths"][st] = {"file": name, "origin": list(FACE_ORIGIN["mouth"])}
    for group in ("poses", "eyes", "mouths"):
        for st, m in meta[group].items():
            b = files[m["file"]]
            m["sha256"], m["bytes"] = hashlib.sha256(b).hexdigest(), len(b)
    allb = [b for b in (hashlib.sha256(files[n]).hexdigest() for n in sorted(files))]
    manifest = {"asset_id": ASSET_ID, "version": 1, "canvas": [CW, CH], "feet_y": FEET_Y, "head_center": list(HEAD), "design_height_px": FEET_Y - min(m["bbox"][1] for m in meta["poses"].values()),
                "pillow_version": PIL.__version__, "built_by": "explainer/narrator/build_assets.py", "params": {k: v for k, v in PARAMS.items()}, **meta,
                "layers_digest": hashlib.sha256("".join(allb).encode()).hexdigest()}
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
