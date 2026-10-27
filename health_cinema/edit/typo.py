"""Animated typography: staggered masked word rises with emphasis, tabular number builds, chips, and the phrase-synchronised caption track.
Text is only ever the narration's own words or labels the planner derived from them; nothing here writes content."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple
from PIL import Image, ImageDraw

from . import gfx, motion as M
from .gfx import WHITE, SOFT, MUTED

class Kinetic:
    """Block of text whose words rise out of a mask line by line, staggered, with emphasised words in the accent colour and an underline sweep."""
    def __init__(self, text: str, px: int, max_w: int, accent, weight: str = "demi", align: str = "left", emphasis: Optional[Set[int]] = None,
                 color=WHITE, line_gap: float = 1.16, words: Optional[Sequence[str]] = None):
        self.words = list(words) if words else text.split(); self.px, self.weight, self.accent, self.color = px, weight, accent, color
        self.emph = set(emphasis or ()); self.pos, self.w, self.h = gfx.layout(self.words, px, weight, max_w, line_gap, align); self.lh = int(px * line_gap)
        self.pad = int(px * 0.35)
    def draw(self, base: Image.Image, x: int, y: int, t: float, t0: float = 0.0, stagger: float = 0.07, dur: float = 0.6, t_out: Optional[float] = None,
             out_dur: float = 0.35, rise: Optional[int] = None, alpha: float = 1.0) -> None:
        rise = rise if rise is not None else int(self.px * 0.55)
        for i, (w, (wx, wy, li)) in enumerate(zip(self.words, self.pos)):
            k = M.out_cubic((t - t0 - i * stagger) / dur)
            if t_out is not None: k = min(k, 1 - M.in_cubic((t - t_out - i * stagger * 0.4) / out_dur))
            if k <= 0.004: continue
            em = i in self.emph; tile = gfx.text_tile(w, self.px, "bold" if em else self.weight, tuple(self.accent) if em else tuple(self.color))
            lh = self.lh + 2 * self.pad; canvas = Image.new("RGBA", (tile.width, lh), (0, 0, 0, 0)); canvas.paste(tile, (0, int((1 - k) * rise) + (lh - tile.height) // 2), tile)
            gfx.paste(base, canvas, x + wx - self.pad, y + wy - self.pad + (self.lh - lh) // 2 + self.pad // 2, alpha * min(1.0, k * 1.4))
            if em:
                u = M.out_cubic((t - t0 - i * stagger - dur * 0.7) / 0.5)
                if u > 0 and (t_out is None or t < t_out):
                    ww = int(gfx.text_size(w, self.px, "bold")[0] * u); yy = y + wy + int(self.px * 1.12)
                    gfx.fill_rect(base, (x + wx, yy, x + wx + ww, yy + max(3, self.px // 16)), self.accent, alpha)

def draw_number(base: Image.Image, s: str, x: int, y: int, px: int, color, align: str = "left", weight: str = "bold", alpha: float = 1.0, glow_r: int = 0) -> int:
    """Tabular number: every digit sits in a fixed cell, so a counting value never jitters. Returns the drawn width."""
    f = gfx.font(px, weight); cell = int(max(f.getlength(str(d)) for d in "0123456789")); widths = [cell if c.isdigit() else int(f.getlength(c)) for c in s]
    total = sum(widths); sx = x if align == "left" else x - total // 2 if align == "center" else x - total
    if glow_r:
        gt = gfx.text_tile(s, px, weight, tuple(color)); gl = gfx.glow(gt, glow_r, 1.4)
        gfx.paste(base, gl, sx - int(px * 0.35) + (total - (gt.width - 2 * int(px * 0.35))) // 2, y - int(px * 0.35), alpha * 0.5)
    cx = sx
    for c, w in zip(s, widths):
        tile = gfx.text_tile(c, px, weight, tuple(color)); pad = int(px * 0.35)
        gfx.paste(base, tile, cx + (w - (tile.width - 2 * pad)) // 2 - pad, y - pad, alpha); cx += w
    return total

def chip(base: Image.Image, text: str, x: int, y: int, px: int, accent, t: float, t0: float, t1: float, anchor: str = "left", dot: bool = True) -> Tuple[int, int, int, int]:
    """Pill with an accent dot; the pill grows open from the dot, text fades in after it, and both leave together."""
    a = M.fade_inout(t, t0, t1, 0.35, 0.3)
    tw, th = gfx.text_size(text, px, "medium", 0.02); pad = int(px * 0.55); w = tw + 2 * pad + (int(px * 0.9) if dot else 0); h = int(px * 1.9)
    bx = x if anchor == "left" else x - w; grow = M.out_cubic((t - t0) / 0.45); cw = max(h, int(w * grow))
    box = (bx, y, bx + cw, y + h)
    if a <= 0.004: return box
    panel = gfx.glass_panel(cw, h, h // 2, tuple(accent)); gfx.paste(base, panel, bx - 24, y - 24, a)
    if dot:
        r = int(px * 0.2); cx, cy = bx + pad + r, y + h // 2; gfx.paste(base, gfx.aa(2 * r + 4, 2 * r + 4, lambda d, ss: d.ellipse([2 * ss, 2 * ss, (2 * r + 2) * ss, (2 * r + 2) * ss], fill=(*accent, 255))), cx - r - 2, cy - r - 2, a)
    if grow > 0.8:
        tile = gfx.text_tile(text, px, "medium", SOFT, 0, 0.02); pad_t = int(px * 0.35)
        gfx.paste(base, tile, bx + pad + (int(px * 0.9) if dot else 0) - pad_t, y + (h - th) // 2 - pad_t, a * M.smooth((grow - 0.8) / 0.2))
    return (bx, y, bx + w, y + h)

def kicker(base: Image.Image, text: str, x: int, y: int, px: int, accent, t: float, t0: float = 0.0, rule: int = 80) -> None:
    """Small tracked uppercase label with a rule that draws out to its left."""
    a = M.out_cubic((t - t0) / 0.5)
    if a <= 0: return
    tile = gfx.text_tile(text.upper(), px, "demi", tuple(accent), 0, 0.16); pad = int(px * 0.35)
    gfx.fill_rect(base, (x, y + px // 2, x + int(rule * a), y + px // 2 + max(2, px // 12)), accent, 1.0)
    gfx.paste(base, tile, x + rule + 14 - pad, y - pad + 2, a)

# ---- captions ---------------------------------------------------------------------------------------------------------------------------
STOP = set("a an and are as at be but by for from had has have he her his i if in into is it its of on or she so than that the their them then there they this to was were what when which who will with you your not no".split())
EMPH_WORDS = set("closed preventable window dark never stroke warning hours days minutes seconds percent strokes eye vision brain heart blood recover recovers rehabilitation major ischemic every most".split())

def emphasis_indices(words: Sequence[str], limit: int = 2) -> Set[int]:
    """Which words of a phrase carry the meaning: digits/percentages first, then the narrative key words, then the longest content word."""
    scored = []
    for i, w in enumerate(words):
        c = re.sub(r"[^\w%']", "", w).lower()
        if not c or c in STOP: continue
        s = (3.0 if any(ch.isdigit() for ch in c) or "%" in c else 0) + (2.0 if c in EMPH_WORDS else 0) + min(1.0, len(c) / 12.0)
        scored.append((s, i))
    scored.sort(reverse=True)
    return {i for s, i in scored[:limit] if s >= 2.0}

@dataclass
class Phrase:
    t0: float; t1: float; text: str; words: List[Tuple[str, float, float]]; emph: Set[int]
    def as_json(self): return [round(self.t0, 3), round(self.t1, 3), self.text, [[w, round(a, 3), round(b, 3)] for w, a, b in self.words], sorted(self.emph)]

def build_phrases(sentences: Sequence[dict], silences: Sequence[Tuple[float, float]] = (), max_chars: int = 46) -> List[Phrase]:
    """Phrase-level captions. Phrase boundaries (at punctuation) are snapped to the narration's detected pauses when one lies within 0.45 s; word times
    inside a phrase are ESTIMATED by character share (no forced alignment is available), so emphasis is phrase-accurate, not word-accurate."""
    out: List[Phrase] = []
    for s in sentences:
        text = " ".join(str(s["text"]).split()); a, b = float(s["start"]), float(s["end"])
        if not text or b <= a: continue
        parts = [q.strip() for q in re.split(r"(?<=[,;:.!?])\s+", text) if q.strip()]; chunks: List[str] = []
        for q in parts:
            if chunks and len(chunks[-1]) + 1 + len(q) <= max_chars and not re.search(r"[.!?]$", chunks[-1]): chunks[-1] += " " + q
            else:
                while len(q) > max_chars + 8:
                    cut = q.rfind(" ", 0, max_chars); cut = cut if cut > 10 else max_chars; chunks.append(q[:cut].strip()); q = q[cut:].strip()
                chunks.append(q)
        end = max(a + 0.4, b - 0.10); total = sum(len(c) for c in chunks) or 1; bounds = [a]; acc = 0
        for c in chunks[:-1]:
            acc += len(c); est = a + (end - a) * acc / total
            near = [(abs((x + y) / 2 - est), (x + y) / 2) for x, y in silences if abs((x + y) / 2 - est) <= 0.45 and a + 0.3 < (x + y) / 2 < end - 0.3]
            bounds.append(min(near)[1] if near else est)
        bounds.append(end)
        for k, c in enumerate(chunks):
            p0, p1 = bounds[k], bounds[k + 1]; ws = c.split(); tl = sum(len(w) + 1 for w in ws) or 1; t = p0; wl = []
            for w in ws: d = (p1 - p0) * (len(w) + 1) / tl; wl.append((w, t, t + d)); t += d
            out.append(Phrase(p0, p1, c, wl, emphasis_indices(ws)))
    return out

class CaptionTrack:
    """Lower-third captions: current phrase centred in the safe area, words brighten as spoken, key words take the accent colour with an underline."""
    def __init__(self, phrases: Sequence[Phrase], U: gfx.Units, accent):
        self.ph, self.U, self.accent = list(phrases), U, tuple(accent); self.px = U.u(42); self._starts = [p.t0 for p in self.ph]
        self.scrim = Image.linear_gradient("L").resize((U.W, int(U.H * 0.36)), Image.BILINEAR).point([int(235 * (i / 255.0) ** 1.35) for i in range(256)])
    def active(self, t: float) -> Optional[Phrase]:
        for p in self.ph:
            if p.t0 - 0.05 <= t < p.t1 + 0.12: return p
        return None
    def draw(self, base: Image.Image, t: float) -> None:
        p = self.active(t)
        if p is None: return
        a = min(M.smooth((t - p.t0 + 0.05) / 0.14), M.smooth((p.t1 + 0.12 - t) / 0.14))
        if a <= 0.01: return
        U = self.U; words = [w for w, _, _ in p.words]; pos, bw, bh = gfx.layout(words, self.px, "medium", int(U.W * 0.68), 1.22, "center")
        x0 = (U.W - bw) // 2; y0 = int(U.H * 0.915) - bh; rise = int((1 - M.out_cubic((t - p.t0 + 0.05) / 0.2)) * U.u(10))
        band_h = self.scrim.height; layer = Image.new("RGB", (U.W, band_h), (0, 0, 8)); region = base.crop((0, U.H - band_h, U.W, U.H))
        base.paste(Image.composite(layer, region, self.scrim.point([int(v * a) for v in range(256)])), (0, U.H - band_h))
        for i, ((w, wt0, wt1), (wx, wy, li)) in enumerate(zip(p.words, pos)):
            spoken = t >= wt0 - 0.02; em = i in p.emph
            col = tuple(self.accent) if (em and spoken) else WHITE if spoken else (214, 222, 238)
            tile = gfx.text_tile(w, self.px, "demi" if spoken else "medium", col, 9); pad = gfx.tile_pad(self.px, 9)
            gfx.paste(base, tile, x0 + wx - pad, y0 + wy - pad + rise, a * (1.0 if spoken else 0.80))
            if em and spoken:
                k = M.out_cubic((t - wt0) / 0.35); ww = int(gfx.text_size(w, self.px, "demi")[0] * k)
                gfx.fill_rect(base, (x0 + wx, y0 + wy + int(self.px * 1.27) + rise, x0 + wx + ww, y0 + wy + int(self.px * 1.27) + rise + max(3, self.px // 14)), self.accent, a)
