"""One frame of a Rep Theory scene: frame(ctx, scene, t) -> RGB image, with t in seconds from the scene's start (it may exceed the scene's length: the last state holds, which is what lets the
next scene's transition read the outgoing frame). Every moving part is keyed to a time taken from the narration (see planner.py); parts of one idea are joined (a ring on the bottle, a line to
the equation; a line from the gripping forearm to the anatomy picture) so a scene reads as one composition."""
from __future__ import annotations
import math
from PIL import Image, ImageDraw

from . import draw as D, theme as T

def _rel(sc: dict, t_abs: float) -> float: return t_abs - sc["start"]

def _camera(sc: dict, t: float) -> tuple:
    """Slow push-in with a small drift, different direction per scene so consecutive scenes do not move identically; eased so it never stops dead or jerks."""
    d = max(2.0, sc["end"] - sc["start"]); p = T.ease_in_out(min(1.0, t / d)); k = sc["no"] % 3
    return 1.0 + 0.06 * p, (-26, 18, -10)[k] * p, (10, -12, 14)[k] * p

ENTRANCE_S, LATE_MAX_S = 0.45, 0.9

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
            if kind == "pose": sway = {"shear": 16 * ctx.S * math.sin(t * 1.5)}          # hangs from the bar and swings gently
            if kind == "prop": sway = {"rot": 1.4 * math.sin(t * 1.3)}
            box = D.paste_art(cv, ctx, sc["art"], 0.30, 0.54, h, zoom, 1.0, dx, dy, **sway)
            if kind in ("trainee",): D.floor_line(cv, ctx, box[0] - ctx.px(120), box[2] + ctx.px(120), box[3] + ctx.px(6), t / 0.8)
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
            at = _rel(sc, g["at"]); p = (t - at) / 0.7; D.anatomy_glow(cv, ctx, box, g["regions"], p, t - at)
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
        c = sc["clip3d"]; fr = c["frames"]; i = min(len(fr) - 1, max(0, int(t * c["fps"]))); im = Image.open(fr[i]).convert("RGB"); pw = int(ctx.W * 0.58); ph = int(pw * im.height / im.width)
        im = im.resize((pw, ph), Image.LANCZOS); x0 = ctx.px(70); y0 = (ctx.H - ph) // 2; a = min(1.0, t / 0.4)
        mask = Image.new("L", (pw, ph), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=ctx.px(18), fill=int(255 * a)); cv.paste(im, (x0, y0), mask)
        D.text_spaced(ImageDraw.Draw(cv, "RGBA"), (x0, y0 + ph + ctx.px(16)), "3D MODEL", ctx.font(T.BODY_FONT, 22), T.GREY + (int(255 * a),), ctx.px(4))
        callouts(cv, ctx, sc, t, (x0 + pw) / ctx.S + 60)
    elif kind == "sketch":      # a scene drawn in code from the beat's own words (see sketch.py), callouts on the right
        from . import sketch as K; K.draw(cv, ctx, sc["sketch"], t); callouts(cv, ctx, sc, t, 1130)
    elif kind == "tier":
        tr = sc["tier"]; D.tier_board(cv, ctx, tr, t, sc["art"] or None, tr.get("item", ""), _rel(sc, tr["at"]), t - _rel(sc, tr["at"]) - 0.8, [(m["letter"], _rel(sc, m["at"])) for m in sc.get("tier_marks", [])])
    if tag: D.section_tag(cv, ctx, sc["section"], t, prev_section, 0.0)
    return cv

def transition(a: Image.Image, b: Image.Image, p: float, ctx: D.Ctx) -> Image.Image:
    """Push: the outgoing frame slides left and fades while the incoming one slides in from the right (eased). Reads as moving on to the next thing."""
    e = T.ease_in_out(p); W = ctx.W; shift = int(W * 0.10)
    out = Image.new("RGB", (W, ctx.H), T.BG_BOT); oa = a.copy(); ob = b.copy()
    oa = Image.blend(oa, Image.new("RGB", oa.size, T.BG_BOT), min(1, e * 1.2)); ob = Image.blend(Image.new("RGB", ob.size, T.BG_BOT), ob, min(1, e * 1.4))
    out.paste(oa, (-int(shift * e), 0)); out.paste(ob, (int(shift * (1 - e)), 0), Image.eval(Image.new("L", ob.size, 255), lambda v: int(255 * min(1, e * 1.6)))); return out
