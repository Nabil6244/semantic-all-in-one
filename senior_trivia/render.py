"""Senior Trivia renderer: every segment drawn frame by frame (PIL), encoded per segment in parallel, joined, then mixed.

Our own "parlor" look, built for a TV across the room: a deep teal wallpaper that slowly drifts, cream cards, mustard
accents, very large text. Nothing is ever still: pictures push in, the countdown ring drains, options pop in as read.
Layouts: question (picture left, question + options right; or 2x2 options without a picture), item (big object photo,
draining time bar, name bar), round title, intro (title + chips over a picture with a polaroid montage), score check,
outro score ladder, host (his Flow talking clip; without a clip his line over a scene picture, never a still of him).
"""
import math
import os
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from prepper_host.render import (ClipReader, _decode, back, clamp, ease, ease_out, font, headroom, kenburns, load,
                                 rounded, shadowed)

ROOT = Path(__file__).resolve().parents[1]
BG_A, BG_B = (20, 58, 64), (11, 34, 40)
CREAM, INK, MUSTARD = (248, 241, 226), (44, 38, 32), (236, 176, 64)
OK, BAD, DIM = (70, 158, 92), (214, 82, 64), (150, 160, 158)
HEAD, BODY = "Outfit-ExtraBold.ttf", "DMSans-Bold.ttf"
SFX = {"tick": ("assets/bundled-sfx/ui/ui_tick_01.opus", -24.0), "chime": ("kids_audio/library/sfx_ding_3.wav", -16.0),
       "pop": ("assets/bundled-sfx/ui/ui_005.opus", -27.0), "whoosh": ("assets/bundled-sfx/whoosh/whoosh_004.opus", -22.0)}
BED = ("assets/music/echoes_of_time_v2.opus", -34.0)   # calm, adult; well under the voice (owner 2026-11-25: kids bed too childish and loud)
SR = 48000


class Stopped(Exception):
    pass


def wrap(draw, text, fnt, width):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=fnt) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit(draw, text, name, px, width, max_lines):
    """Largest font size (down from px) whose wrapped text fits in max_lines."""
    while px > 26:
        f = font(name, px)
        lines = wrap(draw, text, f, width)
        if len(lines) <= max_lines:
            return f, lines
        px -= 4
    f = font(name, px)
    return f, wrap(draw, text, f, width)[:max_lines]


class Drawer:
    def __init__(self, spec, assets):
        self.spec, self.a = spec, assets
        self.W, self.H = spec["size"]
        self.u = self.H / 1080.0
        self._readers = {}
        self._bg = self._wallpaper()

    def U(self, x):
        return int(round(x * self.u))

    def pic(self, key):
        p = (self.a.get("pictures") or {}).get(key) if key else None
        return p if p and os.path.isfile(p) else None

    def _wallpaper(self):
        W, H = self.W, self.H
        y = np.linspace(0, 1, H)[:, None]
        x = np.linspace(-1, 1, W)[None, :]
        r = np.sqrt(x ** 2 * 0.6 + (y - 0.45) ** 2)
        k = np.clip(r, 0, 1)[..., None]
        img = np.array(BG_A) * (1 - k) + np.array(BG_B) * k
        stripes = (np.sin(np.linspace(0, 1, W * 2)[None, :] * math.pi * 2 * 48) * 3.0)[..., None]
        big = np.repeat(np.concatenate([img, img], axis=1), 1, axis=0) + stripes
        return Image.fromarray(np.clip(big, 0, 255).astype(np.uint8)).convert("RGBA")

    def base(self, t):
        off = int((t * 6 * self.u) % self.W)
        return self._bg.crop((off, 0, off + self.W, self.H))

    def close(self):
        for r in self._readers.values():
            r.close()

    # ------------------------------------------------------------------ shared pieces
    def text(self, im, xy, s, fnt, fill, anchor="la", alpha=1.0):
        if alpha <= 0:
            return
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(xy, s, font=fnt, fill=fill + (int(255 * clamp(alpha)),), anchor=anchor)
        im.alpha_composite(layer)

    def chip(self, im, x, y, s, fill=MUSTARD, ink=INK, px=34, anchor="l", alpha=1.0):
        f = font(HEAD, self.U(px))
        d = ImageDraw.Draw(im)
        w = int(d.textlength(s, font=f)) + self.U(44)
        h = self.U(px * 1.75)
        x0 = x if anchor == "l" else (x - w if anchor == "r" else x - w // 2)
        card = rounded((w, h), h // 2, fill + (int(255 * alpha),))
        im.alpha_composite(card, (x0, y))
        self.text(im, (x0 + w // 2, y + h // 2), s, f, ink, "mm", alpha)
        return w

    def topbar(self, im, seg, t):
        a = clamp((t - seg["t0"]) / 0.4)
        if seg.get("round"):
            self.chip(im, self.U(70), self.U(44), seg["round"].upper(), fill=(255, 255, 255), ink=BG_A, px=30, alpha=0.92 * a)
        if seg.get("n") and seg["kind"] in ("question", "item"):
            self.chip(im, self.W - self.U(70), self.U(44), f"QUESTION {seg['n']} / {seg['total']}", px=30, anchor="r", alpha=a)
        if seg["kind"] == "bonus":
            self.chip(im, self.W - self.U(70), self.U(44), "BONUS QUESTION", px=30, anchor="r", alpha=a)

    def ring(self, im, cx, cy, r, seg, t):
        """Countdown ring: drains over the seconds, green -> amber -> red, the number in the middle; a soft pulse per tick."""
        c0, secs = seg["count_at"], seg["seconds"]
        if t < c0 - 0.3 or t > seg["reveal_at"] + 0.4:
            return
        a = clamp((t - (c0 - 0.3)) / 0.3) * (1 - clamp((t - seg["reveal_at"]) / 0.4))
        left = clamp(1 - (t - c0) / secs)
        col = tuple(int(v) for v in (np.array(OK) * left + np.array(BAD) * (1 - left))) if left < 1 else OK
        pulse = 1 + 0.06 * math.exp(-((t - c0) % 1.0) * 6) if c0 <= t < seg["reveal_at"] else 1.0
        R = int(r * pulse)
        s = R * 2 + self.U(16)
        layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        o = self.U(8)
        d.ellipse((o, o, s - o, s - o), fill=(255, 255, 255, int(235 * a)))
        w = self.U(14)
        d.arc((o + w // 2, o + w // 2, s - o - w // 2, s - o - w // 2), -90, -90 + 360 * left, fill=col + (int(255 * a),), width=w)
        n = max(1, math.ceil(secs - max(0.0, t - c0))) if t < seg["reveal_at"] else 0
        if n:
            d.text((s // 2, s // 2), str(n), font=font(HEAD, int(R * 0.95)), fill=INK + (int(255 * a),), anchor="mm")
        im.alpha_composite(layer, (int(cx - s / 2), int(cy - s / 2)))

    def photo(self, im, path, box, f, radius=28, move="push_in", fade=1.0):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        b = self.U(10)
        frame = rounded((w, h), self.U(radius), CREAM + (255,))
        if path:
            inner = kenburns(headroom(path, (w - 2 * b, h - 2 * b)), (w - 2 * b, h - 2 * b), move, f).convert("RGBA")
            mask = rounded((w - 2 * b, h - 2 * b), self.U(radius - 8), (255, 255, 255, 255)).split()[3]
            frame.paste(inner, (b, b), mask)
        card = shadowed(frame, self.U(18))
        if fade < 1:
            card.putalpha(card.split()[3].point(lambda v: int(v * clamp(fade))))
        pad = self.U(18) * 3
        im.alpha_composite(card, (x0 - pad, y0 - pad + self.U(4)))

    # ------------------------------------------------------------------ frame
    def frame(self, seg, t):
        im = self.base(t)
        kind = seg["kind"]
        if kind in ("question", "bonus"):
            self.question(im, seg, t)
        elif kind == "item":
            self.item(im, seg, t)
        elif kind == "round":
            self.round_card(im, seg, t)
        elif kind == "host":
            im = self.host(seg, t)
        elif kind in ("intro", "check", "outro"):
            self.talk_card(im, seg, t)
        return im.convert("RGB")

    def question(self, im, seg, t):
        W, H, U = self.W, self.H, self.U
        tl, dur = t - seg["t0"], seg["t1"] - seg["t0"]
        d = ImageDraw.Draw(im)
        rev = seg["reveal_at"]
        p, fp = self.pic(seg["pic"]), self.pic(seg.get("fact_pic"))
        self.topbar(im, seg, t)
        enter = ease_out(clamp(tl / 0.5))
        if p:
            box = (U(70), U(150) + int((1 - enter) * U(40)), U(1010), U(830) + int((1 - enter) * U(40)))
            f = clamp(tl / dur)
            self.photo(im, p, box, f)
            if fp and t > rev:
                self.photo(im, fp, box, f, move="pull_out", fade=clamp((t - rev) / 0.6))
            self.ring(im, box[2] - U(20), box[3] - U(20), U(70), seg, t)
            x0, x1, qy = U(1070), W - U(70), U(160)
            qf, ql = fit(d, seg["question"], HEAD, U(58), x1 - x0, 5)
            for k, line in enumerate(ql):
                self.text(im, (x0, qy + k * int(qf.size * 1.16)), line, qf, CREAM, alpha=enter)
            oy = qy + len(ql) * int(qf.size * 1.16) + U(40)
            boxes = [(x0, oy + k * U(112), x1, oy + k * U(112) + U(92)) for k in range(len(seg["options"]))]
        else:
            self.ring(im, W // 2, U(905), U(64), seg, t)
            qf, ql = fit(d, seg["question"], HEAD, U(70), W - U(260), 3)
            for k, line in enumerate(ql):
                self.text(im, (W // 2, U(190) + k * int(qf.size * 1.15)), line, qf, CREAM, "ma", alpha=enter)
            oy = U(190) + len(ql) * int(qf.size * 1.15) + U(60)
            cw = (W - U(260) - U(40)) // 2
            boxes = [(U(130) + (k % 2) * (cw + U(40)), oy + (k // 2) * U(130), U(130) + (k % 2) * (cw + U(40)) + cw,
                      oy + (k // 2) * U(130) + U(104)) for k in range(len(seg["options"]))]
        for k, (o, bx) in enumerate(zip(seg["options"], boxes)):
            at = seg["opt_at"][k] if k < len(seg["opt_at"]) else seg["t0"]
            self.option(im, bx, k, o, t, at, rev, k == seg["answer"])
        if t > rev + 0.2:
            self.fact_strip(im, seg, t - rev - 0.2, answer_only=not seg["options"])

    def option(self, im, box, k, text, t, at, rev, right):
        if t < at:
            return
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        pop = back(clamp((t - at) / 0.35))
        r = clamp((t - rev) / 0.35)
        fill = CREAM if r <= 0 else (tuple(int(a + (b - a) * r) for a, b in zip(CREAM, OK)) if right else CREAM)
        alpha = 1.0 if (right or r <= 0) else 1 - 0.6 * r
        card = rounded((w, h), h // 2, fill + (int(255 * alpha),))
        d = ImageDraw.Draw(card)
        cr = h - self.U(20)
        d.ellipse((self.U(10), self.U(10), self.U(10) + cr, self.U(10) + cr), fill=(MUSTARD if not (right and r > 0) else (255, 255, 255)) + (int(255 * alpha),))
        d.text((self.U(10) + cr // 2, h // 2), "ABCD"[k], font=font(HEAD, int(cr * 0.62)), fill=INK + (int(255 * alpha),), anchor="mm")
        ink = (255, 255, 255) if (right and r > 0.5) else INK
        f, lines = fit(d, text, BODY, int(h * 0.42), w - cr - self.U(70), 1)
        d.text((cr + self.U(34), h // 2), lines[0] if lines else "", font=f, fill=ink + (int(255 * alpha),), anchor="lm")
        if right and r > 0:
            cx, cy, s = w - self.U(50), h // 2, self.U(16)
            d.line([(cx - s, cy), (cx - s // 3, cy + s * 2 // 3), (cx + s, cy - s * 2 // 3)], fill=(255, 255, 255, int(255 * r)), width=self.U(8))
        sc = 0.85 + 0.15 * pop
        card = card.resize((max(1, int(w * sc)), max(1, int(h * sc))), Image.BILINEAR)
        im.alpha_composite(card, (x0 + (w - card.width) // 2, y0 + (h - card.height) // 2))

    def fact_strip(self, im, seg, tl, answer_only=False):
        W, U = self.W, self.U
        a = ease_out(clamp(tl / 0.45))
        h = U(150)
        y = self.H - h - U(36) + int((1 - a) * U(60))
        strip = rounded((W - U(140), h), U(26), (12, 28, 32, int(235 * a)))
        im.alpha_composite(strip, (U(70), y))
        d = ImageDraw.Draw(im)
        label = "THE ANSWER" if answer_only or not seg.get("fact") else "DID YOU KNOW?"
        self.chip(im, U(100), y - U(26), label, px=28, alpha=a)
        body = seg.get("fact") or seg.get("answer_text", "")
        if answer_only and seg.get("answer_text"):
            body = f"{seg['answer_text']}. {seg.get('fact', '')}".strip()
        f, lines = fit(d, body, BODY, U(40), W - U(260), 2)
        for k, line in enumerate(lines):
            self.text(im, (U(110), y + U(40) + k * int(f.size * 1.2)), line, f, CREAM, alpha=a)

    def item(self, im, seg, t):
        W, H, U = self.W, self.H, self.U
        tl, dur = t - seg["t0"], seg["t1"] - seg["t0"]
        rev = seg["reveal_at"]
        p = self.pic(seg["pic"])
        box = (W // 2 - U(560), U(120), W // 2 + U(560), U(860))
        self.photo(im, p, box, clamp(tl / dur), move="still")
        self.chip(im, U(70), U(44), f"{seg['n']}", px=44)
        c0, secs = seg["count_at"], seg["seconds"]
        left = clamp(1 - (t - c0) / secs) if t >= c0 else 1.0
        bw = box[2] - box[0]
        bar = Image.new("RGBA", (bw, U(22)), (255, 255, 255, 60))
        col = tuple(int(v) for v in (np.array(OK) * left + np.array(BAD) * (1 - left)))
        if left > 0:
            bar.alpha_composite(rounded((max(2, int(bw * left)), U(22)), U(11), col + (255,)))
        im.alpha_composite(bar, (box[0], U(890)))
        if t > rev:
            a = ease_out(clamp((t - rev) / 0.35))
            nb = rounded((bw, U(110)), U(24), MUSTARD + (int(255 * a),))
            im.alpha_composite(nb, (box[0], U(930)))
            self.text(im, (W // 2, U(985)), seg["answer_text"], font(HEAD, U(62)), INK, "mm", alpha=a)

    def round_card(self, im, seg, t):
        W, H, U = self.W, self.H, self.U
        tl, dur = t - seg["t0"], seg["t1"] - seg["t0"]
        p = self.pic(seg.get("pic"))
        if p:
            bg = kenburns(headroom(p, (W, H)), (W, H), "push_in", clamp(tl / dur)).convert("RGBA")
            bg = bg.filter(ImageFilter.GaussianBlur(self.U(6)))
            im.alpha_composite(Image.blend(bg, Image.new("RGBA", (W, H), BG_B + (255,)), 0.62))
        a = back(clamp(tl / 0.5))
        self.text(im, (W // 2, U(330)), f"ROUND {seg['n']}", font(HEAD, int(U(170) * (0.8 + 0.2 * a))), MUSTARD, "mm", clamp(tl / 0.3))
        d = ImageDraw.Draw(im)
        f, lines = fit(d, seg["title"].upper(), HEAD, U(84), W - U(300), 2)
        for k, line in enumerate(lines):
            self.text(im, (W // 2, U(500) + k * int(f.size * 1.1)), line, f, CREAM, "mm", clamp((tl - 0.25) / 0.4))
        if seg.get("level"):
            self.chip(im, W // 2, U(640), seg["level"].upper(), fill=(255, 255, 255), ink=BG_A, px=34, anchor="m",
                      alpha=clamp((tl - 0.5) / 0.4))

    def talk_card(self, im, seg, t):
        W, H, U = self.W, self.H, self.U
        tl, dur = t - seg["t0"], seg["t1"] - seg["t0"]
        p = self.pic(seg.get("pic"))
        if p:
            bg = kenburns(headroom(p, (W, H)), (W, H), "drift", clamp(tl / dur)).convert("RGBA")
            im.alpha_composite(Image.blend(bg, Image.new("RGBA", (W, H), BG_B + (255,)), 0.55))
        d = ImageDraw.Draw(im)
        kind = seg["kind"]
        if kind == "intro":
            for k, key in enumerate(seg.get("montage") or []):
                pk = self.pic(key)
                if not pk:
                    continue
                a = ease_out(clamp((tl - 0.3 - 0.35 * k) / 0.6))
                w, h = U(420), U(300)
                pol = Image.new("RGBA", (w + U(30), h + U(80)), CREAM + (255,))
                pol.paste(load(pk, (w, h)), (U(15), U(15)))
                pol = pol.rotate((-6, 4, -2)[k % 3], expand=True, resample=Image.BICUBIC)
                x = U(170) + k * U(560) + int((1 - a) * U(120))
                y = U(560) + int(U(14) * math.sin(tl * 0.8 + k))
                if a > 0:
                    pol.putalpha(pol.split()[3].point(lambda v: int(v * a)))
                    im.alpha_composite(pol, (x, y))
            f, lines = fit(d, (seg.get("title") or "Trivia Time").upper(), HEAD, U(96), W - U(240), 2)
            for k, line in enumerate(lines):
                self.text(im, (W // 2, U(180) + k * int(f.size * 1.08)), line, f, CREAM, "mm", clamp(tl / 0.4))
            chips = [f"{seg['total']} QUESTIONS", "KEEP SCORE", "BONUS AT THE END"]
            for k, c in enumerate(chips):
                self.chip(im, W // 2 + (k - 1) * U(420), U(400), c, px=32, anchor="m", alpha=clamp((tl - 0.5 - 0.25 * k) / 0.3))
            return
        sents = [s for s in seg.get("line", "").replace("? ", "?|").replace(". ", ".|").split("|") if s.strip()]
        times = seg.get("line_at") or []
        label = "END OF " + seg["round"].upper() if kind == "check" and seg.get("round") else ("YOUR SCORE" if kind == "outro" else "")
        if label:
            self.chip(im, W // 2, U(150), label, px=36, anchor="m", alpha=clamp(tl / 0.3))
        y = U(300) if kind == "outro" else U(420)
        for k, s in enumerate(sents):
            at = times[k] if k < len(times) else seg["t0"] + 0.6 + k
            a = ease_out(clamp((t - at) / 0.4))
            if a <= 0:
                continue
            f, lines = fit(d, s.strip(), HEAD if kind == "check" else BODY, U(64 if kind == "check" else 52), W - U(320), 2)
            if kind == "outro":
                row = rounded((W - U(420), U(108)), U(30), (255, 255, 255, int(40 * a)))
                im.alpha_composite(row, (U(210), y - U(14) + int((1 - a) * U(30))))
            for line in lines:
                self.text(im, (W // 2, y + int((1 - a) * U(30))), line, f, CREAM, "ma", a)
                y += int(f.size * 1.2)
            y += U(54) if kind == "outro" else U(30)

    def host(self, seg, t):
        W, H, U = self.W, self.H, self.U
        tl, dur = t - seg["t0"], seg["t1"] - seg["t0"]
        clip = seg.get("clip")
        im = None
        if clip and os.path.isfile(clip):
            r = self._readers.get(seg["row"])
            if r is None:
                r = self._readers[seg["row"]] = ClipReader(clip, (W, H), (0.5, 0.5, 1.0, 1.0), start=seg.get("clip_start", 0.0),
                                                           fps=self.spec["fps"], loop=False)
            fr = r.next()
            if fr is not None:
                im = fr.convert("RGBA")
        if im is None:   # no clip: his line over the row's scene picture (never a still of him)
            im = self.base(t)
            p = self.pic(seg.get("pic"))
            if p:
                im = kenburns(headroom(p, (W, H)), (W, H), "push_in", clamp(tl / dur)).convert("RGBA")
            d = ImageDraw.Draw(im)
            f, lines = fit(d, seg.get("line", ""), HEAD, U(60), W - U(300), 3)
            box = rounded((W - U(200), len(lines) * int(f.size * 1.2) + U(70)), U(30), (12, 28, 32, 210))
            y0 = H - box.height - U(60)
            im.alpha_composite(box, (U(100), y0))
            for k, line in enumerate(lines):
                self.text(im, (W // 2, y0 + U(35) + k * int(f.size * 1.2)), line, f, CREAM, "ma", clamp(tl / 0.4))
            return im
        if seg.get("first") and tl < 5.0:
            a = clamp(tl / 0.4) * clamp((5.0 - tl) / 0.4)
            name = (self.spec.get("host") or {}).get("name", "Hal").upper()
            tag = (self.spec.get("host") or {}).get("tagline", "your quiz host")
            self.chip(im, U(90), H - U(200), name, px=44, alpha=a)
            self.chip(im, U(90), H - U(118), tag.upper(), fill=(255, 255, 255), ink=BG_A, px=28, alpha=a)
        return im


# ------------------------------------------------------------------ encode
def _encode_seg(args):
    spec, assets, i, f0, f1, out, crf = args
    seg = spec["segs"][i]
    dr = Drawer(spec, assets)
    W, H = spec["size"]
    fps = spec["fps"]
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
                          "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
                          "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", out], stdin=subprocess.PIPE)
    try:
        for fr in range(f0, f1):
            p.stdin.write(dr.frame(seg, fr / fps).tobytes())
    finally:
        p.stdin.close()
        p.wait()
        dr.close()
    if p.returncode:
        raise RuntimeError(f"ffmpeg failed on segment {i}")
    return i


def render_picture(spec, assets, out, workers=None, progress=None, cancel=None, crf=19):
    fps = spec["fps"]
    segs = spec["segs"]
    total = int(round(spec["duration"] * fps))
    starts = [int(round(s["t0"] * fps)) for s in segs] + [total]
    starts[0] = 0
    with tempfile.TemporaryDirectory() as wd:
        jobs = [(spec, assets, i, starts[i], max(starts[i] + 1, starts[i + 1]), os.path.join(wd, f"s{i:04d}.mp4"), crf)
                for i in range(len(segs))]
        workers = workers or max(1, min(8, (os.cpu_count() or 4) - 1))
        made = set()

        def tick():
            if progress:
                progress(len(made) / len(jobs), f"drawing part {len(made)}/{len(jobs)}")
            if cancel and cancel():
                raise Stopped("Stopped.")

        if workers > 1:
            try:
                import multiprocessing as mp
                with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
                    futs = {ex.submit(_encode_seg, j): j[2] for j in jobs}
                    try:
                        for fu in as_completed(futs):
                            made.add(fu.result())
                            tick()
                    except Stopped:
                        for g in futs:
                            g.cancel()
                        raise
            except Stopped:
                raise
            except Exception as e:  # noqa: BLE001 - finish on this core
                if progress:
                    progress(len(made) / len(jobs), f"workers failed ({type(e).__name__}); drawing on one core")
        for j in jobs:
            if j[2] not in made:
                made.add(_encode_seg(j))
                tick()
        lst = os.path.join(wd, "list.txt")
        with open(lst, "w") as fh:
            for j in jobs:
                fh.write(f"file '{j[5]}'\n")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", str(out)], check=True)
    return out


# ------------------------------------------------------------------ sound
def _db(x):
    return 10 ** (x / 20)


def _level(y, target=-19.0):
    loud = y[np.abs(y) > 0.01]
    rms = np.sqrt(np.mean(loud ** 2)) if len(loud) else 0.1
    return y * (_db(target) / max(rms, 1e-4))


def mix(spec, out_wav):
    """Announcer pieces + host clip audio (levelled alike), ticks/pops/chimes, a calm bed ducked under speech."""
    n = int(spec["duration"] * SR) + SR
    speech = np.zeros(n, np.float32)
    cache = {}

    def put(buf, y, t, gain=1.0):
        s = int(t * SR)
        if s >= n:
            return
        e = min(n, s + len(y))
        buf[s:e] += y[:e - s] * gain

    for v in spec["voice"]:
        if v["path"] not in cache:
            cache[v["path"]] = _level(_decode(v["path"]))
        put(speech, cache[v["path"]], v["t"])
    for seg in spec["segs"]:
        if seg["kind"] == "host" and seg.get("clip_audio") and seg.get("clip"):
            try:
                y = _level(_decode(seg["clip"]))
                y = y[int(seg.get("clip_start", 0.0) * SR):][:int((seg["t1"] - seg["t0"]) * SR)].copy()
                f = min(len(y), int(0.12 * SR))      # a short fade, so the cut away from him never clicks
                if f:
                    y[-f:] *= np.linspace(1.0, 0.0, f, dtype=np.float32)
                put(speech, y, seg["t0"])
            except Exception:  # noqa: BLE001 - a clip without sound stays silent
                pass
    out = speech.copy()
    for e in spec["sfx"]:
        name = e["name"]
        if name not in SFX:
            continue
        path, db = SFX[name]
        if name not in cache:
            cache[name] = _decode(ROOT / path)
        put(out, cache[name], e["t"], _db(db) / max(1e-4, float(np.max(np.abs(cache[name])) or 1)))
    try:
        bed = _decode(ROOT / BED[0])
        bed = np.tile(bed, n // len(bed) + 1)[:n]
        bed = bed / max(1e-4, np.sqrt(np.mean(bed ** 2))) * _db(BED[1])
        env = np.abs(speech)
        hop = SR // 50
        m = len(env) // hop
        e = env[:m * hop].reshape(m, hop).max(axis=1)
        duck = np.ones(m, np.float32)
        cur = 0.0
        for k in range(m):
            cur = 1.0 if e[k] > 0.02 else cur * 0.97
            duck[k] = 1.0 - 0.6 * cur
        duck = np.repeat(duck, hop)
        duck = np.pad(duck, (0, n - len(duck)), constant_values=1.0)
        fade = np.minimum(1.0, np.arange(n) / (SR * 2.0)) * np.minimum(1.0, (n - np.arange(n)) / (SR * 3.0))
        out += bed * duck * fade
    except Exception:  # noqa: BLE001 - no bed is fine
        pass
    peak = float(np.max(np.abs(out)) or 1)
    if peak > 0.97:
        out *= 0.97 / peak
    import wave
    pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out_wav
