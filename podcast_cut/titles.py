"""Packaging: title choices, YouTube chapters and the thumbnail.

Titles follow the reference channel's pattern, with the real length and the episode's main theme:
    "The Only {N} Minutes You Need To {change} | {Speaker} Motivation"
plus the other shapes it uses ("Watch This When Life Feels Too Heavy | ...", "Rewire Your Mind For Success | ...").
Chapters: 0:00 first, every chapter at least 2 minutes, named from its own most-said words.
Thumbnail: the sharpest well-lit frame of the speaker's camera, graded darker, 2-3 big words on the left.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import look
from .picker import STOP, _tok

THEMES = [
    ({"mind", "brain", "thoughts", "thinking", "rewire"}, "Rewire Your Mind"),
    ({"control", "choose", "choice", "power"}, "Take Back Control Of Your Life"),
    ({"fear", "afraid", "scared", "courage"}, "Conquer Your Fear"),
    ({"discipline", "habits", "habit", "routine"}, "Build Unbreakable Self-Discipline"),
    ({"grief", "breakup", "heartbreak", "loss", "past", "letting"}, "Let Go Of Your Old Self"),
    ({"stress", "anxiety", "pressure", "adrenaline"}, "Master Your Stress"),
    ({"dopamine", "motivation", "reward", "drive"}, "Master Your Dopamine"),
    ({"success", "goals", "goal", "career", "ambition"}, "Rewire Your Mind For Success"),
    ({"purpose", "meaning", "potential"}, "Reach Your True Potential"),
    ({"change", "rebuild", "transform", "reinvent"}, "Rebuild Yourself"),
]
EXTRA = ["Watch This When Life Feels Too Heavy", "Watch This Before You Give Up On Yourself", "Rewire Your Mind For Success"]


def speaker_from(meta: Dict) -> str:
    """'Breakups, Sadness ... - Dr Andrew Huberman (4K)' -> 'Andrew Huberman' (else the uploader)."""
    title = str(meta.get("title") or "")
    m = re.search(r"[-|–—]\s*([^-|–—]+?)\s*(\(.*\))?\s*$", title)
    name = m.group(1) if m else ""
    name = re.sub(r"\b(Dr\.?|Prof\.?|Professor|PhD|MD)\s+", "", name).strip(" .")
    if 1 < len(name.split()) <= 4 and all(w[:1].isupper() for w in name.split()):
        return name
    return str(meta.get("uploader") or "").strip()


def theme(text: str) -> str:
    toks = Counter(_tok(w) for w in text.split())
    best, best_n = "Rebuild Yourself", 0
    for words, phrase in THEMES:
        n = sum(toks[w] for w in words)
        if n > best_n:
            best, best_n = phrase, n
    return best


def titles(meta: Dict, clips: Sequence, length_s: float, speaker: str = "") -> List[str]:
    speaker = speaker or speaker_from(meta) or "Podcast"
    mins = max(1, int(round(length_s / 60)))
    text = " ".join(getattr(c, "text", "") for c in clips)
    main = theme(text)
    tail = f" | {speaker} Motivation"
    out = [f"The Only {mins} Minutes You Need To {main}{tail}"]
    for words, phrase in THEMES:
        if phrase != main and sum(text.lower().count(w) for w in words) >= 6 and len(out) < 3:
            out.append(f"The Only {mins} Minutes You Need To {phrase}{tail}")
    out += [e + tail for e in EXTRA if (e + tail) not in out]
    return out[:6]


def _label(text: str) -> str:
    c = Counter(t for t in (_tok(w) for w in text.split()) if len(t) > 3 and t not in STOP)
    words = [w for w, _ in c.most_common(3)]
    return " & ".join(w.capitalize() for w in words[:2]) or "Part"


def chapters(plan: Dict, clips: Sequence, min_len: float = 120.0) -> List[Dict]:
    """[{'t': out seconds, 'title'}], first at 0:00, each at least min_len."""
    segs = plan["segments"]
    out = [{"t": 0.0, "title": "Intro"}]
    group, g_start = [], None
    for s in segs:
        c = clips[s["clip"]]
        if c.role == "hook":
            continue
        if g_start is None:
            g_start = s["out_start"]
        group.append(c.text)
        if s["out_end"] - g_start >= min_len:
            out.append({"t": g_start, "title": _label(" ".join(group))})
            group, g_start = [], None
    if group and g_start is not None:
        if plan["length"] - g_start >= 30 or len(out) == 1:
            out.append({"t": g_start, "title": _label(" ".join(group))})
        else:
            pass
    if len(out) > 1 and out[1]["t"] < 10:
        out.pop(0)
        out[0]["t"] = 0.0
    return out


def chapters_text(chs: List[Dict]) -> str:
    def f(t):
        t = int(t)
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"
    return "\n".join(f"{f(c['t'])} {c['title']}" for c in chs) + "\n"


def _frame(video: Path, t: float, dest: Path) -> Optional[Path]:
    from providers.media_clip.ffmpeg_clip import _ffmpeg
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", look.fit_filter(), str(dest)], capture_output=True)
    return dest if r.returncode == 0 and dest.is_file() else None


def _sharpness(path: Path) -> float:
    import numpy as np
    from PIL import Image
    g = np.asarray(Image.open(path).convert("L").resize((480, 270)), dtype=np.float32)
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    mean = g.mean()
    # a close-up against a dark set beats a wide shot: favour frames whose dark area is large and whose middle is busy
    dark = float((g < 45).mean())
    h, w = g.shape
    mid = g[h // 6: h * 5 // 6, w // 4: w * 3 // 4]
    return float(lap.var()) * (1.0 if 25 < mean < 170 else 0.4) * (0.6 + dark) * (0.5 + float(mid.std()) / 64)


def thumbnail(camera_frames: Sequence[tuple], words: str, speaker: str, dest: Path, tmp: Path) -> Optional[Path]:
    """camera_frames: [(video, seconds)]. Picks the sharpest, grades it, writes the words. None if no frame was readable."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    tmp.mkdir(parents=True, exist_ok=True)
    frames = []
    for k, (v, t) in enumerate(camera_frames[:16]):
        f = _frame(Path(v), t, tmp / f"thumb_{k:02d}.jpg")
        if f:
            frames.append(f)
    if not frames:
        return None
    best = max(frames, key=_sharpness)
    img = Image.open(best).convert("RGB")
    img = ImageEnhance.Brightness(ImageEnhance.Color(img).enhance(0.75)).enhance(0.8)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    w, h = img.size
    shade = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(shade)
    for x in range(w // 2):                       # darker on the left, where the words go
        sd.line([(x, 0), (x, h)], fill=int(170 * (1 - x / (w / 2))))
    img = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), img, shade)
    d = ImageDraw.Draw(img)
    lines = [ln for ln in re.split(r"\s+", words.upper().strip()) if ln]
    rows = [" ".join(lines[i:i + 2]) for i in range(0, len(lines), 2)][:3]
    size = int(h * 0.15)
    fnt = look.font(size)
    y = h * 0.5 - len(rows) * size * 0.55
    for r in rows:
        while d.textlength(r, font=fnt) > w * 0.5 and size > 40:
            size -= 6
            fnt = look.font(size)
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((w * 0.05, y + 4), r, font=fnt, fill=(0, 0, 0, 220))
        img = Image.alpha_composite(img.convert("RGBA"), sh.filter(ImageFilter.GaussianBlur(6))).convert("RGB")
        d = ImageDraw.Draw(img)
        d.text((w * 0.05, y), r, font=fnt, fill=(255, 214, 120) if r is rows[-1] else (255, 255, 255))
        y += size * 1.1
    if speaker:
        d.text((w * 0.05, y + size * 0.15), speaker.upper(), font=look.font(int(h * 0.045), bold=False), fill=(230, 230, 230))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, quality=92)
    return dest
