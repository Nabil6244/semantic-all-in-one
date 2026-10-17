"""Tracking what the narration says is moving: a marker on every spacecraft, planet and moon the narrator talks about as
moving, from the moment its name is spoken, and a light line when a signal travels.

Generic, from the words and the catalog -- no mission is known here:
  * a map beat's sentences are read for things that move (orbit, fly, travel, race, drift, km/h ...) and the bodies and
    craft named in the same sentence (by any catalog alias, any craft name of the beat's datasets);
  * each gets an automatic row: a craft row for a craft the beat has none for (its tracker and trajectory come with it), a
    `track` row for a planet or moon (a marker with its recent orbital path as a dotted trail), at most MAX_AT_ONCE a beat;
  * the row appears when its name is SPOKEN (the narration's own words); when the word cannot be found, at its place in the
    sentence's share of the beat, and a note says so (to review);
  * a sentence about the motion itself ("Io whips round Jupiter every 42 hours") marks its body `orbiting`: the clock may run
    faster through that beat so the orbit visibly turns (accelerate(), real positions at real dates, never backwards);
  * a signal or light that travels ("a radio message takes 23 hours") gets a light line from Earth to the craft.
Rows the CSV wrote itself always win: nothing is added for a craft or body the beat already tracks."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from .beat_csv import Item, Plan
from .catalog import Catalog, CatalogError
from .temporal import iso, parse_iso

MAX_AT_ONCE = 3
MOVING = re.compile(r"\b(orbit\w*|circl\w*|travel\w*|mov(e|es|ed|ing)|fl(y|ies|ew|ying|own)|rac(e|es|ed|ing)|speed(s|ed|ing)|sped|drift\w*|"
                    r"head(s|ed|ing)|journey\w*|swing\w*|swung|whip\w*|spin\w*|rotat\w*|cross\w*|approach\w*|leav(e|es|ing)|left|"
                    r"launch\w*|coast\w*|plung\w*|hurtl\w*|zoom\w*|sail\w*|pass(es|ed|ing)?\b|rac(e|ing)|km/h|km/s|mph|"
                    r"kilomet(re|er)s? (per|an|a) (hour|second)|miles (per|an|a) hour)\b", re.I)
ORBITING = re.compile(r"\b(orbit(s|ed|ing)?|circl(e|es|ed|ing)|whip\w*|go(es)? (a)?round|around [A-Z]\w+ (once )?every|"
                      r"every [\d.,]+ (hours?|days?|years?)|year on|its year)\b", re.I)
SIGNAL = re.compile(r"\b(radio|signal|message|transmission|command|light|data)\b.{0,80}?\b(take|takes|took|travel\w*|reach\w*|"
                    r"arriv\w*|hours?|minutes?|light-day|light-hour)\b", re.I)
_SENTENCE = re.compile(r"[^.!?]+[.!?]*")
# a name right after one of these is where something goes or is measured from, not the thing that moves
_NOT_MOVER = re.compile(r"\b(from|to|toward|towards|past|beyond|of|at|near|around|round|by|than|between|with|behind|"
                        r"orbiting|reach(ed|es)?|left|leave|leaves|visit(ed)?|toward)\s+(the\s+)?$", re.I)
MOVER_WINDOW = 10            # words between a mover's name and its motion word (the clause it is the subject of)


def _is_mover(sent: str, a: int, z: int) -> bool:
    """Is the name at sent[a:z] the thing that moves: before a motion word in its clause, not the object of a preposition?"""
    if _NOT_MOVER.search(sent[:a]):
        return False
    after = re.split(r"[,;:]|\b(but|while|when|which|that|and then)\b", sent[z:], maxsplit=1)[0]
    m = MOVING.search(after)
    return bool(m) and len(after[:m.start()].split()) <= MOVER_WINDOW
_WORD = re.compile(r"[^\w'-]+")


def _norm(w: str) -> str:
    w = _WORD.sub("", str(w).lower())
    return w[:-2] if w.endswith("'s") else w


def _names(cat: Catalog, ctx: List[str]) -> List[Tuple[str, str, str, str]]:
    """(alias, kind, id, label) for every body with an orbit and every craft of the beat's datasets, longest alias first."""
    out = []
    periodic = {w["id"]: w for w in cat.world if w.get("period_days")}
    for alias, bid in cat.aliases.items():
        if bid in periodic and len(alias) >= 2 and alias.isascii() and "'s " not in alias:
            out.append((alias.lower(), "body", bid, bid))
    for bid in periodic:
        out.append((bid.lower(), "body", bid, bid))
    for did in ctx:
        ds = cat.index.datasets.get(did)
        if ds is None:
            continue
        for key, craft in ds.craft.items():
            for a in {key, str(craft.get("label", "")).lower()} | {a for a, c in ds.craft_aliases.items() if c == key}:
                if a and len(a) >= 3:
                    out.append((a.lower(), "craft", ds.q(key), craft.get("label", key)))
    return sorted(set(out), key=lambda x: -len(x[0]))


def spoken_at(words: List[Tuple[str, float, float]], start: float, end: float, phrase: str) -> Optional[float]:
    """When `phrase` is spoken between start and end (its first word's start), or None."""
    toks = [_norm(t) for t in phrase.split() if _norm(t)]
    inside = [(i, w) for i, w in enumerate(words) if start - 0.3 <= w[1] <= end]
    for i, w in inside:
        if _norm(w[0]) == toks[0] and all(i + k < len(words) and _norm(words[i + k][0]) == toks[k] for k in range(1, len(toks))):
            return round(float(w[1]), 3)
    return None


def add_auto_rows(plan: Plan, cat: Catalog, res: Any) -> List[str]:
    """Adds the automatic rows to the plan's map beats (idempotent: earlier automatic rows are replaced). Returns notes to
    review (a name whose spoken moment could not be found)."""
    notes: List[str] = []
    for b in plan.beats:
        b.layers = [it for it in b.layers if not it.extra.get("auto")]
        if b.mode == "footage" or not b.text:
            continue
        ctx = res.ctx(b.id) if res else []
        have_craft, have_body = set(), set()
        for it in b.layers:
            try:
                if it.type == "craft" and it.id:
                    have_craft.add(cat.craft_id(it.id, ctx))
                elif it.type == "track" and it.place:
                    have_body.add(cat.place(it.place, ctx).body)
            except CatalogError:
                pass
        has_light = any(it.type == "line" and it.id == "light" for it in b.layers)
        # the missions the beat's own words name count too (a craft spoken of in a beat with only a place and a date)
        names = _names(cat, list(dict.fromkeys(list(ctx) + list(cat.index.narration_matches(b.text)))))
        found: Dict[str, Dict[str, Any]] = {}
        signal_t: Optional[float] = None
        length = max(0.5, b.end - b.start)
        for m in _SENTENCE.finditer(b.text):
            sent, off = m.group(0), m.start()
            moving, orbiting = bool(MOVING.search(sent)), bool(ORBITING.search(sent))
            taken: List[Tuple[int, int]] = []
            hits = []
            low = sent.lower()
            for alias, kind, qid, label in names:
                for hit in re.finditer(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", low):
                    if any(a <= hit.start() < z for a, z in taken):
                        continue                                  # "voyager 1" already took "voyager"
                    if kind == "body" and " " not in alias and not sent[hit.start()].isupper():
                        continue                                  # "the moon's surface" of Io is not the Moon: a name is capitalised
                    taken.append((hit.start(), hit.end()))
                    hits.append((hit, kind, qid, label))
            for hit, kind, qid, label in sorted(hits, key=lambda h: h[0].start()):
                    # the mover is the name NEAREST its motion word: "After Saturn, Voyager 1 races" -> Voyager 1
                    verb = MOVING.search(sent, hit.end())
                    closer = verb is not None and any(hit.end() <= a < verb.start() for a, _ in taken)
                    if not moving or closer or qid in found or qid in have_craft or qid in have_body or not _is_mover(sent, hit.start(), hit.end()):
                        continue
                    t = spoken_at(plan.words, b.start, b.end, sent[hit.start():hit.end()])
                    verified = t is not None
                    if t is None:
                        t = round(b.start + length * (off + hit.start()) / max(1, len(b.text)), 3)
                        notes.append(f"beat {b.id}: {label} named but its spoken moment was not found; marker at {t:.1f}s (estimated)")
                    found[qid] = dict(kind=kind, qid=qid, label=label, t=max(b.start, min(t, b.end - 0.5)), verified=verified,
                                      orbiting=orbiting and kind == "body")
            if SIGNAL.search(sent) and signal_t is None and not has_light:
                w = SIGNAL.search(sent)
                signal_t = spoken_at(plan.words, b.start, b.end, w.group(1)) or round(b.start + length * (off + w.start()) / max(1, len(b.text)), 3)
        ordered = sorted(found.values(), key=lambda x: x["t"])
        picks = ordered[:MAX_AT_ONCE]
        if ordered[MAX_AT_ONCE:]:
            notes.append(f"beat {b.id}: also named as moving but not marked ({MAX_AT_ONCE} at once): "
                         + ", ".join(str(x["label"]) for x in ordered[MAX_AT_ONCE:]))
        for p in picks:
            if p["kind"] == "craft":
                b.layers.append(Item(row=b.row, kind="layer", type="craft", id=p["qid"], t=p["t"], extra={"auto": True}))
                have_craft.add(p["qid"])
            else:
                b.layers.append(Item(row=b.row, kind="layer", type="track", place=p["qid"], label=str(p["label"]).upper(), t=p["t"],
                                     extra={"auto": True, "orbiting": p["orbiting"], "verified": p["verified"]}))
        if signal_t is not None and have_craft:
            # the craft must be on screen when the line starts: the earliest craft row of the beat
            crafts = [it for it in b.layers if it.type == "craft"]
            first = min(crafts, key=lambda it: it.t if it.t is not None else b.start)
            t = max(signal_t, first.t if first.t is not None else b.start)
            if t < b.end - 1.0:
                b.layers.append(Item(row=b.row, kind="layer", type="line", id="light", place=f"earth;{first.id}", t=t, extra={"auto": True}))
    return notes


ROTATE_DEG = 40.0              # a planet filling the screen turns this much through its beat (its real rotation, time-lapsed)


def accelerate(clock: Dict[str, Any], plan: Plan, cat: Catalog, actions: Dict[str, Any]) -> List[str]:
    """Through a beat whose narration is about a body's orbit, the clock runs a quarter of that orbit (real positions at
    real dates: the universe keeps its true directions and relative places), only where the time is free: never into the
    next beat's own date, never backwards, never through an action's staged clock. Modifies clock["keys"]; returns notes."""
    keys = clock.get("keys") or []
    if not keys:
        return []
    from .compile import _clock_utc                                    # noqa: PLC0415 (compile imports this module)

    period = {w["id"]: float(w["period_days"]) for w in cat.world if w.get("period_days")}
    spin = {w["id"]: float(w["rotation_hours"]) / 24 for w in cat.world if w.get("rotation_hours")}
    notes = []
    for b in plan.beats:
        if b.mode == "footage" or b.id in (actions or {}):
            continue
        orb = [it for it in b.layers if it.type == "track" and it.extra.get("orbiting")]
        body = next((it.place for it in orb if it.place in period), None)
        # else a fast-turning planet the camera is close on: its own rotation, time-lapsed, so its clouds visibly turn
        place = (b.place or "").strip().lower()
        turning = body is None and place in spin and (b.frame or "body") in ("body", "close", "surface")
        if body is None and not turning:
            continue
        if turning:
            body = place
        u0 = parse_iso(_clock_utc(clock, b.start))
        # only keys strictly inside the beat where time runs forward at real speed are replaced; the next beat's own date
        # (a key at the beat's end, a jump forward or back) is never touched
        inside = [k for k in keys if b.start < k["t"] < b.end - 0.02]
        held = [k for k in inside if 0 <= (parse_iso(k["utc"]) - u0).total_seconds() <= (k["t"] - b.start) * 1.01 + 1]
        t_end = max([k["t"] for k in held], default=b.end - 0.05)
        if any(k not in held and k["t"] <= t_end for k in inside) or t_end - b.start < 3:
            continue                                                  # time already runs or jumps inside: leave it
        want = timedelta(days=spin[body] * ROTATE_DEG / 360) if turning else timedelta(days=period[body] / 4)
        later = [k for k in keys if k["t"] > t_end + 1e-6]
        room = want
        if later:
            k = later[0]
            room = min(want, parse_iso(k["utc"]) - u0 - timedelta(seconds=k["t"] - t_end))
        if room < (want / 3 if turning else timedelta(days=period[body] / 24)):
            continue                                                  # no room for a visible turn: time stays as it was
        keys[:] = [k for k in keys if k not in held]
        keys += [{"t": round(b.start, 3), "utc": iso(u0)}, {"t": round(t_end, 3), "utc": iso(u0 + room)}]
        keys.sort(key=lambda k: k["t"])
        dedup = []
        for k in keys:
            if dedup and abs(dedup[-1]["t"] - k["t"]) < 1e-6:
                dedup[-1] = k
            else:
                dedup.append(k)
        keys[:] = dedup
        notes.append(f"beat {b.id}: time runs {room.total_seconds() / 3600:.1f} hours so {body} visibly "
                     + ("turns" if turning else "moves along its orbit"))
    return notes
