"""Pillow card renderer for Health Cinema (chapter, text, stat, evidence cards). Landscape only. Frames are piped to ffmpeg as raw RGB; only the
short entrance animation produces distinct frames, the rest re-sends the same bytes. Typography comes from the profile (accessible defaults)."""
from __future__ import annotations
import math, subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from . import profiles as P
from .overlay import _font
from . import graphics as G
from .render_journey import Cancelled

BG_TOP, BG_BOT = (12, 18, 34), (6, 9, 18)
WHITE, SOFT, MUTED = (245, 247, 252), (205, 214, 232), (150, 163, 188)
ANIM_S = 0.9

def _ease(x: float) -> float: x = min(1.0, max(0.0, x)); return x * x * (3 - 2 * x)

def _bg(W, H) -> Image.Image:
    im = Image.new("RGB", (W, H)); px = ImageDraw.Draw(im)
    for y in range(0, H, 4):
        k = y / H; c = tuple(round(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * k) for i in range(3)); px.rectangle([0, y, W, y + 4], fill=c)
    return im

def wrap(draw, text, font, max_w) -> List[str]:
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def _fit(draw, text, size_px, max_w, max_h, min_px=28, line_gap=1.25):
    """Largest font <= size_px whose wrapped text fits the box (never below min_px: the caller trims the text instead)."""
    px = size_px
    while True:
        f = _font(px); lines = wrap(draw, text, f, max_w)
        if len(lines) * px * line_gap <= max_h or px <= min_px: return f, lines, px
        px -= 2

def _trim(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"

def _cap_index(params, t):
    for k, (a, b, _) in enumerate(params.get("captions") or []):
        if a <= t < b: return (k, round(min((t - a) / 0.15, (b - t) / 0.15, 1.0) * 6))
    return None

def _with_caption(im, params, t, H):
    for a, b, text in params.get("captions") or []:
        if a <= t < b: return G.draw_caption(im, text, H, alpha=min(1.0, (t - a) / 0.15, (b - t) / 0.15))
    return im

def _beat_index(beats, t):
    i = 0
    for k, b in enumerate(beats):
        if t >= b["t0"]: i = k
    return i

def frame_state(kind, params, t, fps):
    """Key that changes only when the picture does (so identical frames are not redrawn)."""
    if kind == "text_card":
        beats = params.get("beats") or [{"t0": 0.0}]; bi = _beat_index(beats, t); return (bi, round(min(max(t - beats[bi]["t0"], 0), 0.6) * fps))
    if kind == "counter_card": return round(t * fps)                                    # the ring never stops
    if kind == "bar_card": return round(min(t, 2.5) * fps)
    if kind == "timeline_card":
        last = max([e["t0"] for e in params.get("events", [])] or [0]) + 1.2; cap = [i for i, (a, b, _) in enumerate(params.get("captions") or []) if a <= t < b]
        return (round(min(t, last) * fps), cap[0] if cap else -1, round((t * 6) % 6) if False else 0)
    return round(min(t, max(ANIM_S, 1.5)) * fps)

def draw_card(kind: str, params: dict, prof: P.Profile, W: int, H: int, t: float) -> Image.Image:
    """One frame of a card at time t seconds."""
    sz = P.type_sizes(prof, H); a = _ease(t / ANIM_S); im = _bg(W, H); d = ImageDraw.Draw(im, "RGBA"); m = round(W * 0.08); acc = prof.accent
    def text_block(txt, px, x, y, max_w, max_h, fill=WHITE, alpha=1.0):
        f, lines, used = _fit(d, txt, px, max_w, max_h); yy = y
        for ln in lines: d.text((x, yy), ln, font=f, fill=(*fill, round(255 * alpha))); yy += round(used * 1.25)
        return yy
    d.rectangle([0, 0, round(W * 0.012), H], fill=(*acc, round(255 * a)))
    dy = round((1 - a) * H * 0.02)
    if kind in ("counter_card", "bar_card", "timeline_card"):
        {"counter_card": G.draw_counter, "bar_card": G.draw_bar, "timeline_card": G.draw_timeline}[kind](d, params, prof, W, H, t, sz)
        return _with_caption(im, params, t, H)
    if kind == "chapter_card":
        d.text((m, H * 0.40 + dy), params.get("kicker", "").upper(), font=_font(sz["label"]), fill=(*acc, round(255 * a)))
        text_block(params.get("title", ""), sz["title"] + 10, m, H * 0.40 + sz["label"] * 1.6 + dy, W - 2 * m, H * 0.35, alpha=a)
    elif kind == "stat_card":
        raw = str(params.get("number", "")); unit = params.get("unit", "")
        try: val = float(raw.replace(",", "")); shown = f"{val * _ease(t / 1.4):,.{0 if val == int(val) else 1}f}" if t < 1.4 else raw
        except ValueError: shown = raw
        big = _font(round(sz["title"] * 2.6)); d.text((m, H * 0.20), shown + unit, font=big, fill=(*acc, 255))
        y = H * 0.20 + sz["title"] * 2.6 * 1.25
        y = text_block(_trim(params.get("context", ""), 220), sz["body"], m, y, W - 2 * m, H * 0.30, alpha=a)
        src = params.get("source_line") or "Source needed (not shown to viewers until attached)"
        d.text((m, H - m - sz["source"] * 1.4), _trim(src, 120), font=_font(sz["source"]), fill=(*MUTED, round(255 * a)))
    elif kind == "evidence_card":
        d.text((m, H * 0.14 + dy), params.get("heading", "What the evidence says").upper(), font=_font(sz["label"]), fill=(*acc, round(255 * a)))
        y = text_block(_trim(params.get("claim", ""), 230), sz["body"] + 6, m, H * 0.14 + sz["label"] * 2 + dy, W - 2 * m, H * 0.46, alpha=a)
        lvl = {"established": "Established evidence", "preliminary": "Preliminary research", "unsourced": "Source needed"}.get(params.get("level", ""), "")
        if lvl:
            f = _font(sz["label"]); w = d.textlength(lvl, font=f) + 36; y0 = H - m - sz["source"] * 2.8 - sz["label"] * 1.7
            d.rounded_rectangle([m, y0, m + w, y0 + sz["label"] * 1.5], radius=10, outline=(*acc, round(255 * a)), width=3); d.text((m + 18, y0 + sz["label"] * 0.16), lvl, font=f, fill=(*acc, round(255 * a)))
        src = params.get("source_line") or ("" if params.get("level") == "unsourced" else "Source needed")
        d.text((m, H - m - sz["source"] * 1.4), _trim(src, 130), font=_font(sz["source"]), fill=(*MUTED, round(255 * a)))
    else:   # text_card: one spoken sentence at a time, large; numbers in the accent colour
        beats = params.get("beats") or [{"text": params.get("text", ""), "t0": 0.0}]; bi = _beat_index(beats, t); b = beats[bi]
        ba = _ease((t - b["t0"]) / 0.5); fnt, lines, used = _fit(d, _trim(b["text"], 200), sz["title"], W - 2 * m, H * 0.55, min_px=sz["body"]); yy = H * 0.5 - len(lines) * used * 1.25 / 2 + round((1 - ba) * H * 0.015)
        for ln in lines:
            x = m
            for w in ln.split():
                col = acc if any(ch.isdigit() for ch in w) else WHITE; d.text((x, yy), w, font=fnt, fill=(*col, round(255 * ba))); x += d.textlength(w + " ", font=fnt)
            yy += round(used * 1.25)
        if len(beats) > 1:   # progress ticks: where we are in this scene's sentences
            for i in range(len(beats)): d.ellipse([m + i * 26, H - m * 0.9, m + i * 26 + 12, H - m * 0.9 + 12], fill=(*(acc if i <= bi else MUTED), 255))
        if params.get("want_footage"):
            d.text((m, H - m - sz["source"] * 1.4), "Footage wanted for this scene", font=_font(sz["source"]), fill=(*MUTED, round(255 * a)))
    if params.get("illustrative"):
        d.text((m, H - m * 0.55), params["illustrative"], font=_font(sz["source"]), fill=(*MUTED, 255))
    return _with_caption(im, params, t, H)

def render_card_clip(kind: str, params: dict, prof: P.Profile, W: int, H: int, fps: int, frames: int, out: Path, ffmpeg: str,
                     cancel: Optional[Callable[[], bool]] = None) -> None:
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True); tmp = out.with_suffix(".part.mp4")
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium",
           "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        last = None; last_key = None
        for i in range(frames):
            if cancel and cancel(): raise Cancelled("cancelled")
            key = (frame_state(kind, params, i / fps, fps), _cap_index(params, i / fps))
            if key != last_key: last = draw_card(kind, params, prof, W, H, i / fps).tobytes(); last_key = key
            p.stdin.write(last)
        p.stdin.close()
        try: rc = p.wait(timeout=900)
        except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=30); raise RuntimeError('ffmpeg timed out')
        if rc != 0: raise RuntimeError(f"ffmpeg exit {rc}")
        tmp.replace(out)
    except BaseException:
        try: p.kill(); p.wait(timeout=30)   # Windows keeps the file locked until ffmpeg has really exited
        except Exception: pass
        try: tmp.unlink(missing_ok=True)
        except OSError: pass   # a leftover .part file must not hide why the render stopped
        raise
