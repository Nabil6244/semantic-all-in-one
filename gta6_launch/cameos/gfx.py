"""Animated info graphics for the manifest videos, timed to the spoken words (Whisper words.json).

gfx.json lists cards per beat; every item is anchored to a phrase the narrator says, so each line appears at the moment
it is spoken. Card types:
  trophy  - pop-up top-right (slides in)            {"type":"trophy","phrase","title","sub"}
  steps   - checklist card, right side              {"type":"steps","title","items":[{"label","phrase","warn"?}]}
  keypad  - 4-digit keypad, digits light one by one {"type":"keypad","phrase","code_phrase","digits","note","note_phrase"}
  stats   - upgrade bars that fill one by one       {"type":"stats","title","items":[{"label","phrase"}]}
  notes   - pinned sticky notes, one by one         {"type":"notes","title","items":[{"text","phrase","red"?}]}

cues(beats, words, spec) -> [(start, end, key)] with no overlap per card; draw(img, key) paints one state.
Animation = short still states (fade/slide over 0.24 s), so it fits the overlay track's state list."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from game_launch import look as L  # noqa: E402

W, H = 1920, 1080
YEL, WHITE, RED, GREEN = (255, 214, 10), (255, 255, 255), (255, 72, 72), (80, 230, 140)
CARD, CARD_X, CARD_W, CARD_Y = (10, 10, 15, 215), W - 48 - 640, 640, 190
HOLD = 4.0                     # a card stays this long after its last line (never past the beat)
STEPS_IN = (0.33, 0.66, 1.0)   # fade/slide states, 0.08 s each


def _anchor(words, phrase, lo, hi):
    from align import find
    sub = words[:hi]
    i, r = find(sub, phrase, lo)
    return (sub[i]["s"], r) if r >= 0.55 else (None, r)


def cues(beats, words, spec):
    out, misses = [], []
    for b in beats:
        lo = next((i for i, w in enumerate(words) if w["s"] >= b["cut_in_sec"] - 0.05), len(words))
        hi = next((i for i, w in enumerate(words) if w["s"] >= b["cut_out_sec"]), len(words))
        for ci, card in enumerate(spec.get(b["beat_id"], [])):
            cid = f"{b['beat_id']}#{ci}"
            items = card.get("items") or [card]
            times = []
            for it in items:
                t, r = _anchor(words, it["phrase"], lo, hi)
                if t is None:
                    misses.append((cid, it["phrase"], round(r, 2)))
                times.append(t)
            if all(t is None for t in times):
                continue
            first = min(t for t in times if t is not None)
            times = [t if t is not None else first for t in times]       # an unmatched line shows with the first one
            if card["type"] == "keypad":
                code_t, _ = _anchor(words, card["code_phrase"], lo, hi)
                note_t, _ = _anchor(words, card["note_phrase"], lo, hi)
                code_t = code_t or first + 1.0
                marks = [first] + [code_t + 0.4 * k for k in range(len(card["digits"]))] + ([note_t] if note_t else [])
            else:
                marks = sorted(times)
            end = min(b["cut_out_sec"], max(marks) + HOLD + (3.0 if card["type"] == "trophy" else 0))
            # state list: level n = first n lines shown; each new level fades in over a few short states
            states = []
            for lvl, t in enumerate(marks, 1):
                for k, a in enumerate(STEPS_IN):
                    states.append((t + 0.08 * k, (cid, card["type"], lvl, a)))
            states.sort(key=lambda x: x[0])
            for (t, key), nxt in zip(states, states[1:] + [(end, None)]):
                if nxt[0] > t + 0.005 and t < end:
                    out.append((round(t, 3), round(min(nxt[0], end), 3), key))
    return out, misses


def _font(n):
    return L.font(L.F_HEAD, n)


def _layer():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def _blend(img, layer, alpha):
    if alpha < 1.0:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)
    img.alpha_composite(layer)


def _card(d, x, y, w, h, accent=YEL):
    d.rounded_rectangle((x, y, x + w, y + h), radius=26, fill=CARD)
    d.rounded_rectangle((x, y, x + 10, y + h), radius=5, fill=accent + (255,))


def _title(d, x, y, text, color=YEL):
    d.text((x, y), text, font=_font(40), fill=color + (255,))
    return y + 62


def _wrap(d, text, f, width):
    out, cur = [], ""
    for w_ in text.split():
        if cur and d.textlength(cur + " " + w_, font=f) > width:
            out.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    return out + [cur]


def draw(img, key, spec_card):
    cid, kind, lvl, alpha = key
    lay = _layer()
    d = ImageDraw.Draw(lay)
    slide = int((1.0 - alpha) * 60)
    if kind == "trophy":
        x, y, w, h = W - 48 - 660 + slide, 48, 660, 132
        d.rounded_rectangle((x, y, x + w, y + h), radius=24, fill=(14, 14, 20, 235))
        cx, cy = x + 70, y + 66                                           # simple gold cup icon
        d.ellipse((cx - 44, cy - 44, cx + 44, cy + 44), fill=(60, 48, 10, 255))
        d.polygon([(cx - 22, cy - 26), (cx + 22, cy - 26), (cx + 14, cy + 6), (cx - 14, cy + 6)], fill=YEL + (255,))
        d.rectangle((cx - 4, cy + 6, cx + 4, cy + 18), fill=YEL + (255,))
        d.rectangle((cx - 16, cy + 18, cx + 16, cy + 24), fill=YEL + (255,))
        d.text((x + 132, y + 22), spec_card["sub"].upper(), font=_font(28), fill=(200, 200, 210, 255))
        d.text((x + 132, y + 62), spec_card["title"], font=_font(44), fill=WHITE + (255,))
        _blend(img, lay, alpha)
        return
    x0 = CARD_X + slide
    if kind == "keypad":
        digits, w = spec_card["digits"], CARD_W
        h = 88 + 196 + (64 if lvl > 1 + len(digits) else 0)
        _card(d, x0, CARD_Y, w, h)
        y = _title(d, x0 + 34, CARD_Y + 26, "DREAM KEYPAD CODE")
        lit = max(0, min(len(digits), lvl - 1))
        bw, gap = 118, 22
        bx = x0 + (w - (4 * bw + 3 * gap)) // 2
        for k, ch in enumerate(digits):
            on = k < lit
            r = (bx + k * (bw + gap), y + 10, bx + k * (bw + gap) + bw, y + 10 + 160)
            d.rounded_rectangle(r, radius=18, fill=(255, 214, 10, 255) if on else (40, 40, 50, 255),
                                outline=(255, 214, 10, 255), width=3)
            f = _font(110)
            tw = d.textlength(ch, font=f)
            d.text((r[0] + (bw - tw) / 2, r[1] + 14), ch if on else "•", font=f, fill=(10, 10, 15, 255) if on else (120, 120, 130, 255))
        if lvl > 1 + len(digits):
            d.text((x0 + 34, y + 192), spec_card["note"], font=_font(34), fill=WHITE + (255,))
        _blend(img, lay, alpha if lvl == 1 else 1.0)
        if lvl > 1 and alpha < 1.0:      # only the newest digit/line fades: redraw handled by the caller's state order
            pass
        return
    items = spec_card["items"]
    shown = items[:lvl]
    if kind == "notes":
        f = _font(44)
        y = CARD_Y
        d2 = d
        for i, it in enumerate(shown):
            lines = _wrap(d2, it["text"], f, CARD_W - 90)
            h = 40 + 56 * len(lines)
            tilt_x = x0 + (18 if i % 2 else 0)
            col = (255, 236, 140, 255) if not it.get("red") else (255, 255, 255, 255)
            d2.rectangle((tilt_x, y, tilt_x + CARD_W - 30, y + h), fill=col)
            d2.ellipse((tilt_x + CARD_W / 2 - 26, y - 10, tilt_x + CARD_W / 2 - 6, y + 10), fill=(200, 30, 30, 255))
            ty = y + 20
            for ln in lines:
                d2.text((tilt_x + 30, ty), ln, font=f, fill=(200, 20, 20, 255) if it.get("red") else (25, 20, 10, 255))
                ty += 56
            y += h + 18
            if y > 840:
                break
    else:
        f = _font(38)
        rows = []
        for it in shown:
            rows.append(_wrap(d, it["label"], f, CARD_W - 150))
        h = 26 + 62 + sum(18 + 48 * len(r) for r in rows) + 20
        if kind == "stats":
            h = 26 + 62 + len(shown) * 100 + 20
        _card(d, x0, CARD_Y, CARD_W, min(h, 860 - CARD_Y))
        y = _title(d, x0 + 34, CARD_Y + 26, spec_card["title"])
        for i, it in enumerate(shown):
            newest = i == len(shown) - 1
            if kind == "stats":
                d.text((x0 + 34, y), it["label"].upper(), font=_font(34), fill=WHITE + (255,))
                d.text((x0 + CARD_W - 120, y), "+1", font=_font(34), fill=GREEN + (255,))
                fill = alpha if newest else 1.0
                d.rounded_rectangle((x0 + 34, y + 50, x0 + CARD_W - 40, y + 74), radius=12, fill=(45, 45, 55, 255))
                d.rounded_rectangle((x0 + 34, y + 50, x0 + 34 + int((CARD_W - 74) * (0.55 + 0.45 * fill)), y + 74), radius=12,
                                    fill=GREEN + (255,))
                y += 100
                continue
            col = RED if it.get("warn") else YEL
            n = i + 1
            d.ellipse((x0 + 34, y + 2, x0 + 34 + 46, y + 48), fill=col + (255,))
            num = str(n)
            d.text((x0 + 34 + 23 - d.textlength(num, font=_font(30)) / 2, y + 6), num, font=_font(30), fill=(10, 10, 15, 255))
            for ln in rows[i]:
                d.text((x0 + 100, y + 2), ln, font=f, fill=(WHITE if not newest else col) + (255,))
                y += 48
            y += 18
            if y > 840:
                break
    _blend(img, lay, 1.0 if lvl > 1 else alpha)
