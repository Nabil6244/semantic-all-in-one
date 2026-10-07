"""The resolver: a beat plan -> which datasets it uses and, for every beat, its full context -- deterministically, from the CSV
and the local dataset library only (no network, no AI; the same plan and reference date always give the same answer).

For each map beat, the datasets it is about come from, in order:
  1. explicit context in the beat's extra ({"mission": "artemis3"} or {"dataset": ...})
  2. qualified ids anywhere in the beat (apollo11.lm, artemis3.landing, voyager1.T+...)
  3. names only one dataset has (eagle -> apollo11, orion -> artemis1, a dataset's own site or body)
  4. the previous map beat's context (the plan row's id, an old mission pack id, starts the chain)
  5. the beat's narration naming a dataset (whole words): a limited fallback, and when it names a DIFFERENT dataset than the
     previous beat, a name several datasets share is reported as ambiguous instead of being guessed
Every reference is then resolved in that context: a qualified id as written, a bare name only if exactly one dataset in the
context (or in the whole library) has it. Ambiguous and unknown names are errors naming the row. Nothing is dropped.

The beat's temporal context: the universe date (its date column), the date's status/precision/net (an event's own, the
dataset's default), the status of what it shows (planned, projected and hypothetical things make the beat that), the geometry
basis of what it shows, whether a position is past its observed data (estimated, if the dataset allows extrapolation), its
timeline, and its mission clock. A beat's extra may lower certainty ({"status": "hypothetical"}), never raise it.

Between two dated map beats time either runs on screen (continuous: the same timeline, the same certainty, a short gap) or
JUMPS: the old date holds and the new one arrives in one frame, hidden by footage when there is footage between them, else by
a short time-jump transition (compile.py draws it). extra {"continuous": true | false} decides explicitly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .beat_csv import Beat, Item, Plan
from .catalog import Catalog, CatalogError, DateInfo
from .datasets import Dataset, norm, split_qualified
from .temporal import BADGE, CERTAINTY, PRECISIONS, STATUSES, TemporalError, iso_days, least_certain, parse_iso, reference_date, show_date

SKY = "sky"
DEFAULT_CONTINUITY_DAYS = 180.0         # a dataset's own story may run on screen this far; datasets can say more (temporal.continuity_days)
SKY_CONTINUITY_DAYS = 31.0
MAX_CONTINUOUS_DAYS = 3660.0            # even when a CSV asks, ten years is the most that may visibly run on screen


@dataclass
class BeatContext:
    beat: str
    row: int
    datasets: List[str] = field(default_factory=list)
    primary: Optional[str] = None
    utc: Optional[str] = None                     # the beat's own universe date (None: time keeps running from the beat before)
    date_kind: str = ""                           # iso | event | mission_time | now | "" (undated)
    event: Optional[str] = None                   # the event's qualified id
    precision: str = "minute"
    net: bool = False
    status: Optional[str] = None                  # None: no dataset content (the sky, computed for the date)
    basis: List[str] = field(default_factory=list)
    timeline: str = SKY
    estimated_from: Optional[str] = None          # observed data ends here; the position shown is extrapolated
    met_zero: Optional[str] = None
    clock_prefix: str = ""
    source: str = ""
    as_of: Optional[str] = None
    lowered_by_csv: bool = False
    refs: Dict[str, str] = field(default_factory=dict)          # "row:field:name" -> qualified id

    @property
    def badge(self) -> str:
        """The on-screen label the beat needs (empty: none): PLANNED · NET SEP 2027, HYPOTHETICAL · 2050, ESTIMATED · DATA TO JUN 2026."""
        if self.status in BADGE:
            when = show_date(self.utc, "month" if self.precision in ("second", "minute", "day") and self.status != "planned" else self.precision, self.net) \
                if self.utc else ""
            if self.status in ("projected", "hypothetical") and self.utc:
                when = str(parse_iso(self.utc).year)
            parts = [BADGE[self.status]] + ([when] if when else []) + (["ILLUSTRATIVE"] if "illustrative" in self.basis and self.status != "hypothetical" else [])
            return " · ".join(parts)
        if self.estimated_from:
            return f"ESTIMATED · DATA TO {show_date(self.estimated_from, 'month')}"
        return ""


@dataclass
class Transition:
    a: str                                        # beat ids (dated map beats, in order)
    b: str
    kind: str                                     # continuous | jump
    reason: str
    hidden_by_footage: bool
    a_utc: str
    b_utc: str
    label: str = ""                               # for the time-jump card: "1969 → 2026", "2027 → 2050 · HYPOTHETICAL"


@dataclass
class Resolution:
    reference_now: Optional[str]
    contexts: Dict[str, BeatContext] = field(default_factory=dict)
    transitions: List[Transition] = field(default_factory=list)
    used: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def ctx(self, beat_id: str) -> List[str]:
        c = self.contexts.get(beat_id)
        return c.datasets if c else []

    def detected(self, cat: Catalog) -> List[str]:
        """Check plan's "Detected" lines: each dataset, its status and geometry, freshness, and the beats that use it."""
        out = []
        for did in self.used:
            ds = cat.index.datasets[did]
            beats = [b for b, c in self.contexts.items() if did in c.datasets]
            statuses = sorted({c.status for b, c in self.contexts.items() if did in c.datasets and c.status}, key=STATUSES.index)
            years = sorted({parse_iso(c.utc).year for c in self.contexts.values() if did in c.datasets and c.utc})
            when = (f"{years[0]}" if len(years) == 1 else f"{years[0]}–{years[-1]}") if years else ""
            bases = sorted({b for c in self.contexts.values() if did in c.datasets for b in c.basis})
            fresh = [f"observed data through {show_date(t.observed_until, 'month')}" for t in ds.trajectories.values() if t.observed_until]
            line = f"  {ds.name} ({did})  " + " · ".join(x for x in [", ".join(s.capitalize() for s in statuses) or ds.status.capitalize(), when,
                                                                       ", ".join(f"{b} geometry" for b in bases)] + fresh[:1] if x)
            if ds.as_of and ds.status in ("planned", "projected", "hypothetical"):
                line += f" · as of {show_date(ds.as_of, 'month')}"
            if ds.fixture:
                line += " · TEST FIXTURE"
            out.append(line + f"  [beats {', '.join(beats)}]")
        return out


def resolve(plan: Plan, cat: Catalog, *, reference_now: Optional[str] = None) -> Resolution:
    now = None
    raw_now = reference_now or getattr(plan, "reference_now", "")
    res = Resolution(reference_now=None)
    if raw_now:
        try:
            now = reference_date(raw_now)
        except TemporalError as exc:
            res.errors.append(f"plan row: {exc}")
    res.reference_now = now
    hint: List[str] = []
    if getattr(plan, "pack", ""):
        ds = cat.index.get(plan.pack)
        if ds is None:
            res.errors.append(f"plan row: unknown dataset {plan.pack!r}" + cat._suggest(norm(plan.pack), list(cat.index.datasets)))
        else:
            hint = [ds.id]
    elif cat.default:
        hint = [cat.default]
    prev: Optional[BeatContext] = None
    prev_ctx: List[str] = list(hint)
    for b in plan.beats:
        if b.mode == "footage":
            continue
        ctx = _beat_context(b, cat, res, prev_ctx)
        c = _temporal(b, ctx, cat, res, now, prev)
        res.contexts[b.id] = c
        prev = c
        if c.datasets:
            prev_ctx = c.datasets
    res.used = sorted({d for c in res.contexts.values() for d in c.datasets})
    _transitions(plan, res, cat)
    for p in cat.index.problems:
        res.warnings.append(f"dataset library: {p}")
    return res


# ---- which datasets a beat is about -------------------------------------------------------------------------------------
_REF_TYPES = {"craft": "craft", "path": "path", "orbit": "orbit"}


def _names(b: Beat) -> List[Tuple[Item, str, str, str]]:
    """(item, field, kind, name) for every structured reference of a beat's rows: craft/path/orbit ids, places (a distance or
    a line may name a craft too)."""
    out = []
    for it in b.layers:
        if it.type in _REF_TYPES and it.id:
            out.append((it, "id", _REF_TYPES[it.type], it.id))
        if it.place and it.type in ("distance", "line"):
            for nm in [x.strip() for x in it.place.split(";") if x.strip()]:
                out.append((it, "place", "place_or_craft", nm))
        elif it.place:
            out.append((it, "place", "place", it.place))
    return out


def _datasets_named(cat: Catalog, kind: str, name: str) -> Set[str]:
    """The datasets a bare or qualified name can only belong to (empty when it is shared or unknown)."""
    q = split_qualified(name)
    if q and q[0] in cat.index.datasets:
        return {q[0]}
    kinds = ["craft", "site", "body"] if kind == "place_or_craft" else (["site", "body"] if kind == "place" else [kind])
    if kind in ("place", "place_or_craft") and norm(name) in cat.aliases:
        return set()                                              # a base body (moon, earth+moon ...) belongs to no dataset
    cands: Set[str] = set()
    for k in kinds:
        for qq in cat.index.candidates(k, name):
            cands.add(qq.split(".", 1)[0])
    if kind in ("place", "place_or_craft") and "+" in name:
        for part in name.split("+"):
            cands |= _datasets_named(cat, "place", part)
        return cands if len(cands) == 1 else set()
    if kind == "place" and norm(name) in cat._site_alias:
        return set()                                              # a shared site everyone may use (sites.json)
    return cands if len(cands) == 1 else set()


def _date_datasets(cat: Catalog, expr: str) -> Set[str]:
    e = norm(expr).replace(" ", "")
    q = split_qualified(e)
    if q and q[0] in cat.index.datasets:
        return {q[0]}
    from .catalog import _EVENT_EXPR, _MET

    if _MET.fullmatch(e):
        return set()
    m = _EVENT_EXPR.fullmatch(e)
    name = m[1] if m else e
    cands = {qq.split(".", 1)[0] for qq in cat.index.candidates("event", name)}
    return cands if len(cands) == 1 else set()


def _beat_context(b: Beat, cat: Catalog, res: Resolution, prev_ctx: List[str]) -> List[str]:
    explicit: Set[str] = set()
    for key in ("mission", "dataset"):
        if b.extra.get(key):
            vals = b.extra[key] if isinstance(b.extra[key], list) else [b.extra[key]]
            for v in vals:
                ds = cat.index.get(str(v))
                if ds is None:
                    res.errors.append(f"row {b.row}: extra {key}: unknown dataset {v!r}" + cat._suggest(norm(str(v)), list(cat.index.datasets)))
                else:
                    explicit.add(ds.id)
    named: Set[str] = set(explicit)
    if b.date:
        named |= _date_datasets(cat, b.date)
    if b.place:
        named |= _datasets_named(cat, "place", b.place)
    for it, fld, kind, name in _names(b):
        named |= _datasets_named(cat, kind, name)
    if named:
        return sorted(named)
    # nothing in the beat's own rows says: the previous beat, checked against what the narration names
    said = cat.index.narration_matches(b.text)
    if not needs_context(b, cat):
        return []
    if prev_ctx and (not said or set(said) & set(prev_ctx)):
        return list(prev_ctx)
    if said and not prev_ctx and len(said) == 1:
        return said
    if said:
        res.errors.append(f"row {b.row}: beat {b.id} names shared ids without saying which mission: the narration names "
                          f"{', '.join(said)} but the beat before was about {', '.join(prev_ctx) or 'nothing'}; write qualified ids "
                          f"(e.g. {said[0]}.launch) or extra {{\"mission\": \"{said[0]}\"}}")
    return list(prev_ctx)


def needs_context(b: Beat, cat: Catalog) -> bool:
    """Does the beat use a name that only a dataset can give meaning to (a bare event, craft, path or orbit, mission time)?"""
    if b.date and norm(b.date).replace(" ", "") not in ("now", "today"):
        try:
            parse_iso(b.date)
        except ValueError:
            return True
    return any(kind in ("craft", "path", "orbit") for _, _, kind, _ in _names(b)) or any(
        kind == "place_or_craft" and cat.index.candidates("craft", name) for _, _, kind, name in _names(b))


# ---- the temporal context ------------------------------------------------------------------------------------------------
def _temporal(b: Beat, ctx: List[str], cat: Catalog, res: Resolution, now: Optional[str], prev: Optional[BeatContext]) -> BeatContext:
    c = BeatContext(beat=b.id, row=b.row, datasets=list(ctx), primary=ctx[0] if len(ctx) == 1 else None)
    info: Optional[DateInfo] = None
    if b.date:
        try:
            info = cat.date_info(b.date, ctx, now)
        except CatalogError as exc:
            res.errors.append(f"row {b.row}: {exc}")
    shown: List[Tuple[str, Any]] = []                     # (qualified id, trajectory) of the geometry the beat draws
    for it, fld, kind, name in _names(b):
        try:
            if kind in ("craft", "path", "orbit"):
                qid, val = cat.lookup(kind, name, ctx)
                c.refs[f"{it.row}:{fld}:{name}"] = qid
                tid = val.get("trajectory") if kind in ("craft", "orbit") else val.get("of")
                if tid:
                    shown.append((qid, cat.index.trajectories[tid]))
            elif kind == "place_or_craft":
                try:
                    p = cat.place(name, ctx)
                    if p.dataset:
                        c.refs[f"{it.row}:{fld}:{name}"] = p.dataset
                except CatalogError:
                    qid, val = cat.lookup("craft", name, ctx)
                    c.refs[f"{it.row}:{fld}:{name}"] = qid
            else:
                cat.place(name, ctx)
        except CatalogError as exc:
            res.errors.append(f"row {it.row}: {exc}")
    for qid in c.refs.values():
        did = qid.split(".", 1)[0]
        if did in cat.index.datasets and did not in c.datasets:
            c.datasets.append(did)
    if info is not None and info.dataset and info.dataset not in c.datasets:
        c.datasets.append(info.dataset)
    c.datasets.sort()
    c.primary = c.datasets[0] if len(c.datasets) == 1 else (info.dataset if info is not None and info.dataset else None)
    pds: Optional[Dataset] = cat.index.datasets.get(c.primary) if c.primary else None

    if info is None and not b.date and prev is not None:
        # undated: time keeps running from the beat before, and so does its era
        c.utc, c.status, c.precision, c.net, c.timeline = None, prev.status, prev.precision, prev.net, prev.timeline
        c.met_zero, c.clock_prefix, c.source, c.as_of = prev.met_zero, prev.clock_prefix, prev.source, prev.as_of
        if c.datasets and not set(c.datasets) & set(prev.datasets):
            c.timeline = "+".join(c.datasets)
            c.met_zero = pds.met_zero if pds else None
    elif info is not None:
        c.utc, c.date_kind, c.precision, c.net = info.utc, info.kind, info.precision, info.net
        c.event = info.event.qid if info.event else None
    base: Optional[str] = None
    if info is not None:
        if info.event is not None:
            base = info.event.status
        elif info.kind == "now":
            base = "current"
        elif pds is not None:
            base = pds.status if pds.status != "current" else "historical"
    elif not b.date and prev is not None:
        base = prev.status
    uncertain = [cat.index.datasets[d].status for d in c.datasets if CERTAINTY[cat.index.datasets[d].status] > 0]
    uncertain += [t.status for _, t in shown if CERTAINTY[t.status] > 0]
    if c.datasets and base is None:
        base = "historical"
    c.status = least_certain([base] + uncertain) if (base or uncertain) else None
    c.basis = sorted({t.basis for _, t in shown})
    if pds is not None and b.date:
        c.timeline = pds.id
        c.met_zero = pds.met_zero
        c.source, c.as_of = pds.source, pds.as_of
    elif b.date and not c.datasets:
        c.timeline = SKY
    if c.datasets and not c.primary:
        c.timeline = "+".join(c.datasets)
    if b.extra.get("timeline"):
        c.timeline = str(b.extra["timeline"])
    # the CSV may only make a beat LESS certain
    want = b.extra.get("status")
    if want:
        w = norm(str(want))
        if w not in STATUSES:
            res.errors.append(f"row {b.row}: extra status must be one of {', '.join(STATUSES)} (got {want!r})")
        elif c.status and CERTAINTY[w] < CERTAINTY[c.status]:
            res.errors.append(f"row {b.row}: conflicting status: the data says {c.status} but the CSV says {w}; a CSV may make a beat "
                              f"less certain, never more")
        else:
            c.status, c.lowered_by_csv = w, True
    if c.status == "hypothetical" and not c.basis:
        c.basis = ["illustrative"]
    c.clock_prefix = BADGE.get(c.status or "", "")
    # facts against the reference date
    if now and c.utc and info is not None:
        if c.status == "historical" and info.event is not None and parse_iso(c.utc) > parse_iso(now):
            res.errors.append(f"row {b.row}: unsupported date: {b.date} ({c.utc[:10]}) is after the project's reference date ({now[:10]}) "
                              f"but its data says it is historical")
        if info.event is not None and info.event.status in ("planned", "projected") and parse_iso(c.utc) < parse_iso(now):
            res.warnings.append(f"row {b.row}: {info.event.qid} is {info.event.status} for {c.utc[:10]}, before the project's reference date "
                                f"({now[:10]}): its dataset (as of {pds.as_of[:10] if pds and pds.as_of else 'unknown'}) may be out of date")
    # positions past the observed data
    when = c.utc or (prev.utc if prev else None)
    for qid, t in shown:
        if not when:
            continue
        limit = t.observed_until or (t.end if t.basis == "observed" else None)
        if not limit or parse_iso(when) <= parse_iso(limit):
            continue
        days = iso_days(limit, when)
        what = f"{qid.split('.', 1)[0]} ({t.id})"
        if not t.extrapolate:
            res.errors.append(f"row {b.row}: unavailable observed data: {what} has observed data through {limit[:10]}; {when[:10]} is "
                              f"{days:.0f} days later and the dataset gives no extrapolation rule")
        elif days > float(t.extrapolate["max_days"]):
            res.errors.append(f"row {b.row}: unsupported extrapolation: {what} may be extrapolated {t.extrapolate['max_days']} days past "
                              f"{limit[:10]}; {when[:10]} is {days:.0f} days past it")
        else:
            c.estimated_from = limit if not c.estimated_from or limit < c.estimated_from else c.estimated_from
    return c


# ---- time between beats --------------------------------------------------------------------------------------------------
def _transitions(plan: Plan, res: Resolution, cat: Catalog) -> None:
    beats = plan.beats
    dated = [b for b in beats if b.mode != "footage" and res.contexts.get(b.id) and res.contexts[b.id].utc]
    for a, b in zip(dated, dated[1:]):
        ca, cb = res.contexts[a.id], res.contexts[b.id]
        ia, ib = beats.index(a), beats.index(b)
        hidden = any(beats[k].mode == "footage" for k in range(ia + 1, ib))
        # how far time would run on screen: from a's date, held in real time to b's start, then to b's date
        gap = abs(iso_days(ca.utc, cb.utc))
        span = SKY_CONTINUITY_DAYS
        if ca.timeline == cb.timeline and ca.primary:
            span = float(cat.index.datasets[ca.primary].data.get("temporal", {}).get("continuity_days", DEFAULT_CONTINUITY_DAYS))
        explicit = b.extra.get("continuous")
        if explicit is True:
            kind, why = "continuous", "the CSV asks for continuous time"
            if gap > MAX_CONTINUOUS_DAYS and not hidden:
                res.errors.append(f"row {b.row}: invalid temporal transition: continuous time from {ca.utc[:10]} to {cb.utc[:10]} would run "
                                  f"{gap / 365.25:.0f} years on screen (at most {MAX_CONTINUOUS_DAYS / 365.25:.0f}); let it jump instead")
        elif explicit is False:
            kind, why = "jump", "the CSV asks for a jump"
        elif ca.timeline != cb.timeline:
            kind, why = "jump", f"a new timeline ({ca.timeline} -> {cb.timeline})"
        elif CERTAINTY.get(ca.status or "historical", 0) != CERTAINTY.get(cb.status or "historical", 0):
            kind, why = "jump", f"a new temporal context ({ca.status or 'sky'} -> {cb.status or 'sky'})"
        elif gap > span:
            kind, why = "jump", f"{gap:.0f} days apart (more than the {span:.0f} days that may run on screen)"
        else:
            kind, why = "continuous", "the same timeline"
        if explicit is not None and not isinstance(explicit, bool):
            res.errors.append(f"row {b.row}: extra continuous must be true or false (got {explicit!r})")
        res.transitions.append(Transition(a.id, b.id, kind, why, hidden, ca.utc, cb.utc, _jump_label(ca, cb)))


def _jump_label(a: BeatContext, b: BeatContext) -> str:
    days = abs(iso_days(a.utc, b.utc))
    prec = "year" if days >= 300 else ("month" if days >= 20 else "day")
    coarse = lambda own: max(prec, own, key=PRECISIONS.index)  # noqa: E731  -- never more precise than the jump or the data
    fa = show_date(a.utc, coarse(a.precision))
    fb = show_date(b.utc, coarse(b.precision), b.net and coarse(b.precision) != "year")
    tail = f" · {BADGE[b.status]}" if b.status in BADGE else (" · TODAY" if b.date_kind == "now" else "")
    return f"{fa} → {fb}{tail}"
