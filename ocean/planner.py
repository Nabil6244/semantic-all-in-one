"""Ocean planner (docs/ocean/PATTERNS.md section 7, step 5): narration -> shots on the ocean stage + captions.

    plan(scenes, chapters=(), channel="Ocean") -> OceanPlan
        scenes: [{"text", "start", "end", optional "words": [(word, t0, t1)] or [{"word","start","end"}]}]
        chapters: chapter start times (seconds)
    OceanPlan.layers   [{"name": "ocean.lay_ocean" | "ocean.lay_captions", "start", "end", "params"}]
    OceanPlan.shots    [{"start", "end", "set", "cards": [...], "animals": [...]}]   (for the report / the app's scene list)
    OceanPlan.report   counts, shot lengths, longest still stretch

How a sentence becomes a picture (rules by sentence shape, ocean/reader.py):
- the animals it names act it on the stage (one: centre; two: face each other; plural / pod / school: a group).
  "fled / ran / vanished" -> the animal swims off; "attacked / hunted / bit" -> it glides at the other one, jaw open.
- a number becomes its card: percent -> progress bar, "N hours" -> clock, "in 1997" -> calendar, "N of M" -> dot grid,
  two counts -> standoff, a length beside an animal -> size bar, any other number + unit -> big number card;
  "N m down" -> the depth-ruler set with that mark.
- researchers / a study -> paper card; "would you X or Y?" -> choose-your-move menu; list ordinals ("the first one is")
  -> the mystery line-up revealing slot N; "except one animal" -> a silhouette of the next animal named;
  "you" in a what-would-you-do chapter -> the diver with the depth / air panel.
- a joke prop (wanted poster, crime tape, halo, bunting, shop, playbook) when the sentence's shape asks for one and none
  was shown for GAG_GAP_S; data cards keep CARD_GAP_S apart and never repeat the same kind back to back.
- the set follows the sentence (abyss, kelp, depth, seafloor, surface) and stays until another sentence asks for a change;
  a new chapter returns to open water.
- shots cut every SHOT_MIN_S-SHOT_MAX_S at a sentence end, earlier at a chapter start or a set change.
- something on screen changes at least every STILL_MAX_S (an animal drifts to a new place when nothing else happens).
- captions (ocean/captions.py) are dropped while a text card is up, so a number is never said twice on screen.
- the last seconds show the watch-next card; a closing "let us know in the comments" line shows the comment card.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import captions as CAP
from . import reader as R
from .stage import OceanStage

SHOT_MIN_S, SHOT_MAX_S = 6.0, 11.0
CARD_GAP_S, GAG_GAP_S = 2.0, 45.0
STILL_MAX_S = 3.6
CARD_HOLD_S = 2.6
FULL = {"island_map", "size_compare", "dot_grid", "mystery", "paper", "choose_move", "quiz", "playbook", "wanted", "shop", "comments", "watch_next",
        "duel", "silhouettes", "icon_rows", "bar_race", "strata", "name_chips"}
TEXT_CARDS = FULL | {"number_hero", "standoff", "progress", "calendar", "clock", "meters", "counter"}
GAGS = {"wanted", "crime_tape", "halo", "bunting", "shop", "playbook", "quiz", "duel"}
from . import species as _SP  # noqa: E402
FAMILY = {k: s.family for k, s in _SP.SPECIES.items() if s.family}    # "sharks" in a tiger-shark film means tiger sharks
PAPER_GAP_S = 60.0
FULL_MAX_S = 4.4
END_CARD_MIN_S = 120.0                        # a short test / Short ends on its last line, not on the end screen
LONG_FULL = {"island_map": 7.5}               # scenes that play out (the group circles, then leaves) hold longer
GROUP_TRACK = re.compile(r"\b(tracked|tagged|counted|vanish(ed|es)?|disappear(ed|s)?|fled|left|came back|gone|islands?|"
                         r"gathered|circled|patrolled)\b", re.I)
LEAVE = re.compile(r"\b(not one|none|nobody|vanish(ed|es)?|disappear(ed|s)?|fled|ran|left|gone|swam away|never came back)\b",
                   re.I)
OPENING_YOU = re.compile(r"\b(below|beneath|under)\s+you\b|\byou'?re\s+(floating|swimming|diving|in the water|treading)", re.I)
FEET_M = 0.3048
GAG_REPEAT_S = 120.0
CARRY_SET_SHOTS = 0
SIDE_CARDS = {"calendar", "clock", "counter", "meters", "diver_hud", "name_tag"}   # corner cards: captions still show
LOW_TEXT_SETS = {"surface"}                 # sets with a horizon up top: text cards sit below the water line
GROUP_WORDS = {"two": 2, "pair": 2, "both": 2, "three": 3, "four": 4, "five": 5}
CONJ = {"and", "but", "so", "then", "which", "while", "yet"}
CARD_POS = {
    "number_hero": ((640, 175), 1.0), "standoff": ((640, 110), 1.0), "progress": ((640, 190), 0.9),
    "clock": ((1060, 240), 0.62), "calendar": ((1060, 230), 0.7), "counter": ((230, 80), 1.0),
    "bunting": ((640, 70), 1.0), "crime_tape": ((640, 360), 1.0), "diver_hud": ((330, 110), 1.0),
    "name_tag": ((300, 64), 1.0), "meters": ((900, 250), 0.8),
}
ENTERS = ("slide_left", "slide_right", "pop", "rise")


@dataclass
class OceanPlan:
    layers: List[Dict[str, Any]] = field(default_factory=list)
    shots: List[Dict[str, Any]] = field(default_factory=list)
    captions: List[Dict[str, Any]] = field(default_factory=list)
    report: Dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------------------------------------------------------ helpers

def _t_at(sc: Dict[str, Any], pos: Optional[int]) -> float:
    a, b = float(sc["start"]), float(sc["end"])
    n = max(1, len(str(sc.get("text", ""))))
    return a + (b - a) * min(1.0, max(0.0, (pos or 0) / n))


def _label(word: str) -> str:
    w = re.sub(r"\s+", " ", word.strip())
    w = re.sub(r"s$", "", w) if w.lower().endswith("s") and not w.lower().endswith(("ss", "us")) else w
    return w[:1].upper() + w[1:]


def _after(text: str, pos: int, n: int = 6) -> List[str]:
    return re.findall(r"[A-Za-z'][A-Za-z'\-]*", text[pos:])[:n]


def _layout(n: int) -> List[Tuple[float, float, str]]:
    return {1: [(600.0, 400.0, "right")], 2: [(390.0, 410.0, "right"), (900.0, 400.0, "left")]}.get(
        n, [(300.0, 340.0, "right"), (690.0, 450.0, "right"), (1010.0, 330.0, "left")])


def _animal_args(a: Tuple, face: str, width: int = 520, **extra: Any) -> Dict[str, Any]:
    args = {"name": a[0], "width": width, "face": face}
    args.update({k: v for k, v in a[2].items() if k != "generic"})
    args.update(extra)
    return args


def _group_n(text: str, a: Tuple) -> int:
    """'two orcas' -> 2, 'a pod of orcas' -> 3: how many of a plural animal swim in."""
    before = re.findall(r"[A-Za-z0-9]+", text[: a[3]].lower())[-2:]
    for w in reversed(before):
        if w in GROUP_WORDS:
            return GROUP_WORDS[w]
        if w.isdigit() and 1 < int(w) <= 5:
            return int(w)
    return 3


def _tail_line(text: str, start: int) -> Tuple[str, str]:
    """The rest of the clause after a number, for the number card: (plain words, KEY words).
    '300 teeth, and nothing in the ocean hunts it.' -> ('nothing in the ocean', 'hunts it')."""
    if re.match(r"\s*[,.;!?]", text[start:]):
        return "", ""                           # the number's own clause ended there: the number stands alone ("~300 TEETH")
    rest = re.split(r"[,.;!?]", text[start:], maxsplit=1)[0]
    words = re.findall(r"[A-Za-z0-9'][A-Za-z0-9'\-]*", rest)
    while words and words[0].lower() in CONJ:
        words = words[1:]
    words = words[:7]
    if len(words) >= 3:
        return " ".join(words[:-2]), " ".join(words[-2:])
    return "", " ".join(words)


def _key(a: Tuple) -> str:
    return a[0] + repr(sorted((k, v) for k, v in a[2].items() if k != "generic"))


def _resolve(animals: List[Tuple], family_last: Dict[str, Tuple]) -> List[Tuple]:
    """'sharks' in a great-white film means great whites: a generic name takes the last specific animal of its family
    (in this sentence first, else from the story so far); duplicates go; at most 3."""
    out: List[Tuple] = []
    for a in animals:
        if not a[2].get("generic") and FAMILY.get(a[0]):
            family_last[FAMILY[a[0]]] = a
    for a in animals:
        g = a[2].get("generic")
        if g and g in family_last and family_last[g][0] != a[0]:
            b = family_last[g]
            a = (b[0], a[1], b[2], a[3], b[4])
        if g and any(FAMILY.get(b[0]) == g for b in out):
            continue
        if _key(a) not in [_key(b) for b in out]:
            out.append(a)
    return out[:3]


# ------------------------------------------------------------------------------------------------------------------ card choice

class _Cards:
    """Chooses at most one card per sentence and keeps the gaps / no-repeat rules."""

    def __init__(self, total: float, list_items: List[str]) -> None:
        self.total = total
        self.last_end = -1e9
        self.last_kind = ""
        self.last_gag = -1e9
        self.last_paper = -1e9
        self.gag_times: Dict[str, float] = {}
        self.list_items = list_items
        self.revealed = 0
        self.counts: Dict[str, int] = {}

    def ok(self, kind: str, t: float) -> bool:
        if kind in GAGS and t - self.last_gag < GAG_GAP_S:
            return False
        if kind == "paper" and t - self.last_paper < PAPER_GAP_S:
            return False
        if kind in GAGS and t - self.gag_times.get(kind, -1e9) < GAG_REPEAT_S:
            return False
        if kind == self.last_kind and kind != "mystery" and t - self.last_end < 20:
            return False
        return t - self.last_end >= CARD_GAP_S or kind == "mystery"

    def took(self, kind: str, t0: float, t1: float) -> None:
        self.last_end, self.last_kind = t1, kind
        if kind in GAGS:
            self.last_gag = t0
            self.gag_times[kind] = t0
        if kind == "paper":
            self.last_paper = t0
        self.counts[kind] = self.counts.get(kind, 0) + 1

    def choose(self, sc: Dict[str, Any], f: R.Features, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        t0 = float(sc["start"])
        text = f.text
        opts: List[Dict[str, Any]] = []
        if f.comment and t0 > self.total * 0.8:
            opts.append({"kind": "comments", "args": {"text": text.strip()[:70]}, "pos": 0})
        if f.ordinal is not None and len(self.list_items) >= 3 and ctx.get("list_start"):
            i = min(self.revealed, len(self.list_items) - 1)
            slots = [self.list_items[k].replace("_", " ") if k < i else "" for k in range(len(self.list_items))]
            animals = [self.list_items[k] if k <= i else "" for k in range(len(self.list_items))]
            self.revealed += 1
            opts.append({"kind": "mystery", "args": {"slots": slots[:5], "animals": animals[:5], "lit": i}, "pos": 0})
        paper_opt: List[Dict[str, Any]] = []
        if f.study:
            year = next((n.raw for n in f.numbers if n.kind == "year"), "")
            title = " ".join(re.findall(r"[A-Za-z0-9',\-]+", text)[:12])
            paper_opt.append({"kind": "paper", "args": {"journal": ("Field study, " + year) if year else "Field study",
                                                   "title": title}, "pos": 0})
        if paper_opt and not any(n.kind == "count" for n in f.numbers):
            opts += paper_opt
            paper_opt = []
        if f.choice and f.you:
            opts.append({"kind": "choose_move", "args": {"options": f.choice, "selected": len(f.choice) - 1}, "pos": 0})
        nums = [n for n in f.numbers if n.value > 0 or n.kind == "count"]
        counts = [n for n in nums if n.kind == "count"]
        group_n = next((n for n in counts if 3 <= n.value <= 60), None)
        if group_n is not None and GROUP_TRACK.search(text):          # "Researchers tracked 17 sharks ... not one came back"
            who = next((a for a in f.animals if 0 <= a[3] - group_n.end <= 3), None)
            animal = who[0] if who else (f.animals[0][0] if f.animals else ctx.get("subject"))
            if animal and animal not in ("boat", "cage", "tooth", "diver"):
                if FAMILY.get(animal) and ctx.get("subject") and FAMILY.get(ctx["subject"]) == FAMILY.get(animal):
                    animal = ctx["subject"]                       # "sharks" in a great-white story: great whites
                word = who[4] if who else (group_n.unit or (f.animals[0][4] if f.animals else ctx.get("subject_word") or ""))
                tracked = re.search(r"\b(tracked|tagged)\b", text, re.I)
                label = ((tracked.group(1).lower() + " ") if tracked else "") + (word if word.endswith("s") else word + "s")
                year = next((n.raw for n in f.numbers if n.kind == "year"), "") or ctx.get("year", "")
                pm = re.search(r"\b((?:[A-Z][a-z]+\s){1,2}Islands?)\b", text)
                place = pm.group(1) if pm else ""
                opts.append({"kind": "island_map", "args": {"count": int(group_n.value), "label": label, "animal": animal,
                                                            "year": year, "place": place,
                                                            "leave_frac": 0.38 if LEAVE.search(text) else None},
                             "pos": group_n.pos})
        size_n = next((n for n in nums if n.kind == "length" and n.unit not in ("cm", "mm", "km", "inch", "inches")), None)
        size_who = (f.animals[0] if f.animals else None)
        if size_n is not None and size_who is not None and size_who[0] not in ("boat", "cage", "tooth", "diver"):
            metres = size_n.value * (FEET_M if size_n.unit in ("ft", "feet", "foot") else 1.0)
            if 0.5 <= metres <= 40:
                mass = next((n.raw for n in nums if n.kind == "mass"), "")
                ref = "diver" if metres < 3 else "car" if metres < 9 else "bus"
                animal = size_who[0]
                if size_who[2].get("generic") and ctx.get("subject") and FAMILY.get(ctx["subject"]) == size_who[2]["generic"]:
                    animal = ctx["subject"]
                opts.append({"kind": "size_compare", "args": {
                    "animal": animal, "metres": round(metres, 2),
                    "label": (size_n.raw + (" · " + mass if mass else "")).upper(),
                    "ref": ref, "ref_label": {"diver": "DIVER · 1.8 M", "car": "CAR · 4.5 M", "bus": "BUS · 12 M"}[ref]},
                    "pos": size_n.pos})
        for n in nums:
            if n.kind == "percent":
                opts.append({"kind": "progress", "args": {"value": n.value, "label": n.raw,
                                                          "note": " ".join(_after(text, n.end, 6))}, "pos": n.pos})
            elif n.kind == "time":
                hours = n.value / 60.0 if n.unit.startswith("min") else n.value
                opts.append({"kind": "clock", "args": {"hours": min(hours, 12.0), "time": n.raw.upper()}, "pos": n.pos})
            elif n.kind == "year" and (f.month or re.search(r"\b(in|by|since|until|of)\s+$", text[: n.pos], re.I)):
                opts.append({"kind": "calendar", "args": {"month": f.month or "", "day": n.raw, "line": ""}, "pos": n.pos})
        if len(counts) >= 2:
            a, b = counts[0], counts[1]
            between = text[a.pos: b.pos + 1].lower()
            if b.value <= a.value <= 300 and re.search(r"\bof\b|out of|only|just", text[a.pos: b.pos + 12].lower() + between):
                opts.append({"kind": "dot_grid", "args": {"total": int(a.value), "marked": int(b.value),
                                                          "cols": 15 if a.value > 40 else 10,
                                                          "left": [a.raw, " ".join(_after(text, a.end, 2))],
                                                          "right": [b.raw, " ".join(_after(text, b.end, 2))]},
                             "pos": a.pos})
            else:
                la = (f.animals[0][4] if f.animals else a.unit) or a.unit
                lb = (f.animals[1][4] if len(f.animals) > 1 else b.unit) or b.unit
                opts.append({"kind": "standoff", "args": {"left": [a.raw, la], "right": [b.raw, lb]}, "pos": a.pos})
        for n in nums:
            if n.kind == "length" and f.animals and not any(o["kind"] == "size_compare" for o in opts):
                opts.append({"kind": "size_bar", "args": {"label": n.raw, "length": 460}, "pos": n.pos, "with_animal": True})
            elif n.kind in ("count", "mass", "money", "length") and (n.unit or n.value >= 10 or n.pre):
                who = next((a for a in f.animals if 0 <= a[3] - n.end <= 3), None)     # "8 great whites"
                tail_from = (who[3] + len(who[4])) if who else n.end
                if not who and n.kind == "count" and n.unit:
                    m_u = re.match(r"\s*" + re.escape(n.unit), text[tail_from:], re.I)
                    tail_from += m_u.end() if m_u else 0
                plain, key = _tail_line(text, tail_from)
                unit_word = who[4] if who else (n.unit if n.kind == "count" and n.unit and len(n.unit) <= 8 and n.unit.isalpha() else "")
                big = n.raw + ((" " + unit_word) if unit_word and n.kind == "count" else "")
                opts.append({"kind": "number_hero", "args": {"number": big.upper() if n.unit else big, "line": plain,
                                                             "key": key, "size": 110 if len(big) < 8 else 84}, "pos": n.pos})
        opts += paper_opt                            # a study with a count: the number first, the paper if it cannot show
        if f.gag:
            gargs: Dict[str, Any] = {}
            if f.gag == "wanted":
                who = f.animals[0][0] if f.animals else (ctx.get("subject") or "great_white")
                gargs = {"animal": who, "crime": " ".join(re.findall(r"[A-Za-z']+", text)[:7]), "reward": "one very long grudge"}
            elif f.gag == "shop":
                gargs = {"title": (f.animals[0][4] if f.animals else "Genuine fossil") + " - genuine",
                         "price": next((n.raw for n in f.numbers if n.kind == "money"), "$249.99"),
                         "animal": "tooth" if not f.animals else f.animals[0][0]}
            elif f.gag == "quiz":
                head = " ".join(re.findall(r"[A-Za-z']+", text)[:6])
                gargs = {"title": head + "...", "options": [["myth", "check"], ["fact", "x"]]} if re.search(
                    r"myth|wrong|misconception", text, re.I) else {"title": head + "...",
                                                                   "options": [["what people think", "x"], ["what's true", "check"]]}
            elif f.gag == "duel":
                names = [a for a in f.animals if a[0] not in ("boat", "cage", "tooth", "diver")]
                if len(names) >= 2:
                    gargs = {"left": [names[0][0], _label(names[0][4])], "right": [names[1][0], _label(names[1][4])]}
                elif names and ctx.get("subject") and names[0][0] != ctx["subject"]:
                    gargs = {"left": [ctx["subject"], "predator"], "right": [names[0][0], "prey"]}
                else:
                    gargs = {}
            elif f.gag == "playbook":
                gargs = {"title": "the " + _label(ctx.get("subject_word") or "hunter").lower() + " playbook", "step": "1. separate"}
            if f.gag != "duel" or gargs:
                opts.append({"kind": f.gag, "args": gargs, "pos": 0, "with_animal": f.gag in ("halo", "bunting", "crime_tape")})
        if f.question and not any(o["kind"] in GAGS for o in opts) and f.choice:
            opts.append({"kind": "quiz", "args": {"title": " ".join(re.findall(r"[A-Za-z']+", text)[:6]) + "...",
                                                  "options": [[c, ""] for c in f.choice[:3]]}, "pos": 0})
        for o in opts:
            at = _t_at(sc, o["pos"])
            if self.ok(o["kind"], at):
                return o
            later = self.last_end + CARD_GAP_S         # blocked only by the gap: come in later in the same sentence
            if later < float(sc["end"]) - 1.2 and self.ok(o["kind"], later):
                return dict(o, at=later)
        return None


# ------------------------------------------------------------------------------------------------------------------ plan

def _shots(scenes: Sequence[Dict[str, Any]], feats: Sequence[R.Features], chapters: Sequence[float]) -> List[List[int]]:
    out: List[List[int]] = []
    cur: List[int] = []
    cur_set = ""
    for i, sc in enumerate(scenes):
        start = float(sc["start"])
        if cur:
            dur = start - float(scenes[cur[0]]["start"])
            chap = any(float(scenes[cur[-1]]["start"]) < c <= start + 0.05 for c in chapters)
            new_set = feats[i].set_hint and feats[i].set_hint != cur_set
            this = float(sc["end"]) - start
            too_long = dur + this > SHOT_MAX_S and dur >= SHOT_MIN_S * 0.7
            if chap or dur >= SHOT_MAX_S or too_long or (dur >= SHOT_MIN_S and (new_set or feats[i].animals)):
                out.append(cur)
                cur, cur_set = [], ""
        cur.append(i)
        cur_set = cur_set or feats[i].set_hint
    if cur:
        out.append(cur)
    return out


def _list_items(scenes: Sequence[Dict[str, Any]], feats: Sequence[R.Features]) -> List[str]:
    items: List[str] = []
    for i, f in enumerate(feats):
        if f.ordinal is None:
            continue
        for j in range(i, min(len(feats), i + 3)):
            names = [a[0] for a in feats[j].animals if a[0] not in ("boat", "cage", "tooth", "diver")]
            if names:
                items.append(names[0])
                break
    return items[:5]


def plan(scenes: Sequence[Dict[str, Any]], chapters: Sequence[float] = (), channel: str = "Ocean") -> OceanPlan:
    scenes = [dict(s) for s in scenes if str(s.get("text", "")).strip()]
    if not scenes:
        return OceanPlan(report={"shots": 0})
    total = max(float(s["end"]) for s in scenes)
    feats = [R.read(s["text"]) for s in scenes]
    chapters = sorted(float(c) for c in chapters)
    groups = _shots(scenes, feats, chapters)
    cards = _Cards(total, _list_items(scenes, feats))
    chapter_of = [sum(1 for c in chapters if c <= float(s["start"]) + 0.05) for s in scenes]
    you_count: Dict[int, int] = {}
    for i, f in enumerate(feats):
        if f.you:
            you_count[chapter_of[i]] = you_count.get(chapter_of[i], 0) + 1

    out = OceanPlan()
    seen_species: set = set()
    last_set = "open_water"
    carried = 0
    subject: Optional[Tuple] = None
    family_last: Dict[str, Tuple] = {}
    text_windows: List[Tuple[float, float, bool]] = []     # (from, to, corner card) - a corner card blocks only number captions
    events: List[float] = []
    enter_i = 0
    story_year = ""
    first_chapter_sent = {min((i for i, c in enumerate(chapter_of) if c == ch), default=-1) for ch in set(chapter_of)}

    for gi, g in enumerate(groups):
        s0, s1 = float(scenes[g[0]]["start"]), float(scenes[g[-1]]["end"])
        if gi + 1 < len(groups):
            s1 = float(scenes[groups[gi + 1][0]]["start"])
        st = OceanStage()
        new_chapter = g[0] in first_chapter_sent and gi > 0
        hint = next((feats[i].set_hint for i in g if feats[i].set_hint), "")
        carry = last_set if (not new_chapter and carried < CARRY_SET_SHOTS) else "open_water"
        set_name = hint or carry
        carried = 0 if hint else carried + 1
        set_args: Dict[str, Any] = {}
        depth_n = next((n for i in g for n in feats[i].numbers if n.kind == "depth"), None)
        if depth_n is not None:
            set_name = "depth_column"
            set_args = {"marks": [[0, "surface"], [depth_n.value, depth_n.raw]], "max_m": depth_n.value * 1.25}
        if set_name == "split_columns":
            set_args = {"left": {"label": "here"}, "right": {"label": "everywhere else", "color": [236, 120, 40, 255]}}
        st.set(0.0, set_name, set_args)
        last_set = set_name
        live: Dict[str, str] = {}                   # animal key -> element id
        live_t: Dict[str, Tuple] = {}               # animal key -> the reader's animal tuple
        live_pos: Dict[str, Tuple[float, float, str]] = {}
        shot_cards: List[str] = []
        shot_animals: List[str] = []
        last_event = 0.0
        sev: List[float] = []                       # this sentence's event times (shot clock)
        followers: Dict[str, List[Tuple[str, float, float]]] = {}     # a group's lead key -> [(id, dx, dy)] behind it
        tags: List[Tuple[str, float]] = []          # name tags shown in this shot: (id, removed at)

        def drop(k: str, at: float, exit: str = "fade") -> None:
            """The animal (and the rest of its group) leaves."""
            st.remove(live.pop(k), at, exit=exit)
            live_t.pop(k, None)
            for fid, _dx, _dy in followers.pop(k, []):
                st.remove(fid, at + 0.1, exit=exit)
            live_pos.pop(k, None)

        def glide(k: str, at: float, pos: Tuple[float, float], scale: Optional[float] = None, dur: Optional[float] = None) -> None:
            """Move an animal; its group keeps its place around it."""
            kw = {} if dur is None else {"dur": dur}
            st.move(live[k], at, pos=pos, scale=scale, **kw)
            for fid, dx, dy in followers.get(k, []):
                st.move(fid, at + 0.1, pos=(pos[0] + dx, pos[1] + dy), scale=scale, **kw)

        def place(animals: List[Tuple], at: float, shrink: bool = False, keep: bool = False, text: str = "") -> None:
            """Put the sentence's animals on stage at `at`. keep=True: the ones already there stay (the shark that
            flees from the orcas swims in beside them instead of replacing them)."""
            nonlocal enter_i, last_event
            if keep:
                new = [_key(a) for a in animals]
                animals = ([live_t[k] for k in live if k not in new] + list(animals))[-3:]
            keys = [_key(a) for a in animals][:3]
            if any(k not in live for k in keys):        # a new cast: the old one swims out so nothing overlaps
                for k in list(live):
                    if k not in keys:
                        drop(k, at)
            slots = _layout(len(keys))
            for (a, k), (x, y, face) in zip(zip(animals[:3], keys), slots):
                yy, s = (y + (110 if set_name in LOW_TEXT_SETS else 70), 0.78) if shrink else (y, 1.0)
                if a[0] == "boat":                        # boats float on the water line
                    yy = 236.0 if set_name == "surface" else 70.0
                    x = 860.0
                width = 520 if len(keys) == 1 else (440 if len(keys) == 2 else 360)
                if a[0] in ("tooth",):
                    width = 220
                if k in live:
                    glide(k, at, (x, yy), scale=s)
                else:
                    enter = ENTERS[enter_i % len(ENTERS)]
                    enter_i += 1
                    if face == "left" and enter == "slide_left":
                        enter = "slide_right"
                    group = a[1] and a[0] not in ("boat", "cage", "tooth", "diver")
                    live[k] = st.add("animal", at, _animal_args(a, face, int(width * (0.62 if group else 1.0))),
                                     pos=(x, yy), scale=s, enter=enter)
                    live_t[k] = a
                    if group:                       # a pod / school: the rest of the group behind the first ("two orcas" -> 2)
                        n_more = (_group_n(text, a) - 1) if text and a[3] >= 0 else 2
                        for dx, dy in ((-150, -70), (130, -110), (-260, 40), (220, 60))[: max(1, n_more)]:
                            fid = st.add("animal", at + 0.15, _animal_args(a, face, int(width * 0.5)), pos=(x + dx, yy + dy),
                                         scale=s, enter=enter, z=0)
                            followers.setdefault(k, []).append((fid, dx, dy))
                    shot_animals.append(a[0])
                    if k not in seen_species and a[0] not in ("boat", "cage", "tooth"):
                        seen_species.add(k)
                        if tags and tags[-1][1] > at + 0.3:      # one name at a time: the earlier tag steps aside
                            prev = st._get(tags[-1][0])
                            prev["t1"] = min(float(prev["t1"] or 1e9), at + 0.3)
                        tag = st.add("ocean_name_tag", at + 0.3 + (0.25 if tags and tags[-1][1] > at + 0.3 else 0.0),
                                     {"text": _label(a[4]), "_flat": True},
                                     pos=CARD_POS["name_tag"][0], enter="fade", anim=0.6)
                        st.remove(tag, at + 3.2, exit="fade")
                        tags.append((tag, at + 3.2))
                live_pos[k] = (x, yy, face)
            sev.append(at)

        def alive(t: float) -> None:
            """Keep the frame moving at t: the main animal drifts, or far-off shapes pass when nothing is on stage."""
            if live:
                k = next(iter(live))
                x, y, face = live_pos[k]
                nx = x + (90 if face == "right" else -90) * (1 if int(t) % 2 == 0 else -0.6)
                nx = min(1080.0, max(200.0, nx))
                glide(k, t, (nx, y + (12 if int(t) % 2 else -12)), dur=2.2)
                live_pos[k] = (nx, y, face)
            elif not any(e["kind"].startswith("ocean_") and e["t0"] <= t < (e["t1"] or 1e9) and e["kind"][6:] in FULL
                         for e in st.params()["elements"]):
                y = 210.0 + 60 * (int(t) % 3)
                for j in range(3):
                    sh = st.add("animal", t + j * 0.25, {"name": "dolphin", "width": 110, "silhouette": True},
                                pos=(-80.0 - j * 90, y + j * 26), enter="fade", z=0, float_=False)
                    st.move(sh, t + j * 0.25, pos=(1400.0 - j * 90, y + j * 26 - 30), dur=6.0)
                    st.remove(sh, t + j * 0.25 + 6.0, exit="none")
            else:
                return
            events.append(s0 + t)

        for i in g:
            sc, f = scenes[i], feats[i]
            rs, re_ = float(sc["start"]) - s0, float(sc["end"]) - s0
            sev.clear()
            yr = next((n.raw for n in f.numbers if n.kind == "year"), "")
            if yr:
                story_year = yr
            ctx = {"list_start": f.ordinal is not None, "subject": subject[0] if subject else None,
                   "subject_word": subject[4] if subject else None, "year": story_year}
            card = cards.choose(sc, f, ctx)
            animals = _resolve(list(f.animals), family_last)
            in_you = f.you and you_count.get(chapter_of[i], 0) >= 2 and float(sc["start"]) > 30
            if in_you and not any(a[0] == "diver" for a in animals):
                animals = [("diver", False, {}, 0, "diver")] + animals
            if not animals and not live:
                if subject is not None:
                    animals = [subject]
            named = [a for a in animals if a[0] != "diver" and a[3] >= 0 and a in f.animals]
            enter_at = max(0.0, rs)
            if named:                                    # the animal swims in when its name is said, not at the sentence start
                enter_at = max(enter_at, min(re_ - 1.0, _t_at(sc, min(a[3] for a in named)) - s0 - 0.25))
            if f.except_:
                here = [a for a in animals if _key(a) not in live and a in f.animals]
                nxt = here[0] if here else next((a for j in range(i + 1, min(len(feats), i + 4)) for a in feats[j].animals
                                                 if _key(a) not in live), None)
                if nxt is not None:
                    reveal = max(rs + 1.4, enter_at) if here else re_
                    sil = st.add("animal", rs + 0.2, _animal_args(nxt, "right", 560, silhouette=True), pos=(640, 380),
                                 enter="fade")
                    st.remove(sil, reveal, exit="fade")
                    events.append(s0 + rs + 0.2)
                    if here:
                        enter_at = reveal
                    else:
                        animals = []
            if OPENING_YOU.search(f.text) and float(sc["start"]) < 25 and not in_you:
                if set_name == "surface":            # "you're floating ... below you": seen from under the water, the diver above
                    st.set(rs, "open_water")
                    set_name = "open_water"
                me = st.add("animal", rs, {"name": "diver", "width": 150, "silhouette": True, "face": "right"},
                            pos=(560.0, 92.0), enter="fade", z=0)
                st.move(me, rs, pos=(640.0, 100.0), dur=max(1.0, re_ - rs))
                st.remove(me, re_ + 0.6, exit="fade")
                deep = next((a for a in animals if a in f.animals and a[0] not in ("boat", "cage", "tooth", "diver")), None)
                if deep is not None:                 # a far, dark shape deep down; the drawn animal rises in when named
                    far = st.add("animal", rs + 0.4, _animal_args(deep, "left", 260, silhouette=True), pos=(980.0, 590.0),
                                 enter="fade", z=0)
                    st.move(far, rs + 0.4, pos=(760.0, 560.0), dur=max(1.0, enter_at - rs))
                    st.remove(far, max(rs + 1.4, enter_at + 0.3), exit="fade")
                    enter_at = max(enter_at, rs + 1.6)
                events.append(s0 + rs)
            full_card = bool(card) and card["kind"] in FULL
            if animals:
                real = [a for a in animals if a[0] not in ("boat", "cage", "tooth", "diver")]
                if real:
                    subject = real[0]
                if not full_card:                        # a full-screen card first: the animals come in after it
                    shrink = bool(card) and card["kind"] not in ("halo", "size_bar", "crime_tape")
                    place(animals, enter_at, shrink, keep=f.flee is not None, text=f.text)
                    events.append(s0 + enter_at)
            if in_you:
                n = next((n for n in f.numbers if n.kind in ("depth", "length")), None)
                hud = st.add("ocean_diver_hud", rs + 0.2, {"depth": n.raw if n else "5 m", "air": 0.7 if i % 2 else 0.4,
                                                          "tip": ""}, pos=CARD_POS["diver_hud"][0], enter="fade")
                st.remove(hud, re_, exit="fade")
            if card:
                kind = card["kind"]
                at = max(rs, (card["at"] if "at" in card else _t_at(sc, card["pos"]) - 0.15) - s0)
                end = min(s1 - s0, max(re_, at + CARD_HOLD_S))
                if kind in FULL:
                    hold = LONG_FULL.get(kind, FULL_MAX_S)
                    if kind in LONG_FULL:
                        end = min(s1 - s0, max(end, at + hold - 1.5))      # let the scene play out past its sentence
                    end = min(end, at + hold)
                if kind in FULL:
                    for k in list(live):
                        drop(k, at)
                    live_pos.clear()
                    if kind == "island_map":           # plays out over its whole time: smooth steps, no bobbing
                        dur = max(1.0, end - at)
                        lf = card["args"].pop("leave_frac", None)
                        args = dict(card["args"], dur=dur, leave=(lf * dur) if lf is not None else None, _flat=True)
                        el = st.add("ocean_island_map", at, args, pos=(640, 360), enter="fade", anim=dur, float_=False)
                        next(e for e in st._els if e["id"] == el)["anim_steps"] = int(dur * 12)
                        next(e for e in st._els if e["id"] == el)["anim_delay"] = 0.0
                    else:
                        el = st.add("ocean_" + kind, at, dict(card["args"], _flat=True), pos=(640, 360),
                                    scale=0.9 if kind in ("paper", "shop", "wanted") else 1.0,
                                    enter="fade" if kind == "size_compare" else "pop", anim=1.2,
                                    float_=kind != "size_compare")
                else:
                    (x, y), sc_ = CARD_POS.get(kind, ((640, 190), 1.0))
                    if set_name in LOW_TEXT_SETS and kind in ("number_hero", "standoff", "progress") and y < 300:
                        y = 330                         # under the water line, never over the island / sky
                    if kind in ("number_hero", "standoff", "progress"):
                        drop_y = y + 200                # animals already on stage make room under the card
                        for k in list(live):
                            lx, ly, lf = live_pos[k]
                            if ly < drop_y:
                                glide(k, max(0.0, at - 0.3), (lx, drop_y), scale=0.78, dur=0.6)
                                live_pos[k] = (lx, drop_y, lf)
                    if kind == "size_bar" and live_pos:
                        lx, ly, _ = next(iter(live_pos.values()))
                        x, y = lx, ly + 120
                    if kind == "halo" and live_pos:
                        lx, ly, _ = next(iter(live_pos.values()))
                        x, y = lx, ly - 140
                    el = st.add("ocean_" + kind, at, dict(card["args"], _flat=True), pos=(x, y), scale=sc_,
                                enter="fade" if kind == "crime_tape" else "pop", anim=1.0)
                st.remove(el, end, exit="fade")
                back = [a for a in animals if a[0] != "diver"] or ([subject] if subject is not None else [])
                if kind in FULL and back and end < (s1 - s0) - 1.0:
                    place(back, end + 0.1, text=f.text)   # this sentence's animals (or the story's) come in after the card
                    events.append(s0 + end + 0.1)
                cards.took(kind, s0 + at, s0 + end)
                shot_cards.append(kind)
                events.append(s0 + at)
                if kind in TEXT_CARDS:
                    text_windows.append((s0 + at, s0 + end, kind in SIDE_CARDS))
                sev.append(at)
            if f.flee is not None and live:
                said = [a for a in f.animals if a[3] <= f.flee]        # the one named before "fled" is the one that runs
                k = next((_key(a) for a in sorted(said, key=lambda a: -a[3]) if _key(a) in live), None) or \
                    next((x for x in live if FAMILY.get(live_t.get(x, ("",))[0]) == (said[-1][2].get("generic") if said else None)), None) or \
                    next(iter(live))
                t_flee = max(enter_at + 1.2, _t_at(sc, f.flee) - s0)
                x_me = live_pos.get(k, (640.0, 0, "right"))[0]
                others = [v[0] for kk, v in live_pos.items() if kk != k]
                away_left = bool(others) and x_me < sum(others) / len(others)
                if others:                                 # turn tail first, then swim off away from the others
                    face = "left" if away_left else "right"
                else:
                    face = live_pos.get(k, (0, 0, "right"))[2]
                drop(k, t_flee, "slide_left" if face == "left" else "slide_right")
                events.append(s0 + t_flee)
                sev.append(t_flee)
            elif f.attack is not None and len(live) >= 2:
                ks = list(live)
                ax, ay, af = live_pos[ks[0]]
                bx, by, _ = live_pos[ks[1]]
                t_a = _t_at(sc, f.attack) - s0
                glide(ks[0], t_a, (ax + (bx - ax) * 0.45, ay + (by - ay) * 0.45))
                events.append(s0 + t_a)
                sev.append(t_a)
            # keep the frame alive: drift the main animal when nothing else happened for a while
            marks = sorted(set([last_event] + [x for x in sev if x >= last_event] + [re_ - 0.5]))
            for a_mark, b_mark in zip(marks, marks[1:]):
                t = a_mark
                while t + STILL_MAX_S < b_mark:
                    t += STILL_MAX_S
                    alive(t)
            last_event = max(last_event, marks[-2] if len(marks) > 1 else last_event,
                             max([t for t in sev] + [last_event]))
            while last_event + STILL_MAX_S < re_ - 0.5:       # no events at all in this sentence after the last one
                last_event += STILL_MAX_S
                alive(last_event)

        if gi == len(groups) - 1 and total >= END_CARD_MIN_S:     # watch-next end card over the last seconds of a full film
            at = max(0.0, (s1 - s0) - 5.0)
            st.clear(at, exit="fade")
            st.add("ocean_watch_next", at, {"channel": channel, "line": "more ocean predators", "_flat": True},
                   pos=(640, 360), enter="pop")
            text_windows.append((s0 + at, s1, False))
            shot_cards.append("watch_next")
        p = st.params()
        out.layers.append({"name": "ocean.lay_ocean", "start": round(s0, 3), "end": round(s1, 3), "params": p})
        out.shots.append({"start": round(s0, 3), "end": round(s1, 3), "set": set_name, "cards": shot_cards,
                          "animals": shot_animals, "scenes": [scenes[i].get("scene_no", i) for i in g]})
        events.append(s0)

    words: List[Tuple[str, float, float]] = []
    for sc in scenes:
        if sc.get("words"):
            words += CAP.as_words(sc["words"])
        else:
            words += CAP.words_from_text(str(sc["text"]), float(sc["start"]), float(sc["end"]))
    caps = CAP.plan(words, chapters=chapters, every_s=2.5)      # a phrase every few seconds, like the reference
    kept = []
    for c in caps:
        overlap = max([0.0] + [min(c["t1"], b) - max(c["t0"], a) for a, b, side in text_windows
                               if not side or c.get("kind") == "number"])
        if overlap <= 0.4 * (c["t1"] - c["t0"]):
            kept.append(c)
    out.captions = kept
    out.layers.append({"name": "ocean.lay_captions", "start": 0.0, "end": round(total, 3), "params": {"items": kept}})
    events += [c["t0"] for c in kept]
    ev = sorted(set(round(e, 2) for e in events if e <= total) | {0.0, round(total, 2)})
    lens = [s["end"] - s["start"] for s in out.shots]
    out.report = {"shots": len(out.shots), "shot_avg_s": round(sum(lens) / len(lens), 2), "shot_max_s": round(max(lens), 2),
                  "cards": dict(cards.counts), "captions": len(kept),
                  "longest_still_s": round(max(b - a for a, b in zip(ev, ev[1:])) if len(ev) > 1 else 0.0, 2),
                  "sets": sorted({s["set"] for s in out.shots}), "species": len(seen_species)}
    return out
