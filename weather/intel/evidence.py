"""The Weather Evidence Model: verified facts with their provenance, and every source request the engine made.

A Fact is one thing the engine knows from a source (a storm's identity, a best-track peak, the number of tornado reports in a
state on a convective day, a river crest). Its `kind` keeps categories apart that must never be presented as interchangeable:

    identity            who / what the event is (an NHC storm record)
    best_track          NHC's analysed (historical) track and intensity
    forecast            an advisory, an outlook: what was predicted at its issue time
    warning             an official NWS warning (polygon, issue time)
    preliminary_report  SPC storm reports (not survey results)
    observed            a measurement (station rainfall, river stage, radar scan time)
    estimate            a remote-sensing estimate (MRMS radar rainfall)
    official_record     a published record or category (ACIS ranking, NWS flood categories)
    derived             computed by the engine from other facts (method and inputs recorded)

The renderer never reads this file: it renders from resolved.json (the data snapshot the facts came from). evidence.json is the
reproducible record of what was found, when, and from where — and of what could not be found and why."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

EVIDENCE_VERSION = 1
KINDS = ("identity", "best_track", "forecast", "warning", "preliminary_report", "observed", "estimate", "official_record", "derived")
STATUSES = ("ok", "cached", "unavailable", "temporary", "malformed", "skipped", "ambiguous")


@dataclass
class Fact:
    id: str
    kind: str
    subject: str  # the event / hazard ("Hurricane Ian", "tornado reports, SC")
    what: str  # the measurement ("peak sustained wind", "count", "crest stage")
    value: Any
    unit: str = ""
    where: str = ""
    source: str = ""  # weather.intel.sources id
    record: str = ""  # URL or record id
    retrieved: str = ""
    issued: str = ""  # issue or observation time
    valid: str = ""  # valid period ("2026-10-10T12:00Z..2026-10-11T12:00Z")
    timeframe: str = "historical"  # historical | current | forecast
    quality: str = "final"  # final | preliminary | provisional | estimate | unverified
    caveats: List[str] = field(default_factory=list)
    derived_from: List[str] = field(default_factory=list)
    method: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"fact kind {self.kind!r} is not one of {', '.join(KINDS)}")


@dataclass
class Attempt:
    source: str
    request: str  # the URL or data_source asked for
    purpose: str
    status: str  # ok | cached | unavailable | temporary | malformed | skipped | ambiguous
    detail: str = ""
    at: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"attempt status {self.status!r} is not one of {', '.join(STATUSES)}")


@dataclass
class Evidence:
    event: Dict[str, Any] = field(default_factory=dict)
    facts: List[Fact] = field(default_factory=list)
    attempts: List[Attempt] = field(default_factory=list)
    created: str = ""

    def add(self, **kw: Any) -> Fact:
        kw.setdefault("id", f"f{len(self.facts) + 1}")
        f = Fact(**kw)
        self.facts.append(f)
        return f

    def tried(self, source: str, request: str, purpose: str, status: str, detail: str = "", now: Optional[datetime] = None) -> Attempt:
        a = Attempt(source, request, purpose, status, detail, _iso(now or datetime.now(timezone.utc)))
        self.attempts.append(a)
        return a

    def find(self, what: str, subject_has: str = "") -> Optional[Fact]:
        for f in self.facts:
            if f.what == what and subject_has.lower() in f.subject.lower():
                return f
        return None

    def failed(self) -> List[Attempt]:
        return [a for a in self.attempts if a.status not in ("ok", "cached", "skipped")]

    def to_json(self) -> str:
        return json.dumps({"version": EVIDENCE_VERSION, "created": self.created, "event": self.event,
                           "facts": [asdict(f) for f in self.facts], "attempts": [asdict(a) for a in self.attempts]},
                          indent=1, ensure_ascii=False, default=str)

    @staticmethod
    def from_json(text: str) -> "Evidence":
        d = json.loads(text)
        if d.get("version") != EVIDENCE_VERSION:
            raise ValueError(f"evidence.json is version {d.get('version')}, this Weather reads {EVIDENCE_VERSION}")
        return Evidence(d.get("event", {}), [Fact(**f) for f in d.get("facts", [])], [Attempt(**a) for a in d.get("attempts", [])],
                        d.get("created", ""))


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_error(exc: BaseException) -> str:
    """unavailable (the archive answered: it does not hold this), temporary (network / server trouble: try again), malformed."""
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        return "temporary" if exc.code >= 500 or exc.code == 429 else "unavailable"
    text = str(exc)
    if any(f"HTTP {c}" in text for c in ("404", "410", "403", "400")):
        return "unavailable"
    if any(s in text for s in ("HTTP 5", "HTTP 429", "timed out", "Timeout", "URLError", "Connection", "could not be fetched (",
                               "Temporary failure", "Name or service", "nodename")):
        return "temporary"
    if isinstance(exc, (KeyError, IndexError)) or "not in" in text or "has no" in text or "no " in text[:40].lower():
        return "unavailable"
    return "malformed"
