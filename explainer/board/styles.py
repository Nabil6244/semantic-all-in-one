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
STYLES = ("tile", "circle", "box", "lite", "tag", "scroll", "line", "set", "figure", "crowd", "prop", "stamp", "plate", "cross", "bubble", "spot", "bars", "photo", "node")
MOTION_STYLES = ("stamp", "plate", "cross")                       # schema v1.5: the motion kit (explainer/motion); drawn and animated there
RECIPE_STYLES = ("bars", "photo", "node")                                   # opt-in composition recipes (director/compose_recipes.py): an animated bar and an archival picture card
BUBBLE_STYLES = ("bubble", "spot")                                  # opt-in dialogue (explainer/motion/bubbles.py): a speech bubble and a stage spotlight
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
    if style in BUBBLE_STYLES:
        from ..motion import bubbles as BU
        return {"bubble": BU.measure_bubble, "spot": BU.measure_spot}[style](text, params)
    if style in MOTION_STYLES:
        from ..motion import sprites as MS
        return {"stamp": MS.measure_stamp, "plate": MS.measure_plate, "cross": MS.measure_cross}[style](text, params)
    if style == "node":                          # a diagram node: rounded box with an optional picture at its left (params.solid fills it, params.wmax caps its width, params.px/minpx the text size)
        wmax, solid = int(params.get("wmax", 560)), bool(params.get("solid", False))
        icon_w = 124 if asset else 0
        for px in range(int(params.get("px", 60)), int(params.get("minpx", 48)) - 1, -4):
            f = T.font("body", px)
            tr = px * TH.tracking_em
            lines = LY.wrap(T.body_text(TH, text).split(), f, wmax - 56 - icon_w, tr)
            if len(lines) <= int(params.get("lines", 2)) and max(T.tracked_width(f, ln, tr) for ln in lines) <= wmax - 56 - icon_w:
                asc, desc = f.getmetrics()
                tw = max(T.tracked_width(f, ln, tr) for ln in lines)
                return {"w": max(int(tw + 56 + icon_w), int(params.get("minw", 0))), "h": max(int(len(lines) * (asc + desc) + 46), 150 if asset else 0, int(params.get("minh", 0))), "px": px, "lines": lines, "inner": (1 if solid else 0, icon_w)}
        return None
    if style == "bars":
        bh = int(params.get("box_h", 560))
        return {"w": int(params.get("box_w", 240)), "h": bh, "px": int(params.get("px", 48)), "lines": [text]} if text else None
    if style == "photo":
        w, h = int(params.get("w", 560)), int(params.get("h", 520))
        fit = LY.fit_text(text, w - 30, 10 ** 4, "body", 52, 40, 1) if text else None
        return {"w": w, "h": h, "px": fit[0], "lines": fit[1]} if fit else None
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
        wrap_w = int(params.get("wrap", 520))                  # params.wrap: a narrower text width (composition recipes); the default is unchanged
        for px in range(int(params.get("px", 56)), 43, -4):
            f = T.font("body", px)
            tr = px * TH.tracking_em
            lines = LY.wrap(T.body_text(TH, text).split(), f, wrap_w, tr)
            if len(lines) <= 2 and max(T.tracked_width(f, ln, tr) for ln in lines) <= wrap_w:
                asc, desc = f.getmetrics()
                tw = max(T.tracked_width(f, ln, tr) for ln in lines)
                w, h = max(int(tw + 84), int(params.get("min_w", 0))), int(len(lines) * (asc + desc) + 54)       # min_w: a tier of a pyramid is wider than its text
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
    elif style == "node":
        solid = bool(inner[0])
        fill = ROLE_FILL.get(role, ROLE_FILL["blue"]) if solid else tuple(int(255 - (255 - c) * 0.16) for c in ROLE_FILL.get(role, ROLE_FILL["blue"]))
        d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=22 * ss, fill=fill, outline=TH.outline if solid else ring, width=(3 if solid else 5) * ss)
        if asset:
            dm = min(h - 28, 112)
            d.ellipse([16 * ss, (h - dm) // 2 * ss, (16 + dm) * ss, ((h - dm) // 2 + dm) * ss], fill=(252, 252, 252), outline=ring, width=4 * ss)
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
    elif style == "node":
        icon_w = inner[1]
        if asset:
            dm = min(h - 28, 112)
            isz = int(dm * 0.72)
            ic = I.icon_sprite(asset, role if role != "ink" else "blue", isz)
            sp.paste(ic, (16 + (dm - isz) // 2, (h - isz) // 2), ic)
        _text_block(d2, list(lines), px, (icon_w, 0, w, h), (255, 255, 255) if inner[0] else TH.ink)
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
        bb = kit.crowd_sprite(int(params.get("n", 6)), int(params.get("height", 170)), int(params.get("seed", 0)), *([str(params["kind"])] if params.get("kind") else [])).getchannel("A").getbbox()
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
        im = kit.crowd_sprite(int(params.get("n", 6)), int(params.get("height", 170)), int(params.get("seed", 0)), *([str(params["kind"])] if params.get("kind") else []))
    return im.crop(im.getchannel("A").getbbox())


def _ease_out(k: float) -> float:
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


BAR_GROW_S = 0.6


def draw_bar(im: Image.Image, it, age: float) -> None:
    """One bar of an animated bar chart: its height grows with ease-out over BAR_GROW_S from the base; the spoken value rides on its top and the label is under the base."""
    vp = it.vparams or {}
    x0, y0, x1, y1 = it.rect
    if vp.get("divider"):                       # a centre line between two columns that grows downward; the spoken marker word sits on it when it is wide enough for it
        cur = max(6, int((y1 - y0) * _ease_out(age / BAR_GROW_S)))
        d = ImageDraw.Draw(im)
        cx = (x0 + x1) // 2
        d.rounded_rectangle([cx - 5, y0, cx + 5, y0 + cur], radius=5, fill=ROLE_FILL["ink"], outline=TH.outline, width=2)
        if x1 - x0 >= 150 and age >= 0.3:
            f = T.font("body", it.px)
            tw = T.tracked_width(f, it.text, it.px * TH.tracking_em)
            ym = (y0 + y1) // 2
            d.rounded_rectangle([cx - tw / 2 - 22, ym - it.px * 0.8, cx + tw / 2 + 22, ym + it.px * 0.8], radius=int(it.px * 0.8), fill=ROLE_FILL["ink"], outline=TH.outline, width=3)
            T.draw_tracked(d, (cx, ym - it.px * 0.55), it.text, f, (255, 255, 255), it.px * TH.tracking_em, anchor="m")
        return
    ratio = max(0.04, min(1.0, float(vp.get("ratio", 0.5))))
    lab_h, val_h = 72, 84
    base = y1 - lab_h
    full = (base - y0 - val_h) * ratio
    cur = max(4, int(full * _ease_out(age / BAR_GROW_S)))
    bw = int(vp.get("bar_w", 170))
    bx0 = (x0 + x1) // 2 - bw // 2
    ss = 2
    big = Image.new("RGBA", (bw * ss, cur * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle([0, 0, bw * ss - 1, cur * ss + 14 * ss], radius=14 * ss, fill=ROLE_FILL.get(it.role, ROLE_FILL["blue"]), outline=TH.outline, width=4 * ss)
    sp = big.resize((bw, cur), Image.LANCZOS)
    im.paste(sp, (bx0, base - cur), sp)
    d = ImageDraw.Draw(im)
    d.line([(x0 + 6, base + 2), (x1 - 6, base + 2)], fill=TH.outline, width=5)
    f = T.font("body", it.px)
    tr = it.px * TH.tracking_em
    if age >= 0.2:
        T.draw_tracked(d, ((x0 + x1) / 2, base - cur - val_h + 8), it.text, f, ROLE_TEXT.get(it.role, ROLE_TEXT["blue"]), tr, anchor="m")
    label = str(vp.get("label", ""))
    if label:
        fl = T.font("body", 52)
        T.draw_tracked(d, ((x0 + x1) / 2, base + 8), label, fl, TH.ink, 52 * TH.tracking_em, anchor="m")


@lru_cache(maxsize=24)
def photo_sprite(path: str, w: int, h: int, caption: str, px: int, role: str) -> Image.Image:
    """An archival picture card: a paper frame with the picture inside (the whole picture, never cropped); when it does not fill the frame (a portrait or a tall painting) a blurred,
    scaled copy of the same picture fills the sides. The name sits under the frame."""
    from PIL import ImageFilter
    cap_h = 78
    ss = 2
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([0, 0, w * ss - 1, (h - cap_h + 14) * ss], radius=18 * ss, fill=(250, 246, 232), outline=TH.outline, width=5 * ss)
    sp = big.resize((w, h), Image.LANCZOS)
    pad = 22
    iw, ih = w - 2 * pad, h - cap_h - 2 * pad + 14
    src = Image.open(path).convert("RGB")
    k = max(iw / src.width, ih / src.height)
    fill = src.resize((max(iw, int(src.width * k)), max(ih, int(src.height * k))), Image.BILINEAR)
    fl, ft = (fill.width - iw) // 2, (fill.height - ih) // 2
    fill = fill.crop((fl, ft, fl + iw, ft + ih)).filter(ImageFilter.GaussianBlur(22))
    fill = Image.blend(fill, Image.new("RGB", fill.size, (40, 36, 30)), 0.35)
    k2 = min(iw / src.width, ih / src.height)
    pic = src.resize((max(1, int(src.width * k2)), max(1, int(src.height * k2))), Image.LANCZOS)
    fill.paste(pic, ((iw - pic.width) // 2, (ih - pic.height) // 2))
    sp.paste(fill, (pad, pad))
    ImageDraw.Draw(sp).rectangle([pad - 1, pad - 1, pad + iw, pad + ih], outline=TH.outline, width=3)
    if caption:
        _text_block(ImageDraw.Draw(sp), [caption], px, (0, h - cap_h + 10, w, h), ROLE_TEXT.get(role, ROLE_TEXT["blue"]))
    return sp
