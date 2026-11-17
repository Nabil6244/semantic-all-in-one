"""Wall Moments planner: which stretches of a film go onto the wall (about 20 % of the runtime) and what lands there.

    plan(scenes, words, total, shots, *, pct=20, blocks=(), theme="slate", work=None) -> {
        "pct", "share", "total", "segments": [ {"start", "end", "scenes", "score", "closing", "params", "cues"} ] }

Input, style-neutral (each style's adapter builds it):
    scenes  [{"no", "text", "start", "end", "card": 0..1 share of the scene that today is a graphic card, "keep": must stay as it is}]
    words   [(word, start, end)] Whisper words of the narration
    shots   [{"start", "end", "path", "seek", "kind": footage | still | black}] the film's base shots (contiguous)
    blocks  [(a, b)] spans a wall moment may not start or end inside (a full-frame card, a map, a long sticker stage)

Rules (docs/wall/PLAN.md): runs of 1-4 neighbouring scenes, 8-20 s each, at least 45 s apart, not in the first 5 s, never the last
scene, nothing marked keep; a budget of pct +/- 2 % of the runtime, never above 25 %. Score: + numbers / money / percents / years,
+ scenes that today become cards, + twist lines, + clips to pull out of and dive into, - strong footage of their own (that stays
full screen). The same input always gives the same plan.
"""

from __future__ import annotations

import bisect
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import engine as E
from . import facts as FA

MIN_S, MAX_S = 8.0, 20.0
MIN_GAP_S = 45.0
NO_WALL_BEFORE_S = 5.0
MAX_SHARE = 25.0
BAND = 2.0
CLOSING_S = 60.0
PRINT_W = 900
ENTRY_PULL_S = 1.25
EXIT_HOLD_S = 0.25


# ---------------------------------------------------------------------------------------------------------------- helpers

def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _shot_at(shots: Sequence[Dict[str, Any]], t: float) -> Optional[Dict[str, Any]]:
    for s in shots:
        if float(s["start"]) - 1e-6 <= t < float(s["end"]) - 1e-6:
            return s
    return None


def _clip_ok(s: Optional[Dict[str, Any]]) -> bool:
    return bool(s) and s.get("kind") in ("footage", "still") and bool(s.get("path"))


def _strong_share(shots: Sequence[Dict[str, Any]], sc: Dict[str, Any]) -> float:
    a, b = float(sc["start"]), float(sc["end"])
    return sum(_overlap(a, b, float(s["start"]), float(s["end"])) for s in shots if s.get("kind") == "footage") / max(0.01, b - a)


def _inside_block(t: float, blocks: Sequence[Tuple[float, float]]) -> bool:
    return any(a + 0.05 < t < b - 0.05 for a, b in blocks)


# ---------------------------------------------------------------------------------------------------------------- scoring

FIRST_PIN_S = 1.2            # with no clip to pull out of, the first thing to pin must be spoken this soon (never an empty wall)


def _first_pin(sc: Dict[str, Any], fs: Sequence[FA.Fact], words) -> float:
    """Seconds from the scene's start to its first pinnable word (inf when it has none)."""
    if not fs:
        return float("inf")
    a = float(sc["start"])
    if not words:
        n = max(1, len(FA.normalize(str(sc.get("text") or ""))))
        return (float(sc["end"]) - a) * min(f.start for f in fs) / n
    tm = FA.Timer(str(sc.get("text") or ""), a, float(sc["end"]), words)
    return min(tm.at(f.start) for f in fs) - a


def candidates(scenes: Sequence[Dict[str, Any]], shots: Sequence[Dict[str, Any]], total: float,
               blocks: Sequence[Tuple[float, float]] = (), words=None) -> List[Dict[str, Any]]:
    out = []
    n = len(scenes)
    facts_of = [FA.facts(str(sc.get("text") or "")) for sc in scenes]
    for i in range(n):
        for j in range(i, min(n, i + 4)):
            a, b = float(scenes[i]["start"]), float(scenes[j]["end"])
            dur = b - a
            if dur > MAX_S:
                break
            if dur < MIN_S or a < NO_WALL_BEFORE_S or j >= n - 1:
                continue
            run = scenes[i:j + 1]
            if any(sc.get("keep") for sc in run) or _inside_block(a, blocks) or _inside_block(b, blocks):
                continue
            fs = [f for k in range(i, j + 1) for f in facts_of[k]]
            nums = sum(1 for f in fs if f.kind in ("money", "percent", "count", "change", "approx"))
            dates = sum(1 for f in fs if f.kind in ("year", "date"))
            twist = any(f.kind == "twist" for f in fs)
            verdict = any(f.kind == "verdict" for f in fs)
            card = sum(float(sc.get("card") or 0.0) * (float(sc["end"]) - float(sc["start"])) for sc in run) / dur
            pins = nums + dates + int(twist) + int(verdict)
            if pins < 2 and not (pins == 1 and card >= 0.3):
                continue                                       # the wall needs two things to pin (one, where it replaces cards)
            strong = sum(_overlap(a, b, float(s["start"]), float(s["end"])) for s in shots if s.get("kind") == "footage") / dur
            if any(_strong_share(shots, sc) > 0.5 for sc in (run[0], run[-1])):
                continue                                       # a moment never opens or closes on a scene's own real footage
            entry, exit_ = _shot_at(shots, a - 0.02), _shot_at(shots, b + 0.02)
            if not _clip_ok(entry) and _first_pin(run[0], facts_of[i], words) > FIRST_PIN_S:
                continue                                       # it would open on an empty wall
            score = (1.2 * min(nums, 6) + 0.6 * min(dates, 3) + 3.0 * card + 1.5 * twist + 0.8 * verdict - 3.0 * strong
                     + 0.5 * _clip_ok(entry) + 0.5 * _clip_ok(exit_))
            out.append({"i": i, "j": j, "start": a, "end": b, "dur": dur, "score": round(score, 4),
                        "scenes": [sc.get("no") for sc in run]})
    return out


def pick(cands: Sequence[Dict[str, Any]], total: float, pct: float) -> List[Dict[str, Any]]:
    """The set of moments with the best total score whose length lands in the band (pct +/- 2 %, never above 25 %), every two at
    least 45 s apart. Exact (interval scheduling with a length budget in 0.25 s steps); when no set reaches the band, the longest
    set under its top. Ties go to the earlier moments, so the same input always gives the same pick."""
    pct = max(0.0, min(float(pct), MAX_SHARE))
    if pct <= 0 or total <= 0:
        return []
    step = 0.25
    hi_u = int(total * min(pct + BAND, MAX_SHARE) / 100.0 / step)
    lo_u = int(math.ceil(total * max(0.0, pct - BAND) / 100.0 / step))
    tg_u = total * pct / 100.0 / step
    cs = sorted((c for c in cands if c["score"] > 0), key=lambda c: (c["end"], c["start"]))
    n = len(cs)
    ends = [c["end"] for c in cs]
    units = [max(1, int(round(c["dur"] / step))) for c in cs]
    prev = [bisect.bisect_right(ends, c["start"] - MIN_GAP_S + 1e-9) for c in cs]       # candidates 0..prev-1 end early enough
    NEG = float("-inf")
    f = [[NEG] * (hi_u + 1) for _ in range(n + 1)]                                    # f[k][u]: best score, first k, exactly u
    f[0][0] = 0.0
    for k in range(1, n + 1):
        row, last, src, d, sc = f[k], f[k - 1], f[prev[k - 1]], units[k - 1], cs[k - 1]["score"]
        for u in range(hi_u + 1):
            row[u] = last[u]
            if u >= d and src[u - d] != NEG and src[u - d] + sc > row[u] + 1e-9:
                row[u] = src[u - d] + sc
    ok = [u for u in range(lo_u, hi_u + 1) if f[n][u] != NEG]
    if ok:
        u = max(ok, key=lambda u: (round(f[n][u], 6), -abs(u - tg_u)))
    else:
        u = max(v for v in range(hi_u + 1) if f[n][v] != NEG)
    out: List[Dict[str, Any]] = []
    k = n
    while k > 0 and u > 0:
        if f[k][u] == f[k - 1][u]:
            k -= 1
            continue
        out.append(cs[k - 1])
        u -= units[k - 1]
        k = prev[k - 1]
    return sorted(out, key=lambda c: c["start"])


# ---------------------------------------------------------------------------------------------------------------- layout

def _text_w(text: str, size: int, name: str = E.BOLD) -> float:
    bb = E._measure(text, E.font(name, size))
    return float(bb[2] - bb[0])


class _Cell:
    def __init__(self, t: float, items: List[Dict[str, Any]], x: float, y: float, w: float, h: float, anchor_l, anchor_r):
        self.t, self.items, self.x, self.y, self.w, self.h = t, items, x, y, w, h
        self.anchor_l, self.anchor_r = anchor_l, anchor_r
        self.keys: List[Tuple[float, float, float, float]] = []      # (t, x, y, z)
        self.fs: Optional[Tuple[str, float, float]] = None           # (video id, from, to): full-screen hold

    def bbox(self) -> Tuple[float, float, float, float]:
        return self.x - self.w / 2, self.y - self.h / 2, self.x + self.w / 2, self.y + self.h / 2


def _fit(bw: float, bh: float, k: float = 0.62, lo: float = 0.3, hi: float = 1.2) -> float:
    return max(lo, min(hi, k * E.W / max(1.0, bw), k * E.H / max(1.0, bh)))


_CLIP_EXTRA: List[Any] = [None]       # the style's clip_extra(shot, at) for the plan being built (wall.adapter.Style)


def _video_item(vid: str, x: float, y: float, shot: Dict[str, Any], seek: float, t0: float, span: Tuple[float, float],
                t_in: float, res: Tuple[int, int], label: Optional[str] = None, label_t: Optional[float] = None,
                at: Optional[float] = None) -> Dict[str, Any]:
    d = {"id": vid, "type": "video", "x": x, "y": y, "w": PRINT_W, "t_in": t_in,
         "clip": {"path": shot["path"], "seek": round(seek, 3), "t0": round(t0, 3), "a": round(max(0.0, span[0]), 3),
                  "b": round(max(span[0] + 0.2, span[1]), 3), "res": list(res)}}
    fn = _CLIP_EXTRA[0]
    if fn is not None and shot.get("_shot") is not None:
        try:                              # the style's own look of this shot at its hand-off frame (grade, zoom, fill)
            d["clip"].update(fn(shot["_shot"], float(shot["start"]) if at is None else at) or {})
        except Exception:  # noqa: BLE001 - a plain print is still a print
            pass
    if label:
        d["label"], d["label_t"] = label, label_t if label_t is not None else t_in + 0.6
    return d


def _name_of(text: str) -> Optional[str]:
    """The first proper name in a line ('Lufthansa', 'Lisbon Airport'), for a print's red name bar."""
    words = str(text or "").replace("'s", "").replace("’s", "").split()
    best: List[str] = []
    for k, w in enumerate(words):
        clean = w.strip(",.;:!?\"'()")
        if clean[:1].isupper() and k > 0 and clean.lower() not in FA.STOP and len(clean) > 2 and not clean.isdigit():
            best.append(clean)
            if len(best) == 3:
                break
        elif best:
            break
    return " ".join(best).upper() if best else None


def build_segment(seg: Dict[str, Any], scenes: Sequence[Dict[str, Any]], words, shots: Sequence[Dict[str, Any]], *,
                  theme: str = "slate", work: Optional[str] = None, earlier: Sequence[Dict[str, Any]] = ()) -> Dict[str, Any]:
    """The params of one wall moment (engine format). `earlier` = params of previous moments, shown on a closing pull-back."""
    a, b = float(seg["start"]), float(seg["end"])
    dur = b - a
    items: List[Dict[str, Any]] = []
    cells: List[_Cell] = []
    p: Dict[str, Any] = {"theme": theme, "dur": round(dur, 3), "work": work, "items": items, "cam": []}

    # entry: the clip playing before the moment keeps playing while the camera pulls back
    entry = _shot_at(shots, a - 0.02)
    has_entry = _clip_ok(entry)
    if has_entry:
        seek = float(entry["seek"]) + (a - float(entry["start"]))
        items.append(_video_item("entry", 0.0, 0.0, entry, seek, 0.0, (seek, seek + min(6.0, dur)), -1.0, (1280, 720), at=a))
        cursor = PRINT_W / 2 + 380
        prev = _Cell(-1.0, [items[-1]], 0.0, 0.0, PRINT_W, PRINT_W * 9 / 16, (-PRINT_W / 2, 0.0), (PRINT_W / 2, 0.0))
    else:
        p["fade_in"] = 0.4
        cursor = 0.0
        prev = None
    row = 0
    rows = (-40.0, 270.0)
    used_shots = set()

    def add_cell(t: float, its: List[Dict[str, Any]], w: float, h: float, y: Optional[float] = None) -> _Cell:
        nonlocal cursor, row, prev
        cy = rows[row % 2] if y is None else y
        row += 1
        cx = cursor + w / 2
        c = _Cell(t, its, cx, cy, w, h, (cx - w / 2, cy), (cx + w / 2, cy))
        cursor += w + 320
        if prev is not None:
            items.append({"type": "string", "a": list(prev.anchor_r), "b": list(c.anchor_l), "t_in": round(max(0.0, t - 0.35), 3)})
            c.items.append(items[-1])
        items.extend(i for i in its if i not in items)
        cells.append(c)
        prev = c
        return c

    last_counter: Optional[Tuple[_Cell, Dict[str, Any]]] = None
    for sc in scenes:
        s0, s1 = float(sc["start"]), float(sc["end"])
        if s1 <= a + 1e-6 or s0 >= b - 1e-6:
            continue
        text = FA.normalize(str(sc.get("text") or ""))
        tm = FA.Timer(text, s0, s1, words)
        rel = lambda t: round(max(0.05, min(dur - 0.3, t - a)), 3)
        # the scene's own clip: a print on the wall (real footage goes full screen while its words play)
        own = [s for s in shots if _clip_ok(s) and _overlap(s0, s1, float(s["start"]), float(s["end"])) > 0.3
               and a - 1e-6 <= float(s["start"]) and float(s["end"]) <= b + 1e-6 and id(s) not in used_shots]
        beats: List[Tuple[float, int, str, Any]] = []
        if own:
            sh = max(own, key=lambda s: float(s["end"]) - float(s["start"]))
            for s in own:
                used_shots.add(id(s))
            beats.append((max(s0, float(sh["start"])) - 0.6, 0, "print", sh))
        for f in FA.facts(text):
            beats.append((tm.at(f.start), 1, "fact", f))
        for _t, _o, what, obj in sorted(beats, key=lambda q: (q[0], q[1])):   # cells in spoken order, left to right
            if what == "print":
                sh = obj
                strong = sh.get("kind") == "footage"
                vid = f"v{len(cells)}"
                t_in = rel(max(s0, float(sh["start"])) - 0.6)
                span0 = float(sh["seek"])
                it = _video_item(vid, 0.0, 0.0, sh, span0, float(sh["start"]) - a, (span0, span0 + min(6.0, float(sh["end"]) - float(sh["start"]) + 2.0)),
                                 t_in, (1280, 720) if strong else (640, 360), _name_of(text), rel(s0 + 0.4))
                c = add_cell(t_in, [it], PRINT_W, PRINT_W * 9 / 16, y=30.0)
                it["x"], it["y"] = c.x, c.y
                c.anchor_l, c.anchor_r = (c.x - PRINT_W / 2, c.y - 200), (c.x + PRINT_W / 2, c.y + 200)
                if strong and float(sh["end"]) - float(sh["start"]) >= 1.6:
                    c.fs = (vid, rel(float(sh["start"]) + 0.35), rel(float(sh["end"]) - 0.35))
                else:
                    c.keys.append((t_in + 0.4, c.x, c.y, _fit(PRINT_W, PRINT_W * 9 / 16, 0.8)))
                continue
            f = obj
            if f.kind in ("money", "percent", "count"):
                size = 120
                final = E.fmt_value(f.value, f.fmt)
                w = max(_text_w(final, size), _text_w(f.caption, int(size * 0.24), E.SANS)) + 60
                land_abs = tm.at(f.at) + 0.1
                t_land = rel(land_abs)
                t_in = rel(min(tm.at(f.start) - 0.15, land_abs - 0.6))
                it = {"type": "counter", "x": 0.0, "y": 0.0, "size": size, "value": f.value, "fmt": f.fmt, "caption": f.caption,
                      "bad": f.bad, "t_in": t_in, "t_land": t_land}
                c = add_cell(t_in, [it], w, size * 1.6)
                it["x"], it["y"] = c.x, c.y
                c.keys += [(t_in + 0.35, c.x, c.y + 40, _fit(w + 500, 600)), (t_land + 0.2, c.x, c.y + 30, _fit(w + 500, 600) * 1.12)]
                last_counter = (c, it)
                if f.text == "of":
                    k = text.find(" of", f.span[1] - 1)
                    t_of = rel(tm.at(k + 1)) if k >= 0 else t_land + 0.4
                    pen = {"type": "pen", "cx": c.x, "cy": c.y + size * 0.42, "rx": w * 0.62, "ry": size * 0.85, "t_in": max(t_of, t_land + 0.1)}
                    items.append(pen)
                    c.items.append(pen)
            elif f.kind == "approx" and last_counter:
                c, ctr = last_counter
                t = rel(tm.at(f.start))
                under = {"type": "under", "x0": c.x - c.w / 2 + 30, "x1": c.x + c.w / 2 - 30, "y": c.y + ctr["size"] * 1.55, "t_in": t}
                note = {"type": "note", "text": f.text, "x": c.x - 40, "y": c.y + ctr["size"] * 2.2, "size": 46, "rot": -2, "t_in": rel(t + 0.3)}
                items += [under, note]
                c.items += [under, note]
                c.h += 180
                c.keys.append((t + 0.3, c.x, c.y + 120, _fit(c.w + 400, c.h + 300)))
            elif f.kind in ("change", "verdict"):
                t = rel(tm.at(f.at) + 0.05)
                st = {"type": "stamp", "text": f.text, "size": 64, "rot": 8 if len(cells) % 2 else -9, "t_in": t, "x": 0.0, "y": 0.0}
                if last_counter and last_counter[0] is prev and t - last_counter[1]["t_land"] < 8.0:   # a verdict on the number just shown
                    c = last_counter[0]
                    st["x"], st["y"] = c.x + c.w * 0.25, c.y + 200
                    c.items.append(st)
                    items.append(st)
                    c.keys.append((t + 0.15, c.x + c.w * 0.12, c.y + 120, _fit(c.w + 300, 700)))
                else:
                    w = _text_w(f.text, 64) + 90
                    c = add_cell(t - 0.1, [st], w, 110)
                    st["x"], st["y"] = c.x, c.y
                    c.keys.append((t + 0.15, c.x, c.y, _fit(w + 600, 500)))
            elif f.kind == "twist":
                t = rel(tm.at(0) + 0.1)
                w = _text_w(f.text, 54) + 80
                it = {"type": "text", "text": f.text, "size": 54, "t_in": t, "hit": "boom", "block": list(E.TH.get(theme)["slam_block"]),
                      "x": 0.0, "y": 0.0}
                if has_entry and t < ENTRY_PULL_S + 0.6 and not cells:
                    it["x"], it["y"] = 0.0, -PRINT_W * 9 / 32 - 95          # opens the moment: a title over the clip being pulled back
                    items.append(it)
                    continue
                c = add_cell(t, [it], w, 110, y=-260.0)
                it["x"], it["y"] = c.x, c.y
                c.keys.append((t + 0.3, c.x, c.y + 60, _fit(w + 300, 500)))
            elif f.kind in ("date", "year"):
                t = rel(tm.at(f.start))
                size = 44 if f.kind == "date" else 54
                it = {"type": "text", "text": f.text, "size": size, "t_in": t, "type_on": 0.8, "block": list(E.TH.get(theme)["block"])}
                host = prev if prev is not None and (prev.t < 0 or t - prev.t < 4.0) else None
                if host is not None:
                    x0, y0, x1, y1 = host.bbox()
                    it["x"], it["y"] = x0 + _text_w(f.text, size) / 2 + 40, y1 - 40
                    host.items.append(it)
                    items.append(it)
                    host.keys.append((t + 0.3, host.x, host.y + 80, _fit(host.w + 300, host.h + 300)))
                else:
                    w = _text_w(f.text, size) + 80
                    c = add_cell(t, [it], w, 100)
                    it["x"], it["y"] = c.x, c.y
                    c.keys.append((t + 0.3, c.x, c.y, _fit(w + 600, 500)))

    # dimming: two cells back dims as the third arrives
    for k, c in enumerate(cells):
        if k + 2 < len(cells):
            for it in c.items:
                it["dim_at"] = round(cells[k + 2].t, 3)

    # exit: the next scene's clip drops in, the camera pulls back over the wall and dives into it
    exit_ = _shot_at(shots, b + 0.02)
    has_exit = _clip_ok(exit_)
    last_t = max([c.t for c in cells] + [0.5])
    if has_exit:
        seek = float(exit_["seek"]) + (b - float(exit_["start"]))
        t_in = round(min(max(last_t + 0.6, dur - 3.4), dur - 1.8), 3)
        ex = _video_item("exit", cursor + PRINT_W / 2 + 80, 40.0, exit_, seek, dur, (seek - min(6.0, dur), seek + 0.2), t_in, (1280, 720),
                         _name_of(_scene_text(scenes, b + 0.02)), round(t_in + 0.3, 3), at=b)
        items.append(ex)
        if prev is not None:
            items.append({"type": "string", "a": list(prev.anchor_r), "b": [ex["x"] - PRINT_W / 2, ex["y"] - 200], "t_in": round(t_in - 0.2, 3)})
    else:
        p["fade_out"] = 0.4

    # earlier moments, for the closing pull-back: already on the wall, to the left of this one
    if earlier:
        left = min([_bbox(items)[0]] + [0.0])
        for k, ep in enumerate(reversed(list(earlier)[-2:])):
            bb = _bbox(ep["items"])
            dx = left - 700 - bb[2]
            for it in ep["items"]:
                items.append(_shifted(it, dx, f"c{k}_"))
            left = dx + bb[0]

    if has_exit:                         # spoken during the last second, while the camera dives: nobody would see it
        late_ids = {id(i) for i in items if i.get("type") not in ("video",) and float(i.get("t_in", 0)) > dur - 1.1}
        items[:] = [i for i in items if id(i) not in late_ids]
        for c in cells:
            c.items = [i for i in c.items if id(i) not in late_ids]
        cells[:] = [c for c in cells if c.items and c.t <= dur - 1.1]
    p["cam"] = _camera(cells, items, dur, has_entry, has_exit, closing=bool(earlier))
    return p


def _scene_text(scenes: Sequence[Dict[str, Any]], t: float) -> str:
    for sc in scenes:
        if float(sc["start"]) - 1e-6 <= t < float(sc["end"]):
            return str(sc.get("text") or "")
    return ""


def _bbox(items: Sequence[Dict[str, Any]]) -> Tuple[float, float, float, float]:
    xs, ys = [], []
    for it in items:
        if it.get("type") in ("video", "print"):
            w = float(it.get("w", PRINT_W))
            xs += [it["x"] - w / 2, it["x"] + w / 2]
            ys += [it["y"] - w * 0.3, it["y"] + w * 0.3]
        elif "x" in it:
            xs.append(float(it["x"]))
            ys.append(float(it["y"]))
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs) - 200, min(ys) - 150, max(xs) + 200, max(ys) + 150)


def _shifted(it: Dict[str, Any], dx: float, pre: str) -> Dict[str, Any]:
    d = {k: v for k, v in it.items() if k != "dim_at"}
    if "id" in d:
        d["id"] = pre + str(d["id"])
    for k in ("x", "cx", "x0", "x1"):
        if k in d:
            d[k] = float(d[k]) + dx
    for k in ("a", "b"):
        if isinstance(d.get(k), list):
            d[k] = [float(d[k][0]) + dx, float(d[k][1])]
    for k in ("t_in", "label_t", "t_land"):
        if k in d:
            d[k] = -1.0
    return d


def _camera(cells: List[_Cell], items: List[Dict[str, Any]], dur: float, has_entry: bool, has_exit: bool, closing: bool) -> List[Dict[str, Any]]:
    keys: List[Dict[str, Any]] = []
    t_first = 0.0
    if has_entry:
        keys += [{"t": 0.0, "fs": "entry", "edge": True}, {"t": 0.15, "fs": "entry", "edge": True},
                 {"t": ENTRY_PULL_S, "x": 250.0, "y": 30.0, "z": 0.8}]
        t_first = ENTRY_PULL_S + 0.35
    elif cells:
        c = cells[0]
        keys.append({"t": 0.0, "x": c.x, "y": c.y, "z": 0.85})
        t_first = 0.3
    # pull back before the dive (on a closing moment, a long look at the whole wall). A beat spoken late keeps the camera on it
    # instead: no pull-back, and a shorter dive straight from it into the next clip.
    hold = 2.6 if closing else 0.0
    last_beat = max([c.t for c in cells] + [0.0])
    t_dive = dur - EXIT_HOLD_S - (1.5 if has_exit else 0.0)
    late = has_exit and last_beat + 1.2 > t_dive - 0.9 - hold
    if late:
        t_dive = max(t_dive, min(dur - EXIT_HOLD_S - 1.0, last_beat + 0.9))
        t_pb = t_dive
    else:
        t_pb = max(t_first + 0.4, min(t_dive - 0.9 - hold, last_beat + 1.2))
    fs_spans = [c.fs for c in cells if c.fs]
    body: List[Tuple[float, Dict[str, Any]]] = []
    for c in cells:
        ready = min([float(i.get("t_in", c.t)) for i in c.items if i.get("t_in") is not None] or [c.t])
        for t, x, y, z in c.keys:
            body.append((t, {"t": t, "x": x, "y": y, "z": z, "_ready": ready}))
        if c.fs:
            vid, f0, f1 = c.fs
            body.append((f0, {"t": f0, "fs": vid}))
            body.append((f1, {"t": f1, "fs": vid}))
    body.sort(key=lambda q: q[0])
    last = keys[-1]["t"] if keys else -1.0
    early = [k for t, k in body if t < t_first]
    if early and t_first <= t_pb - 0.4:            # beats that land during the pull-back: the camera reaches the latest of them next
        body = [(t_first, dict(early[-1], t=t_first))] + [(t, k) for t, k in body if t >= t_first]
    for t, k in body:
        in_fs = any(f0 - 0.45 < t < f1 + 0.35 and k.get("fs") != vid for vid, f0, f1 in fs_spans)
        if t < t_first or t > t_pb - 0.4 or in_fs or t - last < 0.35:
            continue
        keys.append(k)
        last = t
    last = keys[-1]["t"] if keys else -1.0
    bb = _bbox([i for i in items if not str(i.get("id", "")).startswith("exit")] if not closing else items)
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    z = _fit(bb[2] - bb[0], bb[3] - bb[1], 0.95, 0.08 if closing else 0.3, 0.75)
    if not late and t_pb - last >= 0.3:
        keys.append({"t": round(t_pb, 3), "x": cx, "y": cy, "z": z})
        if closing:
            keys.append({"t": round(t_pb + hold, 3), "x": cx + 60, "y": cy, "z": z * 0.96})
    if has_exit:
        keys += [{"t": round(dur - EXIT_HOLD_S, 3), "fs": "exit", "edge": True}, {"t": round(dur, 3), "fs": "exit", "edge": True}]
    elif cells:
        c = cells[-1]
        keys.append({"t": round(dur, 3), "x": c.x, "y": c.y, "z": 1.1})
    return _hold_then_move(_wait_for_items(keys), t_first)


READY_LEAD_S, MIN_MOVE_S = 0.25, 0.5


def _wait_for_items(keys: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The camera never sets off for a part of the wall before anything is on it (owner, 2026-11-17: the Falklands film showed
    ~0.6 s of empty wall at 2:02 - the camera reached the spot where the next photo would drop, before it dropped). The previous
    framing holds (a slow push-in) until just before the next cell's first item lands, then the camera moves."""
    out: List[Dict[str, Any]] = []
    for k in keys:
        ready = k.pop("_ready", None)
        prev = out[-1] if out else None
        if ready is not None and prev is not None and "x" in prev and not prev.get("edge"):
            go = min(float(ready) - READY_LEAD_S, float(k["t"]) - MIN_MOVE_S)
            if go > float(prev["t"]) + 0.05:
                hold = dict(prev, t=round(go, 3))
                hold["z"] = round(float(prev["z"]) * min(1.05, 1.0 + 0.02 * (go - float(prev["t"]))), 4)
                out.append(hold)
        out.append(k)
    return out


def _hold_then_move(keys: List[Dict[str, Any]], t_from: float) -> List[Dict[str, Any]]:
    """A long gap between two framings becomes a hold and a quick move (0.9 s; 1.3 s into or out of a full-screen clip), never a
    slow drift over empty wall. A held full-screen clip keeps playing."""
    out: List[Dict[str, Any]] = []
    for k in keys:
        if out and k["t"] >= t_from:
            move = 1.3 if ("fs" in k or "fs" in out[-1]) else 0.9
            if k["t"] - out[-1]["t"] > move + 0.9 and not out[-1].get("edge"):
                hold = dict(out[-1], t=round(k["t"] - move, 3))
                if "z" in hold:                   # a hold is a slow push-in, never a still frame
                    hold["z"] = round(float(hold["z"]) * min(1.08, 1.0 + 0.02 * (hold["t"] - out[-1]["t"])), 4)
                out.append(hold)
        out.append(k)
    return out


# ---------------------------------------------------------------------------------------------------------------- the plan

def plan(scenes: Sequence[Dict[str, Any]], words, total: float, shots: Sequence[Dict[str, Any]], *, pct: float = 20.0,
         blocks: Sequence[Tuple[float, float]] = (), theme: str = "slate", work: Optional[str] = None, cues: bool = True,
         clip_extra: Any = None) -> Dict[str, Any]:
    _CLIP_EXTRA[0] = clip_extra
    try:
        return _plan(scenes, words, total, shots, pct=pct, blocks=blocks, theme=theme, work=work, cues=cues)
    finally:
        _CLIP_EXTRA[0] = None


def _plan(scenes, words, total, shots, *, pct, blocks, theme, work, cues) -> Dict[str, Any]:
    words = FA.words_of(words)
    cands = candidates(scenes, shots, total, blocks, words)
    chosen = pick(cands, total, pct)
    segs = []
    built: List[Dict[str, Any]] = []
    closing_done = False
    for c in chosen:
        closing = not closing_done and c["end"] >= total - CLOSING_S and c["dur"] >= 12.0 and bool(built)
        params = build_segment(c, scenes, words, shots, theme=theme, work=work, earlier=built if closing else ())
        closing_done = closing_done or closing
        built.append(params)
        seg = {"start": round(c["start"], 3), "end": round(c["end"], 3), "scenes": c["scenes"], "score": c["score"],
               "closing": closing, "params": params}
        if cues:
            seg["cues"] = [(round(c["start"] + t, 3), name) for t, name in E.Wall(params).cues()]
        segs.append(seg)
    used = sum(s["end"] - s["start"] for s in segs)
    return {"pct": float(pct), "share": round(100.0 * used / total, 2) if total else 0.0, "total": round(float(total), 3), "segments": segs}
