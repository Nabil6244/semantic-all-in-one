"""Beat grouping and the choice of kind (map, archive, board) for each beat."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..beats.relevance import beat_tokens, find_phrase, local_file_problem
from .options import DirectorOptions
from . import lexicon as LX
from . import meaning as MN
from .segment import Sent, norm


@dataclass
class PlaceHit:
    name: str
    kind: str
    is_area: bool
    match: Dict[str, Any]


@dataclass
class BeatPlan:
    id: str
    start: float
    end: float
    sents: List[Sent]
    kind: str = "board"             # board | map | archive
    places: List[PlaceHit] = field(default_factory=list)
    archive: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)
    comparisons: List[str] = field(default_factory=list)      # places spoken here only as a yardstick ("the size of England"): never a map trigger
    scene_hint: Optional[str] = None                          # a cartoon beat whose words name no scene stands its cast on this stage (v2 fallback)
    idea: str = ""                                            # the idea the beat carries (meaning.py): spatial | quantitative | comparative | dialogue | evidence | cause; "" = no clear signal (only with DirectorOptions.meaning)
    source: str = ""                                          # a footage beat made by the picture pass (compose_pictures) names its own source here; "" = DirectorOptions.footage_source
    picture_query: str = ""                                   # ... and its query (only with DirectorOptions.pictures)

    @property
    def dur(self) -> float:
        return self.end - self.start


def group(sents: Sequence[Sent], duration: float, opt: DirectorOptions) -> List[BeatPlan]:
    """Greedy grouping into beats of min_beat_s..max_beat_s that tile 0..duration."""
    def eff_end(i: int) -> float:                 # a beat runs to the next sentence's start, so it includes the pause after its last sentence
        return sents[i + 1].start if i + 1 < len(sents) else duration

    groups: List[List[Sent]] = []
    cur: List[Sent] = []
    for i, s in enumerate(sents):
        if cur and (eff_end(i) - cur[0].start) > opt.max_beat_s:
            groups.append(cur)
            cur = []
        cur.append(s)
        if (eff_end(i) - cur[0].start) >= opt.min_beat_s or s.para_end:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    # a beat under 2 s (a one-line paragraph, the tail) cannot be taken in and fails the Hybrid validator: fold it into its neighbour
    k = 0
    while len(groups) > 1 and k < len(groups):
        end_k = groups[k + 1][0].start if k + 1 < len(groups) else duration
        if end_k - groups[k][0].start < 2.0:
            if k + 1 < len(groups):
                groups[k] += groups.pop(k + 1)
            else:
                groups[k - 1] += groups.pop(k)
                k -= 1
            continue
        k += 1
    beats = []
    for k, g in enumerate(groups):
        start = 0.0 if k == 0 else g[0].start
        end = duration if k == len(groups) - 1 else groups[k + 1][0].start
        beats.append(BeatPlan(f"e{k + 1}", start, end, g))
    return beats


_PLACE_KINDS = ("country", "region", "admin1", "admin2", "city", "county", "state")


def place_candidates(script: Optional[str], opt: DirectorOptions, limit: int = 60) -> Tuple[List[str], set]:
    """(candidate names, the names seen only at a sentence start). A sentence-start word is capitalised anyway, so it counts only if it resolves to a country or region
    (or is capitalised elsewhere, or the caller listed it): 'In', 'Nice', 'Mobile', 'Sale' and 'Reading' all resolve to something."""
    out: List[str] = []
    weak: set = set()
    for p in opt.places:
        if p and p not in out:
            out.append(p)
    if script:
        for sent in re.split(r"(?<=[.!?])\s+|\n+", script):
            toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", sent)
            if toks and toks[0][0].isupper() and norm(toks[0]) not in LX.STOP and toks[0] not in out:
                out.append(toks[0])
                weak.add(toks[0])
            run: List[str] = []
            for k, t in enumerate(toks + [""]):
                if t and t[0].isupper() and k > 0:
                    run.append(t)
                else:
                    for n in (3, 2, 1):
                        if len(run) >= n:
                            for i in range(len(run) - n + 1):
                                name = " ".join(run[i:i + n])
                                weak.discard(name)
                                if name not in out:
                                    out.append(name)
                    run = []
    return out[:limit], weak


NOT_PLACES = frozenset("republic empire kingdom now back grand today arsenal union state states federation league council".split())


def resolve_places(cands: Sequence[str], weak: set = frozenset(), allow: Sequence[str] = ()) -> Tuple[Dict[str, Tuple[str, bool]], List[str]]:
    """Names the offline lookup knows. A single direction word ("South", "North") is not a place on its own: the lookup answers with some region called that (South Lebanon), which is
    wrong for "The South is blazing"; it counts only when the caller lists it (`allow`) and is otherwise ignored with that reason. A name the lookup cannot find is ignored, never replaced by a near match."""
    from hybrid import geo

    ok: Dict[str, Tuple[str, bool]] = {}
    ignored: List[str] = []
    for c in cands:
        if c.strip().lower() in NOT_PLACES and c not in allow:
            ignored.append(c + " (a common word the lookup would take for some small county, not a place the narration means)")
            continue
        if c.strip().lower() in LX.OCEAN_WORDS and c not in allow:
            ignored.append(c + " (an ocean, not a place the map can mark)")
            continue
        if c.strip().lower() in LX.DIRECTION_WORDS and c not in allow:
            ignored.append(c + " (ambiguous direction word, not a place on its own)")
            continue
        try:
            r = geo.resolve(c)
            if c in weak and str(r.kind) not in ("country", "region"):
                ignored.append(c + " (sentence start, not a country or region)")
                continue
            ok[c] = (str(r.kind), bool(r.is_area))
        except Exception:
            ignored.append(c)
    return ok, ignored


def places_in(beat: BeatPlan, words, resolved: Dict[str, Tuple[str, bool]]) -> List[PlaceHit]:
    tk = beat_tokens(words, beat.start, beat.end)
    hits = []
    beat.comparisons = []
    for name, (kind, area) in resolved.items():
        m = None
        occ = 1
        while True:                                       # the first mention that is not a yardstick ("the size of England") is the one that counts
            cand = find_phrase(tk, name, occ)
            if cand is None:
                break
            before = " ".join(t["tok"] for t in tk[:next(i for i, t in enumerate(tk) if t["word_index"] == cand["word_indices"][0])][-4:])
            if any(re.search(r"(?:^|\s)" + pat + r"$", before) for pat in LX.COMPARISON_BEFORE):
                beat.comparisons.append(f"{name} ({before} {name.lower()}) at {cand['start']:.1f} s: a size comparison, not a place to show")
                occ += 1
                continue
            m = cand
            break
        if m:
            hits.append(PlaceHit(name, kind, area, m))
    hits.sort(key=lambda h: h.match["start"])
    # a longer name swallows a shorter one spoken inside it ("New York" vs "York")
    keep = [h for h in hits if not any(o is not h and set(norm(h.name).split()) < set(norm(o.name).split()) and o.match["start"] <= h.match["start"] <= o.match["end"] for o in hits)]
    return keep


def load_archive(opt: DirectorOptions) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not opt.archive_dir:
        return [], []
    base = Path(opt.archive_dir)
    f = base / "archive.json"
    if not f.is_file():
        return [], [f"archive library: {f} not found"]
    try:
        items = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:
        return [], [f"archive library: {f} is not valid JSON ({e})"]
    good, notes = [], []
    for k, it in enumerate(items if isinstance(items, list) else []):
        why = local_file_problem(str(it.get("file", "")), base)
        if why:
            notes.append(f"archive library entry {k + 1}: {why}")
        elif not str(it.get("reason", "")).strip() or not it.get("subjects"):
            notes.append(f"archive library entry {k + 1}: needs a reason and subjects")
        else:
            good.append({"asset": str((base / it["file"]).resolve()) if not Path(it["file"]).is_absolute() else it["file"], "subjects": [str(s) for s in it["subjects"]], "reason": str(it["reason"]).strip()})
    return good, notes


def _run(beats, k: int, step: int, kind: str) -> int:
    """How many beats of `kind` sit right next to beat k on one side (a run, not a total)."""
    n, j = 0, k + step
    while 0 <= j < len(beats) and beats[j].kind == kind:
        n += 1
        j += step
    return n


def _assign_cartoons(beats: List[BeatPlan], words, duration: float, opt: DirectorOptions, info: Dict[str, Any]) -> None:
    """Opt-in: the board beats that suit a cartoon best (scene words and people words said inside them) become cartoon beats, up to `cartoon_share` of the runtime, never three in a row."""
    from .compose_cartoon import scene_score

    cap = opt.cartoon_share * duration
    used = 0.0
    scored = []
    skipped = []
    for k, b in enumerate(beats):
        if b.kind != "board" or b.dur < opt.min_beat_s - 1e-6:
            continue
        toks = [t["tok"] for t in beat_tokens(words, b.start, b.end)]
        sc = scene_score(toks, scenes2=getattr(opt, "scenes2", False))
        if opt.meaning and b.idea in MN.NOT_CARTOON and sc > 0:
            skipped.append({"beat": b.id, "reason": f"meaning: the beat explains a {b.idea} idea, so a board diagram shows it better than the cartoon scene its words suggest"})
            info.setdefault("meaning_effects", []).append({"beat": b.id, "effect": f"kept off cartoon ({b.idea} idea)"})
            continue
        if sc > 0:
            scored.append((-(sc + (MN.CARTOON_BONUS.get(b.idea, 0) if opt.meaning else 0)), k))
        else:
            skipped.append({"beat": b.id, "reason": "the words name no scene (family, people or rain alone do not choose one): it stays a board"})
    chosen = []
    for _s, k in sorted(scored):
        b = beats[k]
        if used + b.dur > cap + 1e-9:
            continue
        run_l = _run(beats, k, -1, "cartoon")
        if run_l >= 2 or (k + 1 < len(beats) and beats[k + 1].kind == "cartoon" and k + 2 < len(beats) and beats[k + 2].kind == "cartoon"):
            continue
        if run_l == 1 and k + 1 < len(beats) and beats[k + 1].kind == "cartoon":
            continue
        b.kind = "cartoon"
        b.notes.append("cartoon beat: the words suggest a scene and people")
        if opt.meaning and MN.CARTOON_BONUS.get(b.idea):
            info.setdefault("meaning_effects", []).append({"beat": b.id, "effect": f"preferred for a cartoon scene ({b.idea} idea: people speak or deal with each other)"})
        used += b.dur
        chosen.append(b.id)
    if getattr(opt, "scenes2", False):             # a story of people (a general, an emperor, a revolt) names few stages: the cast still stands on a plain town square, up to the same share of the runtime
        from . import lexicon_v2 as LV
        named = set(info.get("named_subjects", ()))
        extra = []
        for k, b in enumerate(beats):
            if b.kind != "board" or b.dur < opt.min_beat_s - 1e-6 or any(s_.label in ("hook", "question") for s_ in b.sents):
                continue
            toks = [t["tok"] for t in beat_tokens(words, b.start, b.end)]
            who = sum(1 for t in toks if t in LV.PEOPLE_V2) + sum(1 for t in toks if t in named)
            if opt.meaning and b.idea in MN.NOT_CARTOON:
                continue
            if who:
                extra.append((-who, k))
        for _s, k in sorted(extra):
            b = beats[k]
            if used + b.dur > cap + 1e-9 or _run(beats, k, -1, "cartoon") >= 1 or _run(beats, k, 1, "cartoon") >= 1:
                continue
            b.kind, b.scene_hint = "cartoon", "old_town"
            b.notes.append("cartoon beat: people are named but no scene word is: the cast stands in the town square")
            used += b.dur
            chosen.append(b.id)
    info["cartoon_beats"] = sorted(chosen)
    info["cartoon_skipped"] = skipped


def named_subjects(script: str, places=()) -> set:
    """Lower-case words the script writes with a capital in the middle of a sentence (Napoleon, Bonaparte, Waterloo, Elba): the people and events a picture of the subject can show. Words that are
    only a nationality or a place the map shows are left to the map."""
    import re
    out = set()
    for m in re.finditer(r"(?<=[a-z,;] )([A-Z][a-z]{2,})", script or ""):
        t = m.group(1).lower()
        if t not in LX.STOP and not t.endswith(("ian", "ish", "ans", "ch")) and t not in {"revolution", "republic", "prussia", "countries", "ocean", "sea", "channel", "battle", "emperor", "congress", "south", "low", "atlantic", "mediterranean", "september", "october", "november", "december", "january", "february", "march", "april", "june", "july", "august", "french", "british", "english", "prussian", "russian", "austrian", "european", "spanish", "german", "italian"}:
            out.add(t)
    return out - {str(p_).lower() for p_ in places}


def footage_blocked(b: BeatPlan, toks: Sequence[str]) -> bool:
    """The opening hook, a question and a beat with a quantity stay boards (a year does not count as a quantity: history is dated). Shared by the footage and the picture passes."""
    return bool({s.label for s in b.sents} & {"hook", "question"}) or any(t.isdigit() and not (len(t) == 4 and 1000 <= int(t) <= 2100) for t in toks)


def footage_run_blocked(beats: List[BeatPlan], k: int) -> bool:
    """True when making beat k a footage beat would put three footage beats in a row."""
    run_l = _run(beats, k, -1, "footage")
    run_r = _run(beats, k, 1, "footage")
    return run_l + run_r >= 2 or (run_l >= 1 and run_r >= 1)


def _assign_footage(beats: List[BeatPlan], words, duration: float, opt: DirectorOptions, info: Dict[str, Any]) -> None:
    """Opt-in: board beats whose words name things a camera can film (ships, armies, railways, markets) become footage beats, up to `footage_share` of the runtime, never three in a row. The
    opening hook, questions and beats with numbers stay boards: they belong to the narrator and the pictures. The application's own sources supply the clips."""
    cap = opt.footage_share * duration
    used = 0.0
    scored, skipped = [], []
    for k, b in enumerate(beats):
        if b.kind != "board" or b.dur < opt.min_beat_s - 1e-6:
            continue
        toks = [t["tok"] for t in beat_tokens(words, b.start, b.end)]
        if footage_blocked(b, toks):
            skipped.append({"beat": b.id, "reason": "an opening, a question or a number: it stays a board"})
            continue
        if opt.meaning and b.idea in MN.NOT_FOOTAGE:
            skipped.append({"beat": b.id, "reason": f"meaning: the beat explains a {b.idea} idea, so a diagram says it and a camera cannot"})
            info.setdefault("meaning_effects", []).append({"beat": b.id, "effect": f"kept off footage ({b.idea} idea)"})
            continue
        strong = sum(1 for t in toks if t in LX.CONCRETE_STRONG)
        named = sum(1 for t in toks if t in info.get("named_subjects", ()))
        bonus = MN.FOOTAGE_BONUS.get(b.idea, 0) if opt.meaning else 0
        if strong == 0 and named:
            scored.append((-(named + bonus), k))          # a person or an event is named: a picture of the subject (a portrait, a painting) is the footage
            continue
        if strong == 0:
            skipped.append({"beat": b.id, "reason": "nothing a camera can film is said (a title or a single object is better as a board): it stays a board"})
            continue
        scored.append((-(2 * strong + sum(1 for t in toks if t in LX.CONCRETE_WEAK) + bonus), k))
    chosen = []
    for _s, k in sorted(scored):
        b = beats[k]
        if used + b.dur > cap + 1e-9:
            continue
        if footage_run_blocked(beats, k):
            continue
        b.kind = "footage"
        b.notes.append("footage beat: the words name something a camera can film")
        used += b.dur
        chosen.append(b.id)
    info["footage_beats"] = sorted(chosen)
    info["footage_skipped"] = skipped


def annotate_meaning(beats: List[BeatPlan], words, named: Sequence[str]) -> Dict[str, Any]:
    """Opt-in: give every beat the idea its narration carries (meaning.py) and return the per-beat scores for the report."""
    out: Dict[str, Any] = {}
    named_set = set(named)
    for b in beats:
        toks = [t["tok"] for t in beat_tokens(words, b.start, b.end)]
        m = MN.classify(toks, " ".join(s_.text for s_ in b.sents), has_place=bool(b.places), has_named=any(t in named_set for t in toks))
        b.idea = m.idea
        out[b.id] = m.to_dict()
    return out


def choose_kinds(beats: List[BeatPlan], words, script, duration: float, opt: DirectorOptions) -> Dict[str, Any]:
    cands, weak = place_candidates(script, opt)
    resolved, ignored = resolve_places(cands, weak, opt.places)
    library, lib_notes = load_archive(opt)
    used_assets = set()
    map_s = arch_s = 0.0
    run_maps = 0
    info: Dict[str, Any] = {"place_candidates": cands, "places_resolved": {k: list(v) for k, v in resolved.items()}, "places_ignored": ignored, "archive_notes": lib_notes, "warnings": [], "places_comparison": [], "places_not_shown": []}
    from ..beats import geography as GEO
    _cands = []
    _people = set(named_subjects(script or "", list(resolved)))      # a beat that names a person AND a place is the one where a portrait card beside the map earns its place
    for _k, b in enumerate(beats):
        b.places = places_in(b, words, resolved)
        info["places_comparison"] += [f"{b.id}: {c}" for c in b.comparisons]
        b.notes += [f"{c}" for c in b.comparisons]
        if b.places and b.dur >= opt.map_min_beat_s:
            _sc, _why = GEO.map_priority(beat_tokens(words, b.start, b.end), b.places)
            _cands.append({"idx": _k, "id": b.id, "dur": b.dur, "score": _sc})
            if _people & {t["tok"] for t in beat_tokens(words, b.start, b.end)}:
                _sc += 2
                _why.append("a named person is spoken with the place: a portrait card goes beside the map")
            if _sc:
                b.notes.append("geography beat (priority " + str(_sc) + "): " + "; ".join(_why))
    map_ids = set(GEO.pick_map_beats(_cands, len(beats), opt.max_map_share * duration))
    for b in beats:
        tk = beat_tokens(words, b.start, b.end)
        if b.id in map_ids:
            b.kind = "map"
            map_s += b.dur
            run_maps += 1
            for h in b.places[3:]:
                info["places_not_shown"].append({"place": h.name, "beat": b.id, "at_s": round(float(h.match.get("start", b.start)), 2), "reason": "a map beat draws its first three places only"})
            continue
        run_maps = 0
        for h in b.places:
            why = ("the beat is shorter than map_min_beat_s" if b.dur < opt.map_min_beat_s else
                   f"the map budget ({opt.max_map_share:.0%} of the runtime) or the {2}-in-a-row limit was reached")
            info["places_not_shown"].append({"place": h.name, "beat": b.id, "at_s": round(float(h.match.get("start", b.start)), 2), "reason": why + ": shown as a board"})
        if b.places and b.dur >= opt.map_min_beat_s:
            b.notes.append("places spoken (" + ", ".join(h.name for h in b.places) + ") but the map budget or the 2-in-a-row limit was reached: board beat")
        hit = None
        for it in library:
            if it["asset"] in used_assets:
                continue
            if any(find_phrase(tk, s) for s in it["subjects"]):
                hit = it
                break
        if hit and (arch_s + b.dur) <= opt.max_archive_share * duration + 1e-9:
            b.kind, b.archive = "archive", hit
            used_assets.add(hit["asset"])
            arch_s += b.dur
    info["named_subjects"] = sorted(named_subjects(script or "", [h.name for b_ in beats for h in b_.places]))
    if opt.meaning:
        info["meaning"] = annotate_meaning(beats, words, info["named_subjects"])
    # the required opening map is decided BEFORE the cartoon/footage budgets are spent: it used to turn an already chosen cartoon beat into the map afterwards, and the share it had used stayed spent
    if not any(b.kind == "map" for b in beats):
        first = beats[0]
        fp = None
        try:
            from hybrid import geo
            r = geo.resolve(opt.fallback_place)
            fp = PlaceHit(opt.fallback_place, str(r.kind), bool(r.is_area), {})
        except Exception:
            pass
        if fp is None:
            info["warnings"].append(f"no place is spoken and the fallback place {opt.fallback_place!r} cannot be found: the plan cannot have the map beat Hybrid requires")
        else:
            first.kind, first.places, first.archive = "map", [fp], None
            first.notes.append(f"no place is spoken anywhere: the required opening map shows the fallback place {opt.fallback_place!r} (arbitrary)")
            info["warnings"].append(f"no place qualified: the opening map shows the arbitrary fallback place {opt.fallback_place!r}")
    if opt.cartoon_share > 0:
        _assign_cartoons(beats, words, duration, opt, info)
    if opt.footage_share > 0:
        _assign_footage(beats, words, duration, opt, info)
    if opt.pictures:                                          # opt-in: thin boards that name a pictureable subject become still/footage beats (director/compose_pictures.py)
        from . import compose_pictures as CPX
        info["pictures"] = CPX.upgrade_boards(beats, words, script, duration, opt, info)
    return info
