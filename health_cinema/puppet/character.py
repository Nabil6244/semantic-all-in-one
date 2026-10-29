"""Rig: assembles the cached part layers into one posed paper-cutout figure with a white cut-out outline."""
from __future__ import annotations
import math
from typing import Dict, Optional, Tuple
import numpy as np
from PIL import Image, ImageChops, ImageFilter

from . import actions as A

HR = 3.0            # part pixels per unit (parts are cached at this resolution)
OUTLINE = 6.2       # off-white paper edge, units (~5-6 px at 1080p for a 0.45-frame figure)
PAPER = (252, 246, 232)
FAR_TINT = (74, 46, 32)
sin, cos, rad = math.sin, math.cos, math.radians


def _rot(x, y, deg):
    l = rad(deg); return x * cos(l) - y * sin(l), x * sin(l) + y * cos(l)


def _make_noise():
    rng = np.random.default_rng(7)
    a = rng.normal(size=(800, 800)).astype(np.float32)
    for _ in range(2): a = (np.roll(a, 1, 0) + 2 * a + np.roll(a, -1, 0)) / 4; a = (np.roll(a, 1, 1) + 2 * a + np.roll(a, -1, 1)) / 4
    return a / (a.std() + 1e-6)


_NOISE = _make_noise()


def fit_height(frame_h: float, ground_y_frac: float, horizon_frac: float, ref_person_h_frac: Optional[float] = None) -> float:
    """Pixel height (sole to crown) a puppet should have when its feet stand at ground_y_frac (0..1 of the frame height, 0 = top).

    Perspective: a person's height is proportional to how far their feet are below the horizon line (horizon_frac, also 0..1 from the top).
    A person standing at 0.88 with the horizon at 0.48 comes out at ~0.47 of the frame (the default look: big enough to read as a character, never
    more than 0.54 or less than 0.34 of the frame unless ref_person_h_frac asks for it). ref_person_h_frac, when given, is the height fraction you want
    for a person standing 0.40 of the frame below the horizon (e.g. the scale of people already drawn in the still); distance then scales it.
    Use scale_for_height(character, px) to turn the result into the `scale` argument of render_character_frame."""
    depth = max(0.05, float(ground_y_frac) - float(horizon_frac))
    if ref_person_h_frac is None: frac = min(0.54, max(0.34, 0.47 * (depth / 0.40) ** 0.6))
    else: frac = min(0.66, max(0.05, 1.12 * float(ref_person_h_frac) * (depth / 0.40) ** 0.9))
    return frac * float(frame_h)


def scale_for_height(character: str, px_h: float) -> float:
    """render_character_frame scale that makes `character` px_h pixels tall (sole to crown, hat included roughly)."""
    from . import cast
    return float(px_h) / cast.get_rig(character).standing_h


class Rig:
    shadow = 1.0

    def __init__(self, name: str, spec: dict, parts: Dict[str, Image.Image]):
        self.name, self.spec, self.d, self.parts = name, spec, spec["dims"], parts
        self._sc: dict = {}
        d = self.d
        self.height = d["thigh"] + d["shin"] + d["foot_h"] + d["torso"] + d["neck"] + 2 * d["hr"] + 50
        self.standing_h = A.stand_h(d) + d["torso"] + d["neck"] + 2 * d["hr"] * 1.04      # units from sole to crown (hat adds a little)
        self._noise = _NOISE
        self._tight = {}
        for k, im in parts.items():          # parts are stored as a square centred on their pivot; keep only the painted box so rotation is cheap
            bb = im.getchannel("A").getbbox() or (0, 0, 2, 2); bb = (max(0, bb[0] - 2), max(0, bb[1] - 2), min(im.width, bb[2] + 2), min(im.height, bb[3] + 2))
            self._tight[k] = (im.crop(bb), im.width / 2 - bb[0], im.height / 2 - bb[1])

    def joints(self, pose: dict) -> dict:
        """Joint positions in the ground frame (units; x forward, y down, ground y = 0, anchor x = 0)."""
        p = {**A.BASE, **pose}; d = self.d
        heel, toe = self.spec.get("heel", 14), d["foot_len"] - self.spec.get("heel", 14)
        rel = {}
        for s_ in "ab":
            th, sh, ft = p["th" + s_], p["sh" + s_], p["ft" + s_]
            kx, ky = d["thigh"] * sin(rad(th)), d["thigh"] * cos(rad(th))
            ax, ay = kx + d["shin"] * sin(rad(sh)), ky + d["shin"] * cos(rad(sh))
            f = rad(ft)
            low = max(-px * sin(f) + d["foot_h"] * cos(f) for px in (-heel, toe))
            rel["knee_" + s_], rel["ankle_" + s_], rel["bottom_" + s_] = (kx, ky), (ax, ay), ay + low
        hh = p["hip_h"] if "hip_h" in p else max(rel["bottom_a"], rel["bottom_b"])
        hx = p["hip_x"]; hip = (hx, -hh)
        J = dict(hip=hip, hip_h=hh)
        sx, sy = _rot(4, -d["torso"] * d["sh_frac"], p["lean"]); J["shoulder"] = (hx + sx + p["sh_dx"], -hh + sy + p["sh_dy"])
        nx, ny = _rot(0, -d["torso"], p["lean"]); J["neck"] = (hx + nx, -hh + ny)
        for s_ in "ab":
            for k in ("knee", "ankle"): J[f"{k}_{s_}"] = (hx + rel[f"{k}_{s_}"][0], -hh + rel[f"{k}_{s_}"][1])
            J["bottom_" + s_] = -hh + rel["bottom_" + s_]
            u, f, h = p["ua" + s_], p["fa" + s_], p["ha" + s_]
            ex, ey = J["shoulder"][0] + d["uarm"] * sin(rad(u)), J["shoulder"][1] + d["uarm"] * cos(rad(u))
            wx, wy = ex + d["farm"] * sin(rad(f)), ey + d["farm"] * cos(rad(f))
            J["elbow_" + s_], J["wrist_" + s_] = (ex, ey), (wx, wy)
            J["grip_" + s_] = (wx + d["hand"] * 0.62 * sin(rad(f + h)), wy + d["hand"] * 0.62 * cos(rad(f + h)))
        return J

    def _img(self, name, far, q):
        key = (name, far, q)
        hit = self._sc.get(key)
        if hit is None:
            if len(self._sc) > 600: self._sc.clear()
            src, pvx, pvy = self._tight[name]
            if far:
                a = np.asarray(src, np.float32).copy()
                a[..., :3] = a[..., :3] * 0.66 + np.array(FAR_TINT, np.float32) * 0.34
                src = Image.fromarray(a.astype(np.uint8))
            f = q / HR
            im = src.resize((max(2, int(round(src.width * f))), max(2, int(round(src.height * f)))), Image.LANCZOS if f < 1 else Image.BICUBIC)
            hit = self._sc[key] = (im, pvx * im.width / src.width, pvy * im.height / src.height)
        return hit

    def draw(self, pose: dict, scale: float, facing: str = "right", tint=None) -> Tuple[Image.Image, Tuple[float, float]]:
        """tint: optional (r, g, b) multipliers (1.0 = neutral, e.g. (1.08, 1.0, 0.88) warm, (0.9, 1.0, 1.08) cool) or a scene light dict with a "tint" key;
        colours the inked figure fully and the paper border at half strength, so the sprite sits in the scene's light."""
        p = {**A.BASE, **pose}; J = self.joints(p); d = self.d
        sc = float(scale); q = max(0.05, round(sc / 0.004) * 0.004)
        X, top, bot = self.height * 0.8, self.height * 1.12, 60
        cw, ch = int(2 * X * sc) + 8, int((top + bot) * sc) + 8
        ox, oy = cw / 2, top * sc
        cv = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

        def blit(name, pt, ang=0.0, far=False, xs=1.0):
            im, pvx, pvy = self._img(name, far, q)
            if xs != 1.0:
                w0 = im.width; nw = max(2, int(w0 * abs(xs))); im = im.resize((nw, im.height), Image.BILINEAR); pvx = pvx * nw / w0
                if xs < 0: im = im.transpose(Image.FLIP_LEFT_RIGHT); pvx = nw - pvx
            if ang:
                w0, h0 = im.size; im = im.rotate(ang, resample=Image.BILINEAR, expand=True)
                vx, vy = pvx - w0 / 2, pvy - h0 / 2; th = rad(ang)
                pvx, pvy = im.width / 2 + vx * cos(th) + vy * sin(th), im.height / 2 - vx * sin(th) + vy * cos(th)
            x, y = int(round(ox + pt[0] * sc - pvx)), int(round(oy + pt[1] * sc - pvy))
            sx0, sy0 = max(0, -x), max(0, -y)
            sx1, sy1 = min(im.width, cw - x), min(im.height, ch - y)
            if sx1 > sx0 and sy1 > sy0: cv.alpha_composite(im.crop((sx0, sy0, sx1, sy1)), (x + sx0, y + sy0))

        def arm(s_, far):
            blit("uarm", J["shoulder"], p["ua" + s_], far); blit("farm", J["elbow_" + s_], p["fa" + s_], far)

        def hand(s_, far): blit("hand", J["wrist_" + s_], p["fa" + s_] + p["ha" + s_], far)

        def leg(s_, far):
            hp = J["hip"]; blit("thigh", hp, p["th" + s_], far); blit("shin", J["knee_" + s_], p["sh" + s_], far)
            blit("foot", J["ankle_" + s_], p["ft" + s_], far)

        prop = p.get("prop"); seat = p.get("seat")
        if seat: blit("prop_stool", (seat["x"], seat["y"]))
        for sw in self.spec.get("sway", []):
            if sw["carrier"] == "torso": lx, ly = _rot(*sw["local"], p["lean"]); pt = (J["hip"][0] + lx, J["hip"][1] + ly)
            else: lx, ly = _rot(*sw["local"], p["lean"] + p["head"]); pt = (J["neck"][0] + lx, J["neck"][1] + ly)
            blit(sw["part"], pt, p[sw["key"]])
        arm("a", True); hand("a", True); leg("a", True)
        blit("torso", J["hip"], -p["lean"], xs=p["torso_xs"])
        blit("head", J["neck"], -(p["lean"] + p["head"]), xs=p["head_xs"])
        leg("b", False)
        if prop and prop["mode"] == "at": blit("prop_" + prop["name"], (prop["x"], prop["y"]))
        blit("uarm", J["shoulder"], p["uab"]); blit("farm", J["elbow_b"], p["fab"])
        if prop and prop["mode"] == "hand":
            ang = p["fab"] + p["hab"] if prop.get("follow") else p.get("prop_rot", 0.2 * p["fab"])
            blit("prop_" + prop["name"], J["grip_b"], ang)
        hand("b", False)

        # off-white cut-out paper edge: irregular (slightly torn), fixed to the figure, with paper grain, a darker rim and a soft lift shadow
        bb = cv.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox() or (0, 0, 1, 1)
        class _B:  # bbox as min/max like the arrays used below
            pass
        ys = np.array([bb[1], bb[3] - 1]); xs_ = np.array([bb[0], bb[2] - 1])
        sh = float(p.get("shadow", self.shadow))
        m = int(math.ceil(OUTLINE * sc)) + 8 + (int(14 * sc) if sh > 0 else 0)
        ax, ay = ox, oy + 0.0
        x0 = max(0, min(xs_.min() if len(xs_) else 0, int(ax) - 1) - m); y0 = max(0, min(ys.min() if len(ys) else 0, int(ay) - 1) - m)
        x1 = min(cw, max(xs_.max() + 1 if len(xs_) else 1, int(ax) + 2) + m); y1 = min(ch, max(ys.max() + 1 if len(ys) else 1, int(ay) + 2) + m)
        ink = cv.crop((x0, y0, x1, y1)); W0, H0 = ink.size
        tmul = None
        if tint is not None:
            tt_ = tint.get("tint") if isinstance(tint, dict) else tint
            tmul = np.clip(np.asarray(tt_, np.float32).reshape(3), 0.4, 1.6)
            if np.allclose(tmul, 1.0, atol=0.003): tmul = None
        if tmul is not None:
            ia = np.asarray(ink, np.float32).copy(); ia[..., :3] = np.clip(ia[..., :3] * tmul, 0, 255); ink = Image.fromarray(ia.astype(np.uint8), "RGBA")
        al = ink.getchannel("A")
        r = max(1.2, OUTLINE * sc / 1.5)
        bl = np.asarray(al.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255
        # noise in figure units (anchor-fixed): coarse = torn edge, fine = paper fibre
        NN = self._noise; ux0, uy0 = (x0 - ox) / sc + 1000, (y0 - oy) / sc + 1000; ux1, uy1 = (x1 - ox) / sc + 1000, (y1 - oy) / sc + 1000
        def nz(cell):
            if cell < 1: bx = (0, 0, min(800, W0 * 0.8), min(800, H0 * 0.8))
            else:
                bx = (ux0 / cell, uy0 / cell, ux1 / cell, uy1 / cell)
                if bx[0] < 0 or bx[1] < 0 or bx[2] > 800 or bx[3] > 800: bx = (0, 0, min(800, (ux1 - ux0) / cell), min(800, (uy1 - uy0) / cell))
            return np.asarray(Image.fromarray(NN, "F").resize((W0, H0), Image.BILINEAR, box=bx), np.float32)
        nc, nf = nz(2.6), nz(0.5)
        edge_n = 0.7 * nc + 0.3 * nz(0.9)
        dil = np.clip((bl + 0.05 * edge_n - 0.075) * 10, 0, 1)
        grain = 1 + 0.028 * nf + 0.018 * nc
        rim = 0.92 + 0.08 * np.clip(bl * 2.2, 0, 1)
        paper = np.zeros(dil.shape + (4,), np.uint8)
        paper[..., :3] = np.clip(np.array(PAPER, np.float32) * (grain * rim)[..., None], 0, 255).astype(np.uint8); paper[..., 3] = (dil * 255).astype(np.uint8)
        if tmul is not None: paper[..., :3] = np.clip(paper[..., :3].astype(np.float32) * (1 + (tmul - 1) * 0.5), 0, 255).astype(np.uint8)
        # thin dark outer edge around the white border, so the sticker separates from light and dark pictures alike
        kr = max(1, int(round(1.5 * sc))); ring = Image.fromarray(paper[..., 3]).filter(ImageFilter.MaxFilter(2 * kr + 1))
        rl = Image.new("RGBA", ring.size, (40, 28, 20, 0)); rl.putalpha(ring.point(lambda v: int(v * 0.82)))
        out = Image.alpha_composite(Image.alpha_composite(rl, Image.fromarray(paper, "RGBA")), ink)
        if sh > 0:
            sa = ring.filter(ImageFilter.GaussianBlur(max(1.5, 4.5 * sc)))
            sa = ImageChops.offset(sa, int(round(6 * sc)), int(round(5 * sc)))
            lay = Image.new("RGBA", out.size, (34, 22, 14, 0)); lay.putalpha(sa.point(lambda v: int(v * 0.58 * sh)))
            out = Image.alpha_composite(lay, out)
        anchor = [ax - x0, ay - y0]
        sx_ = p["xscale"] * (-1 if facing == "left" else 1)
        sy_ = 1.0 - p["squash"]; wx_ = 1.0 + 0.6 * p["squash"]
        W, H = out.size
        nw, nh = max(2, int(round(W * abs(sx_) * wx_ if abs(sx_) > 0.02 else 2))), max(2, int(round(H * sy_)))
        if abs(sx_) < 0.1: nw = max(nw, int(W * 0.1))
        if (nw, nh) != (W, H): out = out.resize((nw, nh), Image.BILINEAR)
        fx, fy = nw / W, nh / H
        anchor = [anchor[0] * fx, anchor[1] * fy]
        if sx_ < 0: out = out.transpose(Image.FLIP_LEFT_RIGHT); anchor[0] = nw - anchor[0]
        anchor = (min(max(anchor[0], 0), out.width - 1), min(max(anchor[1], 0), out.height - 1))
        return out, anchor
