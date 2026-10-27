"""War Documentary: which clip belongs under which narration, as an ESTIMATE from metadata.

Nothing here looks at pixels. A clip's relevance is estimated from what its record says (stock_query, video_title, description, tags, channel,
file name, ...) compared with what the narration names (figures, equipment, places, countries, years, topic words). A good score means "the
record's words agree with the narration", never "this clip shows it". The result is therefore a class, not a verdict:

    verified_event   the record carries a confirmed verification, is not generic stock, and agrees with the narration
    user_supplied    the user's own file (rights stated by the user); still scored, still flagged when it contradicts the narration
    relevant_stock   generic stock/b-roll whose record agrees with the narration; shown as stock, never as footage of a specific event
    illustrative     weak, contradictory or unknown: labelled ILLUSTRATIVE FOOTAGE by the planner (or replaced by a card/map)
    ai_generated     a generated clip (Flow records, or a file marked ai_generated): generic=True and an illustration, never footage of an event

Contradiction (a different named system, a different named person, a different country, a different year) is flagged as mismatch even when
other words agree: Patriot footage under narration about the Pantsir is a mismatch whatever the keyword overlap.

Reuse: a clip already in the project (the pool of manifest records and `footage_candidates`) may return for the same SUBJECT (a named figure,
system or place) when its score beats the scene's own clip clearly; a scene that merely shares generic words never pulls a clip. A deliberate
return is marked `reused` (not `recycled`, which means old file footage passed off as new).

Never raises: missing or odd metadata gives "no information", and a scene that cannot be matched keeps whatever it had.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

CLASSES = ("verified_event", "user_supplied", "relevant_stock", "illustrative", "ai_generated")
MAX_USES = 2                 # one clip appears in at most this many scenes of a video
RELEVANT_MIN = 0.30          # score at or above which stock counts as relevant
REUSE_MIN = 0.45             # a pool clip must reach this and be a subject match to be reused
REUSE_MARGIN = 0.15          # ... and beat the scene's own clip by this much
SWAP_MARGIN = 0.10           # a candidate replaces the scene's own manifest clip only by this margin
_CONFIRMED = ("confirmed", "event_matched", "geolocated")

_META_TEXT_KEYS = ("stock_query", "query", "search_query", "video_title", "title", "description", "caption", "tags", "keywords", "subject",
                   "channel", "location", "place", "country", "event", "visual_prompt", "prompt", "note")
_STOP = frozenset("""a an and are as at be been but by for from had has have he her his in into is it its of on or our she that the their them they
this those to was were which with will would about after against all also any because before between both can could did do does down during each
even every few first had how if more most much new no not now off once only other out over own same so some such than then there these through
under until up very what when where who why you your said says say""".split())
_COUNTRIES = {"russia": ("russia", "russian", "russians", "kremlin", "moscow"), "ukraine": ("ukraine", "ukrainian", "ukrainians", "kyiv", "kiev"),
              "united states": ("usa", "u s", "us army", "american", "united states", "pentagon", "washington"),
              "china": ("china", "chinese", "beijing"), "iran": ("iran", "iranian", "tehran"), "israel": ("israel", "israeli"),
              "belarus": ("belarus", "belarusian"), "poland": ("poland", "polish"), "turkey": ("turkey", "turkish", "turkiye")}
_YEAR = re.compile(r"\b(19[4-9]\d|20[0-4]\d)\b")


def _norm(text: Any) -> str:
    try:
        from .catalog import normalise
        return normalise(str(text or ""))
    except Exception:
        return re.sub(r"[\W_]+", " ", str(text or "").lower()).strip()


def _words(norm_text: str) -> Set[str]:
    return {w for w in norm_text.split() if len(w) > 2 and w not in _STOP and not w.isdigit()}


def _flatten(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple, set)):
        return " ".join(_flatten(x) for x in v)
    if isinstance(v, dict):
        return " ".join(_flatten(x) for x in v.values())
    return str(v)


def clip_text(meta: Optional[Dict[str, Any]], path: str = "") -> str:
    """All descriptive words the record holds, as one string (file name included: 'pantsir_site_03.mp4')."""
    m = meta if isinstance(meta, dict) else {}
    parts = [_flatten(m.get(k)) for k in _META_TEXT_KEYS]
    if path:
        parts.append(Path(str(path)).stem.replace("_", " ").replace("-", " "))
    return " ".join(p for p in parts if p)


def _countries_in(norm_text: str) -> Set[str]:
    padded = f" {norm_text} "
    return {c for c, marks in _COUNTRIES.items() if any(f" {m} " in padded for m in marks)}


def _years_in(text: str) -> Set[int]:
    return {int(y) for y in _YEAR.findall(str(text or ""))}


def _catalog_hits(text: str) -> Dict[str, Dict[str, str]]:
    """{kind: {id: name}} for the specific figures / equipment / places named in `text`; generic classes come back under 'class'."""
    out: Dict[str, Dict[str, str]] = {"figure": {}, "equipment": {}, "place": {}, "class": {}}
    try:
        from . import catalog as C
    except Exception:
        return out
    for kind, fn in (("figure", "find_figure"), ("equipment", "find_equipment"), ("place", "find_place")):
        try:
            for m in getattr(C, fn)(text) or []:
                if m.entry and m.confidence != "generic":
                    out[kind][str(m.entry.get("id") or m.entry.get("name"))] = str(m.entry.get("name") or "")
                elif kind == "equipment" and m.class_id:
                    out["class"][str(m.class_id)] = str(m.matched_alias or m.class_id)
        except Exception:
            continue
    return out


def _entry_of(kind: str, eid: str) -> Dict[str, Any]:
    try:
        from . import catalog as C
        if kind == "equipment":
            return C.get_equipment(eid) or {}
    except Exception:
        pass
    return {}


class Profile:
    """What a piece of text names. Built once per scene and once per clip."""

    def __init__(self, text: str):
        self.norm = _norm(text)
        self.words = _words(self.norm)
        self.hits = _catalog_hits(str(text or ""))
        self.countries = _countries_in(self.norm)
        self.years = _years_in(text)

    @property
    def subjects(self) -> Set[str]:
        return {f"{k}:{i}" for k in ("figure", "equipment", "place") for i in self.hits[k]}


def narration_profile(text: str) -> Profile:
    return Profile(text)


def score_clip(narr: Profile, meta: Optional[Dict[str, Any]], path: str = "") -> Dict[str, Any]:
    """{score 0..1, reasons [str], contradictions [str], subject_match (bool: shares a named figure/system/place), informative (bool)}.
    `informative` is False when the record says nothing usable: the score is then 0 and the clip is illustrative, not 'wrong'."""
    text = clip_text(meta, path)
    if not text.strip():
        return {"score": 0.0, "reasons": [], "contradictions": [], "subject_match": False, "informative": False}
    clip = Profile(text)
    score, reasons, contra = 0.0, [], []
    subject_match = False
    # equipment: the exact system, or a different named system (contradiction, look-alikes included)
    n_eq, c_eq = set(narr.hits["equipment"]), set(clip.hits["equipment"])
    if n_eq and c_eq:
        both = n_eq & c_eq
        if both:
            score += 0.45
            subject_match = True
            reasons.append("names the same system: " + ", ".join(sorted(narr.hits["equipment"][i] for i in both)))
        else:
            contra.append("clip names " + ", ".join(sorted(clip.hits["equipment"].values())) + " but the narration is about " + ", ".join(sorted(narr.hits["equipment"].values())))
    elif n_eq and clip.hits["class"] and not c_eq:
        classes = {str((_entry_of("equipment", i) or {}).get("class", "")) for i in n_eq}
        if classes & set(clip.hits["class"]):
            score += 0.15
            reasons.append("same kind of equipment (" + ", ".join(sorted(classes & set(clip.hits["class"]))) + "), system not named")
    # figures
    n_fi, c_fi = set(narr.hits["figure"]), set(clip.hits["figure"])
    if n_fi and c_fi:
        both = n_fi & c_fi
        if both:
            score += 0.4
            subject_match = True
            reasons.append("names the same person: " + ", ".join(sorted(narr.hits["figure"][i] for i in both)))
        else:
            contra.append("clip names " + ", ".join(sorted(clip.hits["figure"].values())) + " but the narration is about " + ", ".join(sorted(narr.hits["figure"].values())))
    # places
    n_pl, c_pl = set(narr.hits["place"]), set(clip.hits["place"])
    if n_pl and c_pl:
        both = n_pl & c_pl
        if both:
            score += 0.3
            subject_match = True
            reasons.append("names the same place: " + ", ".join(sorted(narr.hits["place"][i] for i in both)))
        elif len(c_pl) and not (n_eq & c_eq) and not (n_fi & c_fi):
            contra.append("clip names " + ", ".join(sorted(clip.hits["place"].values())) + ", the narration " + ", ".join(sorted(narr.hits["place"].values())))
    # countries
    if narr.countries and clip.countries:
        if narr.countries & clip.countries:
            score += 0.1
            reasons.append("same country: " + ", ".join(sorted(narr.countries & clip.countries)))
        else:
            contra.append("clip is about " + ", ".join(sorted(clip.countries)) + ", the narration about " + ", ".join(sorted(narr.countries)))
    # period
    if narr.years and clip.years:
        if narr.years & clip.years or any(abs(a - b) <= 1 for a in narr.years for b in clip.years):
            score += 0.1
            reasons.append("same period")
        else:
            contra.append("clip dated " + ", ".join(map(str, sorted(clip.years))) + ", the narration " + ", ".join(map(str, sorted(narr.years))))
    # topic words (a weak signal: capped so words alone never make footage 'relevant' to a named subject)
    shared = narr.words & clip.words
    if shared and clip.words:
        k = min(0.2, 0.05 * len(shared))
        score += k
        reasons.append("shared words: " + ", ".join(sorted(shared)[:6]))
    if contra:
        score = max(0.0, score - 0.4)
    return {"score": round(min(1.0, score), 3), "reasons": reasons, "contradictions": contra, "subject_match": subject_match, "informative": True}


def classify(meta: Optional[Dict[str, Any]], scored: Dict[str, Any]) -> str:
    m = meta if isinstance(meta, dict) else {}
    contradicted = bool(scored["contradictions"])
    ver = str(m.get("verification") or m.get("war_status") or "").lower()
    if m.get("ai_generated") or m.get("kind") == "generated":
        return "ai_generated"             # first: an AI clip the user cut into their own file is still an illustration, never an event
    if m.get("user_supplied") or m.get("kind") == "user":
        return "user_supplied"
    if contradicted or not scored["informative"]:
        return "illustrative"
    if m.get("kind") == "generated":
        return "illustrative"
    if ver in _CONFIRMED and not m.get("generic") and scored["score"] >= 0.5:
        return "verified_event"
    if scored["score"] >= RELEVANT_MIN:
        return "relevant_stock" if m.get("generic") or m.get("kind") in ("stock", "unknown", None) else "illustrative"
    return "illustrative"


def _entry(path: str, meta: Optional[Dict[str, Any]], source: str) -> Dict[str, Any]:
    return {"path": str(path), "meta": dict(meta or {}), "source": source}


def _norm_candidates(items: Optional[Iterable[Any]], source: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items or []:
        try:
            if isinstance(it, str):
                out.append(_entry(it, {}, source))
            elif isinstance(it, dict):
                p = it.get("path") or it.get("footage") or it.get("local_path")
                if p:
                    out.append(_entry(p, it.get("meta") or it.get("footage_meta") or {k: v for k, v in it.items() if k not in ("path", "footage")}, source))
        except Exception:
            continue
    return out


def _apply_flags(meta: Dict[str, Any], scored: Dict[str, Any], cls: str, *, reused_from: str = "") -> Dict[str, Any]:
    """The clip's footage_meta with the estimate recorded and the planner's existing flags set. Flags the caller already set stay."""
    m = dict(meta or {})
    m["footage_class"] = cls
    m["relevance"] = scored["score"]
    m["relevance_reasons"] = list(scored["reasons"])
    m["relevance_contradictions"] = list(scored["contradictions"])
    m["relevance_note"] = "estimated from metadata (not proof of what the clip shows)"
    if scored["contradictions"]:
        m["mismatch"] = True
    if cls == "ai_generated":
        m["generic"] = True
        m["ai_generated"] = True
        m.pop("stock_relevant", None)
    if cls == "illustrative" and m.get("generic") is not False:
        m["generic"] = True            # the planner's existing rule then labels it ILLUSTRATIVE FOOTAGE and writes no headline over it
    if cls == "relevant_stock":
        m["stock_relevant"] = True
    if reused_from:
        m["reused"] = True
        m["reused_from_scene"] = reused_from
    return m


def match_scenes(scenes: Sequence[Dict[str, Any]], pool: Optional[Iterable[Any]] = None, *, allow_reuse: bool = True) -> List[Dict[str, Any]]:
    """Score and choose footage for each scene (in place on copies; returns the new list). For each scene the candidates are
    its own footage, its `footage_candidates` and, for reuse, the project pool. A scene's own file given explicitly by the user is never swapped
    out (it is scored and flagged only). Each result scene gets `footage_match` = {score, class, reasons, contradictions, chosen, source, note}."""
    pool_entries = _norm_candidates(pool, "pool")
    out: List[Dict[str, Any]] = []
    used_by: Dict[str, str] = {}          # path -> first scene no that used it
    uses: Dict[str, int] = {}             # path -> how many scenes use it so far
    prev_path = ""
    for sc in scenes:
        s = dict(sc)
        no = str(s.get("scene_no", ""))
        try:
            narr = narration_profile(str(s.get("text") or ""))
            own_path = s.get("footage") or ""
            own_meta = dict(s.get("footage_meta") or {})
            pinned = bool(own_path) and (own_meta.get("user_supplied") or own_meta.get("pinned") or own_meta.get("kind") == "user")
            cands: List[Dict[str, Any]] = []
            if own_path:
                cands.append(_entry(own_path, own_meta, "own"))
            cands += _norm_candidates(s.get("footage_candidates"), "candidate")
            scored_own = score_clip(narr, own_meta, own_path) if own_path else None
            best = None
            for c in cands:
                c["scored"] = scored_own if c["source"] == "own" else score_clip(narr, c["meta"], c["path"])
                if best is None:
                    best = c
                elif c["scored"]["score"] > best["scored"]["score"] + (SWAP_MARGIN if best["source"] == "own" else 0.0):
                    best = c
            if pinned:
                best = cands[0]
            reused_from = ""
            if allow_reuse and not pinned and narr.subjects:
                cur = best["scored"]["score"] if best else -1.0
                for p in pool_entries:
                    if p["path"] == (best or {}).get("path") or uses.get(p["path"], 0) >= MAX_USES:
                        continue
                    ps = score_clip(narr, p["meta"], p["path"])
                    if (ps["subject_match"] and not ps["contradictions"] and ps["score"] >= REUSE_MIN and ps["score"] >= cur + REUSE_MARGIN
                            and p["path"] != prev_path):
                        p = dict(p, scored=ps)
                        best, cur = p, ps["score"]
                        reused_from = used_by.get(p["path"], "pool")
            limit_note = ""
            if best is not None and not pinned and not reused_from:
                # a clip is not shown in more than MAX_USES scenes, nor in two scenes in a row, unless the same subject deliberately returns
                n_used = uses.get(best["path"], 0)
                adjacent = best["path"] == prev_path
                if n_used >= MAX_USES or (adjacent and not best["scored"]["subject_match"]):
                    limit_note = f"clip already used {n_used} time(s)" if n_used >= MAX_USES else "same clip as the previous scene"
                    alt = [c for c in cands if c["path"] != best["path"] and uses.get(c["path"], 0) < MAX_USES and c["path"] != prev_path
                           and c["scored"]["reasons"]]
                    best = max(alt, key=lambda c: c["scored"]["score"]) if alt else None
            if best is not None and best["source"] != "own" and not best["scored"]["reasons"]:
                best = None                      # a candidate with nothing in common with the narration is never adopted just because it is there
            if best is None:
                s["footage"] = None
                s["footage_match"] = {"score": 0.0, "class": "illustrative", "reasons": [], "contradictions": [], "chosen": None, "source": "none",
                                      "note": ("no clip (" + limit_note + "): a card, map or labelled backdrop is used") if limit_note
                                      else "no clip: a card, map or labelled backdrop is used", "uses": 0}
                out.append(s)
                prev_path = ""
                continue
            cls = classify(best["meta"], best["scored"])
            if best["path"] in used_by and not reused_from and best["path"] != own_path:
                reused_from = used_by[best["path"]]
            if best["path"] in used_by and best["source"] == "own" and cls != "illustrative" and best["scored"]["subject_match"]:
                reused_from = used_by[best["path"]]      # the same subject returning with the same clip is deliberate
            meta = _apply_flags(best["meta"], best["scored"], cls, reused_from=reused_from)
            weak = bool(narr.subjects) and not best["scored"]["reasons"] and not best["scored"]["contradictions"]
            if weak:                             # kept (it may be the user's own pick) but never presented as footage of what is being said
                meta["weak_match"] = True
                meta["mismatch"] = True
                best["scored"]["contradictions"] = list(best["scored"]["contradictions"]) + ["nothing in the clip's metadata relates to the subjects named in the narration"]
            if meta.get("reused") and meta.get("recycled") and not best["meta"].get("recycled"):
                meta.pop("recycled", None)
            s["footage"], s["footage_meta"] = best["path"], meta
            s["footage_match"] = {"score": best["scored"]["score"], "class": cls, "reasons": best["scored"]["reasons"],
                                  "contradictions": best["scored"]["contradictions"], "chosen": os.path.basename(best["path"]), "source": best["source"],
                                  "reused_from_scene": reused_from or None, "note": meta["relevance_note"]}
            used_by.setdefault(best["path"], no)
            uses[best["path"]] = uses.get(best["path"], 0) + 1
            s["footage_match"]["uses"] = uses[best["path"]]
            prev_path = best["path"]
        except Exception as exc:                 # odd metadata must never stop a render: the scene keeps what it had
            s["footage_match"] = {"score": 0.0, "class": "illustrative", "reasons": [], "contradictions": [], "chosen": None, "source": "error",
                                  "note": f"relevance estimate skipped ({type(exc).__name__})"}
        out.append(s)
    return out
