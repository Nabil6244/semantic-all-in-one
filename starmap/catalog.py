"""What a StarMap CSV may name: bodies, surface sites, and everything in the dataset library -- events, craft, paths, orbits,
sites, extra bodies -- across ALL datasets at once (starmap/datasets.py finds them; nothing is selected by the user).

Everything here is DATA (starmap/catalog/*.json, starmap/packs/*.json); the engine knows none of it. A name in a CSV is
resolved in a CONTEXT (the datasets a beat is about, worked out by starmap/resolve.py):

    apollo11.lm            a qualified id: always means exactly that
    eagle                  a name only one dataset has: means that one
    lm, launch, csm        a name several datasets have: the beat's context decides, else it is an error (never a guess)

Catalog("apollo11") is the old single-pack view: the same library, with Apollo 11 as the default context (bare names that
only Apollo 11 can mean still resolve, everything else is unknown)."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .datasets import Dataset, DatasetIndex, Event, default_index, norm, split_qualified
from .temporal import iso, parse_iso

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "catalog"
PACKS = HERE / "packs"
_EVENT_EXPR = re.compile(r"^(.+?)([+-])(\d+):(\d\d)(?::(\d\d))?$")
_MET = re.compile(r"^t([+-])(\d+):(\d\d)(?::(\d\d))?$")
NOW_WORDS = ("now", "today")


class CatalogError(ValueError):
    pass


_norm = norm


def available_packs() -> List[str]:
    """Every dataset in the shipped library (the name is historical: they are no longer chosen, they are found)."""
    return sorted(default_index().datasets)


def base_body_ids() -> Set[str]:
    return {b["id"] for b in json.loads((CATALOG / "bodies.json").read_text(encoding="utf-8"))["world"]}


@dataclass
class Place:
    """A camera target or a marker position. kind: body | site | pair."""
    kind: str
    body: str                      # the body (for a pair: the first)
    ref: str                       # the engine's target string: "moon", "moon@23.473,0.674", "earth+moon"
    label: str = ""
    lon: Optional[float] = None
    lat: Optional[float] = None
    other: str = ""                # a pair's second body
    dataset: str = ""              # the dataset the place came from (a dataset's own site or body), else ""


@dataclass
class DateInfo:
    """A resolved date expression: the UTC moment, and what it came from (an event carries its status and precision)."""
    utc: str
    kind: str                      # iso | event | mission_time | now
    event: Optional[Event] = None
    dataset: str = ""
    precision: str = "minute"
    net: bool = False


class Catalog:
    def __init__(self, pack: Optional[str] = None, pack_data: Optional[Dict[str, Any]] = None, *, index: Optional[DatasetIndex] = None):
        self.bodies = json.loads((CATALOG / "bodies.json").read_text(encoding="utf-8"))
        self.base_world: List[Dict[str, Any]] = self.bodies["world"]
        self.body_ids = {b["id"] for b in self.base_world}
        self.aliases = {**{i: i for i in self.body_ids}, **{norm(k): v for k, v in self.bodies.get("aliases", {}).items()}}
        self.sites: Dict[str, Dict[str, Any]] = {}
        self._site_alias: Dict[str, str] = {}
        for name, s in json.loads((CATALOG / "sites.json").read_text(encoding="utf-8"))["sites"].items():
            key = norm(name)
            self.sites[key] = s
            for a in [key] + [norm(x) for x in s.get("aliases", [])]:
                self._site_alias[a] = key
        if pack_data is not None:                              # a pack given as data (tests, tools): a one-dataset library
            import tempfile

            tmp = Path(tempfile.mkdtemp(prefix="starmap_pack_"))
            (tmp / f"{norm(pack_data['id'])}.json").write_text(json.dumps(pack_data), encoding="utf-8")
            index = DatasetIndex([tmp], base_body_ids=self.body_ids)
            pack = pack or pack_data["id"]
        self.index = index or default_index()
        self.default: Optional[str] = None
        if pack:
            ds = self.index.get(pack)
            if ds is None:
                bad = next((p for p in self.index.problems if p.startswith(f"dataset {norm(pack)}")), "")
                raise CatalogError(f"unknown dataset {pack!r}" + (f": {bad}" if bad else f" (datasets: {', '.join(sorted(self.index.datasets)) or 'none'})"))
            self.default = ds.id
        self.used: Set[str] = set()                            # datasets the compiled video draws on (for its world and credits)

    # ---- the library -------------------------------------------------------------------------------------------------
    def dataset(self, did: str) -> Dataset:
        ds = self.index.get(did)
        if ds is None:
            raise CatalogError(f"unknown dataset {did!r}" + self._suggest(norm(did), list(self.index.datasets)))
        return ds

    @property
    def pack(self) -> Dict[str, Any]:
        """The default dataset's data (the old single-pack view); {} without one."""
        return self.index.datasets[self.default].data if self.default else {}

    @property
    def events(self) -> Dict[str, str]:
        return {k: e.utc for k, e in self.index.datasets[self.default].events.items()} if self.default else {}

    @property
    def world(self) -> List[Dict[str, Any]]:
        """The engine's world: the base bodies and the extra bodies of every dataset the video uses."""
        extra = [b for did in sorted(self.used) for b in self.index.datasets[did].world]
        return self.base_world + extra

    @property
    def trajectories(self) -> Dict[str, Dict[str, Any]]:
        return {tid: t.data for tid, t in self.index.trajectories.items()}

    def _ctx(self, ctx: Sequence[str]) -> List[str]:
        out = [norm(c) for c in ctx if c]
        if not out and self.default:
            out = [self.default]
        return out

    def lookup(self, kind: str, name: str, ctx: Sequence[str] = ()) -> Tuple[str, Any]:
        """A craft / path / orbit / event / site / body name -> (qualified id, its data). Ambiguity and unknown names raise."""
        raw = str(name).strip()
        q = split_qualified(raw)
        if q and q[0] in self.index.datasets:
            ds = self.index.datasets[q[0]]
            table = self.index.table(ds, kind)
            key = q[1]
            if kind == "craft" and key in ds.craft_aliases:
                key = ds.craft_aliases[key]
            if key not in table:
                raise CatalogError(f"invalid qualified id {raw!r}: dataset {ds.id} has no {kind} {q[1]!r}"
                                   + self._suggest(key, list(table)))
            return f"{ds.id}.{key}", table[key]
        if q and q[0] not in self.index.datasets and kind != "site":
            raise CatalogError(f"unknown dataset {q[0]!r} in {raw!r}" + self._suggest(q[0], list(self.index.datasets)))
        cands = self.index.candidates(kind, raw)
        if self.default and not ctx:
            cands = {c for c in cands if c.split(".", 1)[0] == self.default} or (cands if kind in ("site", "body") else set())
        if not cands:
            pool = [n for n in self.index.all_names(kind)]
            raise CatalogError(f"unknown {kind} {raw!r}" + (self._suggest(norm(raw), pool) if pool else f" (no dataset has a {kind})"))
        within = {c for c in cands if c.split(".", 1)[0] in self._ctx(ctx)}
        pick = within if within else cands
        if len(pick) > 1 and kind == "site" and self.index.same_site(pick):
            pick = {sorted(pick)[0]}
        if len(pick) > 1:
            raise CatalogError(f"{raw!r} is ambiguous: use {' or '.join(sorted(pick))}")
        qid = next(iter(pick))
        did, key = qid.split(".", 1)
        return qid, self.index.table(self.index.datasets[did], kind)[key]

    # ---- places -------------------------------------------------------------------------------------------------
    def place(self, name: str, ctx: Sequence[str] = ()) -> Place:
        """A body ("moon"), a pair ("earth+moon"), a site ("tranquility base", "apollo13.fra mauro"), body@lon,lat
        ("moon@23.47,0.67"), or a body a dataset adds (an asteroid, a comet)."""
        raw = str(name).strip()
        key = norm(raw)
        if not key:
            raise CatalogError("no place given")
        if "+" in key:
            a, b = [self.body(x, ctx) for x in key.split("+", 1)]
            return Place("pair", a, f"{a}+{b}", other=b, dataset=self._body_dataset(a) or self._body_dataset(b))
        if "@" in key:
            body, at = key.split("@", 1)
            body = self.body(body, ctx)
            try:
                lon, lat = [float(x) for x in at.split(",")]
            except ValueError:
                raise CatalogError(f"{raw!r}: write body@longitude,latitude in degrees, e.g. moon@23.47,0.67") from None
            if not (-180 <= lon <= 360 and -90 <= lat <= 90):
                raise CatalogError(f"{raw!r}: longitude must be -180..360 and latitude -90..90")
            return Place("site", body, f"{body}@{lon},{lat}", lon=lon, lat=lat, dataset=self._body_dataset(body))
        if key in self.aliases:
            b = self.aliases[key]
            return Place("body", b, b, label=self._body_label(b))
        body = self._dataset_body(raw, ctx)
        if body is not None:
            return body
        q = split_qualified(raw)
        in_ctx = self.index.candidates("site", raw)
        if (q and q[0] in self.index.datasets) or (key not in self._site_alias and in_ctx) or \
                (in_ctx and {c.split(".", 1)[0] for c in in_ctx} & set(self._ctx(ctx))):
            qid, s = self.lookup("site", raw, ctx)
            return Place("site", s["body"], f"{s['body']}@{s['lon']},{s['lat']}", label=s.get("label", raw.upper()), lon=s["lon"], lat=s["lat"],
                         dataset=qid.split(".", 1)[0])
        if key in self._site_alias:
            s = self.sites[self._site_alias[key]]
            return Place("site", s["body"], f"{s['body']}@{s['lon']},{s['lat']}", label=s.get("label", raw.upper()), lon=s["lon"], lat=s["lat"])
        pool = list(self.aliases) + list(self._site_alias) + self.index.all_names("site") + self.index.all_names("body")
        raise CatalogError(f"unknown place {raw!r}" + self._suggest(key, pool))

    def _dataset_body(self, raw: str, ctx: Sequence[str]) -> Optional[Place]:
        if not self.index.candidates("body", raw) and not (split_qualified(raw) and split_qualified(raw)[0] in self.index.datasets
                                                             and split_qualified(raw)[1] in {b["id"] for b in self.index.datasets[split_qualified(raw)[0]].world}):
            return None
        qid, b = self.lookup("body", raw, ctx)
        return Place("body", b["id"], b["id"], label=b.get("label", b["id"].upper()), dataset=qid.split(".", 1)[0])

    def _body_dataset(self, body: str) -> str:
        return self.index.body_owner.get(body, "")

    def body(self, name: str, ctx: Sequence[str] = ()) -> str:
        key = norm(name)
        if key in self.aliases:
            return self.aliases[key]
        p = self._dataset_body(name, ctx)
        if p is not None:
            return p.body
        raise CatalogError(f"unknown body {name!r}" + self._suggest(key, list(self.aliases) + self.index.all_names("body")))

    def _body_label(self, b: str) -> str:
        return next((x.get("label", b.upper()) for x in self.world if x["id"] == b), b.upper())

    def body_radius_km(self, b: str) -> float:
        r = next((x for x in self.base_world + [w for d in self.index.datasets.values() for w in d.world] if x["id"] == b))["radius"]
        return float(r.get("km") or 0) or float(r.get("ly", 0)) * 9.4607e12

    # ---- dates ------------------------------------------------------------------------------------------------------
    def date_info(self, expr: str, ctx: Sequence[str] = (), now: Optional[str] = None) -> DateInfo:
        """A date expression -> DateInfo. Forms: an ISO date; now / today (the project's reference date); an event
        (landing, apollo11.landing); an event +/- HH:MM[:SS] (landing-00:12:40); mission time T+HHH:MM[:SS] or T-...
        (apollo11.T+102:45:40), counted from the context dataset's met_zero."""
        raw = str(expr).strip()
        e = norm(raw).replace(" ", "")
        if e in NOW_WORDS:
            if not now:
                raise CatalogError(f"{raw!r} needs the project's reference date (the plan row's date, or the date set by Check plan)")
            return DateInfo(now, "now", precision="day")
        q = split_qualified(e)
        scoped, rest = (q[0], q[1]) if q and q[0] in self.index.datasets else (None, e)
        m = _MET.fullmatch(rest)
        if m:
            dids = [scoped] if scoped else self._ctx(ctx)
            zeros = [d for d in dids if self.index.datasets[d].met_zero]
            if len(zeros) != 1:
                raise CatalogError(f"invalid mission clock {raw!r}: mission time needs one dataset with a met_zero in this beat's context"
                                   + (f" (it has {', '.join(dids)})" if dids else " (write it qualified, e.g. apollo11.T+102:45:40)"))
            ds = self.index.datasets[zeros[0]]
            d = timedelta(hours=int(m[2]), minutes=int(m[3]), seconds=int(m[4] or 0))
            t = parse_iso(ds.met_zero) + (d if m[1] == "+" else -d)
            return DateInfo(iso(t), "mission_time", dataset=ds.id, precision=ds.precision if ds.status != "historical" else "second")
        m = _EVENT_EXPR.fullmatch(rest)
        name, delta = (m[1], timedelta(hours=int(m[3]), minutes=int(m[4]), seconds=int(m[5] or 0)) * (1 if m[2] == "+" else -1)) if m else (rest, None)
        try:
            return DateInfo(iso(parse_iso(raw)), "iso")
        except ValueError:
            pass
        try:
            qid, ev = self.lookup("event", f"{scoped}.{name}" if scoped else name, ctx)
        except CatalogError as exc:
            if "ambiguous" in str(exc) or (scoped and "invalid qualified" in str(exc)):
                raise
            known = ", ".join(sorted(self.index.all_names("event"))[:12]) or "none"
            raise CatalogError(f"unknown date {raw!r}: use an event (e.g. {known}), an event+HH:MM, T+HHH:MM:SS, now, "
                               f"or an ISO date like 1969-07-20T20:17:40Z" + self._suggest(norm(name), self.index.all_names("event"))) from None
        t = parse_iso(ev.utc) + (delta or timedelta())
        return DateInfo(iso(t), "event", event=ev, dataset=ev.dataset, precision=ev.precision, net=ev.net)

    def date(self, expr: str, ctx: Sequence[str] = (), now: Optional[str] = None) -> str:
        return self.date_info(expr, ctx, now).utc

    # ---- craft, paths, orbits ---------------------------------------------------------------------------------------
    def craft_id(self, name: str, ctx: Sequence[str] = ()) -> str:
        return self.lookup("craft", name, ctx)[0]

    def craft(self, qid: str) -> Dict[str, Any]:
        did, key = qid.split(".", 1)
        return self.index.datasets[did].craft[key]

    def path(self, name: str, ctx: Sequence[str] = ()) -> Dict[str, Any]:
        return self.lookup("path", name, ctx)[1]

    def orbit(self, name: str, ctx: Sequence[str] = ()) -> Dict[str, Any]:
        return self.lookup("orbit", name, ctx)[1]

    @staticmethod
    def _suggest(key: str, options: List[str]) -> str:
        near = difflib.get_close_matches(key, options, n=3, cutoff=0.6)
        return f" (did you mean {', '.join(repr(n) for n in near)}?)" if near else ""


def _parse_iso(s: str):
    return parse_iso(s)


def _iso(t) -> str:
    return iso(t)


def iso_seconds(a: str, b: str) -> float:
    """Seconds from date a to date b."""
    return (parse_iso(b) - parse_iso(a)).total_seconds()


def place_pair(p: Place) -> Tuple[str, str]:
    return p.body, p.other
