"""Three thumbnail candidates for every StarMap video, made after the render from the video's own strongest moments:

    hero     the biggest close-up of a planet (the frame where a body fills the most of the screen)
    number   the full-screen number moment (its figure is the thumbnail's text)
    journey  a craft on its journey (a path shot with the craft in it)

Each is drawn by the engine as a still (STARMAP_STILLS), then finished at 1280x720 with a contrast lift, a dark gradient on
the text side and big outlined text: the title's strongest words, or the number. The author picks one (or uses the script
doctor's thumbnail text instead)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ENGINE = Path(__file__).resolve().parent.parent / "starmap-engine"
FONT = ENGINE / "assets" / "fonts" / "Montserrat-VF.ttf"
SIZE = (1280, 720)
YELLOW, WHITE = (251, 224, 64), (255, 255, 255)
_WEAK = set("the a an of to in on at by for with from and or is was its into how why what who when where".split())


def moments(spec: Dict[str, Any]) -> List[Tuple[str, float, str]]:
    """(kind, narration t, text) for up to three distinct moments."""
    out: List[Tuple[str, float, str]] = []
    foot = [(f["start"], f["end"]) for f in spec.get("footage", [])]
    on_map = lambda t: not any(a - 0.5 <= t <= b + 0.5 for a, b in foot)   # noqa: E731
    moves = spec.get("camera", {}).get("moves", [])
    closes = [m for m in moves if m["to"].get("fill") and on_map(m["t"] + m["dur"] * 0.85)]
    if closes:
        m = max(closes, key=lambda m: min(float(m["to"]["fill"]), 0.6))
        out.append(("hero", round(m["t"] + max(0.2, m["dur"] * 0.85), 2), ""))
    nums = [L for L in spec.get("layers", []) if L.get("type") == "big_number"]
    if nums:
        L = nums[0]
        out.append(("number", round(L["start"] + 1.7, 2), f"{_num(L['value'], L.get('decimals', 0))} {L.get('unit', '')}".strip()))
    trips = [m for m in moves if m["to"].get("path") and on_map(m["t"] + m["dur"] * 0.7)]
    if trips:
        m = max(trips, key=lambda m: m["dur"])
        out.append(("journey", round(m["t"] + m["dur"] * 0.7, 2), ""))
    return out[:3]


def _num(v: Any, dec: int) -> str:
    try:
        return f"{float(v):,.{int(dec)}f}"
    except (TypeError, ValueError):
        return str(v)


CLUTTER = {"photo_card", "stat_chip", "caption", "mission_clock", "status_badge", "title", "footnote", "time_jump", "channel_name",
           "body_labels", "tracker", "distance", "pointer", "big_number", "galaxy_guide"}   # a thumbnail is the picture, not the panels


def punch(title: str, n: int = 4) -> str:
    """The title's head in its own words, in capitals ('THE JOURNEY OF VOYAGER 1: ...' -> 'JOURNEY OF VOYAGER 1'); a longer
    head keeps only its strong words."""
    head = re.split(r"[:\-–—|]", title or "")[0]
    words = re.findall(r"[A-Za-z0-9'.]+", head)
    while words and words[0].lower() in ("the", "a", "an"):
        words = words[1:]
    if len(words) > n:
        words = [w for w in words if w.lower() not in _WEAK][:n]
    return " ".join(words).upper() or (title or "").upper()[:24]


def _font(px: int):
    from PIL import ImageFont

    f = ImageFont.truetype(str(FONT), px)
    try:
        f.set_variation_by_name("Black")
    except Exception:
        try:
            f.set_variation_by_axes([900])
        except Exception:
            pass
    return f


def compose(still: Path, out: Path, text: str, kind: str) -> Path:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

    im = Image.open(still).convert("RGB").resize(SIZE, Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.18)
    im = ImageEnhance.Color(im).enhance(1.25)
    im = ImageEnhance.Sharpness(im).enhance(1.3)
    if text:
        # the words go on the darker half (away from the planet); a dark band under them there only
        # the words go opposite the picture's centre of brightness (the planet, the bright path), never over it
        g = im.convert("L").resize((160, 90))
        px_ = list(g.getdata())
        mass = sum(px_) or 1
        cx = sum((i % 160) * v for i, v in enumerate(px_)) / mass
        left_dark = cx >= 80
        if kind != "number":
            # space is black: slide the picture so its subject sits in the third away from the words
            shift = int(((0.68 if left_dark else 0.32) - cx / 160) * SIZE[0])
            canvas = Image.new("RGB", SIZE, (0, 0, 0))
            canvas.paste(im, (shift, 0))
            im = canvas
        shade = Image.new("L", SIZE, 0)
        d = ImageDraw.Draw(shade)
        for x in range(SIZE[0]):
            u = x if left_dark else SIZE[0] - 1 - x
            a = int(170 * max(0.0, 1 - u / (SIZE[0] * 0.55))) if kind != "number" else 0
            d.line([(x, 0), (x, SIZE[1])], fill=a)
        im = Image.composite(Image.new("RGB", SIZE, (0, 0, 0)), im, shade.filter(ImageFilter.GaussianBlur(30)))
        draw = ImageDraw.Draw(im)
        lines = _wrap(text, 2 if kind != "number" else 1)
        px = 118 if kind != "number" else 104
        while px > 50 and max(draw.textlength(ln, font=_font(px)) for ln in lines) > SIZE[0] * (0.56 if kind != "number" else 0.9):
            px -= 6
        f = _font(px)
        y = (SIZE[1] - len(lines) * px * 1.05) / 2 if kind != "number" else SIZE[1] - px * 1.6
        for i, ln in enumerate(lines):
            w = draw.textlength(ln, font=f)
            x = (60 if left_dark else SIZE[0] - 60 - w) if kind != "number" else (SIZE[0] - w) / 2
            draw.text((x, y + i * px * 1.05), ln, font=f, fill=YELLOW if i == 0 else WHITE, stroke_width=max(4, px // 14), stroke_fill=(0, 0, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=92)
    return out


def _wrap(text: str, max_lines: int) -> List[str]:
    """Two lines at most, split near the middle, never leaving a number or a short word alone ('VOYAGER' / '1')."""
    words = text.split()
    if max_lines == 1 or len(words) <= 2:
        return [text]
    best = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:])))
                                                   + (99 if len(words[k]) <= 2 or words[k][0].isdigit() or len(words[k - 1]) <= 2 else 0))
    return [" ".join(words[:best]), " ".join(words[best:])]


def make_thumbnails(spec_path: Path, out_dir: Path, stem: str, title: str, node: str = "node",
                    log: Callable[[str], None] = lambda s: None) -> List[Path]:
    """Draws the moments as stills with the engine and finishes them; returns the thumbnail files (none if it cannot)."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    picks = moments(spec)
    if not picks:
        return []
    base = Path(out_dir) / f".{stem}.thumbs"
    job = dict(spec, output=str(base), layers=[L for L in spec.get("layers", []) if L.get("type") not in CLUTTER])
    job.pop("segment_cache", None)
    jp = Path(out_dir) / f".{stem}.thumbs.spec.json"
    jp.write_text(json.dumps(job), encoding="utf-8")
    env = dict(os.environ, STARMAP_STILLS=",".join(str(t) for _, t, _ in picks))
    try:
        r = subprocess.run([node, str(ENGINE / "render.mjs"), str(jp), str(base)], cwd=str(ENGINE), env=env, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            log(f"[StarMap] thumbnails skipped: {(r.stderr or r.stdout).strip()[-200:]}")
            return []
        out = []
        for i, (kind, t, text) in enumerate(picks, 1):
            still = Path(f"{base}.t{t}.jpg")
            if still.is_file():
                out.append(compose(still, Path(out_dir) / f"{stem} - thumbnail {i} ({kind}).jpg", text or punch(title), kind))
                still.unlink(missing_ok=True)
        return out
    finally:
        jp.unlink(missing_ok=True)
