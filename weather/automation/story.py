"""The day's lead story, by fixed rules (no judgement, no randomness): the first of these that the data shows wins.

    1. tropical      hurricane, tropical storm or storm surge warnings/watches over land
    2. severe        a severe weather outbreak: 3+ tornado warnings, or 2+ tornado / severe thunderstorm watches, or 10+ severe
                     thunderstorm warnings
    3. extreme_temp  an extreme heat or cold warning over a covered city or 3+ of them nationally, or highs of 100°F or more /
                     lows of 10°F or less in 3+ covered cities on the day
    4. heavy_rain    a flash flood warning, 2+ flood watches, a flood watch or warning over a covered city, or rain at 70 % or
                     more in 3+ covered cities on the day
    5. routine       the covered city with the most to say: the highest chance of rain, else the biggest swing in its highs

Only alerts over the lower 48 count (the video's map is the lower 48). Story.why says, in plain words, what each rule saw and
which one decided."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from ..resolve import Snapshot
from .coverage import Metro, metros
from .fetch import day_date, distance_km, national_alerts, target_date

NOT_LOWER48 = {"AK", "HI", "PR"}
TROPICAL = ("Hurricane Warning", "Hurricane Watch", "Tropical Storm Warning", "Tropical Storm Watch", "Storm Surge Warning",
            "Storm Surge Watch", "Extreme Wind Warning")
SEVERE = ("Tornado Warning", "Tornado Watch", "Severe Thunderstorm Warning", "Severe Thunderstorm Watch")
HEAT = ("Extreme Heat Warning", "Excessive Heat Warning")
COLD = ("Extreme Cold Warning", "Wind Chill Warning")
FLOOD_WATCH = ("Flood Watch", "Flash Flood Watch")
FLOOD = ("Flash Flood Warning", "Flood Warning") + FLOOD_WATCH
KINDS = ("tropical", "severe", "extreme_temp", "heavy_rain", "routine")
HOT_F, COLD_F, SEVERAL = 100, 10, 3
RAIN_POP = 70


@dataclass
class Story:
    kind: str  # one of KINDS
    lead_city: str  # the covered city the video spends the most time on ("Phoenix, AZ")
    on: date  # the day the forecast is for
    alerts: List[Dict[str, Any]] = field(default_factory=list)  # the story's alerts (national summaries), over the lower 48
    events: List[str] = field(default_factory=list)  # their event names, most common first
    states: List[str] = field(default_factory=list)  # their states, most alerts first
    cities: List[str] = field(default_factory=list)  # covered cities in the story (under its alerts, or past its thresholds)
    why: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "lead_city": self.lead_city, "on": self.on.isoformat(), "events": self.events, "states": self.states,
                "cities": self.cities, "alerts": [a["id"] for a in self.alerts], "why": self.why}

    @property
    def why_text(self) -> str:
        return "\n".join(f"- {w}" for w in self.why)


def _lower48(a: Dict[str, Any]) -> bool:
    return a.get("land") and any(s not in NOT_LOWER48 for s in a.get("states", []))


def _day(snap: Snapshot, key: str, on: date) -> Optional[Dict[str, Any]]:
    for d in snap.forecasts.get(key, {}).get("days", []):
        if day_date(d) == on:
            return d
    return None


def _pop(d: Dict[str, Any]) -> int:
    return max([p["value"] for p in (d.get("pop"), d.get("pop_night")) if p] or [0])


def _wet(d: Dict[str, Any]) -> bool:
    return d.get("icon") in ("rain", "storm", "snow", "sleet")


def _states_of(alerts: Sequence[Dict[str, Any]]) -> List[str]:
    c = Counter(s for a in alerts for s in a["states"] if s not in NOT_LOWER48)
    return [s for s, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]


def _events_of(alerts: Sequence[Dict[str, Any]]) -> List[str]:
    c = Counter(a["event"] for a in alerts)
    return [e for e, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]


def _lead_for(alerts: Sequence[Dict[str, Any]], covered: Sequence[Metro]) -> str:
    """The covered city under the most of these alerts; else the one nearest their middle; ties go to the bigger metro."""
    hits = Counter(k for a in alerts for k in a.get("metros", []))
    ranked = [m for m in covered if hits.get(m.key)]
    if ranked:
        return max(ranked, key=lambda m: (hits[m.key], -m.rank)).key
    cs = [a["centre"] for a in alerts if a.get("centre")]
    if not cs:
        return covered[0].key
    mid = (sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs))
    return min(covered, key=lambda m: (round(distance_km(mid, (m.city.lat, m.city.lon))), m.rank)).key


def _list(items: Sequence[str]) -> str:
    return ", ".join(items) if items else "none"


def pick_story(snap: Snapshot, covered: Optional[Sequence[Metro]] = None) -> Story:
    covered = [m for m in (covered if covered is not None else metros()) if m.key in snap.forecasts]
    if not covered:
        raise ValueError("the snapshot has no forecast for any covered city")
    on = target_date(snap)
    land = [a for a in national_alerts(snap) if _lower48(a)]
    why: List[str] = [f"The forecast is for {on.strftime('%A, %B')} {on.day} ({len(covered)} cities, {len(land)} alerts over the lower 48)."]

    def story(kind: str, alerts: Sequence[Dict[str, Any]], lead: str, cities: Sequence[str], reason: str) -> Story:
        why.append(f"Lead: {reason}")
        return Story(kind, lead, on, list(alerts), _events_of(alerts), _states_of(alerts), list(cities), why)

    # 1. tropical
    trop = [a for a in land if a["event"] in TROPICAL]
    if trop:
        return story("tropical", trop, _lead_for(trop, covered), sorted({k for a in trop for k in a["metros"]}),
                     f"tropical alerts over land ({_list(_events_of(trop))}) in {_list(_states_of(trop))}; this rule comes first.")
    why.append("Tropical: no hurricane, tropical storm or storm surge alerts over land.")

    # 2. severe outbreak
    sev = [a for a in land if a["event"] in SEVERE]
    n = Counter(a["event"] for a in sev)
    tw, ta, sw, sa = n["Tornado Warning"], n["Tornado Watch"], n["Severe Thunderstorm Warning"], n["Severe Thunderstorm Watch"]
    counts = f"{tw} tornado warning(s), {ta} tornado watch(es), {sw} severe thunderstorm warning(s), {sa} severe thunderstorm watch(es)"
    if tw >= 3 or ta + sa >= 2 or sw >= 10:
        return story("severe", sev, _lead_for(sev, covered), sorted({k for a in sev for k in a["metros"]}),
                     f"a severe weather outbreak: {counts} in {_list(_states_of(sev))}.")
    why.append(f"Severe: {counts}; not an outbreak (needs 3 tornado warnings, 2 watches or 10 severe thunderstorm warnings).")

    # 3. extreme heat or cold
    hc = [a for a in land if a["event"] in HEAT + COLD]
    hot, cold = [], []
    for m in covered:
        d = _day(snap, m.key, on)
        if d is None:
            continue
        if d["high"]["value"] >= HOT_F:
            hot.append(m.key)
        if d.get("low") and d["low"]["value"] <= COLD_F:
            cold.append(m.key)
    over_city = sorted({k for a in hc for k in a["metros"]})
    if over_city or len(hc) >= SEVERAL or len(hot) >= SEVERAL or len(cold) >= SEVERAL:
        if hc:
            lead = _lead_for(hc, covered)
        else:
            vals = {k: _day(snap, k, on) for k in hot + cold}
            lead = (max(hot, key=lambda k: vals[k]["high"]["value"]) if len(hot) >= len(cold)
                    else min(cold, key=lambda k: vals[k]["low"]["value"]))
        bits = []
        if hc:
            bits.append(f"{_list(_events_of(hc))} in {_list(_states_of(hc))}" + (f", over {_list(over_city)}" if over_city else ""))
        if len(hot) >= SEVERAL:
            bits.append(f"highs of {HOT_F}°F or more in {_list(hot)}")
        if len(cold) >= SEVERAL:
            bits.append(f"lows of {COLD_F}°F or less in {_list(cold)}")
        return story("extreme_temp", hc, lead, sorted(set(over_city + hot + cold)), "extreme temperatures: " + "; ".join(bits) + ".")
    why.append(f"Extreme heat/cold: {len(hc)} heat or cold warning(s), none over a covered city; {len(hot)} city(ies) at "
               f"{HOT_F}°F or more, {len(cold)} at {COLD_F}°F or less (needs {SEVERAL}).")

    # 4. heavy rain and flooding
    fl = [a for a in land if a["event"] in FLOOD]
    ffw = [a for a in fl if a["event"] == "Flash Flood Warning"]
    watches = [a for a in fl if a["event"] in FLOOD_WATCH]
    over_city = sorted({k for a in fl for k in a["metros"]})
    rainy = [m.key for m in covered if (_day(snap, m.key, on) or {}).get("icon") and _wet(_day(snap, m.key, on)) and _pop(_day(snap, m.key, on)) >= RAIN_POP]
    if ffw or len(watches) >= 2 or over_city or len(rainy) >= SEVERAL:
        story_alerts = ffw + watches + [a for a in fl if a not in ffw and a not in watches and a["metros"]]
        if story_alerts:
            lead = _lead_for(story_alerts, covered)
        else:
            lead = max(rainy, key=lambda k: (_pop(_day(snap, k, on)), -next(m.rank for m in covered if m.key == k)))
        bits = []
        if ffw:
            bits.append(f"{len(ffw)} flash flood warning(s) in {_list(_states_of(ffw))}")
        if len(watches) >= 2:
            bits.append(f"{len(watches)} flood watch(es) in {_list(_states_of(watches))}")
        if over_city:
            bits.append(f"flood alerts over {_list(over_city)}")
        if len(rainy) >= SEVERAL:
            bits.append(f"rain at {RAIN_POP}% or more in {_list(rainy)}")
        return story("heavy_rain", story_alerts, lead, sorted(set(over_city + rainy)), "heavy rain and flooding: " + "; ".join(bits) + ".")
    why.append(f"Heavy rain: {len(ffw)} flash flood warning(s), {len(watches)} flood watch(es), no flood alert over a covered city, "
               f"{len(rainy)} city(ies) with rain at {RAIN_POP}% or more (needs {SEVERAL}).")

    # 5. routine: the city with the most to say
    best, reason = None, ""
    wet = [(m, _pop(_day(snap, m.key, on))) for m in covered if _day(snap, m.key, on) and _wet(_day(snap, m.key, on))]
    wet = [(m, p) for m, p in wet if p >= 30]
    if wet:
        best, p = max(wet, key=lambda mp: (mp[1], -mp[0].rank))
        reason = f"a routine day; {best.key} has the highest chance of rain or snow ({p}%)."
    else:
        swings = []
        for m in covered:
            days = snap.forecasts[m.key]["days"]
            d0 = _day(snap, m.key, on)
            if d0 is None:
                continue
            later = [d["high"]["value"] for d in days if day_date(d) > on][:5]
            if later:
                swings.append((max(abs(v - d0["high"]["value"]) for v in later), m))
        if swings:
            sw_, best = max(swings, key=lambda s: (s[0], -s[1].rank))
            reason = f"a routine day; {best.key} has the biggest change in its highs over the next days ({sw_}°F)."
        else:
            best = covered[0]
            reason = f"a routine day; {best.key} is the largest covered city."
    return story("routine", [], best.key, [best.key], reason)
