"""A 2D cut-out rig for a side-view four-legged animal picture (the reference's walking animals): the legs are found in
the picture, cut off at the hip / shoulder and swung from there, so the animal really steps instead of sliding like a
sticker.

    rig = Rig(picture)               # a side view facing right, transparent background
    frame = rig.pose(phase, gait)    # RGBA, same size as the picture (plus a margin), feet on the bottom line

Legs: the columns that still hold the body near the feet are the legs. Each one is cut from the belly line down. The
two legs nearest the head are the front pair, the others the hind pair. A pair that shows as one shape (the far leg
hidden behind the near one) gets a far copy, a little darker, drawn behind the body - the way 2D cut-out animation
does it. Each leg turns around its top on a gait clock:

    walk   hind near 0, front near 1/4, hind far 1/2, front far 3/4 of a cycle (the four-beat walk)
    run    the pairs together, front and hind half a cycle apart (a gallop-like bound)
    idle   a slow small sway (weight shifting), no stepping

The body rises a little twice per walk cycle (once per step) and the head nods with it.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

GAITS: Dict[str, Tuple[float, Dict[str, float]]] = {      # gait -> (swing degrees, phase offsets in cycles)
    "walk": (20.0, {"hind_near": 0.0, "front_near": 0.25, "hind_far": 0.5, "front_far": 0.75}),
    "run": (32.0, {"hind_near": 0.0, "hind_far": 0.08, "front_near": 0.5, "front_far": 0.58}),
    "idle": (3.0, {"hind_near": 0.0, "front_near": 0.5, "hind_far": 0.5, "front_far": 0.0}),
}
MARGIN = 0.25           # room around the picture for legs swinging past its edges


class Leg:
    def __init__(self, img: Image.Image, pivot: Tuple[float, float], role: str, far: bool):
        self.img, self.pivot, self.role, self.far = img, pivot, role, far
        self.lower: Optional[Image.Image] = None      # below the knee / hock: bends on its own joint
        self.knee: Tuple[float, float] = pivot
        self.cap: Tuple[Tuple[int, int, int, int], float] = ((0, 0, 0, 0), 0.0)    # the joint disc: colour, radius

    def split(self, knee_y: int) -> None:
        """Cut the leg at the knee row: the upper part swings from the hip, the lower part bends at the knee."""
        a = np.asarray(self.img).copy()
        ky = int(knee_y)
        lower = a.copy()
        lower[: ky - 2] = 0
        upper = a
        upper[ky + 2:] = 0
        self.img, self.lower = Image.fromarray(upper), Image.fromarray(lower)
        row = a[max(0, ky - 2): ky + 3]
        cols = np.where(row[..., 3].max(axis=0) > 128)[0]
        if len(cols):
            cx = float(cols.mean())
            px_ = row[:, cols][..., :4].reshape(-1, 4)
            px_ = px_[px_[:, 3] > 128]
            col = tuple(int(v) for v in np.median(px_, axis=0)) if len(px_) else (0, 0, 0, 255)
            self.knee = (cx, float(ky))
            self.cap = ((col[0], col[1], col[2], 255), min((cols.max() - cols.min()) / 2.0, a.shape[1] * 0.035))


class Rig:
    def __init__(self, picture: Image.Image):
        sp = picture.convert("RGBA")
        mx, my = int(sp.width * MARGIN), int(sp.height * MARGIN)
        self.canvas = (sp.width + 2 * mx, sp.height + 2 * my)
        self.offset = (mx, my)
        a = np.asarray(sp.getchannel("A")) > 90
        ys = np.where(a.any(axis=1))[0]
        self.ok = len(ys) > 0
        self.body = sp
        self.legs: List[Leg] = []
        self.feet_y = int(ys[-1]) if self.ok else sp.height
        if not self.ok:
            return
        top, bot = int(ys[0]), int(ys[-1])
        h = bot - top
        foot_band = a[int(bot - h * 0.22): bot + 1].any(axis=0)          # columns with a foot / lower leg
        runs: List[Tuple[int, int]] = []
        x = 0
        w = sp.width
        while x < w:
            if foot_band[x]:
                x0 = x
                while x < w and foot_band[x]:
                    x += 1
                if x - x0 >= max(4, w * 0.015):
                    runs.append((x0, x))
            x += 1
        if 2 <= len(runs) < 4:                                            # a near + far pair drawn overlapping: split it
            low = a[int(bot - h * 0.1): bot + 1].sum(axis=0)              # at the notch between the two paws
            widest = max(r[1] - r[0] for r in runs)
            split: List[Tuple[int, int]] = []
            for x0, x1 in runs:
                wd = x1 - x0
                if wd >= widest * 0.8 and wd > w * 0.05:
                    m0, m1 = x0 + int(wd * 0.3), x1 - int(wd * 0.3)
                    seg = low[m0:m1]
                    if len(seg) and seg.min() < 0.45 * low[x0:x1].max():
                        cut_x = m0 + int(seg.argmin())
                        split += [(x0, cut_x), (cut_x, x1)]
                        continue
                split.append((x0, x1))
            runs = split
        if len(runs) < 2:
            self.ok = False
            return
        # the belly: the torso's underside, where the empty gap between the hind and the front legs closes
        gaps = [(runs[i][1], runs[i + 1][0]) for i in range(len(runs) - 1)]
        g0, g1 = max(gaps, key=lambda g: g[1] - g[0])
        cols = slice(g0 + (g1 - g0) // 4, g1 - (g1 - g0) // 4 + 1)
        belly = bot
        for y in range(bot, top, -1):
            if a[y, cols].mean() > 0.9:
                belly = y
                break
        belly = int(min(belly + h * 0.02, bot - h * 0.2))
        self.belly = belly

        arr = np.asarray(sp).copy()
        body = arr.copy()
        cnt = a[top:belly].sum(axis=0).astype(float)                      # front / hind: either side of the body's
        mid_x = float((cnt * np.arange(len(cnt))).sum() / max(1.0, cnt.sum()))   # centre of mass above the belly
        bounds = []
        for i, (x0, x1) in enumerate(runs):                               # each leg owns the columns up to its neighbours
            pad = int((x1 - x0) * 0.45)                                   # the thigh is wider than the foot
            lo = max((runs[i - 1][1] + x0) // 2 if i > 0 else 0, x0 - pad)
            hi = min((x1 + runs[i + 1][0]) // 2 if i + 1 < len(runs) else w, x1 + pad)
            bounds.append((lo, hi, (x0 + x1) / 2))
        front = [b for b in bounds if b[2] >= mid_x]
        hind = [b for b in bounds if b[2] < mid_x]
        if not front or not hind:
            self.ok = False
            return
        cut = int(belly - h * 0.06)                                       # an overlap into the body: no gap at the hip
        ramp = np.ones((bot + 1 - cut, 1), dtype=np.float32)              # the leg fades in over the overlap: no seam
        n_over = max(1, belly - cut)
        ramp[:n_over, 0] = np.linspace(0.0, 1.0, n_over)                 # the top melts into the body

        def leg_part(lo: int, hi: int) -> np.ndarray:
            leg = np.zeros_like(arr)
            leg[cut: bot + 1, lo:hi] = arr[cut: bot + 1, lo:hi]
            leg[cut: bot + 1, lo:hi, 3] = (leg[cut: bot + 1, lo:hi, 3].astype(np.float32) * ramp).astype(np.uint8)
            return leg
        for group, name in ((hind, "hind"), (front, "front")):
            group = sorted(group, key=lambda b: b[2])[-2:] if name == "hind" else sorted(group, key=lambda b: b[2])[:2]
            for j, (lo, hi, cx) in enumerate(group):
                leg = leg_part(lo, hi)
                body[belly: bot + 1, lo:hi, 3] = 0                        # the body keeps only what is above the belly
                img = Image.fromarray(leg)
                far = j == 0 and len(group) == 2 and name == "front" or (j == 1 and len(group) == 2 and name == "hind")
                self.legs.append(Leg(img, (cx, belly), f"{name}_{'far' if far else 'near'}", far))
            if len(group) == 1:                                           # one shape for the pair: a far copy behind
                lo, hi, cx = group[0]
                leg = leg_part(lo, hi)
                dark = ImageEnhance.Brightness(Image.fromarray(leg)).enhance(0.72)
                self.legs.append(Leg(dark, (cx, belly), f"{name}_far", True))
        knee_y = int(belly + (bot - belly) * 0.48)
        for lg in self.legs:
            lg.split(knee_y)
        # head and tail: peeled off the body with a soft edge, so they can nod / sway without a seam
        self.head = self.tail = None
        fronts = [lg.pivot[0] for lg in self.legs if lg.role.startswith("front")]
        hinds = [lg.pivot[0] for lg in self.legs if lg.role.startswith("hind")]
        cols = a[top:belly].sum(axis=0).astype(float)
        torso_h = cols.max() if cols.size else 1.0
        xs_body = np.where(cols > torso_h * 0.45)[0]
        band = max(4, int(w * 0.05))
        xx = np.arange(w)[None, :].astype(np.float32)
        if fronts and len(xs_body):
            xh = max(fronts) + w * 0.05                                    # just in front of the shoulder
            m = np.clip((xx - xh) / band, 0.0, 1.0)
            m = np.repeat(m, sp.height, axis=0)
            m[belly:, :] = 0.0                                             # never the legs
            ys_h = np.where(a[:, min(w - 1, int(xh))])[0]
            pivot_y = float(ys_h.mean()) if len(ys_h) else float(top + h * 0.3)
            self.head = (self._peel(body, m), (xh, pivot_y))
        if hinds and len(xs_body):
            xt = float(xs_body.min()) + w * 0.03                           # where the rump ends and the tail starts
            m = np.clip((xt - xx) / band, 0.0, 1.0)
            m = np.repeat(m, sp.height, axis=0)
            ys_t = np.where(a[:, max(0, int(xt))])[0]
            root_y = float(ys_t.min()) + h * 0.06 if len(ys_t) else float(top)
            self.tail = (self._peel(body, m), (xt, root_y))
        self.body = Image.fromarray(body)

    @staticmethod
    def _peel(body: np.ndarray, m: np.ndarray) -> Image.Image:
        """Move the masked share of the body's pixels into their own layer (the body keeps the rest)."""
        part = body.copy()
        part[..., 3] = (body[..., 3].astype(np.float32) * m).astype(np.uint8)
        body[..., 3] = (body[..., 3].astype(np.float32) * (1.0 - m)).astype(np.uint8)
        return Image.fromarray(part)

    def pose(self, phase: float, gait: str = "walk") -> Image.Image:
        """The animal at `phase` (cycles, any real number) of its gait, on a canvas MARGIN larger than the picture."""
        out = Image.new("RGBA", self.canvas, (0, 0, 0, 0))
        mx, my = self.offset
        if not self.ok:
            out.alpha_composite(self.body, (mx, my))
            return out
        swing, offs = GAITS.get(gait, GAITS["walk"])
        bob = -abs(math.sin(2 * math.pi * phase)) * self.body.height * (0.012 if gait == "walk" else 0.03 if gait == "run" else 0)
        if gait == "idle":
            bob = math.sin(2 * math.pi * phase) * self.body.height * 0.004
        lift = int(round(bob))

        bend_amp = {"walk": 38.0, "run": 62.0}.get(gait, 0.0)

        def draw_leg(lg: Leg) -> None:
            ph = 2 * math.pi * (phase + offs.get(lg.role, 0.0))
            ang = swing * math.sin(ph)
            if gait == "run" and lg.role.startswith("front"):
                ang = -ang                                                # a bound: front legs reach while hind push
            lift = max(0.0, math.cos(ph)) if gait != "run" or not lg.role.startswith("front") else max(0.0, -math.cos(ph))
            bend = -bend_amp * lift                                       # the lower leg folds back while it swings forward
            px, py = lg.pivot
            out.alpha_composite(lg.img.rotate(ang, resample=Image.BICUBIC, center=(px, py)), (mx, my + lift_px))
            if lg.lower is None:
                return
            kx, ky = lg.knee                                              # where the knee went with the thigh
            r = math.radians(-ang)
            nkx = px + (kx - px) * math.cos(r) - (ky - py) * math.sin(r)
            nky = py + (kx - px) * math.sin(r) + (ky - py) * math.cos(r)
            col, rad = lg.cap
            if rad > 1:                                                   # the joint: a disc of the leg's colour, no gap
                cap = Image.new("RGBA", out.size, (0, 0, 0, 0))
                ImageDraw.Draw(cap).ellipse((mx + nkx - rad, my + lift_px + nky - rad, mx + nkx + rad, my + lift_px + nky + rad),
                                            fill=col)
                out.alpha_composite(cap)
            low = lg.lower.rotate(ang, resample=Image.BICUBIC, center=(px, py))
            low = low.rotate(bend, resample=Image.BICUBIC, center=(nkx, nky))
            out.alpha_composite(low, (mx, my + lift_px))

        lift_px = lift
        for lg in sorted(self.legs, key=lambda x: not x.far):            # far legs, then near legs, all under the body:
            draw_leg(lg)                                                   # the body hides each leg's top, so no seam
        tau = 2 * math.pi
        if self.tail is not None:                                          # the tail sways with the steps
            img, (tx, ty) = self.tail
            amp = {"walk": 7.0, "run": 12.0}.get(gait, 4.0)
            ang = amp * math.sin(tau * (phase if gait != "idle" else phase * 0.5) + 1.3)
            out.alpha_composite(img.rotate(ang, resample=Image.BICUBIC, center=(tx, ty)), (mx, my + lift))
        out.alpha_composite(self.body, (mx, my + lift))
        if self.head is not None:                                          # the head nods twice a stride
            img, (hx, hy) = self.head
            amp = {"walk": 2.6, "run": 4.0}.get(gait, 1.5)
            ang = -amp * math.sin(tau * phase * (2 if gait != "idle" else 0.4) + 0.6)
            out.alpha_composite(img.rotate(ang, resample=Image.BICUBIC, center=(hx, hy)), (mx, my + lift))
        return out

    @property
    def leg_len(self) -> float:
        return float(self.feet_y - getattr(self, "belly", self.feet_y))

    @property
    def feet(self) -> int:
        """The feet line on the pose canvas."""
        return self.offset[1] + self.feet_y


@lru_cache(maxsize=32)
def rig_for(name: str, width: int, flat: bool = True) -> Rig:
    """The rig of a library animal (ocean/art_flow.py side view) at a width, facing right."""
    from . import animals as A
    return Rig(A.draw(name, width, 0, face="right", flat=flat))


@lru_cache(maxsize=32)
def rig_vector(name: str, width: int) -> Optional[Rig]:
    """The rig of the library's flat vector picture (ocean/art_flow.py pose "vector", the reference channel's look),
    or None when that picture is not made yet."""
    from . import art_flow as AF
    p = AF.path(name, "vector")
    if p is None:
        return None
    im = Image.open(p).convert("RGBA")
    im = im.resize((int(width), max(1, int(im.height * width / im.width))), Image.LANCZOS)
    rg = Rig(im)
    return rg if rg.ok else None
