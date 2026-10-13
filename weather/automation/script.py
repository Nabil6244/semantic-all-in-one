"""The forecast script, written from the snapshot for reading aloud.

Rules the writer keeps (and test_weather_auto_script.py checks):
  - every number it says is a value in the snapshot (a high, a low, a chance of rain, a temperature now), said as words ("near
    ninety-two") or as the band that value is in ("in the low sixties"); dates are said as ordinals ("October thirteenth");
  - weather words come from the NWS short forecast of that city and day, with its own certainty ("a slight chance of", "a chance
    of", "likely"); a comparison ("highs climb", "highs drop") compares a city only with its own later days;
  - short sentences; no sentence starts with a number (the plan anchors graphics on a sentence's first words);
  - pronunciation hints in brackets only for names in weather.automation.spoken.HINTS;
  - it ends by pointing to the local National Weather Service office.
The wording varies from day to day (the date seeds the choice of templates) and is the same for the same data on the same day.

The result is a Script: sections (each becomes one or two beats of the plan) of sentences, each sentence with the data it says
(refs), so the plan can anchor graphics on it and the changes check can name the lines whose numbers moved."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from ..alerts import county_shapes
from ..resolve import Snapshot
from . import spoken as sp
from .coverage import REGIONS, Metro, by_region, metro, metros
from .fetch import day_date, national_alerts
from .story import NOT_LOWER48, Story, _lower48

MAX_CITIES_PER_REGION = 3


@dataclass
class Ref:
    city: str  # "Dallas, TX"
    date: str  # the forecast day (ISO), or "" for an observation
    field: str  # high | low | pop | now
    value: int
    said: str  # how the script says it ("near ninety-two", "in the low sixties", "fifty-four percent")

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Sentence:
    text: str
    refs: List[Ref] = field(default_factory=list)
    city: str = ""  # the city this sentence is about (its temp marker appears on it)


@dataclass
class Section:
    id: str
    kind: str  # intro | lead | now | footage | region | week | trend | warnings | close
    sentences: List[Sentence]
    cities: List[str] = field(default_factory=list)  # cities shown on the map in this section (markers)
    region: str = ""
    footage: str = ""  # footage condition (rain, storm, sun ...) for a footage section
    footage_city: str = ""

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.sentences)


@dataclass
class Script:
    on: date
    sections: List[Section]

    @property
    def text(self) -> str:
        """script.txt: one paragraph per section."""
        return "\n".join(s.text for s in self.sections) + "\n"

    @property
    def refs(self) -> List[Ref]:
        return [r for s in self.sections for x in s.sentences for r in x.refs]

    def lines(self) -> List[Dict[str, Any]]:
        """Every sentence with its refs (saved in prep.json; weather.automation.changes reads it)."""
        return [{"section": s.id, "text": x.text, "refs": [r.to_dict() for r in x.refs]} for s in self.sections for x in s.sentences]

    @property
    def word_count(self) -> int:
        return len(sp.strip_hints(self.text).split())


# ---- data helpers ----------------------------------------------------------------------------------------------------------

def day_of(snap: Snapshot, key: str, on: date) -> Optional[Dict[str, Any]]:
    for d in snap.forecasts.get(key, {}).get("days", []):
        if day_date(d) == on:
            return d
    return None


def pop_of(d: Dict[str, Any]) -> int:
    return d["pop"]["value"] if d.get("pop") else 0


def category_of(d: Dict[str, Any]) -> str:
    return sp.category(d["short"], d["high"]["value"], pop_of(d))


class _Writer:
    def __init__(self, snap: Snapshot, story: Story, today: Optional[date], seed: str = ""):
        self.snap, self.story, self.on = snap, story, story.on
        self.today = today
        self.covered = [m for m in metros() if day_of(snap, m.key, self.on) is not None]
        self.rng = random.Random(f"weather-forecast-{seed or self.on.isoformat()}")
        self.said_hints: set = set()

    def pick(self, options: Sequence[str]) -> str:
        return options[self.rng.randrange(len(options))]

    def exact(self) -> bool:
        return self.rng.random() < 0.5

    def hi(self, key: str, d: Dict[str, Any], exact: Optional[bool] = None) -> "tuple[str, Ref]":
        v = d["high"]["value"]
        said = sp.temp(v, self.exact() if exact is None else exact)
        return said, Ref(key, day_date(d).isoformat(), "high", v, said)

    def lo(self, key: str, d: Dict[str, Any], exact: Optional[bool] = None) -> "tuple[str, Ref]":
        v = d["low"]["value"]
        said = sp.temp(v, self.exact() if exact is None else exact)
        return said, Ref(key, day_date(d).isoformat(), "low", v, said)

    @property
    def day_word(self) -> str:
        return "today" if self.today == self.on else f"on {self.on.strftime('%A')}"

    def city_sentence(self, m: Metro) -> Sentence:
        d = day_of(self.snap, m.key, self.on)
        said, ref = self.hi(m.key, d)
        cond = sp.condition_clause(d["short"])
        t = self.pick(("For {c}, {cond}, with a high {t}.", "{c} heads for a high {t}, and {cond}.", "In {c}, {cond}, with a high {t}.",
                       "{c} tops out {t}, and {cond}."))
        return Sentence(t.format(c=m.name, cond=cond, t=said), [ref], m.key)


def _region_name(region: str, ms: Sequence[Metro]) -> str:
    states = {m.city.state for m in ms}
    if len(states) == 1:
        return sp.STATES[states.pop()]
    return {"Pacific": "the West Coast"}.get(region, f"the {region}")


def _choose_cities(snap: Snapshot, on: date, ms: Sequence[Metro], n: int) -> List[Metro]:
    """The biggest metro, then the ones whose weather differs most from those already chosen (so a region says something)."""
    ms = [m for m in ms if day_of(snap, m.key, on)]
    if not ms:
        return []
    out = [ms[0]]
    while len(out) < min(n, len(ms)):
        def score(m: Metro) -> "tuple[int, int]":
            d = day_of(snap, m.key, on)
            diff = min(abs(d["high"]["value"] - day_of(snap, o.key, on)["high"]["value"]) + (10 if category_of(d) != category_of(day_of(snap, o.key, on)) else 0)
                       for o in out)
            return diff, -m.rank
        out.append(max([m for m in ms if m not in out], key=score))
    return out


def write_script(snap: Snapshot, story: Story, *, today: Optional[date] = None, seed: str = "") -> Script:
    """The day's script. `today` (the prep's own date in Central time) decides between 'today' and the day's name; the wording
    is seeded by the forecast's date unless `seed` is given."""
    w = _Writer(snap, story, today, seed)
    on = story.on
    lead = metro(story.lead_city)
    sections: List[Section] = []
    when = f"{on.strftime('%A')}, {on.strftime('%B')} {sp.ordinal(on.day)}"

    # 1. national overview
    highs = [(day_of(snap, m.key, on)["high"]["value"], m) for m in w.covered]
    warm = max(highs, key=lambda x: (x[0], -x[1].rank))[1]
    cool = min(highs, key=lambda x: (x[0], x[1].rank))[1]
    s1 = Sentence(w.pick((f"Good morning, and welcome to your national weather forecast for {when}.",
                          f"Good morning. Here is your weather across the country for {when}.",
                          f"Good morning, and thanks for joining us for the national forecast for {when}.")))
    s2 = Sentence(_headline(w, story))
    hs, hr = w.hi(warm.key, day_of(snap, warm.key, on), exact=True)
    cs, cr = w.hi(cool.key, day_of(snap, cool.key, on), exact=True)
    s3 = Sentence(w.pick((f"Among our big cities, {warm.name} is the warmest, with a high {hs}, and {cool.name} is the coolest, with a high {cs}.",
                          f"The warmest of our big cities is {warm.name}, with a high {hs}, while {cool.name} is the coolest, with a high {cs}.")),
                  [hr, cr])
    national_cities = [warm.key, cool.key] + [m.key for m in w.covered if m.key not in (warm.key, cool.key) and m.region not in (warm.region, cool.region)][:2]
    sections.append(Section("intro", "intro", [s1, s2, s3], national_cities))

    # 2. the lead story and its city
    d0 = day_of(snap, lead.key, on)
    lead_s: List[Sentence] = []
    if story.alerts:
        n = Counter(a["event"] for a in story.alerts)
        ev = sp.join_and([sp.event_phrase(e, n[e]) for e in story.events[:2]])
        states = sp.state_list(story.states)
        lead_s.append(Sentence(w.pick((f"The National Weather Service has {ev} in effect for parts of {states}.",
                                       f"Right now, there are {ev} in effect for parts of {states}."))))
        over = [a for a in story.alerts if lead.key in a["metros"]]
        if over:
            county = county_shapes().get(lead.county_fips, {}).get("name", "")
            where = f"{sp.hint(county, w.said_hints)} County" if county and lead.city.state != "DC" else lead.name
            lead_s.append(Sentence(f"That includes {where}, around {lead.name}."))
        else:
            lead_s.append(Sentence(f"Of our big cities, {lead.name} is the closest to those alerts."))
    else:
        lead_s.append(Sentence(w.pick((f"We start in {lead.name}.", f"Our first stop is {lead.name}."))))
    lead_s.append(w.city_sentence(lead))
    sections.append(Section("lead", "lead", lead_s, [lead.key], lead.region))

    now_s: List[Sentence] = []
    obs = snap.observations.get(lead.key)
    if obs:
        v = obs["temp"]["value"]
        text = (obs.get("text") or "").lower().replace("/", " and ").strip()
        tail = f" and {text}" if text else ""
        now_s.append(Sentence(f"The latest report from {lead.name} is {sp.words(v)} degrees{tail}.", [Ref(lead.key, "", "now", v, sp.words(v))]))
    if d0.get("low"):
        ls, lr = w.lo(lead.key, d0)
        now_s.append(Sentence(w.pick((f"Tonight, the low is {ls}.", f"Overnight, it drops to a low {ls}.")), [lr]))
    p = pop_of(d0)
    if p >= 20:
        what = "storms" if sp.category(d0["short"], 0, 100) == "storm" else "snow" if sp.category(d0["short"], 50, 100) == "snow" else "rain"
        now_s.append(Sentence(f"The chance of {what} {w.day_word} is {sp.words(p)} percent.",
                              [Ref(lead.key, on.isoformat(), "pop", p, f"{sp.words(p)} percent")]))
    if now_s:
        sections.append(Section("now", "now", now_s, [lead.key], lead.region))

    # 3. footage of how the day feels, then the regions (footage between them)
    feel_cities = [lead] + [m for m in w.covered if m.key != lead.key]
    footage_plan = _footage_choices(snap, on, feel_cities)
    fi = 0

    def add_footage() -> None:
        nonlocal fi
        if fi < len(footage_plan):
            m, cat = footage_plan[fi]
            fi += 1
            sections.append(Section(f"feel{fi}", "footage", [_feel_sentence(w, m, cat)], region=m.region, footage=cat, footage_city=m.key))

    add_footage()
    groups = by_region()
    order = [r for r in REGIONS if r != lead.region and groups[r]]
    openers = ("Now to {r}.", "Next, {r}.", "On to {r}.", "Let us head to {r}.", "Over to {r}.", "Moving on to {r}.")
    used_openers: set = set()
    for i, region in enumerate(order):
        ms = _choose_cities(snap, on, groups[region], MAX_CITIES_PER_REGION)
        if not ms:
            continue
        name = _region_name(region, groups[region])
        op = w.pick([o for o in openers if o not in used_openers] or openers)
        used_openers.add(op)
        sents = [Sentence(op.format(r=name)[0].upper() + op.format(r=name)[1:])] + [w.city_sentence(m) for m in ms]
        sections.append(Section(f"region{i + 1}", "region", sents, [m.key for m in ms], region))
        if i in (1, 3):
            add_footage()

    # 4. the week ahead for the lead city: the strip, then the trend chart
    days = snap.forecasts[lead.key]["days"]
    i0 = next(i for i, d in enumerate(days) if day_date(d) == on)
    week = days[i0:i0 + 5]
    ws = [Sentence(w.pick((f"Here is the week ahead for {lead.name}.", f"Let us look at the days ahead in {lead.name}.")))]
    if len(week) > 1:
        ws.append(Sentence(f"On {day_date(week[1]).strftime('%A')}, {sp.condition_clause(week[1]['short'])}."))
    wet_days = [d for d in week[2:] if sp.category(d["short"], 50, pop_of(d)) in ("rain", "storm", "snow")]
    if wet_days:
        d = wet_days[0]
        part = next(p for p in sp.parse_short(d["short"]) if p.wet)
        ws.append(Sentence(f"{day_date(d).strftime('%A')} brings {sp.noun_phrase(part)}."))
    elif all(pop_of(d) < 20 and not any(p.wet for p in sp.parse_short(d["short"])) for d in week[1:]):
        ws.append(Sentence(f"The next few days look dry, with no rain in the forecast through {day_date(week[-1]).strftime('%A')}."))
    sections.append(Section("week", "week", ws, [lead.key], lead.region))

    trend_days = days[i0:i0 + 7]
    ts = [Sentence(f"And here are the highs and lows through {day_date(trend_days[-1]).strftime('%A')}.")]
    h0 = trend_days[0]["high"]["value"]
    later = trend_days[1:]
    up = max(later, key=lambda d: (d["high"]["value"], -day_date(d).toordinal()))
    down = min(later, key=lambda d: (d["high"]["value"], day_date(d).toordinal()))
    moves = []
    if up["high"]["value"] - h0 >= 5:
        v = up["high"]["value"]
        said, ref = sp.words(v), Ref(lead.key, day_date(up).isoformat(), "high", v, sp.words(v))
        moves.append((day_date(up), Sentence(f"Highs climb to {said} by {day_date(up).strftime('%A')}.", [ref])))
    if h0 - down["high"]["value"] >= 5:
        v = down["high"]["value"]
        said, ref = sp.words(v), Ref(lead.key, day_date(down).isoformat(), "high", v, sp.words(v))
        moves.append((day_date(down), Sentence(f"Highs drop to {said} by {day_date(down).strftime('%A')}.", [ref])))
    if moves:
        ts += [s for _, s in sorted(moves, key=lambda x: x[0])]
    else:
        lo_d = min(trend_days, key=lambda d: (d["high"]["value"], day_date(d).toordinal()))
        hi_d = max(trend_days, key=lambda d: (d["high"]["value"], -day_date(d).toordinal()))
        a, b = lo_d["high"]["value"], hi_d["high"]["value"]
        ts.append(Sentence(f"Highs hold steady, between {sp.words(a)} and {sp.words(b)} degrees." if a != b else f"Highs hold steady near {sp.words(a)} degrees.",
                           [Ref(lead.key, day_date(lo_d).isoformat(), "high", a, sp.words(a)), Ref(lead.key, day_date(hi_d).isoformat(), "high", b, sp.words(b))]))
    lows = [d for d in trend_days if d.get("low")]
    if len(lows) >= 2:
        lmin = min(lows, key=lambda d: (d["low"]["value"], day_date(d).toordinal()))
        lmax = max(lows, key=lambda d: (d["low"]["value"], -day_date(d).toordinal()))
        a, b = lmin["low"]["value"], lmax["low"]["value"]
        if a != b:
            ts.append(Sentence(f"Nights range from {sp.words(a)} to {sp.words(b)} degrees.",
                               [Ref(lead.key, day_date(lmin).isoformat(), "low", a, sp.words(a)), Ref(lead.key, day_date(lmax).isoformat(), "low", b, sp.words(b))]))
    sections.append(Section("trend", "trend", ts, [lead.key], lead.region))
    add_footage()

    # 5. warnings to know, then the close
    sections.append(Section("warnings", "warnings", _warnings(w, story)))
    office = f"the National Weather Service {lead.office_spoken} office"
    close = [Sentence(w.pick(("Forecasts change through the day, so for the warnings where you live, follow your local National Weather Service office.",
                              "Forecasts can change, so for watches and warnings where you live, always follow your local National Weather Service office."))),
             Sentence(f"For {lead.name}, that is {office}, at weather dot gov."),
             Sentence(w.pick((f"Thanks for watching, and have a good {on.strftime('%A')}.", f"Thanks for watching, and stay safe out there.")))]
    sections.append(Section("close", "close", close))
    return Script(on, sections)


def _headline(w: _Writer, story: Story) -> str:
    if story.kind == "routine":
        return w.pick(("It is a fairly quiet day for most of the country.", "Most of the country has a fairly quiet day ahead."))
    lead = {"tropical": "The big story is in the tropics", "severe": "The big story is severe weather",
            "heavy_rain": "The story to watch is heavy rain and flooding"}.get(story.kind)
    if story.kind == "extreme_temp":
        cold = any(e in ("Extreme Cold Warning", "Wind Chill Warning") for e in story.events)
        lead = "The big story is the cold" if cold else "The big story is the heat"
    if story.states:
        return f"{lead}, in {sp.state_list(story.states)}."
    names = [metro(k).name for k in story.cities[:3]] or [metro(story.lead_city).name]
    return f"{lead}, around {sp.join_and(names)}."


# Footage conditions in the order they are worth showing (filmable weather first).
CATEGORY_RANK = ("storm", "snow", "rain", "fog", "heat", "cold", "wind", "sun", "cloud")


def _footage_choices(snap: Snapshot, on: date, cities: Sequence[Metro]) -> List["tuple[Metro, str]"]:
    """Two or three (city, condition) pairs, each a different condition: the lead city first, then the most filmable others."""
    out: List["tuple[Metro, str]"] = []
    seen = set()
    first = cities[0]
    cat = category_of(day_of(snap, first.key, on))
    out.append((first, cat))
    seen.add(cat)
    rest = sorted(((CATEGORY_RANK.index(category_of(day_of(snap, m.key, on))), m.rank, m) for m in cities[1:]), key=lambda x: (x[0], x[1]))
    for _, _, m in rest:
        c = category_of(day_of(snap, m.key, on))
        if c not in seen and len(out) < 3:
            out.append((m, c))
            seen.add(c)
    if len(out) < 2:   # every city has the same weather: a second city with it
        for m in cities[1:]:
            out.append((m, category_of(day_of(snap, m.key, on))))
            break
    return out


def _feel_sentence(w: _Writer, m: Metro, cat: str) -> Sentence:
    d = day_of(w.snap, m.key, w.on)
    parts = sp.parse_short(d["short"])
    np_ = sp.noun_phrase(next((p for p in parts if p.wet and p.cert != "slight"), parts[-1]))
    fog = next((p.noun for p in parts if any(x in p.noun for x in ("fog", "haze", "smoke"))), "fog")
    text = {
        "storm": f"If you are out in {m.name}, keep an eye on the sky, with {np_} in the forecast.",
        "rain": f"If you are heading out in {m.name}, keep the umbrella close, with {np_} in the forecast.",
        "snow": f"In {m.name}, plan for slick roads, with {np_} in the forecast.",
        "fog": f"Early drivers in {m.name} should allow extra time, with {fog} around.",
        "heat": f"In {m.name}, the afternoon turns hot, so drink plenty of water and find some shade.",
        "cold": f"Bundle up in {m.name}, where it stays cold all day.",
        "wind": f"Hold on to your hat in {m.name}, where it turns {parts[-1].noun}.",
        "sun": f"In {m.name}, it is a fine day to be outside, with {np_}.",
        "cloud": f"In {m.name}, the sky stays gray for much of the day, with {np_}.",
    }[cat]
    return Sentence(text, [], m.key)


def _warnings(w: _Writer, story: Story) -> List[Sentence]:
    alerts = [a for a in national_alerts(w.snap) if _lower48(a) and a["event"] not in story.events
              and a["event"].endswith(("Warning", "Watch"))]
    n = Counter(a["event"] for a in alerts)
    top = sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    if not top:
        return [Sentence("Elsewhere, there are no other watches or warnings of note across the rest of the country.")]
    out = [Sentence(w.pick(("Elsewhere, here are the warnings to know.", "Elsewhere, a few more alerts to know about.")))]
    for event, count in top:
        c = Counter(s for a in alerts if a["event"] == event for s in a["states"] if s not in NOT_LOWER48)
        states = [s for s, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]
        phrase = sp.event_phrase(event, count)
        out.append(Sentence(f"There {'is' if count == 1 else 'are'} {phrase} in {sp.state_list(states)}."))
    return out
