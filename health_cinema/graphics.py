"""Animated, deterministic data graphics for Health Cinema: frequency counter, percentage bar, event timeline, caption chunks.
Every frame is a pure function of the scene-local time t (seconds), so previews and finals match and a cached clip is exact.
Nothing here invents a number or a source: values come from the planner (the narration) and sources from the script author; an unsourced figure
shows "Source needed" and is flagged for review upstream. Landscape only."""
from __future__ import annotations
import math, re
from typing import Dict, List, Tuple
from PIL import Image, ImageDraw

from . import profiles as P
from .overlay import _font

WHITE, SOFT, MUTED, TRACK = (245, 247, 252), (205, 214, 232), (150, 163, 188), (40, 52, 78)

def ease(x: float) -> float: x = min(1.0, max(0.0, x)); return x * x * (3 - 2 * x)

def _trim(text: str, n: int) -> str: return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"

def _wrap(d, text, font, max_w) -> List[str]:
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])

def source_line(sources: List[dict]) -> str:
    if not sources: return ""
    s = sources[0]; bits = [s.get("title") or s.get("citation") or "", str(s.get("year") or ""), s.get("population") or s.get("context") or ""]
    return " · ".join(b for b in bits if b)

# ---- counter: "Every N seconds" --------------------------------------------------------------------------------------------
def draw_counter(d: ImageDraw.ImageDraw, p: dict, prof: P.Profile, W: int, H: int, t: float, sz: Dict[str, int]) -> None:
    """A ring sweeps once per cycle and a tally ticks up each time it completes. The cycle is COMPRESSED time (default 2.4 s per 'N seconds'),
    and the card says so: it illustrates the stated frequency, it is not a live count."""
    n = p.get("interval", 40); unit = p.get("unit", "seconds"); cycle = p.get("cycle_s", 2.4); m = round(W * 0.08); acc = prof.accent
    a = ease(t / 0.6); cx, cy, r = round(W * 0.72), round(H * 0.46), round(H * 0.26)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*TRACK, 255), width=round(H * 0.022))
    phase = (t / cycle) % 1.0; done = int(t // cycle)
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=-90 + 360 * ease(phase) if phase > 0 else -90, fill=(*acc, 255), width=round(H * 0.022))
    ang = math.radians(-90 + 360 * ease(phase)); d.ellipse([cx + r * math.cos(ang) - 14, cy + r * math.sin(ang) - 14, cx + r * math.cos(ang) + 14, cy + r * math.sin(ang) + 14], fill=(*WHITE, 255))
    big = _font(round(sz["title"] * 1.9)); sec = f"{round(n * phase):d}"; d.text((cx, cy - sz["title"] * 0.5), sec, font=big, fill=(*WHITE, 255), anchor="mm")
    d.text((cx, cy + sz["title"] * 1.25), unit, font=_font(sz["label"]), fill=(*SOFT, 255), anchor="mm")
    d.text((m, H * 0.20), p.get("kicker", "AVERAGE FREQUENCY").upper(), font=_font(sz["label"]), fill=(*acc, round(255 * a)))
    head = _font(round(sz["title"] * 1.25)); d.text((m, H * 0.30), f"Every {n} {unit}", font=head, fill=(*WHITE, round(255 * a)))
    y = H * 0.30 + sz["title"] * 1.25 * 1.5
    for ln in _wrap(d, p.get("context", ""), _font(sz["body"]), W * 0.48 - m)[:4]:
        d.text((m, y), ln, font=_font(sz["body"]), fill=(*SOFT, round(255 * a))); y += sz["body"] * 1.3
    tally = _font(sz["label"]); d.text((m, y + sz["body"] * 0.8), f"{done} {p.get('event', 'events')} so far in this animation", font=tally, fill=(*acc, round(255 * a)))
    note = "Time is compressed: this illustrates the stated average, it is not a live count."
    d.text((m, H * 0.80 - sz["source"] * 2.7), note, font=_font(sz["source"]), fill=(*MUTED, 255))
    d.text((m, H * 0.80 - sz["source"] * 1.4), _trim(p.get("source_line") or "Source needed (flagged for review)", 120), font=_font(sz["source"]), fill=(*MUTED, 255))

# ---- bar: "80%" ----------------------------------------------------------------------------------------------------------------
def draw_bar(d, p, prof, W, H, t, sz) -> None:
    value = float(p.get("value", 0)); qual = p.get("qualifier", ""); m = round(W * 0.08); acc = prof.accent
    a = ease(t / 0.6); k = ease((t - 0.5) / 1.8)               # the bar starts after the headline is up and takes 1.8 s
    shown = value * k; d.text((m, H * 0.16), p.get("kicker", "THE FIGURE").upper(), font=_font(sz["label"]), fill=(*acc, round(255 * a)))
    big = _font(round(sz["title"] * 3.0)); label = (qual + " " if qual else "") + f"{shown:.0f}%"
    d.text((m, H * 0.22), label, font=big, fill=(*acc, 255))
    bx0, bx1, by, bh = m, W - m, round(H * 0.50), round(H * 0.075); d.rounded_rectangle([bx0, by, bx1, by + bh], radius=bh // 2, fill=(*TRACK, 255))
    fw = (bx1 - bx0) * shown / 100.0
    if fw > bh: d.rounded_rectangle([bx0, by, bx0 + fw, by + bh], radius=bh // 2, fill=(*acc, 255))
    for pct in (0, 25, 50, 75, 100):
        x = bx0 + (bx1 - bx0) * pct / 100; d.line([x, by + bh + 8, x, by + bh + 22], fill=(*MUTED, 255), width=3); d.text((x, by + bh + 30), f"{pct}%", font=_font(sz["source"]), fill=(*MUTED, 255), anchor="ma")
    y = by + bh + 30 + sz["source"] * 2.6
    for ln in _wrap(d, _trim(p.get("context", ""), 200), _font(sz["body"]), W - 2 * m)[:3]:
        d.text((m, y), ln, font=_font(sz["body"]), fill=(*SOFT, round(255 * a))); y += sz["body"] * 1.3
    d.text((m, H * 0.80 - sz["source"] * 1.4), _trim(p.get("source_line") or "Source needed: this figure is not shown as established fact until a source is attached", 130), font=_font(sz["source"]), fill=(*MUTED, 255))

# ---- timeline: a sequence of events (labels come from the script) -------------------------------------------------------------
def draw_timeline(d, p, prof, W, H, t, sz) -> None:
    ev = p.get("events", []); m = round(W * 0.08); acc = prof.accent; n = max(1, len(ev))
    a = ease(t / 0.6); d.text((m, H * 0.12), p.get("kicker", "WHAT HAPPENED, IN ORDER").upper(), font=_font(sz["label"]), fill=(*acc, round(255 * a)))
    y = round(H * 0.46); x0, x1 = m + 230, W - m - 230; d.line([x0, y, x1, y], fill=(*TRACK, 255), width=8)
    cur = max([i for i, e in enumerate(ev) if t >= e["t0"]] or [-1])
    prog = x0 if cur < 0 else x0 + (x1 - x0) * (cur + ease((t - ev[cur]["t0"]) / 0.8)) / max(1, n - 1) if n > 1 else x0
    d.line([x0, y, min(prog, x1), y], fill=(*acc, 255), width=8)
    colw = (x1 - x0) / max(1, n - 1) if n > 1 else 0
    for i, e in enumerate(ev):
        x = x0 + (x1 - x0) * i / max(1, n - 1) if n > 1 else (x0 + x1) / 2; on = t >= e["t0"]; k = ease((t - e["t0"]) / 0.5) if on else 0.0
        r = 22 + 8 * k; d.ellipse([x - r, y - r, x + r, y + r], fill=(*(acc if on else TRACK), 255), outline=(*WHITE, 255 if on else 90), width=4)
        up = i % 2 == 0; ty = y - 70 if up else y + 70; anchor = "mb" if up else "mt"
        al = round(255 * (0.35 + 0.65 * k))
        d.text((x, ty), e.get("when", ""), font=_font(round(sz["body"] * 1.1)), fill=(*(WHITE if on else MUTED), al), anchor=anchor)
        room = max(1, int((ty - sz["body"] * 1.6 - (H * 0.12 + sz["label"] * 1.8)) // (sz["label"] * 1.25) + 1)) if up else 3      # labels above the line stop short of the heading
        lines = _wrap(d, e.get("label", ""), _font(sz["label"]), max(300, colw * 0.9 if n > 1 else 800)); cap = min(3, room)
        if len(lines) > cap: lines = lines[:cap]; lines[-1] = lines[-1].rstrip(" ,.;:") + "\u2026"
        for j, ln in enumerate(lines):
            yy = (ty - sz["body"] * 1.6 - (len(lines) - 1 - j) * sz["label"] * 1.25) if up else ty + sz["body"] * 1.5 + j * sz["label"] * 1.25
            d.text((x, yy), ln, font=_font(sz["label"]), fill=(*(SOFT if on else MUTED), al), anchor=anchor)
    d.text((m, H * 0.80 - sz["source"] * 2.7), "Order of events only; spacing is not to scale.", font=_font(sz["source"]), fill=(*MUTED, 255))
    d.text((m, H * 0.80 - sz["source"] * 1.4), _trim(p.get("source_line") or "From the narration. A composite example, not a patient record.", 130), font=_font(sz["source"]), fill=(*MUTED, 255))

# ---- captions ------------------------------------------------------------------------------------------------------------------
def caption_chunks(sentences: List[dict], t_origin: float, max_chars: int = 44) -> List[Tuple[float, float, str]]:
    """Phrase-level caption chunks (scene-local seconds). Each sentence is split at punctuation/length; the sentence's spoken interval is shared out in
    proportion to character count (an estimate: no word timings are available for TTS-less input)."""
    out: List[Tuple[float, float, str]] = []
    for s in sentences:
        text = " ".join(str(s["text"]).split()); a, b = float(s["start"]) - t_origin, float(s["end"]) - t_origin
        if not text or b <= a: continue
        b = max(a + 0.4, b - 0.12)    # leave the tail pause empty
        parts = [q.strip() for q in re.split(r"(?<=[,;:.!?])\s+", text) if q.strip()]; chunks: List[str] = []
        for q in parts:
            if chunks and len(chunks[-1]) + 1 + len(q) <= max_chars: chunks[-1] += " " + q
            else:
                while len(q) > max_chars + 8:
                    cut = q.rfind(" ", 0, max_chars); cut = cut if cut > 10 else max_chars; chunks.append(q[:cut].strip()); q = q[cut:].strip()
                chunks.append(q)
        total = sum(len(c) for c in chunks) or 1; t = a
        for c in chunks:
            dur = (b - a) * len(c) / total; out.append((t, t + dur, c)); t += dur
    return out

def draw_caption(im: Image.Image, text: str, H: int, alpha: float = 1.0) -> Image.Image:
    px = max(26, round(36 * H / 1080)); f = _font(px); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov); W = im.width
    lines = _wrap(d, text, f, W * 0.78); h = len(lines) * px * 1.3; y0 = H * 0.90 - h; wmax = max(d.textlength(l, font=f) for l in lines)
    d.rounded_rectangle([(W - wmax) / 2 - 24, y0 - 12, (W + wmax) / 2 + 24, y0 + h + 6], radius=14, fill=(6, 10, 20, round(190 * alpha)))
    for i, l in enumerate(lines): d.text((W / 2, y0 + i * px * 1.3), l, font=f, fill=(255, 255, 255, round(255 * alpha)), anchor="ma", stroke_width=1, stroke_fill=(0, 0, 0, round(255 * alpha)))
    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")


def caption_overlay_png(text: str, W: int, H: int) -> Image.Image:
    """The caption as a transparent RGBA layer (for ffmpeg overlay over footage)."""
    px = max(26, round(36 * H / 1080)); f = _font(px); ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    lines = _wrap(d, text, f, W * 0.78); h = len(lines) * px * 1.3; y0 = H * 0.90 - h; wmax = max(d.textlength(l, font=f) for l in lines)
    d.rounded_rectangle([(W - wmax) / 2 - 24, y0 - 12, (W + wmax) / 2 + 24, y0 + h + 6], radius=14, fill=(6, 10, 20, 190))
    for i, l in enumerate(lines): d.text((W / 2, y0 + i * px * 1.3), l, font=f, fill=(255, 255, 255, 255), anchor="ma", stroke_width=1, stroke_fill=(0, 0, 0, 255))
    return ov
