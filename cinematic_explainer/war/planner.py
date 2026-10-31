"""War Documentary planner: narration -> shots and card layers, deterministic and explained.

    plan(scenes, *, catalog=None, assets=None, config=None) -> Plan(shots, layers, log, credits, stats)

scene   = {text, start, end, words (optional [{w, t0, t1}]), footage (path or None), footage_meta (dict), scene_no}
catalog = module or object with find_equipment / find_figure / find_institution / find_place (default: war.catalog)
assets  = optional {"portrait:<figure id>": path, "equipment:<id>": path} supplying image files; nothing is looked up or downloaded here
config  = optional overrides, see DEFAULTS; "snapshots" is the only way a territorial-control layer can appear (sourced, dated, caller-made)

Order of choice per scene (rules doc 2): footage is the surface; then evidence, attributed figure, statistic, equipment, institution, territory/map,
timeline, comparison. Every candidate is scored, gated by provenance and density, and logged with a reason code when it loses. "No visual" is a
valid outcome. Nothing is invented: card text is the narration's own words or catalog data that carries its source.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..render import Layer, Shot
from . import equipment_images as EQI
from . import semantics as S
from .semantics import SceneAnalysis, SentenceInfo

FPS = 25

DEFAULTS: Dict[str, Any] = {
    # a war explainer is mostly maps and full-frame graphics (docs/war/REFERENCE_PATTERNS.md; the owner, 2026-10-31: "maps and full frame
    # layouts should be used more"): a full-frame graphic may follow another after 8 s, and footage needs only 30 % of the running time
    "first_at": 4.0, "min_gap": 4.0, "full_gap": 8.0, "map_gap": 4.0, "min_card_s": 3.0, "tail_s": 1.0, "lead_s": 0.3, "late_start_s": 2.0,
    "per_minute": 6, "per_minute_footage": 8, "same_kind_gap": 8.0, "same_kind_max": 4, "same_kind_window": 120.0, "same_fact_s": 240.0,
    "clean_floor": 0.30, "clean_floor_min_total": 60.0, "quiet_window": 20.0, "quiet_clear": 10.0, "equipment_repeat_s": 120.0,
    "headline_share": 0.40, "headline_min_s": 2.0, "headline_max_s": 4.2, "kickers": True, "check_kinds": True,
    "narration_status": "unverified", "timeline_status": "attributed", "card_cap_s": None, "short_total_s": 120.0, "profile": "auto", "neutral_map_fallback": True, "filler_footage": None, "snapshots": [], "headlines": True, "direction": True,
}

# logical kind -> layer kind (the card registry key)
LAYER_KIND = {"evidence": "evidence_card", "figure": "figure_card", "number": "stat_number", "compare": "stat_compare", "equipment": "equipment_card",
              "institution": "institution_card", "map": "map_card", "timeline": "timeline", "split": "split_compare", "headline": "shot_headline",
              "kicker": "kicker"}
FULL_FRAME = {"map", "timeline", "split"}
NO_DIM = {"map", "timeline", "split"}   # the map is opaque; timeline and split-compare carry their own scrim/panels, so the footage stays bright
EVIDENCE_KINDS = {"evidence", "figure", "institution"}
BASE_SCORE = {"evidence": 90, "figure": 85, "compare": 80, "number": 75, "equipment": 70, "timeline": 68, "split": 66, "institution": 64,
              "map_territorial": 62, "map_motion": 60, "map_location": 55}
KICKER = {"evidence": "Source", "figure": "Statement", "number": "Key figure", "compare": "Comparison", "equipment": "Equipment",
          "institution": "Institution"}
CONTESTED = ("killed", "dead", "casualties", "wounded", "lost", "destroyed", "shot down", "intercepted", "losses", "downed", "captured",
             "injured", "missing")
HEADLINE_STOP_END = {"of", "the", "a", "an", "to", "in", "on", "at", "and", "or", "but", "with", "for", "by", "as", "from", "that", "which"}
HEADLINE_STOP_START = {"and", "but", "so", "then", "also", "now", "yet", "however"}


# a short demonstration (under two minutes) cannot keep the spacing meant for a 14-minute video and still give each scene its visual: the
# spacing relaxes, the no-overlap rule and the provenance gates do not. Values a caller sets explicitly are never overridden.
SHORT_PROFILE = {"min_gap": 2.0, "map_gap": 2.0, "same_kind_gap": 2.0, "full_gap": 4.0, "per_minute": 10, "per_minute_footage": 10,
                 "clean_floor": 0.30, "quiet_clear": 0.0, "same_kind_max": 4, "card_cap_s": 6.0, "late_start_s": 3.5}


def fr(t: float) -> float:
    return round(float(t) * FPS) / FPS


# ----------------------------------------------------------------------------------------------------------------------------
# result types
# ----------------------------------------------------------------------------------------------------------------------------

@dataclass
class Candidate:
    kind: str                       # logical kind
    score: float
    reason: str
    accepted: bool = False
    code: str = ""                  # reason code when rejected
    start: float = 0.0
    end: float = 0.0
    sentence: int = 0
    key: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    equip_id: str = ""
    fallback: bool = False

    def brief(self) -> Dict[str, Any]:
        d = {"kind": self.kind, "score": round(self.score, 1), "reason": self.reason, "accepted": self.accepted}
        if self.code:
            d["code"] = self.code
        if self.accepted:
            d["start"] = self.start
            d["end"] = self.end
        return d


@dataclass
class Decision:
    scene_no: Any
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    chosen: Optional[str] = None
    fallback_reason: str = ""
    flags: List[str] = field(default_factory=list)


@dataclass
class Plan:
    shots: List[Shot] = field(default_factory=list)
    layers: List[Layer] = field(default_factory=list)
    log: List[Decision] = field(default_factory=list)
    credits: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    flags_profile: str = "standard"

    def to_dict(self) -> Dict[str, Any]:
        return {"shots": [asdict(s) for s in self.shots],
                "layers": [{"kind": ly.kind, "start": ly.start, "end": ly.end, "dim": ly.dim, "params": _jsonable(ly.params)} for ly in self.layers],
                "log": [asdict(d) for d in self.log], "credits": list(self.credits), "stats": dict(self.stats), "profile": self.flags_profile}


def _jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    return f"<{type(o).__name__}>"


def explain(plan: Plan) -> str:
    """The decision log as readable lines (for the app log and the plan report)."""
    lines = []
    for d in plan.log:
        cs = "; ".join(f"{c['kind']}={c['score']}{' ✓' if c['accepted'] else ' ✗' + (':' + c['code'] if c.get('code') else '')}" for c in d.candidates)
        lines.append(f"scene {d.scene_no}: chosen={d.chosen or 'none'} {('(' + d.fallback_reason + ') ') if d.fallback_reason else ''}[{cs}]"
                     + (f" flags={','.join(d.flags)}" if d.flags else ""))
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------------------------------------
# footage provenance (only what the caller's record says)
# ----------------------------------------------------------------------------------------------------------------------------

_VERIFIED = {"confirmed": "confirmed", "event_matched": "confirmed", "geolocated": "confirmed", "provenance_traced": "attributed",
             "source_cited": "attributed", "attributed": "attributed", "disputed": "disputed", "unverified": "unverified",
             "unreviewed": "unverified", "illustrative": "illustrative"}


DROP_BELOW = 0.1      # footage_match relevance under which a mismatched clip has nothing to do with its sentence


def _unrelated(meta: Optional[Dict[str, Any]]) -> bool:
    """The relevance estimate found a contradiction (another system, person, country, year) or next to nothing in common with the sentence
    (render 047: costume soldiers for '1,500 troops', a tractor for a defence pledge). A clip never scored is not judged here."""
    m = meta if isinstance(meta, dict) else {}
    if m.get("relevance_contradictions") and not m.get("weak_match"):
        return True
    try:
        return m.get("relevance") is not None and float(m["relevance"]) < DROP_BELOW
    except (TypeError, ValueError):
        return False


def _kept_anyway(meta: Optional[Dict[str, Any]]) -> bool:
    """A mismatched clip still shown: the user's own pick, an AI illustration they paid for, or file footage of the same event (recycled)."""
    m = meta if isinstance(meta, dict) else {}
    prov = str(m.get("provider") or m.get("source") or "").lower()
    return bool(m.get("user_supplied") or m.get("user_override") or m.get("kind") in ("user", "generated") or m.get("ai_generated")
                or prov in ("manual", "local", "flow", "flow_video") or m.get("recycled"))


def footage_info(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """{status, rejected, recycled, mismatch, chip, publisher, published}. The manifest's own 'status' (download state) is never read."""
    m = dict(meta or {})
    prov = m.get("provenance") if isinstance(m.get("provenance"), dict) else {}
    raw = str(m.get("verification") or m.get("war_status") or prov.get("verification") or prov.get("status") or "").lower()
    status = _VERIFIED.get(raw, "unverified")
    flags = dict(m.get("flags") or {}) if isinstance(m.get("flags"), dict) else {}
    flags.update({k: prov.get(k) for k in ("recycled", "mismatch", "disputed") if prov.get(k)})
    recycled = bool(m.get("recycled") or flags.get("recycled"))
    mismatch = bool(m.get("mismatch") or flags.get("mismatch"))
    rejected = raw == "rejected"
    if flags.get("disputed") and status in ("confirmed", "attributed"):
        status = "disputed"
    publisher = str(m.get("publisher") or prov.get("publisher") or m.get("channel") or m.get("author") or "")
    published = str(m.get("published") or m.get("published_date") or prov.get("published_date") or "")
    chip = ""
    if recycled:
        chip = "FILE FOOTAGE" + (f" · first seen {m.get('first_seen')}" if m.get("first_seen") else "")
    elif mismatch:
        chip = "ILLUSTRATIVE FOOTAGE"
    elif status != "confirmed":
        bits = [status.upper()]
        if publisher:
            bits.append(publisher)
        if published:
            bits.append(published)
        chip = " · ".join(bits)
    # generic stock/b-roll (set by integration.load_scenes from the manifest record) is never footage of a specific event: it is labelled
    # ILLUSTRATIVE FOOTAGE and gets no headline; a third-party source (YouTube) gets an UNVERIFIED · <channel> source chip
    generic = bool(m.get("generic"))
    stock_relevant = bool(m.get("stock_relevant")) and not (recycled or mismatch)   # footage_match: generic stock whose record agrees with the narration
    if generic and not (recycled or mismatch):
        if stock_relevant:
            chip = "STOCK FOOTAGE"      # relevant b-roll is shown as stock, never as footage of the specific event
        else:
            mismatch, chip = True, "ILLUSTRATIVE FOOTAGE"
    return {"status": "unverified" if (recycled or mismatch) and status == "confirmed" else status, "rejected": rejected, "recycled": recycled,
            "mismatch": mismatch, "chip": chip, "publisher": publisher, "published": published, "generic": generic,
            "source_chip": (bool(m.get("source_chip")) or stock_relevant) and status != "confirmed", "rights": str(m.get("rights") or ""),
            "reused": bool(m.get("reused")), "footage_class": str(m.get("footage_class") or "")}


# ----------------------------------------------------------------------------------------------------------------------------
# context shared by the candidate builders
# ----------------------------------------------------------------------------------------------------------------------------

@dataclass
class _Ctx:
    scene: Dict[str, Any]
    A: SceneAnalysis
    cfg: Dict[str, Any]
    catalog: Any
    assets: Dict[str, str]
    start: float
    end: float
    has_words: bool
    seen_equipment: Dict[str, float]
    footage_verified: bool


def _entry(e: S.Entity) -> Dict[str, Any]:
    return e.entry if isinstance(e.entry, dict) else {}


def _key_time(ctx: _Ctx, char: int) -> float:
    return ctx.A.time_at(char)


def _window(ctx: _Ctx, key_char: int, sent: SentenceInfo) -> Tuple[float, float]:
    """(start, end) of a card: 0.3 s before the key word, to the sentence end + 1.0 s, at least 3 s, never before the scene starts."""
    cfg = ctx.cfg
    start = max(ctx.start, _key_time(ctx, key_char) - cfg["lead_s"])
    end = max(ctx.A.end_time_of(sent.span) + cfg["tail_s"], start + cfg["min_card_s"])
    return fr(start), fr(end)


def _tokens_in(ctx: _Ctx, span: Tuple[int, int]) -> Tuple[List[str], List[float]]:
    words, times = [], []
    text = ctx.A.text
    for s, e, a, _b in ctx.A.token_times:
        if s >= span[0] and e <= span[1]:
            words.append(text[s:e])
            times.append(a)
    return words, times


def _rel_times(times: Sequence[float], card_start: float) -> List[float]:
    return [round(max(0.0, t - card_start), 3) for t in times]


def _year_text(sent: SentenceInfo) -> str:
    if sent.years:
        return str(sent.years[0][0])
    m = re.search(r"\b(\d{1,2}\s+(?:" + "|".join(S.MONTHS) + r")(?:\s+\d{4})?)", sent.text, flags=re.IGNORECASE)
    return m.group(1) if m else ""


def _claimant_for(sent: SentenceInfo) -> str:
    if sent.citation:
        return sent.citation.outlet
    return sent.claimant


def _stat_status(sent: SentenceInfo, cfg: Dict[str, Any], claimant: str) -> str:
    if sent.disputed:
        return "disputed"
    if claimant:
        return "attributed"
    return cfg["narration_status"]


def _contested(sent: SentenceInfo, num: S.Number) -> bool:
    low = sent.text.lower()
    return any(re.search(r"\b" + re.escape(c) + r"\b", low) for c in CONTESTED) or any(c in num.unit.lower() for c in CONTESTED)


_TIME_UNIT = re.compile(r"^(year|years|month|months|day|days|week|weeks|hour|hours|minute|minutes|decade|decades|second|seconds|time|times)\b", re.IGNORECASE)


def _fmt_value(n: S.Number) -> str:
    v = n.value
    if abs(v - round(v)) < 1e-9:
        v = int(round(v))
        return f"{v:,}"
    return f"{v:g}"


# ----------------------------------------------------------------------------------------------------------------------------
# candidate builders: each returns Candidates (accepted False; the arbiter decides)
# ----------------------------------------------------------------------------------------------------------------------------

def _rej(kind: str, code: str, reason: str, sentence: int = 0) -> Candidate:
    return Candidate(kind=kind, score=0.0, reason=reason, code=code, sentence=sentence)


def _figure_for(sent: SentenceInfo, speaker: str) -> Optional[S.Entity]:
    sp = speaker.lower()
    for e in sent.entities:
        if e.kind != "figure":
            continue
        names = [e.name.lower()] + [str(a).lower() for a in (S._get(e.entry, "aliases", None) or [])]
        last = e.name.split()[-1].lower() if e.name.split() else ""
        if any(n and n in sp for n in names) or (last and len(last) >= 4 and last in sp):
            return e
    return None


def _portrait(ctx: _Ctx, e: S.Entity) -> Optional[str]:
    cand = ctx.assets.get("portrait:" + e.id) or S._get(e.entry, "portrait", None)
    if cand and isinstance(cand, str) and os.path.isfile(cand) and str(S._get(e.entry, "portrait_licence_reuse", "")).lower() not in ("none", "unknown"):
        return cand
    try:    # the cached Commons portrait for this exact person (no network here); a cache problem leaves the name plate
        from . import portraits as _pt

        hit = _pt.portrait_for(e.id)
        return hit["path"] if hit else None
    except Exception:
        return None


def _cands_quotes(ctx: _Ctx, sent: SentenceInfo) -> List[Candidate]:
    out: List[Candidate] = []
    q = sent.quote
    if q is not None:
        fig = _figure_for(sent, q.speaker) if q.speaker else None
        inst = None
        if q.speaker:
            for e in sent.entities:
                if e.kind == "institution" and (e.name.lower() in q.speaker.lower() or q.speaker.lower() in e.name.lower()):
                    inst = e
        if fig is not None:
            s0, e0 = _window(ctx, q.span[0], sent)
            role = S._get(fig.entry, "role", "") or ""
            intro = sent.intro_figure
            if intro and intro[0] is fig:
                role = intro[1] or role
            qw, qt = _tokens_in(ctx, q.span)
            params = {"name": fig.name, "role": role, "image": _portrait(ctx, fig), "statement": q.text, "statement_date": _year_text(sent),
                      "venue": "", "status": "disputed" if sent.disputed else "attributed", "source": q.speaker, "role_verified": not S._get(fig.entry, "verify_role", False),
                      "figure_id": fig.id, "words": [w.strip("\"“”") for w in qw], "times": _rel_times(qt, s0)}
            sc = BASE_SCORE["figure"] + (5 if fig.subject else 0) + (3 if ctx.has_words else 0)
            out.append(Candidate("figure", sc, f"quotation attributed to {fig.name}" + ("; portrait on disk" if params["image"] else "; name plate only"),
                                 start=s0, end=e0, sentence=sent.index, key=f"figure:{fig.id}:{q.text[:40].lower()}", params=params))
        elif inst is not None:
            s0, e0 = _window(ctx, q.span[0], sent)
            params = {"name": inst.name, "subtitle": str(S._get(inst.entry, "country", "") or ""), "statement": q.text,
                      "status": "disputed" if sent.disputed else "attributed", "source": q.speaker, "institution_id": inst.id}
            out.append(Candidate("institution", BASE_SCORE["institution"] + 4, f"quotation attributed to {inst.name}", start=s0, end=e0,
                                 sentence=sent.index, key=f"inst:{inst.id}:{q.text[:40].lower()}", params=params))
        elif q.speaker:
            # a named speaker the catalog does not know: an attributed text card, never a face
            out.append(_evidence_candidate(ctx, sent, outlet=q.speaker, text=q.text, quoted=True, key_char=q.span[0]))
        else:
            out.append(_rej("figure", "slot_incomplete", "quotation without a named speaker: no card", sent.index))
    return out


def _evidence_candidate(ctx: _Ctx, sent: SentenceInfo, *, outlet: str, text: str, quoted: bool, key_char: int) -> Candidate:
    s0, e0 = _window(ctx, key_char, sent)
    # words and their times: the sentence (or the quoted span) as spoken
    if quoted:
        m = sent.text.find(text[:12]) if text else -1
        lo = sent.span[0] + max(0, m)
        words, times = _tokens_in(ctx, (lo, lo + len(text)))
    else:
        words, times = _tokens_in(ctx, sent.span)
    if not words:
        words = text.split()
        step = (e0 - s0 - 1.0) / max(1, len(words))
        times = [s0 + 0.4 + i * max(0.05, step) for i in range(len(words))]
    mark = None
    if sent.numbers:
        n = sent.numbers[0]
        idx = [i for i, w in enumerate(words) if re.sub(r"[^\w.,%]", "", w) and n.raw.split()[0] in w]
        if idx:
            mark = (idx[0], min(len(words) - 1, idx[0] + (2 if n.unit else 0)))
    if mark is None and len(words) > 6:
        mark = (min(len(words) - 1, len(words) // 3), min(len(words) - 1, len(words) // 3 + 3))
    claimant = _claimant_for(sent)
    params = {"outlet": outlet, "date": _year_text(sent), "words": words, "times": _rel_times(times, s0), "mark": mark,
              "status": "disputed" if sent.disputed else "attributed", "paraphrased": not quoted, "claimant": claimant,
              "kind": "statement" if quoted else ("claim" if sent.claim else "document")}
    sc = BASE_SCORE["evidence"] + (4 if sent.claim else 0) + (3 if ctx.has_words else 0)
    return Candidate("evidence", sc, f"source named: {outlet}" + (" (verbatim quotation)" if quoted else " (narration's own sentence, marked paraphrased)"),
                     start=s0, end=e0, sentence=sent.index, key=f"evidence:{outlet.lower()}:{text[:40].lower()}", params=params)


def _cands_evidence(ctx: _Ctx, sent: SentenceInfo) -> List[Candidate]:
    out: List[Candidate] = []
    c = sent.citation
    if c is None:
        return out
    if sent.quote is not None and sent.quote.speaker:
        return out   # the quote builder owns it
    if sent.quote is None and c.kind != "source_noun" and (sent.numbers or sent.comparison is not None):
        return out   # "the ministry says output rose from 40 to 200": the statistic carries the claimant, not a text card
    outlet = c.outlet
    # citing a person or a catalog institution is handled by the figure / institution builders; the rest is an attributed text card
    text = sent.quote.text if sent.quote else sent.text
    if len(text.split()) < 5:
        return [_rej("evidence", "slot_incomplete", "source named but no line to show", sent.index)]
    for e in sent.entities:
        if e.kind == "institution" and e.name.lower() in outlet.lower():
            s0, e0 = _window(ctx, c.span[0], sent)
            params = {"name": e.name, "subtitle": str(S._get(e.entry, "country", "") or ""), "statement": text,
                      "status": "disputed" if sent.disputed else "attributed", "source": outlet, "institution_id": e.id}
            out.append(Candidate("institution", BASE_SCORE["institution"] + 6, f"statement cited from {e.name}", start=s0, end=e0,
                                 sentence=sent.index, key=f"inst:{e.id}:{text[:40].lower()}", params=params))
            return out
    out.append(_evidence_candidate(ctx, sent, outlet=outlet, text=text, quoted=bool(sent.quote), key_char=c.span[0]))
    return out


def _cands_intro(ctx: _Ctx, sent: SentenceInfo) -> List[Candidate]:
    out: List[Candidate] = []
    if sent.intro_figure and sent.quote is None:
        fig, role = sent.intro_figure
        s0, e0 = _window(ctx, fig.span[0], sent)
        e0 = min(e0, fr(s0 + 4.0))               # an introduction is a few seconds, so a number later in the sentence still gets its card
        later = [n for n in sent.numbers if n.span[0] > fig.span[1] and not n.is_year]
        if later:                                # the introduction hands over to the number's card instead of colliding with it
            hand = _window(ctx, later[0].span[0], sent)[0] - 0.35
            if hand - s0 >= 2.2:
                e0 = min(e0, fr(hand))
        params = {"name": fig.name, "role": role or S._get(fig.entry, "role", ""), "image": _portrait(ctx, fig), "statement": "", "statement_date": "",
                  "venue": "", "status": "attributed", "source": "", "role_verified": bool(role), "figure_id": fig.id}
        out.append(Candidate("figure", BASE_SCORE["figure"] - 8 + (4 if fig.subject else 0), f"{fig.name} introduced with a role in the narration",
                             start=s0, end=e0, sentence=sent.index, key=f"figure:{fig.id}:intro", params=params))
    elif any(e.kind == "figure" for e in sent.entities) and sent.quote is None:
        names = [e.name for e in sent.entities if e.kind == "figure"]
        out.append(_rej("figure", "no_trigger", f"{', '.join(names)} named without role or statement: no portrait", sent.index))
    return out


def _cands_numbers(ctx: _Ctx, sent: SentenceInfo) -> List[Candidate]:
    out: List[Candidate] = []
    cfg = ctx.cfg
    if sent.comparison is not None:
        cmp_ = sent.comparison
        a, b = cmp_.a, cmp_.b
        if not (a.complete and b.complete):
            out.append(_rej("compare", "slot_incomplete", "comparison without a stated unit", sent.index))
        else:
            claimant = _claimant_for(sent)
            if any(_contested(sent, n) for n in (a, b)) and not claimant:
                out.append(_rej("compare", "provenance_failed", "contested figures with no named claimant are never shown as plain numbers", sent.index))
            else:
                s0, e0 = _window(ctx, a.span[0], sent)
                unit = b.unit or a.unit
                la, lb = _label_near(sent, a), _label_near(sent, b)
                if la == lb or la.lower() == (a.unit + (" " + a.period if a.period else "")).strip().lower():
                    la, lb = ("Before", "After") if cmp_.kind == "from_to" else ("First figure", "Second figure")
                params = {"title": _compare_title(sent, a, b, unit), "unit": unit,
                          "items": [{"label": la, "value": a.value, "shown": _fmt_value(a)},
                                    {"label": lb, "value": b.value, "shown": _fmt_value(b)}],
                          "as_of": _year_text(sent), "claimant": claimant, "status": _stat_status(sent, cfg, claimant), "axis_from_zero": True}
                out.append(Candidate("compare", BASE_SCORE["compare"] + (4 if claimant else 0) + (3 if ctx.has_words else 0),
                                     f"two comparable stated values ({_fmt_value(a)} and {_fmt_value(b)} {unit})", start=s0, end=e0, sentence=sent.index,
                                     key=f"compare:{a.value}:{b.value}:{unit.lower()}", params=params))
        return out
    claimant0 = _claimant_for(sent)
    cands = [n for n in sent.numbers if n.complete and not (not claimant0 and (_TIME_UNIT.match(n.unit or "") or (n.raw.isalpha() and n.value <= 12)))]
    incomplete = [n for n in sent.numbers if not n.complete]
    if not cands:
        if incomplete or sent.numbers:
            out.append(_rej("number", "slot_incomplete", "a number with no stated referent", sent.index))
        return out
    n = cands[0]
    claimant = _claimant_for(sent)
    if _contested(sent, n) and not claimant:
        out.append(_rej("number", "provenance_failed", "contested figure with no named claimant is never shown as a plain number", sent.index))
        return out
    s0, e0 = _window(ctx, n.span[0], sent)
    value = int(round(n.value)) if n.unit != "%" or abs(n.value - round(n.value)) < 1e-9 else n.value
    label = (n.unit if n.unit != "%" else "") + ((" " + n.period) if n.period else "")
    sub = f"Reported by {claimant}" if claimant else "As stated in the narration"
    params = {"value": value if isinstance(value, int) and value < 10_000_000 else int(round(n.value)), "prefix": "", "label": label,
              "sub": sub, "suffix": "%" if n.unit == "%" else "", "colour": "red" if sent.claim or sent.disputed else "yellow", "shown": _fmt_value(n) + ("%" if n.unit == "%" else ""),
              "unit": n.unit, "as_of": _year_text(sent), "claimant": claimant, "status": _stat_status(sent, cfg, claimant)}
    out.append(Candidate("number", BASE_SCORE["number"] + (4 if claimant else 0) + (3 if ctx.has_words else 0),
                         f"stated number with referent ({_fmt_value(n)} {n.unit})", start=s0, end=e0, sentence=sent.index,
                         key=f"number:{n.value}:{n.unit.lower()}", params=params))
    return out


_PERIOD_ADJ = {"a day": "Daily", "per day": "Daily", "a night": "Nightly", "a week": "Weekly", "per week": "Weekly", "a month": "Monthly",
               "per month": "Monthly", "a year": "Yearly", "per year": "Yearly", "an hour": "Hourly", "per hour": "Hourly"}
_CHANGE_VERB = re.compile(r"\b([A-Za-z-]+(?:\s+[A-Za-z-]+)?)\s+(?:rose|fell|grew|increased|decreased|dropped|climbed|jumped|declined|doubled|"
                          r"went up|went down|reached|shrank|expanded)\b")


def _compare_title(sent: SentenceInfo, a: S.Number, b: S.Number, unit: str) -> str:
    """'Monthly output, units': the narration's own period, subject noun and unit; the unit alone when the sentence gives no more."""
    period = (b.period or a.period or "").strip().lower()
    if not period:
        _r, period = S._referent(sent.text, b.span[1] - sent.span[0])
    adj = _PERIOD_ADJ.get(period, "")
    subj = ""
    m = _CHANGE_VERB.search(sent.text)
    if m:
        words = [w for w in m.group(1).split() if w.lower() not in ("the", "a", "an", "and", "that", "this", "which", "its", "their")]
        if words and words[-1].lower() not in ("it", "they", "he", "she", "which", "that"):
            subj = words[-1]
    unit_clean = re.sub(r"\s+(?:a|per)\s+\w+$", "", unit).strip()
    head = " ".join(x for x in (adj, subj.lower() if adj or subj else "") if x).strip()
    if head and adj:
        head = adj + (" " + subj.lower() if subj else "")
    return (head + ", " + unit_clean).strip(", ") if head else unit_clean.capitalize()


def _label_near(sent: SentenceInfo, n: S.Number) -> str:
    """A label for a value from the narration itself: a month or year right before it, else the unit and period as spoken."""
    pre = sent.text[max(0, n.span[0] - sent.span[0] - 22):max(0, n.span[0] - sent.span[0])]
    m = re.search(r"\b(?:in|by)\s+((?:" + "|".join(x.capitalize() for x in S.MONTHS) + r")|(?:19|20)\d\d)\s*,?\s*(?:from|to)?\s*$", pre)
    if m:
        return m.group(1)
    return (n.unit + (" " + n.period if n.period else "")).strip() or n.raw


def _cands_equipment(ctx: _Ctx, sent: SentenceInfo) -> List[Candidate]:
    out: List[Candidate] = []
    equip = [e for e in sent.entities if e.kind == "equipment"]
    gen = [e for e in sent.entities if e.kind == "generic_weapon"] + [S.Entity("generic_weapon", w, specific=False) for w in sent.generic_weapons
                                                                       if not any(e.kind == "generic_weapon" and w == e.name.lower() for e in sent.entities)]
    if len(equip) >= 2 and re.search(r"\b(versus|vs\.?|compared (?:with|to)|against|and the)\b", sent.text, flags=re.IGNORECASE) and all(e.specific for e in equip[:2]):
        a, b = equip[0], equip[1]
        s0, e0 = _window(ctx, a.span[0], sent)
        params = {"left": {"label": a.name, "sub": str(S._get(a.entry, "role", "") or ""), "image": None},
                  "right": {"label": b.name, "sub": str(S._get(b.entry, "role", "") or ""), "image": None}, "chip": "", "status": "unverified",
                  "source": "named in the narration"}
        out.append(Candidate("split", BASE_SCORE["split"] + (3 if ctx.has_words else 0), f"two named systems compared: {a.name} / {b.name}", start=s0, end=e0,
                             sentence=sent.index, key=f"split:{a.id}:{b.id}", params=params))
    for e in equip:
        has_attr = any(w in sent.text.lower() for w in S.ATTRIBUTE_WORDS) or bool(sent.numbers)
        first = e.id not in ctx.seen_equipment
        if e.ambiguous or not e.specific:
            cls = e.class_id or str(S._get(e.entry, "class", "") or "")
            out.append(_generic_equipment_card(ctx, sent, e, cls) if has_attr else
                       _rej("equipment", "ambiguous_entity", f"'{e.name}' matches several systems: no model named", sent.index))
            continue
        if not (has_attr or first):
            out.append(_rej("equipment", "no_trigger", f"{e.name} named with nothing stated about it", sent.index))
            continue
        last = ctx.seen_equipment.get(e.id)
        if last is not None and ctx.start - last < ctx.cfg["equipment_repeat_s"]:
            out.append(_rej("equipment", "density", f"{e.name} was carded {ctx.start - last:.0f} s ago", sent.index))
            continue
        out.append(_equipment_card(ctx, sent, e, has_attr))
    if not equip and gen and not sent.numbers:
        out.append(_rej("equipment", "ambiguous_entity", f"class word only ({', '.join(sorted({g.name.lower() for g in gen}))}): no system named", sent.index))
    return out


def _equipment_photo(equip_id: str) -> Optional[dict]:
    try:
        return EQI.lookup(equip_id)
    except Exception:                           # a missing or damaged photo store is a silhouette, never a failed plan
        return None


def _equipment_card(ctx: _Ctx, sent: SentenceInfo, e: S.Entity, has_attr: bool) -> Candidate:
    s0, e0 = _window(ctx, e.span[0], sent)
    fn = getattr(ctx.catalog, "equipment_card_params", None)
    entry = _entry(e)
    if callable(fn) and entry:
        try:
            params = dict(fn(entry))
        except Exception:
            params = {}
    else:
        params = {}
    if not params:
        params = {"name": e.name, "role": entry.get("role", ""), "class": entry.get("class", ""), "operator": "",
                  "specs": [{"label": s["label"], "value": s["value"]} for s in entry.get("specs") or [] if s.get("source")],
                  "source": "reference data; verify before publishing", "status": "attributed"}
    params["image"] = ctx.assets.get("equipment:" + e.id)
    if not params["image"] and ctx.cfg.get("equipment_photos", True):
        rec = _equipment_photo(e.id)            # a stored exact-model Commons photograph, else the labelled silhouette stays
        if rec:
            params["image"], params["image_credit"], params["image_record"] = rec["path"], EQI.credit_line(rec), rec
    params["icon"] = params.get("class") or entry.get("class", "")
    params["confidence"] = "stated"            # the narration names the system; nothing was matched by appearance
    params["equipment_id"] = e.id
    params["generic"] = False
    sc = BASE_SCORE["equipment"] + (5 if e.subject else 0) + (3 if has_attr else 0) + (3 if ctx.has_words else 0)
    return Candidate("equipment", sc, f"named system {e.name}" + (" with a stated attribute" if has_attr else " (first mention)"), start=s0, end=e0,
                     sentence=sent.index, key=f"equipment:{e.id}", params=params, equip_id=e.id)


def _generic_equipment_card(ctx: _Ctx, sent: SentenceInfo, e: S.Entity, cls: str) -> Candidate:
    s0, e0 = _window(ctx, e.span[0], sent)
    label = (cls or "equipment").replace("_", " ").capitalize() + " (type)"
    params = {"name": label, "role": "", "class": cls, "operator": "", "specs": [], "source": "named in the narration", "status": "unverified",
              "image": None, "confidence": "uncertain", "generic": True, "equipment_id": "", "icon": cls}
    return Candidate("equipment", BASE_SCORE["equipment"] - 14, f"alias '{e.name}' is shared by several systems: generic class label only", start=s0, end=e0,
                     sentence=sent.index, key=f"equipment:class:{cls}", params=params)


def _cands_institution(ctx: _Ctx, sent: SentenceInfo) -> List[Candidate]:
    e = sent.inst_subject
    if e is None or sent.quote is not None:
        return []
    s0, e0 = _window(ctx, e.span[0], sent)
    params = {"name": e.name, "subtitle": str(S._get(e.entry, "country", "") or ""), "status": "attributed", "source": "named in narration",
              "institution_id": e.id}
    return [Candidate("institution", BASE_SCORE["institution"] + 4 + (3 if ctx.has_words else 0),
                      f"{e.name} is the subject of the sentence and does something (met, said, issued ...)", start=s0, end=e0, sentence=sent.index,
                      key=f"inst:{e.id}:subject", params=params)]


def _cands_timeline(ctx: _Ctx) -> List[Candidate]:
    events: List[Tuple[str, str, int, SentenceInfo]] = []
    seen = set()
    for sent in ctx.A.sentences:
        for date, label, off in sent.dated_events:
            if date in seen:
                continue
            seen.add(date)
            events.append((date, label, off, sent))
    if len(events) < 2:
        return []
    events = events[:6]
    first, last = events[0][3], events[-1][3]
    s0, _ = _window(ctx, events[0][2], first)
    _, e0 = _window(ctx, events[-1][2], last)
    e0 = fr(max(e0, s0 + 6.0))
    status = ctx.cfg["timeline_status"]
    evs = [{"date": d, "label": lab, "status": status, "source": "named in narration"} for d, lab, _o, _s in events]
    times = [round(max(0.0, ctx.A.time_at(o) - s0), 3) for _d, _l, o, _s in events]
    return [Candidate("timeline", BASE_SCORE["timeline"] + (3 if ctx.has_words else 0), f"{len(events)} dated events in the narration's own words", start=s0, end=e0,
                      sentence=first.index, key="timeline:" + "|".join(e["date"] for e in evs),
                      params={"title": "Key dates", "events": evs, "times": times, "status": status})]


def _preset_for(pins: Sequence[Dict[str, Any]]) -> Optional[str]:
    """The smallest framing preset that contains every pin (the map engine's own presets), else None."""
    try:
        from .geo_data import PRESETS
    except Exception:
        return None
    best = None
    for name, (x0, y0, x1, y1) in PRESETS.items():
        if name in ("ukraine_russia", "nato_east", "baltic"):
            continue
        if all(x0 <= p["lon"] <= x1 and y0 <= p["lat"] <= y1 for p in pins):
            area = (x1 - x0) * (y1 - y0)
            if best is None or area < best[0]:
                best = (area, name)
    return best[1] if best else None


def _cands_geography(ctx: _Ctx) -> List[Candidate]:
    """One map for the scene's geography sentences (lies / borders / shore / north of ...): named countries filled and listed in a text legend."""
    sents = [s for s in ctx.A.sentences if s.geography and s.motion is None and s.territorial is None]
    if not sents:
        return []
    places: List[S.Entity] = []
    seen = set()
    for sent in sents:
        for e in sent.entities:
            if e.kind == "place" and not S._is_possessive(ctx.A.text, e.span[1]) and not e.ambiguous and (e.id or e.name) not in seen:
                seen.add(e.id or e.name)
                places.append(e)
    if len(places) < 2:
        return []
    countries = [e for e in places if e.country]
    others = [e for e in places if not e.country]
    names = {e.name.lower() for e in places}
    pins = [p for p in (_pin(e) for e in others if str(S._get(e.entry, "type", "")) != "sea") if p]
    if "ukraine" in names:
        frame: Any = "ukraine"
    elif pins and _preset_for(pins):
        frame = _preset_for(pins)
    elif "black sea" in names:
        frame = "black_sea"
    else:
        frame = "europe_east"
    fills = []
    legend = []
    for i, c in enumerate(countries):
        role = "highlight" if i == 0 else "neutral"
        fills.append({"name": c.name, "role": role, "label": c.name})
        legend.append({"label": c.name, "role": role})
    first, last = sents[0], sents[-1]
    s0, _ = _window(ctx, places[0].span[0], first)
    _, e0 = _window(ctx, places[-1].span[0], last)
    params = {"places": [e.name for e in places], "frame": frame, "style": "dark", "fills": fills, "legend": legend if legend else False, "labels": True,
              "pins": pins, "arrows": [], "caption": {"title": "Geography as described", "sub": "Schematic · borders as in the map data"}, "as_of": "",
              "status": "illustrative", "illustrative": True}
    return [Candidate("map", BASE_SCORE["map_location"] + 6 + (3 if ctx.has_words else 0) - (8 if ctx.footage_verified else 0),
                      f"geography sentence naming {', '.join(e.name for e in places[:4])}{'…' if len(places) > 4 else ''}", start=s0, end=fr(max(e0, s0 + 3.0)),
                      sentence=first.index, key="map:geo:" + ",".join(sorted(e.id or e.name for e in places)), params=params)]


def _pin(e: S.Entity) -> Optional[Dict[str, Any]]:
    ent = _entry(e)
    if ent.get("lat") is None or ent.get("lon") is None or str(ent.get("type", "")).lower() == "sea":
        return None
    return {"lat": float(ent["lat"]), "lon": float(ent["lon"]), "label": e.name, "note": ""}


def _frame_for(pins: Sequence[Dict[str, Any]], names: Sequence[str]) -> Any:
    """A bounding box [lon0, lat0, lon1, lat1] around the pins with padding; the first place's own name when no coordinates are known."""
    if not pins:
        return names[0] if names else "ukraine"
    lons = [p["lon"] for p in pins]
    lats = [p["lat"] for p in pins]
    span_lon = max(lons) - min(lons)
    span_lat = max(lats) - min(lats)
    pad_lon = max(3.0, 0.35 * span_lon)
    pad_lat = max(1.8, 0.35 * span_lat)
    return [round(min(lons) - pad_lon, 3), round(min(lats) - pad_lat, 3), round(max(lons) + pad_lon, 3), round(max(lats) + pad_lat, 3)]


def _map_params(places: Sequence[S.Entity], *, arrows: Sequence[Tuple[S.Entity, S.Entity]] = (), snapshot: Optional[Dict[str, Any]] = None,
                title: str = "", sub: str = "", claimant: str = "") -> Dict[str, Any]:
    pins = [p for p in (_pin(e) for e in places) if p]
    names = [e.name for e in places]
    arr = []
    for a, b in arrows:
        pa, pb = _pin(a), _pin(b)
        if pa and pb:
            arr.append({"from": (pa["lat"], pa["lon"]), "to": (pb["lat"], pb["lon"]), "label": "", "kind": "movement", "illustrative": True})
    params: Dict[str, Any] = {"places": names, "frame": _frame_for(pins, names), "style": "dark", "pins": pins, "arrows": arr,
                              "caption": {"title": title, "sub": sub}, "as_of": ""}
    if snapshot:
        params["control_snapshots"] = [{k: snapshot[k] for k in ("as_of", "source", "polygons", "role") if k in snapshot}]
        params["as_of"] = str(snapshot.get("as_of", ""))
        params["status"] = "attributed"
        params["control"] = {"as_of": snapshot.get("as_of"), "source": snapshot.get("source")}
    else:
        params["status"] = "illustrative"
    if claimant:
        params["claimant"] = claimant
    return params


def _cands_map(ctx: _Ctx, sent: SentenceInfo) -> List[Candidate]:
    out: List[Candidate] = []
    cfg = ctx.cfg
    amb = [e for e in sent.entities if e.kind == "place" and e.ambiguous]
    if amb:
        out.append(_rej("map", "ambiguous_entity", f"place name '{amb[0].name}' is ambiguous: no pin", sent.index))
    mot = sent.motion
    terr = sent.territorial
    if sent.geography and mot is None and terr is None:
        return out   # handled once for the whole scene by _cands_geography
    loc = [e for e in sent.location if not e.ambiguous]
    snaps = [s for s in cfg.get("snapshots") or [] if isinstance(s, dict) and s.get("as_of") and s.get("source")]
    fv = 8 if ctx.footage_verified else 0
    if mot is not None:
        a, b, verb = mot
        s0, e0 = _window(ctx, a.span[0], sent)
        params = _map_params([a, b], arrows=[(a, b)], title="Illustrative route", sub="Between the two places named · not a track")
        params["illustrative"] = True
        out.append(Candidate("map", BASE_SCORE["map_motion"] + (3 if ctx.has_words else 0) - fv,
                             f"motion verb '{verb}' from {a.name} to {b.name}", start=s0, end=e0, sentence=sent.index,
                             key=f"map:{a.id}:{b.id}", params=params))
    elif terr is not None:
        verb, places = terr
        s0, e0 = _window(ctx, places[0].span[0], sent)
        snap = _snapshot_for(snaps, places)
        params = _map_params(places, snapshot=snap, claimant=_claimant_for(sent),
                             title=("Control as of " + str(snap["as_of"])) if snap else "Places named in the narration",
                             sub=str(snap["source"]) if snap else "Not a front line")
        params["illustrative"] = not snap
        out.append(Candidate("map", BASE_SCORE["map_territorial"] + (4 if snap else 0) + (3 if ctx.has_words else 0) - fv,
                             f"territorial verb '{verb}' with named places" + (" and a sourced snapshot" if snap else " (pins only: no sourced front line)"),
                             start=s0, end=e0, sentence=sent.index, key="map:terr:" + ",".join(p.id or p.name for p in places), params=params))
    elif loc:
        distinct = {e.id or e.name: e for e in loc}
        non_country = [e for e in distinct.values() if not e.country]
        if not non_country and len(distinct) < 2:
            out.append(_rej("map", "no_trigger", f"bare country mention ({', '.join(sorted(e.name for e in distinct.values()))}): no map", sent.index))
            return out
        pick = sorted(distinct.values(), key=lambda e: e.span[0])[:3]
        s0, e0 = _window(ctx, pick[0].span[0], sent)
        params = _map_params(pick, title="Places named in the narration", sub="Schematic")
        params["illustrative"] = True
        subject = any(p.subject for p in pick)
        out.append(Candidate("map", BASE_SCORE["map_location"] + (5 if subject else 0) + (3 if ctx.has_words else 0) - fv - 2,
                             f"location cue with {', '.join(p.name for p in pick)}", start=s0, end=e0, sentence=sent.index,
                             key="map:loc:" + ",".join(p.id or p.name for p in pick), params=params))
    elif len({e.id or e.name for e in sent.entities if e.kind == "place" and not e.country and not e.ambiguous
              and not S._is_possessive(ctx.A.text, e.span[1])}) >= 2:
        pl = sorted({e.id or e.name: e for e in sent.entities if e.kind == "place" and not e.country and not e.ambiguous
                     and not S._is_possessive(ctx.A.text, e.span[1])}.values(), key=lambda e: e.span[0])[:4]
        s0, e0 = _window(ctx, pl[0].span[0], sent)
        params = _map_params(pl, title="Places named in the narration", sub="Schematic")
        pins = params["pins"]
        pre = _preset_for(pins) if pins else None
        if pre:
            params["frame"] = pre
        params["illustrative"] = True
        out.append(Candidate("map", BASE_SCORE["map_location"] - 3 + (3 if ctx.has_words else 0) - (10 if ctx.footage_verified else 0),
                             f"two or more places named together ({', '.join(e.name for e in pl)})", start=s0, end=e0, sentence=sent.index,
                             key="map:multi:" + ",".join(e.id or e.name for e in pl), params=params))
    else:
        places = [e for e in sent.entities if e.kind == "place"]
        if places:
            poss = [e for e in places if S._is_possessive(ctx.A.text, e.span[1])]
            why = "possessive" if poss else "no location cue, or a part of a place"
            out.append(_rej("map", "no_trigger", f"place named without a location or movement ({why}): no map", sent.index))
    return out


def _snapshot_for(snaps: Sequence[Dict[str, Any]], places: Sequence[S.Entity]) -> Optional[Dict[str, Any]]:
    names = {p.name.lower() for p in places} | {p.id.lower() for p in places if p.id}
    for s in sorted(snaps, key=lambda s: str(s.get("as_of"))):
        covers = {str(x).lower() for x in (s.get("places") or [])}
        if covers & names:
            return s
    return None


def _neutral_map(ctx: _Ctx) -> Optional[Candidate]:
    """A scene with no footage and no better visual: a neutral map of the places the narration names (no pins' claims, no arrows, not a front line)."""
    places: List[S.Entity] = []
    seen = set()
    for sent in ctx.A.sentences:
        for e in sent.entities:
            if e.kind == "place" and not e.ambiguous and not S._is_possessive(ctx.A.text, e.span[1]) and not S._is_part(ctx.A.text, e.span[0], e.span[1]) \
                    and (e.id or e.name) not in seen:
                seen.add(e.id or e.name)
                places.append(e)
    if not places:
        return None
    places = places[:3]
    first = ctx.A.sentences[0]
    s0 = fr(ctx.start)
    e0 = fr(max(ctx.end, s0 + ctx.cfg["min_card_s"]))
    params = _map_params(places, title="Places named in the narration", sub="Neutral map · no claim")
    params["pins"] = []                          # a neutral map points at nothing
    params["illustrative"] = True
    return Candidate("map", 40.0, "no footage and no better visual: neutral map of " + ", ".join(e.name for e in places), start=s0, end=e0,
                     sentence=first.index, key="map:neutral:" + ",".join(e.id or e.name for e in places), params=params, fallback=True)


def build_candidates(ctx: _Ctx) -> List[Candidate]:
    out: List[Candidate] = []
    for sent in ctx.A.sentences:
        out += _cands_quotes(ctx, sent)
        out += _cands_evidence(ctx, sent)
        out += _cands_intro(ctx, sent)
        out += _cands_numbers(ctx, sent)
        out += _cands_equipment(ctx, sent)
        out += _cands_map(ctx, sent)
        out += _cands_institution(ctx, sent)
    out += _cands_geography(ctx)
    out += _cands_timeline(ctx)
    return out


# ----------------------------------------------------------------------------------------------------------------------------
# density
# ----------------------------------------------------------------------------------------------------------------------------

@dataclass
class _Acc:
    kind: str
    start: float
    end: float
    full: bool
    key: str
    scene_no: Any


class _State:
    def __init__(self, total: float, cfg: Dict[str, Any]) -> None:
        self.acc: List[_Acc] = []
        self.total = max(1e-6, total)
        self.cfg = cfg
        self.seen_equipment: Dict[str, float] = {}

    def card_time(self) -> float:
        return sum(a.end - a.start for a in self.acc)

    def check(self, c: Candidate, start: float, end: float, scene_no: Any, over_footage: bool) -> Tuple[bool, str, str]:
        cfg = self.cfg
        full = c.kind in FULL_FRAME
        if start < cfg["first_at"] - 1e-9 and over_footage:     # the clean-footage opening only applies when there is footage to keep clean
            return False, "density", f"nothing before {cfg['first_at']:.0f} s"
        if end > self.total + 1e-9:
            return False, "density", "runs past the end of the video"
        for a in self.acc:
            gap = cfg["full_gap"] if (full and a.full) else cfg["min_gap"]
            if c.kind == "map" and a.kind == "map":
                gap = cfg["map_gap"]          # a geography scene may walk through several map views; same-kind spacing still applies
            if a.scene_no == scene_no and {a.kind, c.kind} == {"figure", "number"}:
                gap = 0.3                      # who says it, then what is said: one sequence inside a sentence, not two competing cards
            if start < a.end + gap and end > a.start - gap:
                same_scene = a.scene_no == scene_no
                return False, ("conflict_lost" if same_scene else "density"), (
                    "overlaps a card chosen for this scene" if same_scene else f"within {gap:.0f} s of {a.kind} at {a.start:.1f}-{a.end:.1f} s")
        limit = cfg["per_minute_footage"] if over_footage else cfg["per_minute"]
        recent = [a for a in self.acc if a.start > start - 60.0]
        if len(recent) + 1 > limit:
            return False, "density", f"more than {limit} cards in a minute"
        same = [a for a in self.acc if a.kind == c.kind]
        for a in same:
            sg = cfg["map_gap"] if c.kind == "map" else cfg["same_kind_gap"]
            if start < a.end + sg:
                return False, "density", f"{c.kind} again within {sg:.0f} s"
        if len([a for a in same if a.start > start - cfg["same_kind_window"]]) + 1 > cfg["same_kind_max"]:
            return False, "density", f"more than {cfg['same_kind_max']} {c.kind} cards in {cfg['same_kind_window']:.0f} s"
        for a in self.acc:
            if a.key == c.key and start - a.end < cfg["same_fact_s"]:
                return False, "density", "the same fact was shown less than 240 s ago"
        if (self.card_time() + (end - start)) / max(self.total, cfg["clean_floor_min_total"]) > 1.0 - cfg["clean_floor"] + 1e-9:
            return False, "clean_floor", f"card time would exceed {100 * (1 - cfg['clean_floor']):.0f}% of the video"
        heavy = [a for a in self.acc if a.end > start - cfg["quiet_window"]]
        if len(heavy) >= 2 and c.kind not in EVIDENCE_KINDS:
            last_end = max(a.end for a in heavy)
            if start - last_end < cfg["quiet_clear"]:
                return False, "quiet_moment", "two cards in the last 20 s: a quiet stretch follows"
        return True, "", ""


# ----------------------------------------------------------------------------------------------------------------------------
# headline
# ----------------------------------------------------------------------------------------------------------------------------

_HL_BREAK = {"from", "to", "in", "on", "at", "with", "for", "by", "into", "over", "after", "before", "and", "but", "because", "while", "when",
             "which", "that", "who", "of", "across", "along", "without", "since", "as", "than", "how", "if"}
_HL_BAD_END = HEADLINE_STOP_END | {"is", "are", "was", "were", "be", "been", "has", "have", "had", "it", "its", "their", "his", "her", "this", "these",
                                   "much", "many", "how", "what", "can", "could", "will", "would", "first", "very", "so", "too", "more", "most"}


def headline_text(text: str) -> str:
    """3-7 words taken verbatim from the narration: a whole clause, or the clause up to a natural break. '' when the words would stop mid-phrase
    ('Russia is rehearsing how much it') or the scene opens on the tail of the previous sentence ('Out. Two sailors ...')."""
    sents = [x[0] for x in S.split_sentences(text or "")]
    sents = [x for x in sents if len(x.split()) >= 3] or sents       # a one- or two-word fragment carried over from the last scene is skipped
    if not sents:
        return ""
    first = sents[0]
    if first.rstrip().endswith("?"):
        return ""                                                     # a question is not a headline
    clause = re.split(r",(?!\d)|;|:| — | - |\bthat\b|\bwhich\b|\bwho\b|\bbecause\b", first)[0].strip().strip("\"“”").rstrip(".!")   # '1,500' stays whole
    words = clause.split()
    while words and words[0].lower().strip(",.") in HEADLINE_STOP_START:
        words = words[1:]
    if 3 <= len(words) <= 7 and words[-1].lower().strip(",.") not in _HL_BAD_END:
        return " ".join(words).rstrip(",.;:")
    for n in range(min(7, len(words) - 1), 2, -1):                    # end where the phrase breaks naturally: '... sank | in minutes'
        if words[n].lower() in _HL_BREAK and words[n - 1].lower().strip(",.") not in _HL_BAD_END:
            return " ".join(words[:n]).rstrip(",.;:")
    return ""


# ----------------------------------------------------------------------------------------------------------------------------
# the planner
# ----------------------------------------------------------------------------------------------------------------------------

def _available_kinds() -> Optional[set]:
    try:
        from . import registry
        return set(registry.all_cards())
    except Exception:
        pass
    kinds: set = set()
    try:
        from .. import cards as base
        kinds |= set(base.CARDS)
        got = False
        for modname, attr in (("cards", "WAR_CARDS"), ("maps", "MAP_CARDS")):
            try:
                mod = __import__(f"{__package__}.{modname}", fromlist=[attr])
                kinds |= set(getattr(mod, attr))
                got = True
            except Exception:
                continue
        return kinds if got else None
    except Exception:
        return None


def _default_catalog() -> Any:
    try:
        from . import catalog
        return catalog
    except Exception:
        return None


def plan(scenes: Sequence[Dict[str, Any]], *, catalog: Any = "default", assets: Optional[Dict[str, str]] = None,
         config: Optional[Dict[str, Any]] = None) -> Plan:
    cfg = dict(DEFAULTS)
    cfg.update(config or {})
    explicit = set(config or {})
    cat = _default_catalog() if catalog == "default" else catalog
    assets = dict(assets or {})
    out = Plan()
    rows = []
    for i, sc in enumerate(scenes or []):
        try:
            st, en = fr(float(sc.get("start", 0.0))), fr(float(sc.get("end", 0.0)))
        except (TypeError, ValueError):
            continue
        if en <= st:
            continue
        rows.append(dict(sc, _start=st, _end=en, _no=sc.get("scene_no", i + 1)))
    rows.sort(key=lambda r: (r["_start"], str(r["_no"])))
    if not rows:
        out.stats = {"scenes": 0, "card_share": 0.0, "clean_share": 1.0, "cards": 0, "headlines": 0, "kinds_checked": False}
        return out
    total = max(r["_end"] for r in rows)
    if cfg["profile"] == "auto" and total < cfg["short_total_s"]:
        for k, v in SHORT_PROFILE.items():
            if k not in explicit:
                cfg[k] = v
        out.flags_profile = "short"
    if cfg.get("direction") and "neutral_map_fallback" not in explicit:
        cfg["neutral_map_fallback"] = False       # an empty 'neutral map' is not a visual: the direction pass finds a truthful one or logs the gap
    state = _State(total, cfg)
    kinds = _available_kinds() if cfg["check_kinds"] else None
    shots_n = 0
    headlines = 0
    prev_path = ""
    filler = cfg.get("filler_footage")
    fillers = [filler] if isinstance(filler, str) else list(filler or [])
    missing_footage: List[Any] = []
    cred_items: List[Any] = []
    try:
        from . import provenance as P
    except Exception:
        P = None  # type: ignore[assignment]

    for r in rows:
        no, st, en = r["_no"], r["_start"], r["_end"]
        dec = Decision(scene_no=no)
        text = str(r.get("text") or "")
        meta = r.get("footage_meta") or {}
        finfo = footage_info(meta)
        path = r.get("footage") or ""
        if path and finfo["rejected"]:
            dec.flags.append("footage_rejected")
            path = ""
        if path and finfo["mismatch"] and cfg.get("drop_mismatch", True) and _unrelated(meta) and not _kept_anyway(meta):
            dec.flags.append("mismatch_dropped")        # a clip that does not show what is said is worse than the video's own map, card or footage
            path = ""
        if path:
            out.shots.append(Shot(str(path), st, en, float(meta.get("seek", 0.0) or 0.0) if isinstance(meta, dict) else 0.0))
            prev_path = str(path)
            shots_n += 1
            if P is not None and isinstance(meta, dict) and meta:
                try:
                    cred_items.append(P.from_manifest_record(meta))
                except Exception:
                    pass
            if finfo["recycled"]:
                dec.flags.append("recycled")
            if finfo["mismatch"]:
                dec.flags.append("mismatch")
            if finfo["reused"]:
                dec.flags.append("reused")          # a deliberate same-subject return (footage_match), not 'recycled' file footage
            if finfo["footage_class"]:
                dec.flags.append("footage_" + finfo["footage_class"])
            if finfo["status"] == "unverified":
                dec.flags.append("footage_unverified")
            if finfo["generic"]:
                dec.flags.append("footage_generic")
            if meta.get("kind") == "youtube" or (finfo["rights"] and "clearance" in finfo["rights"]):
                dec.flags.append("rights_clearance_needed")
        else:
            use = (fillers[len(missing_footage) % len(fillers)] if fillers else ('' if cfg.get("direction") else prev_path))   # direction: a new topic never sits on the previous clip
            dec.flags.append("no_footage")
            missing_footage.append(no)
            if use:
                out.shots.append(Shot(str(use), st, en))
                dec.flags.append("filler_footage")
        has_text = bool(text.strip())
        cands: List[Candidate] = []
        A = None
        if not has_text:
            dec.fallback_reason = "no_trigger"
            dec.flags.append("empty_text")
        else:
            A = S.analyze_scene(text, cat, r.get("words"), st, en)
            ctx = _Ctx(scene=r, A=A, cfg=cfg, catalog=cat, assets=assets, start=st, end=en, has_words=bool(r.get("words")),
                       seen_equipment=state.seen_equipment, footage_verified=bool(path) and finfo["status"] in ("confirmed", "attributed"))
            cands = build_candidates(ctx)
            if cfg["neutral_map_fallback"] and not path:
                fb = _neutral_map(ctx)
                if fb is not None:
                    cands.append(fb)
        # arbitrate: highest score first; ties go to the earlier trigger in the scene
        live = sorted([c for c in cands if c.code == ""], key=lambda c: (-c.score, c.start, c.kind, c.key))
        dead = [c for c in cands if c.code != ""]
        chosen: Optional[Candidate] = None
        layer_made: List[Layer] = []
        for c in live:
            lk = LAYER_KIND[c.kind]
            if c.fallback and chosen is not None:
                c.code, c.reason = "conflict_lost", c.reason + " — a better visual was chosen"
                continue
            if kinds is not None and lk not in kinds:
                c.code, c.reason = "provenance_failed", c.reason + f" (card kind '{lk}' is not available)"
                continue
            if c.kind == "map" and c.params.get("status") == "attributed" and not (c.params.get("control") or {}).get("source"):
                c.code, c.reason = "provenance_failed", c.reason + " (control layer without a source)"
                continue
            ok = False
            reason_code, why = "density", ""
            if c.start < cfg["first_at"] - 1e-9 and c.end >= cfg["first_at"] + cfg["min_card_s"] - 1e-9:
                c.start = fr(cfg["first_at"])     # the card waits for the opening seconds to pass instead of being dropped
            for shift in range(0, int(cfg["late_start_s"] * FPS) + 1, 5):
                s2 = fr(c.start + shift / FPS)
                e2 = fr(max(c.end + shift / FPS, s2 + cfg["min_card_s"]))
                if cfg["card_cap_s"] and c.kind != "timeline":
                    e2 = fr(min(e2, s2 + max(cfg["card_cap_s"], cfg["min_card_s"])))
                if s2 > en + cfg["late_start_s"] or e2 > state.total:
                    e2 = min(e2, state.total)
                    if e2 - s2 < cfg["min_card_s"] - 1e-9:
                        reason_code, why = "density", "not enough time left in the video"
                        break
                ok, reason_code, why = state.check(c, s2, e2, no, bool(path))
                if ok:
                    c.start, c.end = s2, e2
                    break
                if reason_code in ("conflict_lost", "clean_floor", "provenance_failed"):
                    break
            if not ok:
                c.code, c.reason = reason_code, c.reason + f" — {why}"
                continue
            c.accepted = True
            chosen = chosen or c
            full = c.kind in FULL_FRAME
            state.acc.append(_Acc(c.kind, c.start, c.end, full, c.key, no))
            if c.kind == "equipment" and c.equip_id:
                state.seen_equipment[c.equip_id] = c.start
                rec = c.params.get("image_record")
                if rec and P is not None:
                    try:
                        cred_items.append(EQI.provenance_for(rec, str(c.params.get("name") or "")))
                    except Exception:
                        pass
            params = dict(c.params)
            params.pop("image_record", None)
            ly = Layer(LAYER_KIND[c.kind], c.start, c.end, params, dim=c.kind not in NO_DIM)
            layer_made.append(ly)
            if cfg["kickers"] and not full and c.kind in KICKER:
                layer_made.append(Layer("kicker", c.start, c.end, {"text": KICKER[c.kind]}, dim=False))
        out.layers.extend(layer_made)
        if chosen is None and not dec.fallback_reason:
            codes = [c.code for c in cands if c.code]
            dec.fallback_reason = codes[0] if codes else "no_trigger"
        # a headline for a footage shot, never under a card
        if path and cfg["headlines"] and has_text and not finfo["generic"]:
            h = headline_text(text)
            hs = fr(st + 0.3)
            he = fr(min(en - 0.2, hs + cfg["headline_max_s"]))
            overlaps = any(a.start < he and a.end > hs for a in state.acc)
            if h and not overlaps and he - hs >= cfg["headline_min_s"] - 1e-9 and (headlines + 1) / max(1, shots_n) <= cfg["headline_share"]:
                hp = {"text": h, "status": finfo["status"]}
                out.layers.append(Layer(LAYER_KIND["headline"], hs, he, hp, dim=False))
                if finfo["chip"] and (finfo["recycled"] or finfo["mismatch"] or finfo["status"] in ("disputed", "attributed") or finfo["source_chip"]):
                    out.layers.append(Layer("status_chip", hs, he, {"status": "illustrative" if finfo["mismatch"] else finfo["status"], "text": finfo["chip"]}, dim=False))
                headlines += 1
                dec.flags.append("headline")
        if path and finfo["chip"] and (finfo["recycled"] or finfo["mismatch"] or finfo["status"] == "disputed" or finfo["source_chip"]) and "headline" not in dec.flags:
            # footage that needs its label gets it even when no headline is shown
            cs = fr(st + 0.3)
            ce = fr(min(en - 0.2, cs + cfg["headline_max_s"]))
            if ce - cs >= cfg["headline_min_s"] - 1e-9:
                out.layers.append(Layer("status_chip", cs, ce, {"status": "illustrative" if finfo["mismatch"] else finfo["status"], "text": finfo["chip"]}, dim=False))
                dec.flags.append("footage_chip")
        dec.candidates = [c.brief() for c in sorted(cands, key=lambda c: (-c.score, c.kind, c.key))]
        dec.chosen = chosen.kind if chosen else None
        out.log.append(dec)

    direction_stats: Dict[str, Any] = {}
    if cfg.get("direction"):
        try:
            from . import direction as _dir

            direction_stats = _dir.apply(out, rows, cfg, cat)
        except Exception as exc:                  # the art direction is an addition: a failure leaves the planner's own plan untouched
            direction_stats = {"error": f"{type(exc).__name__}: {exc}"}
    out.layers.sort(key=lambda ly: (ly.start, ly.end, ly.kind))
    card_time = state.card_time()
    out.stats = {"scenes": len(rows), "cards": len(state.acc), "card_share": round(card_time / state.total, 4), "clean_share": round(1 - card_time / state.total, 4),
                 "headlines": headlines, "footage_shots": shots_n, "headline_share": round(headlines / shots_n, 3) if shots_n else 0.0,
                 "missing_footage_scenes": missing_footage, "kinds_checked": kinds is not None, "total_s": total, "direction": direction_stats}
    if P is not None:
        try:
            from . import portraits as _pt

            seen_img = set()
            for ly in out.layers:   # attribution for every cached portrait that was actually shown
                img = (ly.params or {}).get("image") if getattr(ly, "kind", "") == "figure_card" else None
                if isinstance(img, str) and img not in seen_img:
                    seen_img.add(img)
                    pp = _pt.provenance_for_path(img)
                    if pp is not None:
                        cred_items.append(pp)
        except Exception:
            pass
        try:
            out.credits = list(P.credits_lines(cred_items))
        except Exception:
            out.credits = []
    return out
