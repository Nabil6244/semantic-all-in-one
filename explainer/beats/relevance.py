"""Relevance and safety checks for map and archive beats (docs/explainer/explainer_cue_schema_v1_2.md, section 2).
`validate_plan` checks structure only; it neither opens asset files nor asks whether a place is spoken. Everything in this module is a check the application does not do.

Word tokens: the narration words are split on anything that is not a letter, digit or apostrophe, so 'Saint-Domingue' is two tokens, each carrying its word's time."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]
LOCAL_EXT = (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v")
T_BEFORE_S, T_AFTER_S = 0.2, 0.6          # a layer may start this long before / after its place's word starts (provisional)
_LATLON = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")
REMOTE_PREFIXES = ("stock_image", "stock_video", "flow_image", "flow_video", "youtube_video")


class PlanBuildError(ValueError):
    def __init__(self, problems: Sequence[str]):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


def toks(text: str) -> List[str]:
    return [t.replace("'", "") for t in re.findall(r"[a-z0-9']+", str(text).lower()) if t.replace("'", "")]   # no apostrophe: the script says "you'll", Whisper writes "youll"


def beat_tokens(words: Sequence[Word], start: float, end: float) -> List[Dict[str, Any]]:
    """Flat tokens of the narration words that START inside [start, end)."""
    out = []
    for i, (w, s, e) in enumerate(words):
        if start - 1e-6 <= s < end - 1e-6:
            for t in toks(w):
                out.append({"tok": t, "start": float(s), "end": float(e), "word_index": i, "word": w})
    return out


def find_phrase(tokens: Sequence[Dict[str, Any]], phrase: str, occurrence: int = 1) -> Optional[Dict[str, Any]]:
    """The `occurrence`-th place in the window where the phrase's tokens follow one another, one narration token each."""
    want = toks(phrase)
    if not want:
        return None
    seen = 0
    for i in range(len(tokens) - len(want) + 1):
        if all(tokens[i + k]["tok"] == want[k] for k in range(len(want))):
            seen += 1
            if seen == occurrence:
                seg = tokens[i:i + len(want)]
                return {"phrase": phrase, "tokens": want, "words": [s["word"] for s in seg], "word_indices": [s["word_index"] for s in seg],
                        "start": seg[0]["start"], "end": seg[-1]["end"], "occurrence": occurrence}
    return None


def asset_refusal(asset: str) -> str:
    """'' when the asset reference looks like a plain local path; otherwise why it is refused. Refuses everything the existing plan would fetch or generate."""
    a = (asset or "").strip()
    if not a:
        return "no asset"
    if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://", a) or a.startswith("//") or a.lower().startswith(("www.", "data:", "mailto:")):
        return f"{a[:50]!r} is a URL or network location (local files only)"
    m = re.match(r"^([A-Za-z_]{3,20}):(?![\\/])", a)
    if m:
        kind = m.group(1).lower()
        return (f"{kind}: references fetch or generate pictures at render time and are refused (local files only)" if kind in REMOTE_PREFIXES
                else f"{m.group(1)}: is not a local file path")
    if "|" in a:
        return "a | list is not a single local file"
    return ""


def local_file_problem(asset: str, base_dir: Optional[Path] = None) -> str:
    bad = asset_refusal(asset)
    if bad:
        return bad
    p = Path(asset).expanduser()
    if not p.is_absolute() and base_dir is not None:
        p = Path(base_dir) / p
    if not p.exists():
        return f"file not found: {asset}"
    if not p.is_file():
        return f"not a regular file: {asset}"
    if p.suffix.lower() not in LOCAL_EXT:
        return f"unsupported file type {p.suffix or '(none)'} (use {', '.join(LOCAL_EXT)})"
    try:
        if p.stat().st_size <= 0:
            return f"empty file: {asset}"
        with open(p, "rb") as f:
            f.read(16)
    except OSError as e:
        return f"unreadable file: {asset} ({e.strerror or e})"
    return ""


@dataclass
class Report:
    problems: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    records: List[Dict[str, Any]] = field(default_factory=list)
    validate_plan_problems: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "problems": self.problems, "warnings": self.warnings, "validate_plan_problems": self.validate_plan_problems, "records": self.records}


def _resolvable(place: str) -> Tuple[bool, str]:
    try:
        from hybrid import geo
        geo.resolve(place)
        return True, ""
    except Exception as e:                      # GeoError or anything the offline resolver raises
        return False, str(e)[:120]


ERA_QUERY_WORDS = frozenset({"historical", "painting", "antique", "engraving"})      # appended by the picture planner for narration before 1800; they ask a search engine for old art and are not narration words


def check_plan(plan: Dict[str, Any], words: Sequence[Word], *, subjects: Optional[Dict[str, Dict[str, List[str]]]] = None, base_dir: Optional[Path] = None,
               resolve_offline: bool = True, allow_sources: Sequence[str] = (), composed: Sequence[str] = ()) -> Report:
    """Check a plan dict (the Hybrid JSON shape) against the narration. `subjects` = {beat_id: {clip_index (as text): [subject phrases]}} for archive clips. `composed` = the beat
    ids whose Flow image prompt was written by the scene reading (explainer/scene_intel.flow_prompt): place, period, people and art style are added on purpose, so only the
    spoken-words rule is lifted for them."""
    from hybrid.plan import HybridPlan, PlanError, validate_plan
    from ..captions.timing import resolve_caption

    rep = Report()
    subjects = subjects or {}
    try:
        hp = HybridPlan.from_dict(copy.deepcopy(plan))
    except PlanError as e:
        rep.problems += [f"plan: {p}" for p in e.problems]
        return rep
    rep.validate_plan_problems = validate_plan(hp)
    rep.problems += [f"validate_plan: {p}" for p in rep.validate_plan_problems]
    steps = sorted(((c.t if c.action != "start" else 0.0, c.place, c.frame) for b in hp.beats for c in b.camera if c.place), key=lambda x: x[0])
    try:
        from . import framing as _FR
        views = _FR.plan_views(plan.get("beats", []))
    except Exception:
        views = []

    def framed(place: str, t: float, wide: bool = False) -> Optional[bool]:
        """True/False when the camera target in force at time t (the latest step at or before t) contains `place`; None when it cannot be told."""
        cur = [s for s in steps if s[0] <= t + 1e-9]
        if not cur:
            return None
        try:                                              # the real view (the application's own projection, pull_back / push_in included): the whole place must be inside it
            from . import framing as FR
            v = FR.view_at(views, t)
            if v is not None:
                bb_ = FR.place_bbox(place)
                return FR.inside(FR.view_box(*v), bb_) or (wide and FR.shown_wide(FR.view_box(*v), bb_))      # a world view of three or more places: centred in frame and mostly visible
        except Exception:
            pass
        cam = cur[-1][1]
        if toks(cam) == toks(place):
            return True
        try:
            from hybrid import geo
            c, p = geo.resolve(cam), geo.resolve(place)
        except Exception:
            return None
        if not getattr(c, "is_area", False):
            return False
        x0, y0, x1, y1 = c.bbox
        return x0 <= p.lon <= x1 and y0 <= p.lat <= y1
    for b in hp.beats:
        tk = beat_tokens(words, b.start, b.end)
        if b.mode in ("map", "map_footage"):
            for lay in b.layers:
                rec: Dict[str, Any] = {"beat": b.id, "layer": lay.id, "type": lay.type, "t": lay.t}
                places = [lay.place] if lay.type in ("marker", "zone_label", "fill") else list(lay.places) if lay.type == "line" else []
                starts = []
                for pl in places:
                    if lay.type == "line" and str(lay.id).endswith("_dir1") and _LATLON.match(pl.replace(" ", "")):      # the direction cue's own ends are coordinates; the claim it makes is the direction word + the named place checked below
                        continue
                    m = find_phrase(tk, pl)
                    if m is None:
                        rep.problems.append(f"beat {b.id}: layer {lay.id}: the place {pl!r} is not spoken inside this beat's narration ({b.start:g} to {b.end:g} s); "
                                            f"a mention elsewhere in the script does not count")
                        continue
                    rec.setdefault("matches", []).append(m)
                    starts.append(m["start"])
                    if resolve_offline:
                        ok, why = _resolvable(pl)
                        rec.setdefault("resolvable_offline", {})[pl] = ok
                        if not ok:
                            rep.problems.append(f"beat {b.id}: layer {lay.id}: the application's offline place lookup cannot find {pl!r} ({why})")
                if resolve_offline:
                    for pl in places:
                        fr = framed(pl, lay.t, len({x.place for x in b.layers if x.type in ("fill", "marker") and x.place}) >= 3)
                        if fr is False:
                            rep.warnings.append(f"beat {b.id}: layer {lay.id}: the camera is not looking at an area that contains {pl!r} when the layer appears, so it may be off screen "
                                                f"(warning only: the real view is not computed)")
                if places and len(starts) == len(places):
                    ref = max(starts) if lay.type == "line" else starts[0]
                    rec["t_minus_word_start"] = round(lay.t - ref, 4)
                    if lay.type == "line":
                        lo = min(starts)
                        if not (lo - T_BEFORE_S <= lay.t <= max(starts) + T_AFTER_S):
                            rep.problems.append(f"beat {b.id}: layer {lay.id}: it starts at {lay.t:g} s but its places are spoken between {lo:.2f} and {max(starts):.2f} s")
                    elif not (-T_BEFORE_S - 1e-9 <= lay.t - ref <= T_AFTER_S + 1e-9):
                        rep.problems.append(f"beat {b.id}: layer {lay.id}: it starts at {lay.t:g} s but {places[0]!r} is spoken at {ref:.2f} s "
                                            f"(allowed: {-T_BEFORE_S:g} to +{T_AFTER_S:g} s)")
                if lay.type in ("marker", "zone_label") and lay.label:
                    lt = toks(lay.label)
                    if lt != toks(lay.place) and find_phrase(tk, lay.label) is None:
                        rep.problems.append(f"beat {b.id}: layer {lay.id}: the label {lay.label!r} is neither the place nor words spoken in this beat")
                if lay.type == "caption":
                    first = toks(lay.text)[:1]
                    cand = [t for t in tk if t["tok"] == (first[0] if first else None) and t["start"] >= lay.t - 0.25]
                    if not cand:
                        rep.problems.append(f"beat {b.id}: layer {lay.id}: the caption {lay.text!r} does not start with a word spoken at or after {lay.t - 0.25:.2f} s in this beat")
                    else:
                        a = cand[0]
                        win = [i for i, (_w, s, _e) in enumerate(words) if s >= a["start"] - 1e-6 and s < b.end - 1e-6]
                        ct = resolve_caption(lay.id, lay.text, "words", a["start"], words, win, 0, None, b.end, b.end, 30)
                        rec["caption"] = ct.to_dict()
                        if ct.problems or ct.rung >= 3:
                            rep.problems.append(f"beat {b.id}: layer {lay.id}: the caption {lay.text!r} is not supported by the narration of this beat (rung {ct.rung})")
                        elif abs(lay.t - ct.reveal_times[0]) > 0.05:
                            rep.problems.append(f"beat {b.id}: layer {lay.id}: it starts at {lay.t:g} s but its first word is spoken at {ct.reveal_times[0]:.2f} s")
                        if ct.rung == 2:
                            rep.warnings.append(f"beat {b.id}: layer {lay.id}: the caption {lay.text!r} is only partly supported by the narration (rung 2)")
                        if ct.over_policy:
                            rep.warnings.append(f"beat {b.id}: layer {lay.id}: the caption has more than 8 words")
                rep.records.append(rec)
            for c in b.camera:
                if c.action == "fly_to" and c.place and find_phrase(tk, c.place) is None:
                    rep.warnings.append(f"beat {b.id}: camera fly_to {c.place!r} is not spoken inside this beat (warning only; the opening start camera is exempt)")
            for k, card in enumerate(b.cards):
                src_c, sep_c, query_c = (card.asset or "").partition(":")
                if allow_sources and sep_c and src_c in allow_sources:      # a reference for the application's own source: every query word must be spoken inside this beat
                    spoken_c = {t["tok"] for t in tk} | ERA_QUERY_WORDS
                    miss_c = [w for w in toks(query_c) if w not in spoken_c]
                    if not toks(query_c) or miss_c:
                        rep.problems.append(f"beat {b.id}: photo card {k + 1}: the query {query_c!r} has words that are not spoken inside this beat's narration: {', '.join(miss_c) or '(none)'}")
                    continue
                why = local_file_problem(card.asset, base_dir)
                if why:
                    rep.problems.append(f"beat {b.id}: photo card {k + 1}: {why}")
        elif b.mode == "footage":
            for k, c in enumerate(b.clips):
                rec = {"beat": b.id, "clip": k, "asset": c.asset, "reason": c.reason}
                src, _sep, query = (c.asset or "").partition(":")
                if allow_sources and _sep and src in allow_sources:        # a reference for the application's own source: its query must be about this beat's own words
                    q = toks(query)
                    spoken = {t["tok"] for t in tk} | ERA_QUERY_WORDS
                    missing = [] if (b.id in composed and src == "flow_image") else [w for w in q if w not in spoken]
                    if not q:
                        rep.problems.append(f"beat {b.id}: clip {k + 1}: the {src} reference has no query")
                    elif missing:
                        rep.problems.append(f"beat {b.id}: clip {k + 1}: the query {query!r} has words that are not spoken inside this beat's narration: {', '.join(missing)}")
                    if not (c.reason or "").strip():
                        rep.problems.append(f"beat {b.id}: clip {k + 1}: a footage clip needs a non-empty reason")
                    rec["query"], rec["source"] = query, src
                    for lay in b.layers:
                        if lay.type == "template" and (lay.kind or "") == "typed_caption" and find_phrase(tk, lay.text or "") is None:
                            rep.problems.append(f"beat {b.id}: layer {lay.id}: the caption {lay.text!r} is not a contiguous quote of this beat's narration")
                    rep.records.append(rec)
                    continue
                why = local_file_problem(c.asset, base_dir)
                if why:
                    rep.problems.append(f"beat {b.id}: clip {k + 1}: {why}")
                if not (c.reason or "").strip():
                    rep.problems.append(f"beat {b.id}: clip {k + 1}: an archive clip needs a non-empty reason (what it shows that the map cannot)")
                subj = (subjects.get(b.id) or {}).get(str(k)) or (subjects.get(b.id) or {}).get("*") or []
                if not subj:
                    rep.problems.append(f"beat {b.id}: clip {k + 1}: no subject phrase was given, so its relevance to the narration cannot be established")
                else:
                    hits = [m for m in (find_phrase(tk, s) for s in subj) if m]
                    rec["subject_matches"] = hits
                    if not hits:
                        rep.problems.append(f"beat {b.id}: clip {k + 1}: none of its subjects {subj} is spoken inside this beat's narration")
                rep.records.append(rec)
    return rep


def assemble_plan(duration: float, beats: Sequence[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"version": 1, "duration": float(duration), "settings": dict(settings or {}), "beats": [copy.deepcopy(b) for b in beats]}
