"""The dataset library: every JSON file in starmap/packs/ (and any extra folder given) is a dataset, found automatically. Adding
a mission, a spacecraft, a telescope, a planned flight or a hypothetical base is adding a file; nothing here or in the renderer
names one.

A dataset (every field but id and name is optional; the six original mission packs are valid datasets as they are):

    { "id": "artemis3", "name": "Artemis III", "names": ["artemis 3"],             names the narration may use
      "kind": "crewed_mission",                                                     informational (orbiter, rover, telescope ...)
      "temporal": { "status": "planned", "as_of": "2026-06-01", "source": "NASA reference mission",
                    "date_precision": "month", "basis": "modelled" },              dataset defaults
      "met_zero": "2027-09-15T12:00:00Z",                                           mission time T+0 (T- before it)
      "events": { "launch": "2027-09-15T12:00:00Z",                                 a plain date: the dataset's status
                  "landing": { "utc": "...", "status": "planned", "net": true, "precision": "month" } },
      "sites": {...}, "craft": {...}, "craft_aliases": {...}, "paths": {...}, "orbits": {...},
      "trajectories": [ { "id": "artemis3_orion", "basis": "modelled", "status": "planned",
                          "observed_until": "...", "extrapolate": { "rule": "linear", "max_days": 3650 }, ... } ],
      "world": [ extra bodies for the engine's world, e.g. an asteroid ] }

Defaults where a dataset says nothing: status historical; a trajectory's basis "illustrated" when its source is "illustrated"
(the six mission packs), else the dataset's temporal.basis; precision "second" for events. A trajectory with no basis at all
is a problem (its geometry would be shown without saying how it is known).

Qualified ids are <dataset id>.<name>: apollo11.csm, apollo11.landing, artemis1.outbound_coast, apollo13.fra mauro.
Trajectory ids stay as written and must be unique across the whole library (the engine attaches craft to them by id)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .temporal import TemporalError, check_basis, check_precision, check_status, parse_iso, iso

HERE = Path(__file__).resolve().parent
DEFAULT_DIRS = (HERE / "packs",)
_QUALIFIED = re.compile(r"^([a-z0-9_]+)\.(.+)$")
_WORDS = re.compile(r"[^0-9A-Za-z_'’ -]+")
KINDS = ("craft", "path", "orbit", "event", "site", "body", "dataset")


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower().replace("’", "'"))


def split_qualified(name: str) -> Optional[Tuple[str, str]]:
    """"apollo11.lm" -> ("apollo11", "lm"); None for a bare name."""
    m = _QUALIFIED.match(norm(name))
    return (m.group(1), m.group(2)) if m else None


@dataclass
class Event:
    qid: str
    dataset: str
    name: str
    utc: str
    status: str
    precision: str = "second"
    net: bool = False
    note: str = ""


@dataclass
class Trajectory:
    id: str
    dataset: str
    basis: str
    status: str
    data: Dict[str, Any]
    observed_until: Optional[str] = None
    extrapolate: Optional[Dict[str, Any]] = None
    start: Optional[str] = None
    end: Optional[str] = None


@dataclass
class Dataset:
    id: str
    name: str
    file: Path
    data: Dict[str, Any]
    names: List[str] = field(default_factory=list)
    kind: str = ""
    status: str = "historical"
    basis: Optional[str] = None
    as_of: Optional[str] = None
    source: str = ""
    precision: str = "second"
    met_zero: Optional[str] = None
    events: Dict[str, Event] = field(default_factory=dict)            # by bare name
    craft: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    craft_aliases: Dict[str, str] = field(default_factory=dict)
    paths: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    orbits: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    sites: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    trajectories: Dict[str, Trajectory] = field(default_factory=dict)
    world: List[Dict[str, Any]] = field(default_factory=list)
    fixture: bool = False

    def q(self, name: str) -> str:
        return f"{self.id}.{norm(name)}"

    @property
    def years(self) -> Tuple[Optional[int], Optional[int]]:
        ys = sorted(parse_iso(e.utc).year for e in self.events.values())
        return (ys[0], ys[-1]) if ys else (None, None)


class DatasetIndex:
    """Every dataset found in the folders, indexed: qualified tables, aliases (unique or ambiguous), names for the narration.
    problems: datasets that could not be loaded or are inconsistent (they are left out, with the reason)."""

    def __init__(self, dirs: Optional[Sequence[Path]] = None, *, base_body_ids: Iterable[str] = ()):
        self.dirs = [Path(d) for d in (dirs if dirs is not None else DEFAULT_DIRS)]
        self.base_body_ids: Set[str] = set(base_body_ids)
        self.datasets: Dict[str, Dataset] = {}
        self.problems: List[str] = []
        self.aliases: Dict[str, Dict[str, Set[str]]] = {k: {} for k in KINDS}
        self.trajectories: Dict[str, Trajectory] = {}
        self.body_owner: Dict[str, str] = {}
        for d in self.dirs:
            for f in sorted(d.glob("*.json")) if d.is_dir() else []:
                self._load(f)
        self._build_aliases()

    # ---- loading -----------------------------------------------------------------------------------------------------
    def _load(self, f: Path) -> None:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.problems.append(f"dataset {f.name}: not readable JSON ({exc})")
            return
        if not isinstance(data, dict) or not data.get("id") or not data.get("name"):
            self.problems.append(f"dataset {f.name}: needs an id and a name")
            return
        did = norm(data["id"])
        if not re.fullmatch(r"[a-z0-9_]+", did):
            self.problems.append(f"dataset {f.name}: id {data['id']!r} may use only a-z, 0-9 and _")
            return
        if did in self.datasets:
            self.problems.append(f"dataset {f.name}: id {did!r} is already used by {self.datasets[did].file.name}")
            return
        try:
            ds = self._parse(did, f, data)
        except (TemporalError, ValueError, KeyError, TypeError) as exc:
            self.problems.append(f"dataset {did} ({f.name}): {exc}")
            return
        clash = [t for t in ds.trajectories if t in self.trajectories]
        if clash:
            self.problems.append(f"dataset {did}: trajectory id {clash[0]!r} is already used by dataset {self.trajectories[clash[0]].dataset}")
            return
        bodies = [b["id"] for b in ds.world]
        taken = [b for b in bodies if b in self.base_body_ids or b in self.body_owner]
        if taken:
            self.problems.append(f"dataset {did}: body {taken[0]!r} already exists")
            return
        self.datasets[did] = ds
        self.trajectories.update(ds.trajectories)
        for b in bodies:
            self.body_owner[b] = did

    def _parse(self, did: str, f: Path, data: Dict[str, Any]) -> Dataset:
        tem = data.get("temporal") or {}
        status = check_status(tem.get("status", "historical"), "temporal")
        basis = check_basis(tem["basis"], "temporal") if tem.get("basis") else None
        precision = check_precision(tem.get("date_precision", "second"), "temporal")
        as_of = iso(parse_iso(tem["as_of"] + ("T00:00:00Z" if len(str(tem["as_of"])) == 10 else ""))) if tem.get("as_of") else None
        ds = Dataset(id=did, name=str(data["name"]), file=f, data=data, names=[norm(x) for x in data.get("names", [])], kind=str(data.get("kind", "")),
                     status=status, basis=basis, as_of=as_of, source=str(tem.get("source") or data.get("source") or ""), precision=precision,
                     met_zero=iso(parse_iso(data["met_zero"])) if data.get("met_zero") else None, fixture=bool(data.get("_fixture")))
        for name, v in (data.get("events") or {}).items():
            if isinstance(v, str):
                ev = Event(ds.q(name), did, norm(name), iso(parse_iso(v)), status, precision)
            else:
                ev = Event(ds.q(name), did, norm(name), iso(parse_iso(v["utc"])), check_status(v.get("status", status), f"event {name}"),
                           check_precision(v.get("precision", precision), f"event {name}"), bool(v.get("net")), str(v.get("note", "")))
            ds.events[norm(name)] = ev
        ds.craft = {norm(k): v for k, v in (data.get("craft") or {}).items()}
        ds.craft_aliases = {norm(k): norm(v) for k, v in (data.get("craft_aliases") or {}).items()}
        for a, c in ds.craft_aliases.items():
            if c not in ds.craft:
                raise ValueError(f"craft alias {a!r} names unknown craft {c!r}")
        ds.paths = {norm(k): v for k, v in (data.get("paths") or {}).items()}
        ds.orbits = {norm(k): v for k, v in (data.get("orbits") or {}).items()}
        ds.sites = {norm(k): v for k, v in (data.get("sites") or {}).items()}
        for t in data.get("trajectories") or []:
            tid = t["id"]
            b = t.get("basis") or ("illustrated" if t.get("source") == "illustrated" else basis)
            if not b:
                raise ValueError(f"trajectory {tid}: no basis (observed, modelled, illustrated or illustrative): say how its geometry is known")
            ext = t.get("extrapolate")
            if ext is not None and (ext.get("rule") != "linear" or not isinstance(ext.get("max_days"), (int, float))):
                raise ValueError(f"trajectory {tid}: extrapolate must be {{\"rule\": \"linear\", \"max_days\": N}}")
            times = _trajectory_times(t)
            ds.trajectories[tid] = Trajectory(tid, did, check_basis(b, f"trajectory {tid}"), check_status(t.get("status", status), f"trajectory {tid}"),
                                              t, iso(parse_iso(t["observed_until"])) if t.get("observed_until") else None, ext,
                                              times[0] if times else None, times[-1] if times else None)
        for name, c in ds.craft.items():
            if c.get("trajectory") and c["trajectory"] not in ds.trajectories:
                raise ValueError(f"craft {name}: trajectory {c['trajectory']!r} is not in this dataset")
        for kind, table in (("path", ds.paths), ("orbit", ds.orbits)):
            for name, v in table.items():
                tid = v.get("of") if kind == "path" else v.get("trajectory")
                if tid not in ds.trajectories:
                    raise ValueError(f"{kind} {name}: trajectory {tid!r} is not in this dataset")
        ds.world = list(data.get("world") or [])
        for b in ds.world:
            if not b.get("id"):
                raise ValueError("every world body needs an id")
        return ds

    def _build_aliases(self) -> None:
        def add(kind: str, alias: str, qid: str) -> None:
            self.aliases[kind].setdefault(norm(alias), set()).add(qid)

        for ds in self.datasets.values():
            add("dataset", ds.id, ds.id)
            add("dataset", ds.name, ds.id)
            for n in ds.names:
                add("dataset", n, ds.id)
            for c in ds.craft:
                add("craft", c, ds.q(c))
            for a, c in ds.craft_aliases.items():
                add("craft", a, ds.q(c))
            for p in ds.paths:
                add("path", p, ds.q(p))
            for o in ds.orbits:
                add("orbit", o, ds.q(o))
            for e in ds.events:
                add("event", e, ds.q(e))
            for s, v in ds.sites.items():
                add("site", s, ds.q(s))
                for a in v.get("aliases", []):
                    add("site", a, ds.q(s))
            for b in ds.world:
                add("body", b["id"], f"{ds.id}.{b['id']}")
                for a in b.get("aliases", []):
                    add("body", a, f"{ds.id}.{b['id']}")

    # ---- lookups ----------------------------------------------------------------------------------------------------
    def get(self, did: str) -> Optional[Dataset]:
        return self.datasets.get(norm(did))

    def table(self, ds: Dataset, kind: str) -> Dict[str, Any]:
        return {"craft": ds.craft, "path": ds.paths, "orbit": ds.orbits, "event": ds.events, "site": ds.sites,
                "body": {b["id"]: b for b in ds.world}}[kind]

    def candidates(self, kind: str, name: str) -> Set[str]:
        """Qualified ids a bare name may mean (its own name or an alias), in every dataset."""
        return set(self.aliases[kind].get(norm(name), set()))

    def all_names(self, kind: str) -> List[str]:
        return sorted(self.aliases[kind])

    def same_site(self, qids: Set[str]) -> bool:
        """Several datasets naming one place the same way (Apollo 8, 11 and 13 all have Launch Complex 39A) is not ambiguity."""
        spots = set()
        for q in qids:
            did, name = q.split(".", 1)
            s = self.datasets[did].sites[name]
            spots.add((s["body"], round(float(s["lon"]), 3), round(float(s["lat"]), 3)))
        return len(spots) == 1

    def narration_matches(self, text: str) -> List[str]:
        """Datasets whose name (or one of its names) is said, as whole words, in a piece of narration (a limited fallback)."""
        t = f" {norm(_WORDS.sub(' ', text))} "
        hits = []
        for ds in self.datasets.values():
            for n in [norm(ds.name)] + ds.names:
                if n and f" {n} " in t:
                    hits.append(ds.id)
                    break
        return sorted(set(hits))


def _trajectory_times(t: Dict[str, Any]) -> List[str]:
    out = []
    for s in t.get("samples") or []:
        out.append(iso(parse_iso(s["utc"])))
    for g in t.get("generate") or []:
        for k in ("from_utc", "to_utc"):
            if g.get(k):
                out.append(iso(parse_iso(g[k])))
    return sorted(out)


_DEFAULT: Optional[DatasetIndex] = None


def default_index() -> DatasetIndex:
    """The shipped library (starmap/packs), loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        from .catalog import base_body_ids

        _DEFAULT = DatasetIndex(base_body_ids=base_body_ids())
    return _DEFAULT
