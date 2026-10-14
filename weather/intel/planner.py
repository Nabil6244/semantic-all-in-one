"""Graphic opportunity detection and narration-aligned placement.

For each graphic in the catalogue that fits the event's category, the planner:
  1. skips it when the user's plan already gives the viewer that graphic (a row of a covering type: preserved, never duplicated);
  2. scores every beat by how much its words discuss the graphic's topics (the beat must reach the graphic's min_score);
  3. keeps only beats where it may go: map beats (never full-screen footage), long enough for the graphic, and within the limits —
     at most one loop (radar / satellite / before-after), one counter and three data graphics per beat, the user's rows included;
  4. prefers the strongest beat, then the less crowded one (graphics spread over the narration instead of piling up at the start);
  5. builds the graphic FOR that beat (its advisory, gauges, dates follow what the beat says) and anchors it on the first words of
     the sentence that triggered it.
Every graphic not added has a reason in `skipped`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .catalog import CATALOG, DATA_KINDS, Draft, GraphicSpec, Skip
from .context import EventContext
from .understand import Segment, split_sentences, topic_strengths

MAX_DATA_PER_BEAT = 3
MAX_LOOPS_PER_BEAT = 1
MAX_COUNTERS_PER_BEAT = 1
LOOP_TYPES = {"radar", "satellite_loop", "before_after", "satellite"}
COUNTER_TYPES = {"counter"}
NOT_DATA = {"source_line", "headline", "place_label", "footage_credit", "tp_title", "tp_place", "tp_tag", "tp_lower", "tp_dip",
            "tp_vignette", "tp_stat"}
MAP_MODES = ("map", "map_footage")


@dataclass
class Skipped:
    spec: str
    title: str
    reason: str
    beat: str = ""


@dataclass
class Occupancy:
    loops: int = 0
    counters: int = 0
    data: int = 0

    def add(self, typ: str) -> None:
        if typ in NOT_DATA:
            return
        self.data += 1
        if typ in LOOP_TYPES:
            self.loops += 1
        if typ in COUNTER_TYPES:
            self.counters += 1

    def room(self, types: Sequence[str]) -> Optional[str]:
        o = Occupancy(self.loops, self.counters, self.data)
        for t in types:
            o.add(t)
        if o.loops > MAX_LOOPS_PER_BEAT:
            return "it already has a radar or satellite loop"
        if o.counters > MAX_COUNTERS_PER_BEAT:
            return "it already has a counter"
        if o.data > MAX_DATA_PER_BEAT:
            return f"it already has {self.data} data graphics"
        return None


class Planner:
    def __init__(self, ctx: EventContext, segments: Sequence[Segment], *, net=None, fmt: str = "news", contact: str = "",
                 user_rows: Sequence[Any] = (), overrides: Optional[Dict[str, Any]] = None, evidence=None):
        self.ctx, self.segments, self.net, self.fmt, self.contact = ctx, list(segments), net, fmt, contact
        self.seg_ids = [s.id for s in segments]
        self.by_id = {s.id: s for s in segments}
        self.user_rows = list(user_rows)
        self.ov = overrides or {}
        self.ev = evidence
        self.drafts: List[Draft] = []
        self.skipped: List[Skipped] = []
        self.preserved: List[Tuple[str, str]] = []  # (spec, user row id)
        self.notes: List[str] = []
        self.occ: Dict[str, Occupancy] = {s.id: Occupancy() for s in segments}
        for r in self.user_rows:
            if r.beat in self.occ:
                self.occ[r.beat].add(r.type)

    # ---- lookups the specs ask for -----------------------------------------------------------------------------------------
    def place_name(self) -> str:
        from .catalog import state_name

        return state_name(self.ctx.states[0]) if self.ctx.states else ""

    def advisory(self, target: datetime):
        from ..news import nhc
        from . import identity as idn

        s = self.ctx.storm
        key = f"adv:{s.id}"
        if key not in self.ctx._cache:
            url = idn.ADVISORY_INDEX.format(basin=s.basin.lower(), num=f"{s.number:02d}", year=s.year)
            try:
                self.ctx._cache[key] = idn.advisories(self.net.text(url, source="nhc_gis_advisory", purpose=f"advisory list of {s.id}"), s.id)
            except Exception as exc:
                self.ctx._cache[key] = []
                self.notes.append(f"the NHC advisory list of {s.id} could not be read ({exc})")

        def issued(adv: str) -> datetime:
            blob = self.net.bytes(nhc.ARCHIVE.format(id=s.id.lower(), adv=adv), source="nhc_gis_advisory", purpose=f"issue time of advisory {adv}")
            from ..tz import parse_iso

            return parse_iso(nhc.advisory(blob)["issued"])

        return idn.pick_advisory(s.id, target, self.ctx._cache[key], issued)

    def gauge(self, river: str, context: str):
        from . import identity as idn

        ov = (self.ov.get("gauges") or {}).get(river)
        if ov:
            return idn.Gauge(str(ov), river, 0.0, 0.0), f"gauge {ov} set in the overrides for {river}"
        sites: List[idn.Gauge] = []
        for st in self.ctx.states[:2] or []:
            key = f"usgs_sites:{st}"
            if key not in self.ctx._cache:
                url = idn.USGS_SITES.format(state=st.lower())
                try:
                    self.ctx._cache[key] = idn.parse_sites(self.net.text(url, source="usgs_site", purpose=f"gauges in {st}", max_age_s=7 * 86400.0))
                except Exception as exc:
                    self.ctx._cache[key] = []
                    self.notes.append(f"the USGS gauge list of {st} could not be read ({exc})")
            sites += self.ctx._cache[key]
        g, how = idn.pick_gauge(river, sites, context, self.ctx.focus)
        if self.ev is not None and g is not None:
            self.ev.add(kind="identity", subject=river, what="USGS gauge", value=g.site, where=f"{g.lat},{g.lon}", source="usgs_site",
                        record=idn.USGS_SITES.format(state=(self.ctx.states or ["?"])[0].lower()), retrieved=self.net.stamp if self.net else "",
                        method=how)
        return g, how

    # ---- placement ---------------------------------------------------------------------------------------------------------
    def eligible(self, seg: Segment, spec: GraphicSpec) -> Optional[str]:
        if seg.mode not in MAP_MODES:
            return "it is a full-screen footage beat"
        if seg.start is not None and seg.end is not None and seg.end - seg.start < spec.min_s:
            return f"it is shorter than the {spec.min_s:g} s the graphic needs"
        return None

    def score(self, seg: Segment, spec: GraphicSpec) -> float:
        topics = topic_strengths(seg.text)
        if spec.must and not any(topics.get(t) for t in spec.must):
            return 0.0
        return sum(w * min(topics.get(t, 0.0), 6.0) for t, w in spec.topics.items())

    def anchor(self, seg: Segment, spec: GraphicSpec, entity: str = "") -> str:
        """The first words of the beat's first sentence that discusses the graphic — or names its entity (a river, a county) — (the
        beat's own anchor for its first sentence)."""
        sents = split_sentences(seg.text)
        pick = 0
        for i, s in enumerate(sents):
            if entity:
                if entity.split()[0].lower() in s.lower():
                    pick = i
                    break
                continue
            t = topic_strengths(s)
            if any(t.get(k) for k in spec.topics):
                pick = i
                break
        if pick == 0 and seg.anchor:
            return seg.anchor
        words = [w for w in sents[pick].split() if w.strip("\"'“”")][:4] if sents else []
        return " ".join(words).strip()

    def covered(self, spec: GraphicSpec) -> Optional[Any]:
        """The user's row that already gives the viewer this graphic (a report counter is not a warning counter)."""
        for r in self.user_rows:
            if r.type in spec.covers:
                if spec.key == "severe.counter" and r.data_source is not None and r.data_source.provider != "spc":
                    continue
                return r
        if spec.key == "warnings.counter":
            return next((r for r in self.user_rows if r.type == "counter" and r.data_source is not None and r.data_source.provider == "iem"), None)
        return None

    def entity_covered(self, spec: GraphicSpec, entity: str, segs: Sequence[str] = ()) -> bool:
        key = entity.split()[0].lower()
        if spec.key == "river.crest" and any(r.type == "river_crest" for r in self.user_rows):
            context = " ".join(self.by_id[s].text for s in segs if s in self.by_id)
            g, _how = self.gauge(entity, context)
            if g is not None and any(r.type == "river_crest" and r.data_source is not None and r.data_source.target == g.site
                                     for r in self.user_rows):
                return True
        for r in self.user_rows:
            if r.type in spec.covers:
                said = " ".join([str(r.extra.get("text", "")), str(r.extra.get("label", "")), r.data_source.text if r.data_source else ""])
                if key in said.lower():
                    return True
        return False

    def wanted(self, spec: GraphicSpec) -> Optional[str]:
        only, excl = self.ov.get("only"), set(self.ov.get("exclude") or [])
        if spec.key in excl:
            return "excluded in the overrides"
        if only and spec.key not in only:
            return "not in the overrides' list of graphics to add"
        cats = (self.ctx.category, *self.ctx.u.hazards[:1])
        if "*" not in spec.categories and not any(c in spec.categories for c in cats):
            return f"not a {self.ctx.category.replace('_', ' ')} graphic"
        return None

    def run(self) -> List[Draft]:
        for spec in sorted(CATALOG, key=lambda s: s.priority):
            why = self.wanted(spec)
            if why:
                if "not a" not in why:
                    self.skipped.append(Skipped(spec.key, spec.title, why))
                continue
            have = self.covered(spec)
            if have is not None and spec.per_entity is None:
                self.preserved.append((spec.key, have.id))
                continue
            if spec.per_entity is not None:
                for entity, segs in spec.per_entity(self):
                    if self.entity_covered(spec, entity, segs):
                        self.preserved.append((spec.key, entity))
                        continue
                    self._place(spec, entity=entity, only_segs=segs)
            else:
                self._place(spec)
        self._source_lines()
        return self.drafts

    def _place(self, spec: GraphicSpec, entity: str = "", only_segs: Sequence[str] = ()) -> None:
        forced = (self.ov.get("place") or {}).get(spec.key)
        ranked: List[Tuple[float, int, Segment]] = []
        refusals: List[str] = []
        for i, seg in enumerate(self.segments):
            if forced and seg.id != forced:
                continue
            if only_segs and seg.id not in only_segs:
                continue
            bad = self.eligible(seg, spec)
            if bad:
                refusals.append(f"{seg.id}: {bad}")
                continue
            s = self.score(seg, spec)
            if spec.min_score > 0 and s < spec.min_score and not forced:
                continue
            crowd = self.occ[seg.id].data
            ranked.append((s - 0.35 * crowd - (0.02 * i if spec.key == "broadcast.headline" else 0), -i, seg))
        if spec.key == "broadcast.headline":   # the opening lower-third goes on the first map beat
            ranked = [r for r in ranked if r[2].id == next((x[2].id for x in sorted(ranked, key=lambda r: -r[1])), None)]
        if entity and not ranked and only_segs:
            # a county named only in footage beats: its label goes on the first map beat after it is named
            later = [s for s in self.segments if s.mode in MAP_MODES and self.seg_ids.index(s.id) >= self.seg_ids.index(only_segs[0])]
            ranked = [(0.0, -self.seg_ids.index(s.id), s) for s in later[:1]]
        if not ranked:
            if spec.min_score > 0:
                where = f" ({'; '.join(refusals[:3])})" if refusals and not any(self.score(s, spec) >= spec.min_score for s in self.segments if s.mode in MAP_MODES) and \
                    any(self.score(s, spec) >= spec.min_score for s in self.segments) else ""
                reason = ("the narration never discusses it" + where) if not where else \
                    "the narration discusses it only where weather graphics cannot go" + where
            else:
                reason = "no map beat to put it on"
            self.skipped.append(Skipped(spec.key, spec.title + (f" ({entity})" if entity else ""), reason))
            return
        ranked.sort(key=lambda r: (-r[0], -r[1]))
        last_reason = ""
        for _s, _i, seg in ranked[:4]:
            try:
                drafts = spec.build(self, seg, entity) if entity else spec.build(self, seg)
            except Skip as sk:
                last_reason = sk.reason
                if sk.local:
                    continue
                self.skipped.append(Skipped(spec.key, spec.title + (f" ({entity})" if entity else ""), sk.reason, seg.id))
                return
            room = self.occ[seg.id].room([d.type for d in drafts])
            if room:
                last_reason = f"beat {seg.id} is full ({room})"
                continue
            anchor = self.anchor(seg, spec, entity)
            for d in drafts:
                d.beat, d.vo_anchor = seg.id, anchor
                d.kind = spec.kind if not d.companion_of else "data"
                self.occ[seg.id].add(d.type)
                self.drafts.append(d)
            return
        self.skipped.append(Skipped(spec.key, spec.title + (f" ({entity})" if entity else ""), last_reason or "no beat had room"))

    def _source_lines(self) -> None:
        """One source line on each beat that shows auto data and has none of the user's."""
        user_lines = {r.beat for r in self.user_rows if r.type == "source_line"}
        seen = set()
        for d in list(self.drafts):
            if d.type in NOT_DATA or d.beat in user_lines or d.beat in seen:
                continue
            seen.add(d.beat)
            first = next(x for x in self.drafts if x.beat == d.beat and x.type not in NOT_DATA)
            self.drafts.append(Draft("broadcast.source_line", f"auto_src_{d.beat}", "source_line", beat=d.beat, vo_anchor=first.vo_anchor,
                                     kind="source", why="names the sources of the data graphics on this beat"))
