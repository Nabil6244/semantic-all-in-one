"""Thumbnails from the film's own pictures (docs/aviation/MASTER_PLAN.md section 6 packaging, step 15). Code only, no Flow.

    words(scenes) -> 'ONE AIRLINE BECOME TWO?'     2-5 of the narration's own words: the opening question without its lead-in
                                                   ('So why did ...'), else the first story line's airline names
    picks(plan) -> {hero, card, pair}              the film's stage elements to build on: the first aircraft sticker (hero), the most
                                                   telling full card (split tree > ownership > map > timeline), two airlines' stickers
    make(plan, scenes, out_dir) -> [png paths]     three 1280x720 variants:
        A  hero sticker huge on the black stage + the words in heavy type, key word yellow
        B  the full card (e.g. the split tree) tilted as a sticker + the words
        C  two airline stickers facing each other with a yellow arrow between + the year badge
    Nothing invented: every word is the narration's, every picture the film's own; offered after Render, never uploaded.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from PIL import Image, ImageDraw, ImageFilter

from . import stage as G
from . import style as S

W, H = 1280, 720
_LEAD = re.compile(r"^\s*(?:so|and|but)?\s*(?:why|how|what|when|who)\s+(?:did|does|do|is|was|were|are|could|would|has|have)\s+", re.I)
_STOP = set("the a an of to in on for and or but so that this it its was were is are be been".split())
FULL_RANK = ("split_tree", "ownership", "political_map", "route_map", "split_board", "logo_card")


def words(scenes: Sequence[Dict[str, Any]]) -> str:
    from . import retention as RT
    try:
        q_idx, _a, q = RT.opening_question(scenes)
    except Exception:
        q_idx, q = -1, ""
    if q_idx >= 0 and q:
        core = _LEAD.sub("", q).strip()
        w = core.split()
        if 2 <= len(w) <= 5:
            return core.upper()
        keep = [x for x in w if x.lower().strip("?,.") not in _STOP]
        if len(keep) >= 2:
            return " ".join(keep[:4]).upper().rstrip(",.") + ("?" if q.strip().endswith("?") and not keep[min(3, len(keep) - 1)].endswith("?") else "")
    from . import router as R
    for s in scenes[:12]:
        c = R.classify(str(s.get("text") or ""))
        names = [a["name"] for a in c.airlines]
        if names:
            return " ".join(dict.fromkeys(names))[:40].upper()
    return ""


def _year_at(plan: Any, sh: Dict[str, Any], t0: float) -> str:
    y = ""
    for at, yy in (sh.get("params") or {}).get("years") or []:
        if at <= t0 + 1e-6:
            y = yy
    return str(y)


def picks(plan: Any) -> Dict[str, Any]:
    """hero: the aircraft of the airline the stage shows most (latest of its stickers); card: the most telling full card; pair: the
    split tree's two children (else the first two airlines with stickers); year: the year on the badge when the card appears."""
    from collections import Counter
    from .story import era_type
    els, card, card_sh = [], None, None
    for sh in plan.shots:
        if sh.get("layer") == "stage.lay_stage":
            for e in (sh.get("params") or {}).get("elements") or []:
                els.append((sh, e))
    for k in FULL_RANK:
        hit = next(((sh, e) for sh, e in els if e["kind"] == k), None)
        if hit:
            card_sh, card = hit
            break
    planes = [(sh, e) for sh, e in els if e["kind"] == "aircraft"]
    count = Counter((e.get("args") or {}).get("airline") for _, e in els if (e.get("args") or {}).get("airline"))
    hero = max(planes, key=lambda p: (count[(p[1].get("args") or {}).get("airline")], p[1]["t0"]))[1] if planes else None
    year = _year_at(plan, card_sh, card["t0"]) if card is not None else ""
    pair: List[Dict[str, Any]] = []
    kids = ((card or {}).get("args") or {}).get("children") or [] if card is not None and card["kind"] == "split_tree" else []
    for kid in kids[:2]:
        al = kid.get("airline")
        own = next((e for _, e in planes if (e.get("args") or {}).get("airline") == al), None)
        typ = (own or {}).get("args", {}).get("type") or era_type(int(year) if str(year).isdigit() else 0)
        pair.append({"id": f"thumb_{al}", "kind": "aircraft", "args": {"type": typ, "airline": al, "width": 560}, "edge": True})
    if len(pair) < 2:
        pair, seen = [], set()
        for _, e in planes:
            al = (e.get("args") or {}).get("airline")
            if al and al not in seen:
                seen.add(al)
                pair.append(e)
        pair = pair[:2]
    if kids and len(pair) == 2:
        hero = pair[0]                       # a split story's subject is what came out of it, not its oldest ancestor
    if not year and planes:
        year = _year_at(plan, planes[0][0], planes[0][1]["t0"])
    return {"hero": hero, "card": card, "pair": pair, "year": year}


def _bg() -> Image.Image:
    return G._background(W, H).copy() if (W, H) == (G.W, G.H) else Image.new("RGBA", (W, H), S.STAGE_BG)


def _sprite(e: Dict[str, Any], width: int) -> Optional[Image.Image]:
    try:
        base = G._sprite(G._key(e))
    except Exception:
        return None
    f = width / max(1, base.width)
    return base.resize((width, max(1, int(base.height * f))), Image.LANCZOS)


def _type(canvas: Image.Image, text: str, box, key: str = "") -> None:
    """Heavy white type fitted into box (x0, y0, x1, y1), one key word yellow, black outline for contrast."""
    if not text:
        return
    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    words_ = text.split()
    size = 150
    while size > 40:
        f = S.font("title", size)
        lines, cur = [], ""
        for w in words_:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) > (x1 - x0) and cur:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
        lh = int(f.size * 1.05)
        if len(lines) * lh <= (y1 - y0) and max(d.textlength(ln, font=f) for ln in lines) <= (x1 - x0):
            break
        size -= 8
    key = key or max(words_, key=len)
    y = y0 + ((y1 - y0) - len(lines) * lh) / 2
    for ln in lines:
        x = x0
        for w in ln.split():
            col = S.YELLOW if w.strip("?,.!") == key.strip("?,.!") else S.WHITE
            d.text((x, y), w, font=f, fill=col, stroke_width=max(3, f.size // 14), stroke_fill=(0, 0, 0, 255))
            x += d.textlength(w + " ", font=f)
        y += lh


def _paste(canvas: Image.Image, im: Optional[Image.Image], cx: float, cy: float, rot: float = 0.0) -> None:
    if im is None:
        return
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2))) if (
        cx - im.width / 2 >= 0 and cy - im.height / 2 >= 0 and cx + im.width / 2 <= W and cy + im.height / 2 <= H) else \
        G._paste(canvas, im, cx, cy, 0.0, 1.0)


def make(plan: Any, scenes: Sequence[Dict[str, Any]], out_dir: Any) -> List[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    txt = words(scenes)
    pk = picks(plan)
    paths: List[str] = []

    if pk["hero"] is not None:                                         # A: the hero sticker, huge
        c = _bg()
        _paste(c, _sprite(pk["hero"], 840), 800, 480, -6)
        _type(c, txt, (50, 40, 700, 360))
        p = out / "thumb_A_hero.png"
        c.convert("RGB").save(p)
        paths.append(str(p))
    if pk["card"] is not None:                                         # B: the most telling card as a tilted sticker
        c = _bg()
        sp = _sprite(dict(pk["card"], args=dict(pk["card"].get("args") or {}, _k=1.0)), 760)
        _paste(c, sp, 860, 400, 4)
        _type(c, txt, (40, 60, 560, 660))
        p = out / "thumb_B_card.png"
        c.convert("RGB").save(p)
        paths.append(str(p))
    if len(pk["pair"]) == 2:                                           # C: two airlines facing each other
        c = _bg()
        left = _sprite(pk["pair"][0], 560)
        right = _sprite(pk["pair"][1], 560)
        if right is not None:
            right = right.transpose(Image.FLIP_LEFT_RIGHT)
        _paste(c, left, 330, 470, -4)
        _paste(c, right, 950, 470, 4)
        d = ImageDraw.Draw(c)
        d.polygon([(560, 470), (720, 470), (720, 440), (780, 480), (720, 520), (720, 490), (560, 490)], fill=S.YELLOW)
        _type(c, txt, (60, 30, 1220, 300))
        if pk["year"]:
            f = S.font("badge", 56)
            yb = str(pk["year"])
            tw = d.textlength(" ".join(yb), font=f)
            d.rounded_rectangle((W - tw - 90, 30, W - 40, 110), radius=12, fill=S.NAVY)
            d.text((W - tw - 65, 42), " ".join(yb), font=f, fill=S.WHITE)
        p = out / "thumb_C_pair.png"
        c.convert("RGB").save(p)
        paths.append(str(p))
    return paths
