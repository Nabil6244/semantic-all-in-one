"""One frame of a Rep Theory scene: frame(ctx, scene, t) -> RGB image, with t in seconds from the scene's start (it may exceed the scene's length: the last state holds, which is what lets the
next scene's transition read the outgoing frame). Every moving part is keyed to a time taken from the narration (see planner.py); parts of one idea are joined (a ring on the bottle, a line to
the equation; a line from the gripping forearm to the anatomy picture) so a scene reads as one composition."""
from __future__ import annotations
import math
from PIL import Image, ImageDraw, ImageFilter

from . import draw as D, theme as T, cards as K2

def _rel(sc: dict, t_abs: float) -> float: return t_abs - sc["start"]

def _camera(sc: dict, t: float) -> tuple:
    """Slow push-in with a small drift, different direction per scene so consecutive scenes do not move identically; eased so it never stops dead or jerks."""
    d = max(2.0, sc["end"] - sc["start"]); p = T.ease_in_out(min(1.0, t / d)); k = sc["no"] % 3
    return 1.0 + 0.06 * p, (-26, 18, -10)[k] * p, (10, -12, 14)[k] * p

ENTRANCE_S, LATE_MAX_S = 0.45, 0.9
from .states import STAMP_HOLD_S
from . import states as ST

def _page_layer(ctx: D.Ctx, sc: dict, pg: dict, t: float, x: float, anchor_y: float) -> Image.Image:
    """One callout page drawn on its own transparent layer (so it can fade out when the next page replaces it); times are relative to the scene.
    The page's main element (its headline, else its number) is on screen from the page's first frame; a short entrance only moves it into place. Further elements keep their word-synchronised time but
    never later than LATE_MAX_S after the page starts, so a page is never left showing a bare kicker or rule while the narration talks about it."""
    layer = Image.new("RGBA", (ctx.W, ctx.H), (0, 0, 0, 0)); pa = _rel(sc, pg["at"]); h_at = min(_rel(sc, pg["headline_at"]), pa + (0.0 if pg["headline"] else LATE_MAX_S)) if pg["headline"] else pa
    v_raw = _rel(sc, pg["value_at"]) if "value_at" in pg else h_at + 0.25; v_at = v_raw if pg["headline"] else pa      # a number that comes with a headline keeps the word it is said on; alone it is the main element
    chips = [(c["text"], (t - _rel(sc, c["at"])) / 0.5) for c in pg["chips"]]
    D.callout_column(layer, ctx, pg["headline"], (t - h_at) / ENTRANCE_S, pg["value"], (t - v_at) / ENTRANCE_S, chips, x=x, anchor_y=anchor_y, kicker=pg.get("kicker", ""), k_p=(t - pa) / 0.5, floor=0.6)
    return layer

def callouts(cv: Image.Image, ctx: D.Ctx, sc: dict, t: float, x: float, anchor_y: float = 0.5) -> None:
    """The page the narration is on; when the next sentence's page arrives the old one fades out over 0.3 s as the new one slides in."""
    pages = sc["pages"]
    if not pages: return
    live = [i for i, p in enumerate(pages) if _rel(sc, p["at"]) <= t + 1e-6] or [0]; i = live[-1]
    if i > 0 and t - _rel(sc, pages[i]["at"]) < 0.3: D.overlay_paste(cv, _page_layer(ctx, sc, pages[i - 1], t, x, anchor_y), 1 - (t - _rel(sc, pages[i]["at"])) / 0.3)
    D.overlay_paste(cv, _page_layer(ctx, sc, pages[i], t, x, anchor_y))

def _label_ring(cv, ctx, box, ring, t, sc):
    if ring is None: return
    p = (t - _rel(sc, ring["at"])) / 0.9; w, h = box[2] - box[0], box[3] - box[1]
    D.glow_ring(cv, ctx, box[0] + ring["x"] * w, box[1] + ring["y"] * h, ring["r"] * w, p, t - _rel(sc, ring["at"]) - 0.9)

def _live_ring(sc, t):
    live = [r for r in sc.get("rings", []) if r["at"] - sc["start"] <= t]; ring = live[-1] if live else None      # the newest ring named so far; a ring at the same spot keeps its pulse
    return [r for r in live if (r["x"], r["y"]) == (ring["x"], ring["y"])][0] if ring else None

def frame(ctx: D.Ctx, sc: dict, t: float, prev_section=None, tag: bool = True) -> Image.Image:
    cv = ctx.backdrop(); kind = sc["kind"]; zoom, dx, dy = _camera(sc, t)
    if sc.get("tint"): _tint(cv, ctx, (t - _rel(sc, sc["tint"]["at"])) / 0.7)
    if kind != "tier": D.ghost_word(cv, ctx, sc.get("topic", ""), t)
    if kind == "hold" and sc["art"] and sc["prop"]:
        flip = (t - _rel(sc, sc["flip_at"])) / 0.55 if sc.get("flip_at") is not None else 0.0
        box, neck, fore = D.hold_figure(cv, ctx, sc["art"], sc["prop"], 0.30, 0.54, 0.84, t, [_rel(sc, q) for q in sc["squeezes"]], flip, zoom, dx, dy)
        D.floor_line(cv, ctx, box[0] - ctx.px(120), box[2] + ctx.px(160), box[3] + ctx.px(6), t / 0.8)
        ring = _live_ring(sc, t)
        if ring and (t - _rel(sc, ring["at"])) > 0: D.glow_ring(cv, ctx, neck[0], neck[1] + ctx.px(8), ctx.px(46), (t - _rel(sc, ring["at"])) / 0.8, t - _rel(sc, ring["at"]) - 0.8, 6)
        D.squeeze_pulses(cv, ctx, (neck[0], neck[1] + ctx.px(8)), t, [_rel(sc, q) for q in sc["squeezes"]])
        callouts(cv, ctx, sc, t, max(740, (box[2] / ctx.S) + 90))
    elif kind in ("trainee", "pose", "prop"):
        box = None
        if sc["art"]:
            h = 0.84 if kind != "prop" else 0.76; sway = {}
            if kind == "pose" and sc["art"] != "rep_hang_v1": im_ = ctx.art(sc["art"]); h = min(0.84, 0.56 * ctx.W / (im_.width / im_.height) / ctx.H)      # a lying or wide pose keeps the left part of the frame
            if kind == "pose" and sc["art"] == "rep_hang_v1": sway = {"shear": 16 * ctx.S * math.sin(t * 1.5)}          # hangs from the bar and swings gently
            if kind == "prop": sway = {"rot": 1.4 * math.sin(t * 1.3)}
            if sc.get("morph") and kind == "trainee": mp = T.ease_in_out((t - _rel(sc, sc["morph"]["at"])) / 1.2); sway["gain"] = sc["morph"]["to"] * mp      # the body gains or leans out on its word
            box = D.paste_art(cv, ctx, sc["art"], 0.30, 0.54, h, zoom, 1.0, dx, dy, **sway)
            if kind in ("trainee",): D.floor_line(cv, ctx, box[0] - ctx.px(120), box[2] + ctx.px(120), box[3] + ctx.px(6), t / 0.8)
            if kind in ("trainee", "pose") and sc.get("glows"):      # the part the narration is on now lights up (reptheory/states.py)
                live = [g for g in sc["glows"] if _rel(sc, g["at"]) <= t + 1e-6]
                if live: g = live[-1]; at = _rel(sc, g["at"]); D.anatomy_glow(cv, ctx, box, g["regions"], (t - at) / 0.5, t - at, ST.TONES.get(g.get("tone"), T.ORANGE))
                if sc.get("beam"):      # a signal from the brain to the part it drives (states.apply)
                    bm = sc["beam"]; w_, h_ = box[2] - box[0], box[3] - box[1]; D.beam(cv, ctx, (box[0] + bm["from"][0] * w_, box[1] + bm["from"][1] * h_), (box[0] + bm["to"][0] * w_, box[1] + bm["to"][1] * h_), t - _rel(sc, bm["at"]))
            ring = _live_ring(sc, t)
            if ring and kind == "prop": _label_ring(cv, ctx, box, ring, t, sc)
            if kind == "pose" and sc.get("grip_at") is not None:
                p = (t - _rel(sc, sc["grip_at"])) / 0.8; w, hh = box[2] - box[0], box[3] - box[1]
                for fx in (0.275, 0.72): D.glow_ring(cv, ctx, box[0] + fx * w, box[1] + 0.03 * hh, ctx.px(34), p, t - _rel(sc, sc["grip_at"]) - 0.8, 5)
        callouts(cv, ctx, sc, t, max(760, ((box[2] / ctx.S) if box else 760) + 110))
    elif kind == "anatomy":
        box = D.paste_art(cv, ctx, sc["art"], 0.27, 0.54, 0.84, zoom, 1.0, dx, dy, fade_top=0.14); gl = sc.get("glows") or ([sc["glow"]] if sc.get("glow") else []); w, h = box[2] - box[0], box[3] - box[1]
        live_g = [x for x in gl if _rel(sc, x["at"]) <= t + 1e-6]; g = (live_g[-1] if live_g else (gl[0] if gl else {})) or {}      # the region the narration is on now
        inset = sc.get("inset"); fore = None
        if inset:      # the trainee who is doing the squeezing, small, with a line from his gripping forearm to the picture
            ib, _n, fore = D.hold_figure(cv, ctx, "rep_stand_v1", inset, 0.80, 0.58, 0.66, t, [_rel(sc, q) for q in sc.get("squeezes", [])], 1.0, 1.0, 0, 0)      # mirrored: the gripping forearm faces the anatomy, so the line never crosses the body
        if g:
            at = _rel(sc, g["at"]); p = (t - at) / 0.7; D.anatomy_glow(cv, ctx, box, g["regions"], p, t - at, ST.TONES.get(g.get("tone"), T.ORANGE))
            if gl: D.light_sweep(cv, ctx, box, (t - _rel(sc, gl[0]["at"])) / 0.9)      # the plate is revealed by a light passing over it
            fx, fy, fw, fh = g["regions"][-1]; p0 = (box[0] + (fx + fw * 0.35) * w, box[1] + fy * h)
            if fore: D.connector(cv, ctx, [p0, (p0[0] + ctx.px(120), p0[1] - ctx.px(40)), (fore[0] - ctx.px(40), fore[1] - ctx.px(10)), fore], (t - at - 0.6) / 0.9)
            live_p = [p for p in sc["pages"] if _rel(sc, p["at"]) <= t + 1e-6] or sc["pages"][:1]; pg0 = live_p[-1] if live_p else None; lab = (g.get("label") or (pg0["headline"] if pg0 and pg0["headline"] else "FOREARM")); lx, ly = box[2] + ctx.px(40), box[1] + 0.03 * h
            lp = (t - at - 0.5) / 0.5; f = ctx.font(T.HEAD_FONT, 72); d = ImageDraw.Draw(cv, "RGBA"); off = int((1 - T.ease_out(lp)) * 24 * ctx.S)
            if lp > 0:
                D.text_spaced(d, (lx, ly + off), lab, f, T.WHITE + (int(255 * min(1, lp * 1.6)),), ctx.px(1))
                D.text_spaced(d, (lx, ly + off + ctx.px(86)), "ILLUSTRATION", ctx.font(T.BODY_FONT, 24), T.GREY + (int(255 * min(1, lp * 1.6)),), ctx.px(4))      # an AI picture, not a verified anatomy plate
            for c in (pg0["chips"] if pg0 else []): D.pill(d_cv := cv, ctx, lx, ly + ctx.px(132), c["text"], (t - _rel(sc, c["at"])) / 0.5)
    elif kind == "equation":
        bbox = D.paste_art(cv, ctx, sc["art"], 0.2, 0.54, 0.70, 1.0 + 0.04 * min(1, t / 6), 1.0, dx * 0.5, dy * 0.5, rot=1.2 * math.sin(t * 1.2)) if sc["art"] else None
        lay = D.equation(cv, ctx, [{"lhs": e["lhs"], "rhs": e["rhs"], "at_l": _rel(sc, e["at_l"]), "at_r": _rel(sc, e["at_r"])} for e in sc["equations"]], t)
        chips = [c for pg in sc["pages"] for c in pg["chips"]]      # a phrase the narration adds about the numbers ("with just your fingers and thumb") sits under the equation, in the same pill as every other chip
        if lay and chips and t >= _rel(sc, chips[0]["at"]):
            for i, c in enumerate(chips[:2]): D.pill(cv, ctx, lay[0], lay[1] + ctx.px(130 + 96 * i), c["text"], (t - _rel(sc, c["at"])) / 0.5)
    elif kind == "callout":      # no picture: the narration's own words, large, on the left; an orange rule draws down beside them
        d = ImageDraw.Draw(cv, "RGBA"); rp = T.ease_out(t / 0.9); d.rectangle((ctx.px(150), int(ctx.H * 0.5 - ctx.px(250) * rp), ctx.px(158), int(ctx.H * 0.5 + ctx.px(250) * rp)), fill=T.ORANGE + (230,))
        callouts(cv, ctx, sc, t, 230)
    elif kind == "illus":      # a picture generated from this beat's narration (beat_art.py), callouts to its right
        im = ctx.art(sc["art"]); frac = min(0.80, 0.52 * ctx.W / (im.width / im.height) / ctx.H); box = D.paste_art(cv, ctx, sc["art"], 0.29, 0.52, frac, zoom, 1.0, dx, dy)
        callouts(cv, ctx, sc, t, max(760, (box[2] / ctx.S) + 90))
    elif kind == "clip3d":      # the 3D body (clip3d.py): the clip's frame for this moment in a panel on the left, callouts on the right
        c = sc["clip3d"]; fr = c["frames"]; i = max(0, int(t * c["fps"])); n = len(fr); i = i % (2 * n - 2) if n > 1 else 0; i = i if i < n else 2 * n - 2 - i; im = Image.open(fr[i]).convert("RGB"); pw = int(ctx.W * 0.60); ph = int(pw * im.height / im.width)
        im = im.resize((pw, ph), Image.LANCZOS); x0 = ctx.px(70); y0 = (ctx.H - ph) // 2; a = min(1.0, t / 0.4)
        mask = Image.new("L", (pw, ph), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=ctx.px(18), fill=int(255 * a)); cv.paste(im, (x0, y0), mask)
        D.text_spaced(ImageDraw.Draw(cv, "RGBA"), (x0, y0 + ph + ctx.px(16)), T.MODEL_CREDIT, ctx.font(T.BODY_FONT, 22), T.GREY + (int(255 * a),), ctx.px(4))
        callouts(cv, ctx, sc, t, (x0 + pw) / ctx.S + 40)
    elif kind == "stat":      # the stated number in a ring (cards.py); the beat's words stay on the right as headline and chips
        st = sc["stat"]; K2.stat(cv, ctx, dict(st, at=_rel(sc, st["at"])), t); callouts(cv, ctx, sc, t, 1130)
    elif kind == "steps":
        K2.steps(cv, ctx, [dict(i, at=_rel(sc, i["at"])) for i in sc["steps"]], t); _caption_strip(cv, ctx, sc, t)
    elif kind == "checklist":
        K2.steps(cv, ctx, [dict(i, at=_rel(sc, i["at"])) for i in sc["checklist"]["items"]], t, ticks=True); _caption_strip(cv, ctx, sc, t)
    elif kind == "myth":
        c = sc["myth"]; K2.mistake(cv, ctx, dict({k: dict(c[k], at=_rel(sc, c[k]["at"])) if c.get(k) else None for k in ("wrong", "right")}, labels=c["labels"]), t); _caption_strip(cv, ctx, sc, t)
    elif kind == "question":
        K2.question(cv, ctx, dict(sc["question"], at=_rel(sc, sc["question"]["at"])), t); _caption_strip(cv, ctx, sc, t)
    elif kind == "versus":
        v = sc["versus"]; K2.versus(cv, ctx, {k: dict(v[k], at=_rel(sc, v[k]["at"])) for k in ("a", "b")}, t); _caption_strip(cv, ctx, sc, t)
    elif kind in ("timeline", "mistake", "slider"):      # Step 4 cards that fill the frame, the narration's next phrase in a strip under them
        c = sc[kind]; rel = lambda x: dict(x, at=_rel(sc, x["at"])) if x else None
        if kind == "timeline": K2.timeline(cv, ctx, {"items": [rel(i) for i in c["items"]]}, t)
        elif kind == "mistake": K2.mistake(cv, ctx, {k: rel(c.get(k)) for k in ("wrong", "right")}, t)
        else: K2.slider(cv, ctx, {k: rel(c.get(k)) for k in ("easier", "harder")}, t)
        _caption_strip(cv, ctx, sc, t)
    elif kind in ("dial", "study"):      # a number card on the left, the beat's words as callouts on the right
        c = sc[kind]; (K2.dial if kind == "dial" else K2.study)(cv, ctx, dict(c, at=_rel(sc, c["at"])), t); callouts(cv, ctx, sc, t, 1130)
    elif kind == "graph":
        c = sc["graph"]; K2.graph(cv, ctx, dict(c, segs=[dict(s, at=_rel(sc, s["at"])) for s in c["segs"]]), t); callouts(cv, ctx, sc, t, 1130)
    elif kind == "bars":
        c = sc["bars"]; K2.bars(cv, ctx, dict(c, at=_rel(sc, c["at"])) if c["mode"] == "dots" else dict(c, items=[dict(i, at=_rel(sc, i["at"])) for i in c["items"]]), t); callouts(cv, ctx, sc, t, 1130)
    elif kind in ("calendar", "result", "warning", "engage"):      # Step 4 cards that fill the frame, the narration's next phrase in a strip under them
        c = sc[kind]; key = {"calendar": "days", "result": "tiers", "warning": "rules"}.get(kind)
        c = dict(c, **{key: [dict(x, at=_rel(sc, x["at"])) for x in c[key]]}) if key else dict(c, at=_rel(sc, c["at"])); getattr(K2, kind)(cv, ctx, c, t); _caption_strip(cv, ctx, sc, t)
    elif kind == "takeaway":
        K2.takeaway(cv, ctx, {"words": [dict(w, t0=_rel(sc, w["t0"])) for w in sc["takeaway"]["words"]]}, t)
    elif kind == "sketch":      # a scene drawn in code from the beat's own words (see sketch.py), callouts on the right
        from . import sketch as K; K.draw(cv, ctx, sc["sketch"], t); callouts(cv, ctx, sc, t, 1130)
    elif kind == "tier":
        tr = sc["tier"]; D.tier_board(cv, ctx, tr, t, sc["art"] or None, tr.get("item", ""), _rel(sc, tr["at"]), t - _rel(sc, tr["at"]) - 0.8, [(m["letter"], _rel(sc, m["at"])) for m in sc.get("tier_marks", [])])
    if sc.get("stamp"):      # a short sentence said for emphasis, stamped on its first word, held, then lifted
        st = sc["stamp"]; ts = t - _rel(sc, st["at"])
        if 0 <= ts < STAMP_HOLD_S + 0.3:
            lay = Image.new("RGBA", (ctx.W, ctx.H), (0, 0, 0, 0)); D.stamp(lay, ctx, st["text"], ts, (232, 64, 52) if st["red"] else T.ORANGE, 0.5, 0.15); D.overlay_paste(cv, lay, min(1.0, (STAMP_HOLD_S + 0.3 - ts) / 0.3))
    if sc.get("teaser"): K2.teaser(cv, ctx, sc["teaser"]["text"], t - _rel(sc, sc["teaser"]["at"]))      # Full Guide blueprint (blueprint.py)
    if sc.get("lock") and not (sc.get("teaser") and t >= _rel(sc, sc["teaser"]["at"])): K2.lock(cv, ctx, t - _rel(sc, sc["lock"]["at"]))
    if sc.get("safety"): K2.safety_chip(cv, ctx, sc["safety"], t)
    if sc.get("chapter_card"): K2.chapter(cv, ctx, sc["chapter_card"], t); K2.streak_wipe(cv, ctx, t)
    cv = _push(cv, ctx, sc, t)
    if tag: D.section_tag(cv, ctx, sc["section"], t, prev_section, 0.0)
    return cv

def _caption_strip(cv: Image.Image, ctx: D.Ctx, sc: dict, t: float) -> None:
    """A card that has said everything keeps up with the narration: the phrase being said (states.develop) in a pill under it, centred."""
    live = [p for p in sc.get("pages", []) if p.get("headline") and _rel(sc, p["at"]) <= t + 1e-6]
    if not live: return
    pg = live[-1]; d = ImageDraw.Draw(cv, "RGBA"); w = D._text_w(d, pg["headline"], ctx.font(T.BODY_FONT, 36), ctx.px(1.5)) + ctx.px(60)
    D.pill(cv, ctx, (ctx.W - w) / 2 / ctx.S * ctx.S, ctx.H * 0.82, pg["headline"], (t - _rel(sc, pg["at"])) / 0.5)

def _tint(cv: Image.Image, ctx: D.Ctx, p: float) -> None:
    """A warning, a mistake, pain: the dark background warms red from the edges in (eased in over p = 0..1), behind everything drawn after it."""
    if p <= 0: return
    if getattr(ctx, "_red", None) is None:
        import numpy as np
        xx, yy = np.meshgrid(np.linspace(-1, 1, ctx.W), np.linspace(-1, 1, ctx.H)); a = np.clip((xx ** 2 * 0.8 + yy ** 2) / 1.6, 0, 1) ** 0.8 * 0.55 + 0.12
        ctx._red = Image.fromarray(np.dstack([np.full_like(a, 150), np.full_like(a, 16), np.full_like(a, 12), a * 255]).astype("uint8"), "RGBA")
    lay = ctx._red if p >= 1 else Image.merge("RGBA", (*ctx._red.split()[:3], ctx._red.getchannel("A").point(lambda v: int(v * T.ease_out(p)))))
    cv.paste(lay, (0, 0), lay)

PUSH_RATE, PUSH_MAX, DRIFT = 0.012, 0.10, 0.012      # whole-frame push-in per second, its most over one scene, and the sideways drift (fractions of the frame)

def _push(cv: Image.Image, ctx: D.Ctx, sc: dict, t: float) -> Image.Image:
    """Every scene keeps moving (the reference never holds a still frame): the whole composition pushes in steadily with a slight drift, its direction
    alternating scene to scene. Linear after a short ease-in, so it never stops before the scene ends; the section tag is drawn after, steady."""
    d = max(2.0, sc["end"] - sc["start"]); u = max(0.0, t) / d; p = u * u / 0.2 if u < 0.1 else min(1.25, u - 0.05)      # eases in over the first tenth, then moves at a constant rate
    z = 1.0 + min(PUSH_MAX, PUSH_RATE * d) * p; k = (-1, 1)[sc.get("no", 0) % 2]; W, H = ctx.W, ctx.H; w, h = W / z, H / z
    x0 = (W - w) / 2 + k * DRIFT * W * p; y0 = (H - h) / 2 - 0.4 * DRIFT * H * p; x0 = min(max(0.0, x0), W - w); y0 = min(max(0.0, y0), H - h)
    return cv.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))

FOCUS_BLUR = 18      # px at 1080p: how far out of focus a scene goes as it hands over

def _defocus(im: Image.Image, r: float, ctx: D.Ctx) -> Image.Image:
    if r < 0.5: return im
    q = 4; sm = im.resize((im.width // q, im.height // q), Image.BILINEAR).filter(ImageFilter.GaussianBlur(r * ctx.S / q))
    return sm.resize(im.size, Image.BILINEAR)

def transition(a: Image.Image, b: Image.Image, p: float, ctx: D.Ctx) -> Image.Image:
    """Focus pull: the outgoing scene goes out of focus and darkens while the incoming one comes in out of focus and sharpens (eased)."""
    e = T.ease_in_out(p); dark = Image.new("RGB", a.size, T.BG_BOT)
    oa = Image.blend(_defocus(a, FOCUS_BLUR * e, ctx), dark, 0.35 * e); ob = _defocus(b, FOCUS_BLUR * (1 - e), ctx)
    return Image.blend(oa, ob, min(1.0, e * 1.15))
