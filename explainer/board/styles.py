"""Reference-style board elements (schema v1.3, cue kind `visual`): picture tiles and rings with a short hand-lettered label, labelled diagram boxes, a navy tag, a scroll, and a typed
line in a role colour. Every element is measured (`measure`) and drawn (`sprite`, `draw_line`) from the narration's own words; nothing here generates art (icons come from the existing
code-drawn registry). Sizes follow what is visible in the reference frames (docs/explainer/explainer_visual_fidelity_report.md): large tiles, labels of one to three words, a coloured
typed line for the punchline."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from . import icons as I
from . import layout as LY
from . import theme as T

TH = T.THEME
STYLES = ("tile", "circle", "box", "lite", "tag", "scroll", "line", "set", "figure", "crowd", "prop")
CARTOON_STYLES = ("set", "figure", "crowd", "prop")      # schema v1.4: the cartoon kit (explainer/cartoon); drawn from prebuilt assets
ROLE_TEXT = {"blue": (52, 84, 160), "green": (44, 124, 86), "gold": (172, 116, 22), "red": (176, 52, 60), "ink": TH.ink}
ROLE_FILL = {"blue": (48, 100, 200), "green": (46, 140, 92), "gold": (226, 170, 40), "red": (204, 66, 64), "ink": (60, 62, 70)}
RING = {"blue": (62, 104, 196), "green": (44, 140, 92), "gold": (242, 166, 40), "red": (204, 66, 64), "ink": (60, 62, 70)}
NAVY, YELLOW = (24, 36, 78), (255, 228, 84)
PAPER, ROD = (240, 232, 200), (130, 86, 52)
TILE, RINGD = 300, 270
LABEL_GAP = 14


def _lines(text: str, width: int, max_px: int, min_px: int, max_lines: int) -> Optional[Tuple[int, List[str]]]:
    return LY.fit_text(text, width, 10 ** 4, "body", max_px, min_px, max_lines)


def measure(style: str, text: str, params: Dict[str, Any], asset: str = "") -> Optional[Dict[str, Any]]:
    """{w, h, px, lines} for the element, or None when the text cannot be fitted (a problem on the cue)."""
    text = (text or "").strip()
    if style in CARTOON_STYLES:
        return measure_cartoon(style, params)
    if style == "line":
        width = int(params.get("width", 900))
        fit = LY.fit_text(text, width, 10 ** 4, "body", int(params.get("px", 56)), 40, int(params.get("lines", 1)))
        if fit is None:
            return None
        f = T.font("body", fit[0])
        asc, desc = f.getmetrics()
        return {"w": width, "h": len(fit[1]) * (asc + desc) + 12, "px": fit[0], "lines": fit[1]}
    if style in ("tile", "circle"):
        w = 330 if style == "tile" else 300
        box = TILE if style == "tile" else RINGD
        if not text:
            return {"w": w, "h": box + 10, "px": 0, "lines": []}
        fit = _lines(text, w - 16, int(params.get("px", 58)), 44, 2)
        if fit is None:
            return None
        f = T.font("body", fit[0])
        asc, desc = f.getmetrics()
        return {"w": w, "h": box + LABEL_GAP + len(fit[1]) * (asc + desc) + 10, "px": fit[0], "lines": fit[1]}
    if style in ("box", "lite", "tag"):
        for px in range(int(params.get("px", 56)), 43, -4):
            f = T.font("body", px)
            tr = px * TH.tracking_em
            lines = LY.wrap(T.body_text(TH, text).split(), f, 520, tr)
            if len(lines) <= 2 and max(T.tracked_width(f, ln, tr) for ln in lines) <= 520:
                asc, desc = f.getmetrics()
                tw = max(T.tracked_width(f, ln, tr) for ln in lines)
                w, h = int(tw + 84), int(len(lines) * (asc + desc) + 54)
                if style == "tag":
                    return {"w": w + 40, "h": h + 40, "px": px, "lines": lines, "inner": (w, h)}
                return {"w": w, "h": h, "px": px, "lines": lines}
        return None
    if style == "scroll":
        fit = _lines(text, 600, 66, 44, 2)
        return None if fit is None else {"w": 780, "h": 300, "px": fit[0], "lines": fit[1]}
    return None


def _text_block(d: ImageDraw.ImageDraw, lines: List[str], px: int, box: Tuple[int, int, int, int], color) -> None:
    f = T.font("body", px)
    asc, desc = f.getmetrics()
    lh = asc + desc
    y = box[1] + ((box[3] - box[1]) - lh * len(lines)) / 2
    tr = px * TH.tracking_em
    for ln in lines:
        T.draw_tracked(d, ((box[0] + box[2]) / 2, y), ln, f, color, tr, anchor="m")
        y += lh


@lru_cache(maxsize=96)
def sprite(style: str, text: str, role: str, asset: str, w: int, h: int, px: int, lines: Tuple[str, ...], inner: Tuple[int, int] = (0, 0)) -> Image.Image:
    ss = 2
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    ring = RING.get(role, RING["blue"])
    lab = ROLE_TEXT.get(role, ROLE_TEXT["blue"])
    if style == "tile":
        d.rounded_rectangle([(w - TILE) // 2 * ss, 4 * ss, ((w - TILE) // 2 + TILE) * ss, (4 + TILE) * ss], radius=30 * ss, fill=(252, 252, 252), outline=ring, width=10 * ss)
    elif style == "circle":
        d.ellipse([(w - RINGD) // 2 * ss, 4 * ss, ((w - RINGD) // 2 + RINGD) * ss, (4 + RINGD) * ss], fill=(252, 252, 252), outline=ring, width=10 * ss)
    elif style in ("box", "lite"):
        fill = ROLE_FILL.get(role, ROLE_FILL["blue"]) if style == "box" else tuple(int(255 - (255 - c) * 0.16) for c in ROLE_FILL.get(role, ROLE_FILL["blue"]))
        d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=20 * ss, fill=fill, outline=TH.outline if style == "box" else ring, width=(3 if style == "box" else 5) * ss)
    elif style == "tag":
        iw, ih = inner
        d.rounded_rectangle([(w - iw) // 2 * ss, (h - ih) // 2 * ss, ((w - iw) // 2 + iw) * ss, ((h - ih) // 2 + ih) * ss], radius=18 * ss, fill=NAVY, outline=(10, 16, 40), width=4 * ss)
    elif style == "scroll":
        d.rectangle([30 * ss, 34 * ss, (w - 30) * ss, (h - 34) * ss], fill=PAPER, outline=TH.outline, width=4 * ss)
        for x0 in (6, w - 34):
            d.rounded_rectangle([x0 * ss, 10 * ss, (x0 + 28) * ss, (h - 10) * ss], radius=12 * ss, fill=ROD, outline=TH.outline, width=4 * ss)
    sp = big.resize((w, h), Image.LANCZOS)
    d2 = ImageDraw.Draw(sp)
    if style in ("tile", "circle"):
        box = TILE if style == "tile" else RINGD
        if asset:
            isz = 190 if style == "tile" else 160
            ic = I.icon_sprite(asset, role if role != "ink" else "blue", isz)
            sp.paste(ic, ((w - isz) // 2, 4 + (box - isz) // 2), ic)
        if lines:
            f = T.font("body", px)
            asc, desc = f.getmetrics()
            _text_block(d2, list(lines), px, (0, box + LABEL_GAP, w, box + LABEL_GAP + len(lines) * (asc + desc)), lab)
    elif style in ("box", "lite"):
        _text_block(d2, list(lines), px, (0, 0, w, h), (255, 255, 255) if style == "box" else TH.ink)
    elif style == "tag":
        iw, ih = inner
        _text_block(d2, list(lines), px, ((w - iw) // 2, (h - ih) // 2, (w - iw) // 2 + iw, (h - ih) // 2 + ih), YELLOW)
        sp = sp.rotate(3.0, resample=Image.BICUBIC, expand=False)
    elif style == "scroll":
        _text_block(d2, list(lines), px, (60, 40, w - 60, h - 40), TH.ink)
    return sp


def draw_line(im: Image.Image, it, age: float, frame_no: int = 0) -> None:
    """A typed line in a role colour. Synced lines (the director's): word k appears on clip frame it.reveal_frames[k], the caption ladder of schema v1.2, so the text arrives as it is
    spoken; otherwise character k appears when age >= k / cps. The line keeps its final place and width from the first frame (centred lines are centred on the whole text)."""
    d = ImageDraw.Draw(im)
    f = T.font("body", it.px)
    tr = it.px * TH.tracking_em
    synced = bool(it.reveal_frames) and it.rung in (1, 2)
    color = ROLE_TEXT.get(it.role, ROLE_TEXT["ink"]) if it.tint else TH.ink
    center = it.align == "center"
    asc, desc = f.getmetrics()
    y = it.rect[1] + 4
    if synced:
        remaining = sum(1 for fr in it.reveal_frames if fr <= frame_no)
    else:
        remaining = min(sum(len(t) for t in it.lines), int(age * it.cps) + 1)
    for text in it.lines:
        if synced:
            ws = text.split(" ")
            take = min(len(ws), remaining)
            remaining -= take
            shown = " ".join(ws[:take])
        else:
            shown = text[:max(0, remaining)]
            remaining -= len(text)
        full = T.tracked_width(f, text, tr)
        x = it.rect[0] + ((it.rect[2] - it.rect[0]) - full) / 2 if center else it.rect[0]
        if shown:
            T.draw_tracked(d, (x, y), shown, f, color, tr)
        y += asc + desc


def measure_cartoon(style: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """{w, h, px, lines, ox, oy} for a cartoon element: the size of its opaque pixels (the collision box); (ox, oy) is where they start inside the sprite."""
    from ..cartoon import kit
    if kit.problem(style, params):
        return None
    if style == "set":
        return {"w": 1920, "h": 1080, "px": 0, "lines": [], "ox": 0, "oy": 0}
    if style == "figure":
        h = int(params.get("height", 420))
        bb = kit.cast_bbox(params.get("cast", "blue"), params.get("pose", "idle"), params.get("kit", "a"), h, bool(params.get("flip", False)))
    elif style == "prop":
        bb = kit.prop_sprite(params["prop"], int(params.get("height", 260))).getchannel("A").getbbox()
    else:
        bb = kit.crowd_sprite(int(params.get("n", 6)), int(params.get("height", 170)), int(params.get("seed", 0))).getchannel("A").getbbox()
    return {"w": bb[2] - bb[0], "h": bb[3] - bb[1], "px": 0, "lines": [], "ox": bb[0], "oy": bb[1]}


def cartoon_sprite(style: str, params: Dict[str, Any]) -> Image.Image:
    """The element's pixels cropped to the opaque box (what is pasted at rect)."""
    from ..cartoon import kit
    if style == "set":
        return kit.set_image(params["set"], params.get("tod", "day")).convert("RGBA")
    if style == "figure":
        im = kit.cast_sprite(params.get("cast", "blue"), params.get("pose", "idle"), params.get("kit", "a"), int(params.get("height", 420)), bool(params.get("flip", False)))
    elif style == "prop":
        im = kit.prop_sprite(params["prop"], int(params.get("height", 260)))
    else:
        im = kit.crowd_sprite(int(params.get("n", 6)), int(params.get("height", 170)), int(params.get("seed", 0)))
    return im.crop(im.getchannel("A").getbbox())
