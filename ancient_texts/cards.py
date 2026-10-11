"""The card kinds the existing graphics engine does not have, rendered as ordinary PNG stills.

The existing engine already draws name lower-thirds, big keywords, statistics and maps over footage (graphics/, editorial/
keyword_callouts.py, production/map_director.py) -- those are reused, not redrawn here. These are whole-frame cards:

  source_excerpt  a passage on parchment: a QUOTATION only when a person verified it against a named edition and locator
                  (claims.quote_for_card); otherwise it must be marked a summary, and it never wears quotation marks
  framed_object   a real object (a manuscript photo, a fragment) framed on charcoal, with a caption
  comparison      two real objects side by side with a label each (two readings, two texts, two dates)
  section_break   a title (and optional subtitle) on the dark grid that separates sections
  statement       a short phrase from the narration, set as type -- the last non-AI choice for a scene with no real
                  picture; no attribution, no quotation marks

A card is the scene's numbered file (asset_type `local`) to the renderer, so nothing in the render path changes. Deterministic: the same spec
gives the same pixels.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .issues import Issue

KINDS = ("source_excerpt", "framed_object", "comparison", "section_break", "statement")
REQUIRED = {
    "source_excerpt": ("text", "citation", "locator", "mode"),
    "framed_object": ("image", "caption"),
    "comparison": ("left_image", "left_label", "right_image", "right_label"),
    "section_break": ("title",),
    "statement": ("phrase",),
}
MAX_CHARS = {"text": 420, "caption": 90, "left_label": 40, "right_label": 40, "title": 70, "subtitle": 110, "phrase": 110,
             "citation": 140, "locator": 60}
STATEMENT_MAX_WORDS = 14

# palette (the reference's warm documentary look: charcoal, parchment, amber, sepia ink)
CHARCOAL = (21, 18, 15)
GRID = (58, 51, 43)
PARCHMENT = (233, 222, 198)
PARCHMENT_EDGE = (205, 187, 152)
INK = (43, 31, 20)
CREAM = (242, 232, 213)
AMBER = (201, 151, 63)
AMBER_SOFT = (201, 151, 63, 90)
MUTED = (170, 156, 135)


class CardError(ValueError):
    """The card cannot be made faithfully (missing data, text that does not fit, glyphs the fonts lack)."""


@dataclasses.dataclass(frozen=True)
class CardSpec:
    kind: str
    fields: Dict[str, str]
    claim_ids: tuple = ()
    scene: str = ""


# ---------------------------------------------------------------- fonts

def _bundled(name: str) -> Optional[Path]:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    p = root / "assets" / "fonts" / name
    return p if p.is_file() else None


_SERIF_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Georgia.ttf", r"C:\Windows\Fonts\georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    r"C:\Windows\Fonts\times.ttf",
)
_SERIF_BOLD_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf", r"C:\Windows\Fonts\georgiab.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
)


def font_path(role: str) -> Path:
    """serif / serif_bold for passages and titles (system Georgia or equivalent), sans for labels (bundled Inter)."""
    if role in ("serif", "serif_bold"):
        for c in (_SERIF_BOLD_CANDIDATES if role == "serif_bold" else ()) + _SERIF_CANDIDATES:
            if os.path.isfile(c):
                return Path(c)
    sans = _bundled("Inter-SemiBold.ttf") or _bundled("Inter-Regular.ttf")
    if sans is None:
        raise CardError("no usable font: assets/fonts/Inter-*.ttf is missing")
    return sans


def _font(role: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(role)), size)


def missing_glyphs(text: str, role: str = "serif") -> List[str]:
    """Characters the font draws as its 'missing glyph' box (compared with the box it draws for a private-use character)."""
    f = _font(role, 40)
    notdef = f.getmask("\ue000")
    nd = (notdef.size, bytes(notdef))
    out = []
    for ch in sorted(set(text or "")):
        if ch.isspace() or ch in out:
            continue
        m = f.getmask(ch)
        if (m.size, bytes(m)) == nd and m.size != (0, 0):
            out.append(ch)
    return out


# ---------------------------------------------------------------- validation

def validate(spec: CardSpec, *, verified_quote: Optional[tuple] = None) -> List[Issue]:
    """Required data present and within length; quotations only with a verified quote from the ledger."""
    issues: List[Issue] = []
    ref = spec.scene or spec.kind
    if spec.kind not in KINDS:
        return [Issue("unknown_card_kind", "hard", f"card kind {spec.kind!r} is not one of {KINDS}", ref)]
    for key in REQUIRED[spec.kind]:
        if not str(spec.fields.get(key) or "").strip():
            issues.append(Issue("card_missing_field", "hard", f"{spec.kind} card needs '{key}'", ref))
    for key, limit in MAX_CHARS.items():
        v = str(spec.fields.get(key) or "")
        if len(v) > limit:
            issues.append(Issue("card_text_too_long", "hard", f"{spec.kind} card: '{key}' is {len(v)} characters (max {limit})", ref))
    if spec.kind == "source_excerpt":
        mode = spec.fields.get("mode")
        if mode not in ("quotation", "summary"):
            issues.append(Issue("card_missing_field", "hard", "source_excerpt mode must be 'quotation' or 'summary'", ref))
        if mode == "quotation":
            if verified_quote is None:
                issues.append(Issue("quote_not_verified", "hard",
                                    "a quotation card needs a quotation a person verified against a named edition and locator", ref))
            elif " ".join(str(spec.fields.get("text") or "").split()) != " ".join(verified_quote[0].split()):
                issues.append(Issue("quote_altered", "hard", "the card's text differs from the verified quotation", ref))
    if spec.kind in ("framed_object", "comparison"):
        for key in ("image", "left_image", "right_image"):
            p = spec.fields.get(key)
            if p and not Path(p).is_file():
                issues.append(Issue("card_image_missing", "hard", f"{spec.kind} card: image not found: {p}", ref))
    if spec.kind == "statement":
        phrase = str(spec.fields.get("phrase") or "")
        if len(phrase.split()) > STATEMENT_MAX_WORDS:
            issues.append(Issue("card_text_too_long", "hard", f"statement card: {len(phrase.split())} words (max {STATEMENT_MAX_WORDS})", ref))
        if any(q in phrase for q in ('"', "«", "»", "“", "”")):
            issues.append(Issue("statement_looks_like_quote", "hard", "a statement card must not wear quotation marks", ref))
    if "credential" in spec.fields:
        issues.append(Issue("unbacked_credential", "hard",
                            "cards never print credentials; a name card is the existing lower third, with a credential only "
                            "when the ledger backs it", ref))
    return issues


# ---------------------------------------------------------------- drawing helpers

def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> List[str]:
    lines: List[str] = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font) <= width or not line:
                if draw.textlength(word, font=font) > width:
                    raise CardError(f"the word {word!r} is wider than the card")
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def _fit(draw, text: str, role: str, box_w: int, box_h: int, start: int, minimum: int, spacing: float = 1.32):
    size = start
    while size >= minimum:
        f = _font(role, size)
        try:
            lines = _wrap(draw, text, f, box_w)
        except CardError:
            size -= 2
            continue
        line_h = int(size * spacing)
        if line_h * len(lines) <= box_h:
            return f, lines, line_h
        size -= 2
    raise CardError(f"text does not fit in {box_w}x{box_h}px at the minimum readable size ({minimum}px): {text[:50]}…")


def _background(w: int, h: int, grid: bool) -> Image.Image:
    img = Image.new("RGB", (w, h), CHARCOAL)
    d = ImageDraw.Draw(img)
    if grid:
        step = max(24, h // 12)
        for x in range(0, w + 1, step):
            d.line([(x, 0), (x, h)], fill=GRID, width=max(1, h // 1080))
        for y in range(0, h + 1, step):
            d.line([(0, y), (w, y)], fill=GRID, width=max(1, h // 1080))
    # vignette
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([-w * 0.15, -h * 0.25, w * 1.15, h * 1.25], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=h // 6))
    dark = Image.new("RGB", (w, h), (8, 7, 6))
    return Image.composite(img, dark, mask)


def _image_fit(path: str, max_w: int, max_h: int) -> Image.Image:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_w, max_h), Image.LANCZOS)
        return im.copy()


def _framed(canvas: Image.Image, path: str, cx: int, cy: int, max_w: int, max_h: int, mat: int) -> Tuple[int, int, int, int]:
    pic = _image_fit(path, max_w - 2 * mat, max_h - 2 * mat)
    fw, fh = pic.width + 2 * mat, pic.height + 2 * mat
    x0, y0 = cx - fw // 2, cy - fh // 2
    shadow = Image.new("RGBA", (fw + mat * 4, fh + mat * 4), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([mat * 2, mat * 2, fw + mat * 2, fh + mat * 2], fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(mat))
    canvas.paste(shadow, (x0 - mat * 2 + mat // 2, y0 - mat * 2 + mat), shadow)
    ImageDraw.Draw(canvas).rectangle([x0, y0, x0 + fw, y0 + fh], fill=(247, 244, 236))
    canvas.paste(pic, (x0 + mat, y0 + mat))
    return x0, y0, x0 + fw, y0 + fh


def _tag(draw, text: str, cx: int, top: int, h: int) -> None:
    f = _font("sans", max(14, h // 40))
    label = str(text).upper()
    tw = draw.textlength(label, font=f)
    pad = h // 90
    box = [cx - tw / 2 - pad * 2, top, cx + tw / 2 + pad * 2, top + f.size + pad * 2]
    draw.rectangle(box, fill=AMBER)
    draw.text((cx - tw / 2, top + pad), label, font=f, fill=CHARCOAL)


def _highlight_spans(lines: List[str], phrase: str) -> List[Tuple[int, int, int]]:
    """(line index, start char, end char) of the highlighted phrase inside wrapped lines (word-level, case-insensitive)."""
    if not phrase:
        return []
    target = phrase.lower().split()
    flat: List[Tuple[int, int, int, str]] = []
    for li, line in enumerate(lines):
        pos = 0
        for w in line.split(" "):
            flat.append((li, pos, pos + len(w), w.lower().strip(",.;:!?¡¿«»\"'")))
            pos += len(w) + 1
    n = len(target)
    for i in range(len(flat) - n + 1):
        if [x[3] for x in flat[i:i + n]] == [t.strip(",.;:!?¡¿«»\"'") for t in target]:
            merged: Dict[int, Tuple[int, int]] = {}
            for li, a, b, _ in flat[i:i + n]:                 # one band per line, not one box per word
                lo, hi = merged.get(li, (a, b))
                merged[li] = (min(lo, a), max(hi, b))
            return [(li, a, b) for li, (a, b) in sorted(merged.items())]
    return []


# ---------------------------------------------------------------- render

def render(spec: CardSpec, out_path, size: Tuple[int, int] = (1920, 1080), *, verified_quote: Optional[tuple] = None) -> Path:
    """Validate, then draw. Raises CardError (with every hard problem) rather than drawing an unfaithful card."""
    hard = [i for i in validate(spec, verified_quote=verified_quote) if i.severity == "hard"]
    if hard:
        raise CardError("; ".join(i.message for i in hard))
    w, h = size
    f = spec.fields
    text_for_glyphs = " ".join(str(v) for k, v in f.items() if k not in ("image", "left_image", "right_image", "mode"))
    missing = missing_glyphs(text_for_glyphs, "serif") and missing_glyphs(text_for_glyphs, "sans")
    if missing:
        raise CardError(f"the available fonts cannot draw: {' '.join(missing[:10])}")

    if spec.kind == "source_excerpt":
        img = _background(w, h, grid=False)
        d = ImageDraw.Draw(img, "RGBA")
        px0, py0, px1, py1 = int(w * 0.14), int(h * 0.12), int(w * 0.86), int(h * 0.88)
        d.rectangle([px0 + h // 120, py0 + h // 90, px1 + h // 120, py1 + h // 90], fill=(0, 0, 0, 120))
        d.rectangle([px0, py0, px1, py1], fill=PARCHMENT, outline=PARCHMENT_EDGE, width=max(2, h // 360))
        pad = int(h * 0.07)
        label = "Summary" if f["mode"] == "summary" else ""
        top = py0 + pad
        if label:
            lf = _font("sans", max(14, h // 42))
            d.text((px0 + pad, top), label.upper(), font=lf, fill=AMBER)
            top += int(lf.size * 1.8)
        cite_f = _font("sans", max(14, h // 44))
        cite = f"{f['citation']} — {f['locator']}"
        cite_lines = _wrap(d, cite, cite_f, px1 - px0 - 2 * pad)
        cite_h = int(cite_f.size * 1.35) * len(cite_lines)
        box_w, box_h = px1 - px0 - 2 * pad, (py1 - pad - cite_h - int(h * 0.03)) - top
        body = f["text"] if f["mode"] == "summary" else f"“{f['text']}”"
        font, lines, line_h = _fit(d, body, "serif", box_w, box_h, start=max(26, h // 18), minimum=max(18, h // 40))
        spans = _highlight_spans(lines, f.get("highlight", ""))
        for li, a, b in spans:
            line = lines[li]
            x = px0 + pad + d.textlength(line[:a], font=font)
            x2 = px0 + pad + d.textlength(line[:b], font=font)
            y = top + li * line_h
            d.rectangle([x - 4, y + line_h * 0.08, x2 + 4, y + line_h * 0.92], fill=AMBER_SOFT)
        for li, line in enumerate(lines):
            d.text((px0 + pad, top + li * line_h), line, font=font, fill=INK)
        cy = py1 - pad - cite_h
        for li, line in enumerate(cite_lines):
            d.text((px0 + pad, cy + li * int(cite_f.size * 1.35)), line, font=cite_f, fill=(110, 88, 60))

    elif spec.kind == "framed_object":
        img = _background(w, h, grid=False)
        x0, y0, x1, y1 = _framed(img, f["image"], w // 2, int(h * 0.44), int(w * 0.62), int(h * 0.66), mat=max(6, h // 90))
        d = ImageDraw.Draw(img)
        font, lines, line_h = _fit(d, f["caption"], "sans", int(w * 0.7), int(h * 0.14), start=max(22, h // 26), minimum=max(16, h // 54))
        for li, line in enumerate(lines):
            tw = d.textlength(line, font=font)
            d.text(((w - tw) / 2, y1 + h * 0.04 + li * line_h), line, font=font, fill=CREAM)

    elif spec.kind == "comparison":
        img = _background(w, h, grid=True)
        d = ImageDraw.Draw(img)
        top_pad = 0
        if f.get("title"):
            tf, tl, tlh = _fit(d, f["title"], "serif_bold", int(w * 0.8), int(h * 0.12), start=max(26, h // 22), minimum=max(18, h // 45))
            for li, line in enumerate(tl):
                tw = d.textlength(line, font=tf)
                d.text(((w - tw) / 2, h * 0.07 + li * tlh), line, font=tf, fill=CREAM)
            top_pad = int(h * 0.06)
        mat = max(5, h // 110)
        for side, cx in (("left", int(w * 0.29)), ("right", int(w * 0.71))):
            x0, y0, x1, y1 = _framed(img, f[f"{side}_image"], cx, int(h * 0.46) + top_pad, int(w * 0.36), int(h * 0.5), mat)
            label = f[f"{side}_label"]
            lf = _font("sans", max(14, h // 40))
            if ImageDraw.Draw(img).textlength(label.upper(), font=lf) > w * 0.36:
                raise CardError(f"comparison label too wide: {label}")
            _tag(ImageDraw.Draw(img), label, cx, y1 + int(h * 0.03), h)

    elif spec.kind == "section_break":
        img = _background(w, h, grid=True)
        d = ImageDraw.Draw(img)
        tf, tl, tlh = _fit(d, f["title"], "serif_bold", int(w * 0.8), int(h * 0.3), start=max(40, h // 11), minimum=max(24, h // 30))
        block = tlh * len(tl)
        y = h * 0.45 - block / 2
        for li, line in enumerate(tl):
            tw = d.textlength(line, font=tf)
            d.text(((w - tw) / 2, y + li * tlh), line, font=tf, fill=AMBER)
        if f.get("subtitle"):
            sf, sl, slh = _fit(d, f["subtitle"], "serif", int(w * 0.7), int(h * 0.16), start=max(22, h // 28), minimum=max(16, h // 54))
            for li, line in enumerate(sl):
                tw = d.textlength(line, font=sf)
                d.text(((w - tw) / 2, y + block + h * 0.03 + li * slh), line, font=sf, fill=CREAM)

    else:  # statement
        img = _background(w, h, grid=False)
        d = ImageDraw.Draw(img, "RGBA")
        font, lines, line_h = _fit(d, f["phrase"], "serif", int(w * 0.72), int(h * 0.5), start=max(40, h // 13), minimum=max(24, h // 34))
        spans = _highlight_spans(lines, f.get("highlight", ""))
        y0 = h / 2 - line_h * len(lines) / 2
        for li, a, b in spans:
            line = lines[li]
            lx = (w - d.textlength(line, font=font)) / 2
            x = lx + d.textlength(line[:a], font=font)
            x2 = lx + d.textlength(line[:b], font=font)
            d.rectangle([x - 6, y0 + li * line_h + line_h * 0.05, x2 + 6, y0 + li * line_h + line_h * 0.95], fill=(201, 151, 63, 210))
        for li, line in enumerate(lines):
            tw = d.textlength(line, font=font)
            d.text(((w - tw) / 2, y0 + li * line_h), line, font=font, fill=CREAM)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, format="PNG", optimize=False)
    return out


def text_regions_fit(spec: CardSpec, size: Tuple[int, int] = (1920, 1080)) -> bool:
    """True when the card renders without overflow at this size (used by QC on the plan, without writing a file)."""
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as d:
            render(spec, Path(d) / "probe.png", size)
        return True
    except CardError:
        return False
