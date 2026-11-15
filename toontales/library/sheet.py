"""Contact sheets for the Toon Tales library: every static pose (each character) + every action as a 5-frame strip.

Run: blender -b --factory-startup --python toontales/library/sheet.py -- <out dir>
Then: python3 toontales/library/sheet.py --compose <out dir>   (PIL, outside Blender)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TT = HERE.parent
SAMPLES = [0.04, 0.3, 0.5, 0.72, 0.99]
MOVE_PARAMS = {"walk": {"to": [1.0, 0]}, "run": {"to": [1.4, 0]}, "sneak_walk": {"to": [0.8, 0]}}


def render_all(out):
    import bpy  # noqa: F401
    sys.path[:0] = [str(TT / "cast"), str(HERE)]
    import actions as A
    import puppet
    out.mkdir(parents=True, exist_ok=True)
    cast = json.loads((TT / "cast" / "cast.json").read_text())["characters"]
    cam = puppet.spike_scene()
    chars = [puppet.build(c, TT / "build" / "faces", out, at=(i * 50.0, 0, 0)) for i, c in enumerate(cast)]
    from mathutils import Vector

    def solo(ch):
        """Stand this character on the backdrop at the origin, park the others far away."""
        for i, o in enumerate(chars):
            o["at"] = Vector((0, 0, 0)) if o is ch else Vector((50.0 * (i + 1), 0, 0))
            puppet.apply_state(o, A.pose("idle"))

    for ch in chars:
        solo(ch)
        h = ch["cfg"]["height"]
        x = 0.0
        for name in A.POSES:
            puppet.apply_state(ch, A.pose(name))
            puppet.aim(cam, (x, 0, h * 0.5), 3.4 * h / 1.8 + 0.7, yaw=10, pitch=3, lens=40)
            puppet.render(out / f"pose_{ch['cfg']['id']}_{name}.png", 300, 470)
    ch = chars[0]
    solo(ch)
    m = puppet.metrics(ch)
    for name, (fn, dur, moves, about) in A.ACTIONS.items():
        if name in A.HOLDS:
            continue
        p = MOVE_PARAMS.get(name, {})
        mid = p.get("to", [0, 0])[0] / 2
        for j, f in enumerate(SAMPLES):
            puppet.apply_state(ch, A.state_at(name, dur * f, dur, m, p))
            low = name == "fall"
            puppet.aim(cam, (mid + (0.75 if low else 0), 0, 0.7 if low else 0.95),
                       (5.6 if low else 4.3) + abs(mid) * 1.6, yaw=8, pitch=4, lens=40)
            puppet.render(out / f"act_{name}_{j}.png", 300, 400)
    print("SHEET RENDERS ->", out)


def compose(out):
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(HERE))
    import actions as A
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    cast = [c["id"] for c in json.loads((TT / "cast" / "cast.json").read_text())["characters"]]
    names = list(A.POSES)
    cw, chh, cols = 270, 423, 12
    rows_per = -(-len(names) // cols)
    im = Image.new("RGB", (cw * cols, (chh + 34) * rows_per * len(cast)), (30, 26, 24))
    d = ImageDraw.Draw(im)
    for ci, cid in enumerate(cast):
        for i, n in enumerate(names):
            r, c = divmod(i, cols)
            y = (ci * rows_per + r) * (chh + 34)
            im.paste(Image.open(out / f"pose_{cid}_{n}.png").convert("RGB").resize((cw, chh)), (c * cw, y + 34))
            d.text((c * cw + 8, y + 4), f"{cid} · {n}", fill=(240, 228, 210), font=font)
    im.save(TT.parent / "out" / "toontales_step3_poses.jpg", quality=88)
    acts = [n for n in A.ACTIONS if n not in A.HOLDS]
    fw, fh, lab = 216, 288, 34
    half = -(-len(acts) // 2)
    strip_w = fw * len(SAMPLES)
    im = Image.new("RGB", (strip_w * 2 + 24, (fh + lab) * half), (30, 26, 24))
    d = ImageDraw.Draw(im)
    for i, n in enumerate(acts):
        col, r = divmod(i, half)
        x0, y0 = col * (strip_w + 24), r * (fh + lab)
        d.text((x0 + 8, y0 + 4), f"{n} — {A.ACTIONS[n][3]}", fill=(240, 228, 210), font=font)
        for j in range(len(SAMPLES)):
            im.paste(Image.open(out / f"act_{n}_{j}.png").convert("RGB").resize((fw, fh)), (x0 + j * fw, y0 + lab))
    im.save(TT.parent / "out" / "toontales_step3_actions.jpg", quality=86)
    print("composed")


if __name__ == "__main__":
    if "--compose" in sys.argv:
        compose(Path(sys.argv[sys.argv.index("--compose") + 1]))
    else:
        render_all(Path(sys.argv[sys.argv.index("--") + 1]))
