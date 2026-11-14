"""Code animation for Ocean beat mode (the reference's 2D cut-out animation, no video credits): a beat whose picture is an
animal or person DOING something is made by Flow as a cut-out on green (ocean/beats.py act_prompt), and acted here on a
plain set with a still camera, the way the reference's illustrated animals walk, swim, lunge and turn:

    classify(prompt) -> action | None     None = a diagram / cutaway / idea picture (stays a full illustration)
    setting(prompt, text, land) -> set    the plain set behind it (ocean/backdrop.py sets)
    animate(src, dst, seconds, action, set_name, facing, seed) -> dst      a 25 fps mp4 of the act

Actions
    walk / run      the cut-out crosses part of the frame; legs found under the belly swing in a gait (front and back pairs
                    opposite), the body bobs with each step; run is faster with longer swings
    swim            a travelling body wave, stronger towards the tail, while it glides
    attack          a crouch, a fast lunge forward, then a struggle shake with dust kicked up (land)
    approach        it grows towards the camera (turning to face you / coming closer)
    flee            it turns and runs out of frame
    fall            it tips over and settles (collapse, lying limp)
    idle            breathing (a slow 1-2 % swell) and a small drift: never a frozen still
The cut-out stands on the set's ground line with a soft contact shadow (land) or floats mid-water (sea).
"""

from __future__ import annotations

import math
import random
import re
import subprocess
from typing import Any, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FPS = 25
ACTIONS = [  # (pattern, action) first match wins
    (r"\b(collaps\w*|falls?|fell|lying limp|drops? dead|keels? over|passes out|unconscious)\b", "fall"),
    (r"\b(flee\w*|fled|runs? away|running away|escap\w*|retreat\w*|walks? away|walking away|backing away|steps? backward\w*)\b", "flee"),
    (r"\b(lung\w*|leap\w*|pounc\w*|attack\w*|bit(?:e|es|ing)|strik\w*|swip\w*|grab\w*|clamp\w*|claw\w*|latch\w*|wrestl\w*|fight\w*|"
     r"knock\w*|pull\w* down|gor\w*|charg\w*|snap\w*|chew\w*|eating|eats|tear\w*|crack\w*|kick\w*)\b", "attack"),
    (r"\b(toward\w* the camera|towards? (?:us|you|the viewer)|approach\w*|coming closer|face[- ]to[- ]face|staring (?:straight )?(?:up|at)|"
     r"looks? (?:up|down) at|turn\w* to face)\b", "approach"),
    (r"\b(swim\w*|swam|glid\w*|div(?:e|es|ing))\b", "swim"),
    (r"\b(sprint\w*|run(?:s|ning)?|ran|chas\w*|rac\w*|gallop\w*|dash\w*|full speed)\b", "run"),
    (r"\b(walk\w*|trot\w*|stroll\w*|wander\w*|patrol\w*|cross\w*|limp\w*|step\w*|prowl\w*|stalk\w*|climb\w*|dig\w*|hik\w*)\b", "walk"),
]
_ACTIONS = [(re.compile(p, re.I), a) for p, a in ACTIONS]
NOT_ACTOR = re.compile(r"\b(close-up|closeup|top-down|view from below|from directly above|cutaway|cut-away|cross-section|diagram|x-ray|chart|molecul\w*|dna|skeleton|anatomical|medical illustration|"
                       r"scientific illustration|split image|comparison|side by side|lineup|line-up|timeline|family tree|receipt|bill|"
                       r"magnets?|gauge|chalkboard|monitor|screen|stock market|tablet|platter|first-aid|map|lungs|nerves?|receptor|"
                       r"amino|conceptual|close-up of (?:a |the )?(?:lion'?s?|badger'?s?|honey badger'?s?)? ?(?:eye|teeth|tooth|paw|claws?|"
                       r"skin|nose|mouth|canine))\b", re.I)
SETTINGS = [  # (pattern, set) for the plain set behind an actor
    (r"\b(underground|burrow|den|tunnel\w*|beneath the ground)\b", "burrow"),
    (r"\b(night|moonlit|moonlight|dark blue|after dark|glowing eyes)\b", "savanna_night"),
    (r"\b(underwater|ocean|sea|reef|deep water|swimming)\b", "open_water"),
    (r"\b(snow|on the ice|sea ice|arctic)\b", "ice_plain"),
    (r"\b(lab|laboratory|room|desk|studio|plain background|dark background|black background)\b", "studio"),
]
_SETTINGS = [(re.compile(p, re.I), s) for p, s in SETTINGS]


def classify(prompt: str) -> Optional[str]:
    """The action of an actor beat, or None when the picture is a diagram / cutaway / idea (kept as a full illustration)."""
    p = str(prompt or "")
    if NOT_ACTOR.search(p):
        return None
    for rx, a in _ACTIONS:
        if rx.search(p):
            return a
    return "idle"


def setting(prompt: str, text: str = "", land: bool = True) -> str:
    for rx, s in _SETTINGS:
        if rx.search(prompt or ""):
            return s if land or s not in ("savanna_night",) else "dark"
    return "savanna" if land else "open_water"


# ---------------------------------------------------------------------------------------------------------------- the set

def _set_image(set_name: str, w: int, h: int) -> Tuple[Image.Image, float, bool]:
    """(background, ground line y as a fraction or 0 for water, land?)"""
    from . import backdrop as B
    if set_name == "studio":
        im = B._vgrad(w, h, [(0.0, (22, 34, 46, 255)), (0.7, (12, 20, 28, 255)), (1.0, (6, 10, 14, 255))])
        return B._vignette(im, 170), 0.84, True
    if set_name == "stage_dark":                      # the reference's focus set: warm charcoal, a soft light behind the
        im = B._vgrad(w, h, [(0.0, (14, 13, 12, 255)), (0.55, (26, 23, 20, 255)), (0.78, (20, 18, 16, 255)),
                             (1.0, (8, 8, 8, 255))])     # animal, a faint floor
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((w * 0.2, h * 0.12, w * 0.8, h * 0.92), fill=(70, 60, 50, 70))
        im = im.convert("RGBA")
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(w * 0.08)))
        return B._vignette(im, 180), 0.8, True
    if set_name == "ice_plain":
        im = B._vgrad(w, h, [(0.0, (150, 178, 196, 255)), (0.62, (214, 228, 236, 255)), (0.66, (236, 242, 246, 255)),
                             (1.0, (206, 220, 230, 255))])
        return B._vignette(im, 90), 0.8, True
    img = B.draw(set_name if set_name in B.SETS else "savanna", 0.0, None, w, h)
    land = set_name in B.LAND_SETS
    return img, (B.GROUND_Y if set_name != "burrow" else 0.72) if land else 0.0, land


# ---------------------------------------------------------------------------------------------------------------- the actor

def _legs(sp: Image.Image, split: float = 0.58) -> Tuple[int, int]:
    """(belly row, feet row) of a standing side view: the legs are what is below the belly."""
    a = np.asarray(sp.getchannel("A")) > 90
    ys = np.where(a.any(axis=1))[0]
    if len(ys) == 0:
        return sp.height, sp.height
    top, bot = int(ys[0]), int(ys[-1])
    return int(top + (bot - top) * split), bot


def _gait(sp: Image.Image, phase: float, amp: float, legs: Tuple[int, int]) -> Image.Image:
    """Legs swing like pendulums: below the belly each row is pushed sideways, more towards the feet, the front half
    of the body one way and the back half the other way, then the other way round (a walk / run cycle without cutting
    the picture into pieces, so it works on any four-legged side view)."""
    sy, bot = legs
    if bot - sy < 6:
        return sp
    arr = np.asarray(sp).copy()
    w = arr.shape[1]
    mid = w // 2
    src = np.asarray(sp)
    for y in range(sy, bot + 1):
        f = ((y - sy) / max(1, bot - sy)) ** 1.2
        for x0, x1, ph in ((0, mid, phase + math.pi), (mid, w, phase)):
            d = int(round(amp * f * math.sin(ph)))
            if d == 0:
                continue
            row = src[y, x0:x1]
            shifted = np.zeros_like(row)
            if d > 0:
                shifted[d:] = row[:-d]
            else:
                shifted[:d] = row[-d:]
            arr[y, x0:x1] = shifted
    return Image.fromarray(arr)


def _wave(sp: Image.Image, phase: float, amp: float, facing_right: bool = True) -> Image.Image:
    """A travelling body wave: columns shift up and down, more towards the tail."""
    arr = np.asarray(sp)
    h, w = arr.shape[:2]
    out = np.zeros_like(arr)
    for x in range(w):
        tail = (1 - x / max(1, w - 1)) if facing_right else (x / max(1, w - 1))
        dy = int(round(amp * (tail ** 1.6) * math.sin(phase - 6.0 * tail)))
        if dy > 0:
            out[dy:, x] = arr[:h - dy, x]
        elif dy < 0:
            out[:h + dy, x] = arr[-dy:, x]
        else:
            out[:, x] = arr[:, x]
    return Image.fromarray(out)


def _fit(sp: Image.Image, max_w: float, max_h: float) -> Image.Image:
    s = min(max_w / max(1, sp.width), max_h / max(1, sp.height))
    return sp.resize((max(1, int(sp.width * s)), max(1, int(sp.height * s))), Image.LANCZOS)


def cut(src: str) -> Optional[Image.Image]:
    """The actor off its green screen (a cut-out made before is used as it is)."""
    im = Image.open(src)
    if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 200:
        return im.convert("RGBA").crop(im.getchannel("A").getbbox() or (0, 0, im.width, im.height))
    from .art_flow import cut_out
    return cut_out(src, "side")


# ---------------------------------------------------------------------------------------------------------------- animate

def animate(src: str, dst: str, seconds: float, action: str = "idle", set_name: str = "savanna", facing: str = "right",
            seed: int = 0) -> str:
    from cinematic_explainer.render import H, W

    actor = cut(src)
    if actor is None:
        raise ValueError("no actor on the green screen")
    if facing == "left":
        actor = actor.transpose(Image.FLIP_LEFT_RIGHT)
    bg, ground, land = _set_image(set_name, W, H)
    bg = bg.convert("RGBA")
    rnd = random.Random(seed)
    big = action in ("attack", "approach", "fall")
    sp = _fit(actor, W * (0.62 if big else 0.5), H * (0.62 if big else 0.52))
    legs = _legs(sp) if action in ("walk", "run", "flee") and land else (sp.height, sp.height)
    n = max(2, int(round(seconds * FPS)))
    sign = 1 if facing == "right" else -1
    gy = H * ground if land else H * 0.52
    dust: List[List[float]] = []
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
                             "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", dst],
                            stdin=subprocess.PIPE)
    try:
        for i in range(n):
            t = i / FPS
            k = i / (n - 1)
            e = k * k * (3 - 2 * k)
            frame = bg.copy()
            img, scale, rot, dx, dy = sp, 1.0, 0.0, 0.0, 0.0
            cx = W / 2
            if action in ("walk", "run", "flee"):
                speed = {"walk": 0.22, "run": 0.55, "flee": 0.9}[action]
                steps = {"walk": 1.6, "run": 3.0, "flee": 3.2}[action]
                ph = 2 * math.pi * steps * t
                img = _gait(sp, ph, sp.width * (0.035 if action == "walk" else 0.06), legs)
                start = W / 2 - sign * W * speed * 0.5
                cx = start + sign * W * speed * k
                dy = -abs(math.sin(ph)) * (4 if action == "walk" else 9)
            elif action == "swim":
                img = _wave(sp, 2 * math.pi * 1.1 * t, max(4.0, sp.height * 0.05), facing == "right")
                cx = W / 2 - sign * W * 0.15 + sign * W * 0.3 * k
                dy = math.sin(2 * math.pi * 0.35 * t) * 8
            elif action == "attack":
                if k < 0.18:                                          # crouch
                    dx, dy, scale = -sign * 12 * (k / 0.18), 6 * (k / 0.18), 1.0
                elif k < 0.32:                                        # lunge
                    q = (k - 0.18) / 0.14
                    dx, scale = -sign * 12 + sign * 90 * q, 1.0 + 0.08 * q
                else:                                                 # struggle
                    dx = sign * 78 + math.sin(t * 2 * math.pi * 7) * 7
                    dy = math.cos(t * 2 * math.pi * 9) * 4
                    rot = math.sin(t * 2 * math.pi * 5) * 2.5
                    scale = 1.08
                    if land and rnd.random() < 0.6:
                        dust.append([cx + dx + rnd.uniform(-sp.width * 0.4, sp.width * 0.4), gy - rnd.uniform(0, 14),
                                     rnd.uniform(-1.2, 1.2), rnd.uniform(-1.4, -0.4), rnd.uniform(14, 30), 1.0])
            elif action == "approach":
                scale = 0.85 + 0.4 * e
                dy = 18 * e
            elif action == "fall":
                rot = -sign * 70 * min(1.0, e * 1.6) if k < 0.6 else -sign * 70
                dy = 30 * min(1.0, e * 1.6)
                scale = 0.95
            else:                                                     # idle: breathing + a slow drift
                scale = 1.0 + 0.015 * math.sin(2 * math.pi * 0.4 * t)
                dx = sign * 24 * (e - 0.5)
            a_img = img
            if abs(scale - 1.0) > 1e-3:
                a_img = a_img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)
            if abs(rot) > 0.05:
                a_img = a_img.rotate(rot, resample=Image.BICUBIC, expand=True)
            x = cx + dx - a_img.width / 2
            y = (gy - a_img.height + dy) if land else (gy - a_img.height / 2 + dy)
            if land:                                                  # soft contact shadow under the feet
                sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                sw = a_img.width * 0.42
                ImageDraw.Draw(sh).ellipse((x + a_img.width / 2 - sw, gy - 10, x + a_img.width / 2 + sw, gy + 12),
                                           fill=(0, 0, 0, 110))
                frame.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9)))
            frame.alpha_composite(a_img, (int(round(x)), int(round(y))))
            if dust:                                                  # soft, faint dust: blurred, never a hard blob
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                dd = ImageDraw.Draw(layer)
                for p in dust:
                    p[0] += p[2]
                    p[1] += p[3]
                    p[4] += 0.8
                    p[5] -= 0.035
                    if p[5] > 0:
                        dd.ellipse((p[0] - p[4], p[1] - p[4] * 0.6, p[0] + p[4], p[1] + p[4] * 0.6),
                                   fill=(200, 170, 128, int(42 * p[5])))
                frame.alpha_composite(layer.filter(ImageFilter.GaussianBlur(8)))
                dust[:] = [p for p in dust if p[5] > 0][-120:]
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait(timeout=600)
    return dst


# ---------------------------------------------------------------------------------------------------------------- drawn cast

def animate_cast(names: List[str], dst: str, seconds: float, action: str = "idle", set_name: str = "savanna_night",
                 facing: str = "right", seed: int = 0, widths: Optional[List[int]] = None) -> str:
    """One or two library animals, flat, ACTING on a plain set (ocean/rig.py legs): walk / run cross the frame with the
    body moving exactly as far as the legs step (no sliding), flee runs out of frame, attack runs in and lunges at the
    second animal, approach comes closer, idle stands breathing and shifting its weight. The second animal faces the
    first and stands its ground (it flinches when lunged at). Animals with no legs (snakes) wave instead of stepping."""
    from cinematic_explainer.render import H, W
    from . import rig as RG

    widths = list(widths or [560] * len(names))
    bg, ground, land = _set_image(set_name, W, H)
    bg = bg.convert("RGBA")
    gy = H * ground if land else H * 0.6
    rnd = random.Random(seed)
    from . import puppet as PU
    rigs = [RG.rig_vector(n, int(w)) or (PU.puppet(PU.ALIASES.get(n, n), int(w)) if PU.has(n) else RG.rig_for(n, int(w)))
            for n, w in zip(names, widths)]       # the flat vector picture on a knee rig first, then the code puppet
    n = max(2, int(round(seconds * FPS)))
    sign = 1 if facing == "right" else -1
    two = len(rigs) == 2
    # where each animal is: the actor (0) and the one it meets (1)
    if two:
        x_b = W * (0.72 if sign > 0 else 0.28)
        reach = x_b - sign * (rigs[0].body.width + rigs[1].body.width) * 0.42
    gait = {"walk": "walk", "run": "run", "flee": "run", "attack": "run", "swim": "walk", "approach": "walk"}.get(action, "idle")
    rg0 = rigs[0]
    swing = 0.3 if gait != "run" else 0.55
    stride = max(20.0, 2.0 * rg0.leg_len * math.sin(swing) * (2.0 if gait == "run" else 1.0))
    in_place = not two and action in ("walk", "run", "swim")
    if in_place:
        travel = W * 0.05                                 # walks on the spot, drifting a little: the reference's treadmill
    elif action in ("walk", "run", "swim"):
        travel = W * (0.30 if action == "walk" else 0.55)
    elif action == "flee":
        travel = W * 0.9
    elif action == "attack" and two:
        travel = abs(reach - (W * 0.5 - sign * W * 0.3))
    else:
        travel = 0.0
    move_s = seconds if action != "attack" else min(seconds * 0.55, 1.6)
    speed = travel / max(0.3, move_s)
    freq = max(0.7 if gait != "idle" else 0.25, min(3.6, speed / stride)) if gait != "idle" else 0.3
    if in_place:
        freq = 1.0 if gait == "walk" else 2.0             # a natural cadence (the steps no longer pay for distance)
    x0 = (W * 0.5 - sign * travel / 2) if action in ("walk", "run", "swim") else \
         (W * 0.5) if action == "flee" else (W * 0.5 - sign * W * 0.3) if (action == "attack" and two) else \
         (W * (0.3 if sign > 0 else 0.7) if two else W * 0.5)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
                             "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", dst],
                            stdin=subprocess.PIPE)
    dust: List[List[float]] = []

    def put(frame: Image.Image, rg: Any, img: Image.Image, cx: float, face_left: bool, scale: float = 1.0,
            dy: float = 0.0, rot: float = 0.0) -> None:
        if face_left:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if abs(scale - 1.0) > 1e-3:
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)
        if abs(rot) > 0.05:
            img = img.rotate(rot, resample=Image.BICUBIC, center=(img.width / 2, rg.feet * scale))
        feet = rg.feet * scale
        x, y = cx - img.width / 2, gy - feet + dy
        if land:
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sw = rg.body.width * scale * 0.4
            ImageDraw.Draw(sh).ellipse((cx - sw, gy - 9, cx + sw, gy + 10), fill=(0, 0, 0, 120))
            frame.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        frame.alpha_composite(img, (int(round(x)), int(round(y))))

    try:
        for i in range(n):
            t = i / FPS
            k = i / (n - 1)
            frame = bg.copy()
            # the actor
            if action == "attack" and two:
                q = min(1.0, t / max(0.3, move_s))
                cx = x0 + sign * travel * (1 - (1 - q) ** 2)            # runs in, slows into the lunge
                g = "run" if q < 1.0 else "idle"
                lunge = (t - move_s) if q >= 1.0 else -1.0
                rot = (sign * 14 * math.sin(min(1.0, lunge / 0.22) * math.pi / 2)) if 0 <= lunge < 0.5 else \
                      (sign * (6 + 5 * math.sin(t * 2 * math.pi * 3.5))) if lunge >= 0.5 else 0.0    # rears up, then grapples
                img = rg0.pose(t * (freq if g == "run" else 0.3), g)
                if lunge >= 0 and land and rnd.random() < 0.5:
                    dust.append([cx + sign * rg0.body.width * 0.3 + rnd.uniform(-40, 40), gy - rnd.uniform(0, 10),
                                 rnd.uniform(-1.2, 1.2), rnd.uniform(-1.2, -0.3), rnd.uniform(12, 24), 1.0])
                put(frame, rg0, img, cx + (sign * 14 if 0 <= lunge < 0.5 else 0), sign < 0, 1.0, 0.0, rot)
            elif action == "approach":
                img = rg0.pose(t * freq * 0.6, "walk")
                put(frame, rg0, img, x0, sign < 0, 0.8 + 0.35 * (k * k * (3 - 2 * k)), 20 * k)
            elif action == "fall":
                img = rg0.pose(0.0, "idle")
                put(frame, rg0, img, x0, sign < 0, 1.0, 0.0, -sign * 75 * min(1.0, k * 2.2))
            elif not rg0.ok:                                            # a snake / bird: a travelling body wave
                img = _wave(rg0.body, 2 * math.pi * 1.1 * t, max(4.0, rg0.body.height * 0.05), sign > 0)
                put(frame, rg0, img, x0 + sign * travel * k, sign < 0)
            else:
                img = rg0.pose(t * freq, gait)
                cx = x0 + sign * speed * t if travel else x0 + sign * 16 * math.sin(2 * math.pi * 0.12 * t)
                breathe = 1.0 + (0.012 * math.sin(2 * math.pi * 0.4 * t) if gait == "idle" else 0.0)
                put(frame, rg0, img, cx, sign < 0, breathe)
            # the one it meets: stands its ground, facing the actor; flinches back when lunged at
            if two:
                rg1 = rigs[1]
                flinch = 0.0
                if action == "attack" and t > move_s:
                    flinch = sign * (30 * min(1.0, (t - move_s) / 0.3) + 8 * math.sin((t - move_s) * 2 * math.pi * 3))
                img = rg1.pose(t * 0.3 + 0.37, "idle")
                put(frame, rg1, img, x_b + flinch, sign > 0, 1.0 + 0.01 * math.sin(2 * math.pi * 0.45 * t + 1.0))
            if dust:
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                dd = ImageDraw.Draw(layer)
                for p in dust:
                    p[0] += p[2]
                    p[1] += p[3]
                    p[4] += 0.8
                    p[5] -= 0.035
                    if p[5] > 0:
                        dd.ellipse((p[0] - p[4], p[1] - p[4] * 0.6, p[0] + p[4], p[1] + p[4] * 0.6),
                                   fill=(190, 170, 140, int(38 * p[5])))
                frame.alpha_composite(layer.filter(ImageFilter.GaussianBlur(8)))
                dust[:] = [p for p in dust if p[5] > 0][-120:]
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait(timeout=600)
    return dst
