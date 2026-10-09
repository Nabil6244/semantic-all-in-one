"""Modern Tech News editorial logic: scene concepts, evidence framing, VisualDirector guidance and a deterministic
refinement of the VisualPlan the director returns. Wording-based rules only; no facts are stored or invented here
(products and components come from the script's own words)."""

from __future__ import annotations

import dataclasses
import math
import re
from typing import List, Optional

EDITING_SYSTEM = "modern_tech"

WORDS_PER_SECOND = 2.5
HOOK_SECONDS = 15.0
# the longest a scene may run before it is split (seconds); a scene is only split past cap * TOLERANCE
CAPS = {"HOOK": 2.5, "TECHNICAL_EXPLAINER": 5.0}
BODY_CAP = 4.0
TOLERANCE = 1.25
MIN_PIECE_WORDS = 4  # ~1.6 s, above the plan's 1.5 s minimum

_RX = lambda s: re.compile(s, re.I)  # noqa: E731

CONCEPT_RULES = [  # first match wins
    ("COMPARISON", _RX(r"\b(vs\.?|versus|compared (to|with)|than (the|its|last|before|apple|samsung)|outperforms?|beats?)\b")),
    ("QUOTE", re.compile(r"[\"“][^\"”]{12,}[\"”]|\b(said|says|told)\b")),
    ("TECHNICAL_EXPLAINER", _RX(r"\b(works by|uses? (a|an|two|three|the)|made (of|from)|consists? of|layers?|inside|mechanism|"
                                r"architecture|transistors?|cooling|reduces?|allows?|instead of|built on)\b")),
    ("NEWS", _RX(r"\b(announc\w*|unveil\w*|launch\w*|reports?|reported|reportedly|leak\w*|rumou?r\w*|revealed|confirmed|"
                 r"teased|keynote|event)\b")),
    ("EVIDENCE", _RX(r"\b(according to|documents?|filings?|benchmarks?|teardown|certification|patent|data shows?|tests? show)\b")),
    ("MARKET_CONTEXT", _RX(r"\b(market|sales|shipments|revenue|share|industry|competitors?|competition|analysts?|investors?)\b")),
    ("TIMELINE", _RX(r"\b(in (19|20)\d\d|since (19|20)\d\d|last year|next year|years? ago|generations?|first introduced)\b")),
    ("CONCLUSION", _RX(r"\b(in the end|ultimately|bottom line|remains to be seen|for now|time will tell|so the question)\b")),
]

EVIDENCE_RULES = [  # strongest framing first
    ("LEAKED", _RX(r"\b(leak\w*|surfaced|spotted|was found in code)\b")),
    ("RUMORED", _RX(r"\b(rumou?r\w*|tipped|said to be|whispers?)\b")),
    ("REPORTED", _RX(r"\b(reports?|reported|reportedly|according to|sources (say|familiar))\b")),
    ("ANALYSIS", _RX(r"\b(analysts?|expects?|expected|estimates?|forecasts?|predicts?|likely)\b")),
    ("SPECULATIVE", _RX(r"\b(could|might|may|possibly|perhaps|imagine)\b")),
    ("CONFIRMED", _RX(r"\b(announc\w*|confirmed|officially|unveil\w*|launched|released|introduced|is available|ships?)\b")),
]

UI_RX = _RX(r"\b(app|apps|interface|ui|settings|menu|controls?|gestures?|ai features?|drag|multitasking|split[- ]screen|home screen|lock screen|widgets?|notifications?|ios|android|windows|"
            r"macos|website|browser|chatbot|software|operating system|update|tap|swipe|screen recording|dashboard)\b")
EVENT_RX = _RX(r"\b(keynote|event|stage|unveil\w*|launch\w*|presentation|announc\w*)\b")
GENERIC_RX = _RX(r"\b(robots?|server room|data cent(er|re)|circuit board|motherboard|programmer|coder|hacker|"
                 r"(person|man|woman|people) (using|holding|typing)|typing on (a )?keyboard|office|futuristic|hologram\w*|"
                 r"digital (network|background)|abstract|technology background|tech gadget|cyber\w*|modern (smartphone|laptop|technology))\b")
DEVICE_RX = _RX(r"\b(smart)?phones?|foldables?|laptops?|tablets?|watch(es)?|headsets?|glasses|earbuds|chips?|processors?|gpus?|cpus?|"
                r"consoles?|cameras?|cars?|drones?|tvs?|monitors?|devices?|gadgets?|computers?|technology\b")
COMPONENT_RX = _RX(r"\b(hinge|display|screen|crease|camera( module)?|sensor|lens|battery|chip|processor|frame|port|keyboard|"
                   r"trackpad|speaker|cooling|antenna|stylus|button|bezel|notch|charger|charging|modem|memory|storage)\b")
_STOP = set("the this that it in on but and a an early so then now its their what when why how here there if we you i they he she "
            "yet still even just last next new our these those after before while with for from at by as of to or one two "
            "every some most all january february march april may june july august september october november december".split())
_OPENERS = set("imagine users user meanwhile however today also plus instead unlike compared finally first second third "
               "overall together both many most some people everyone nobody prices sales analysts reports rumors rumours leaks "
               "apps developers critics fans customers buyers owners others another each such without unfortunately "
               "interestingly importantly notably surprisingly clearly perhaps maybe yes no well right inside under over "
               "behind around above below thanks because although while since until unless whether folded unfolded "
               "closed opened open there's it's that's".split())
# units and spec words: never a name, never split from their number ("4,400 mAh", "120 Hz", "3 nm")
UNITS = set("mah ah gb tb mb kb hz ghz mhz mp nm mm cm kg g w v fps ppi nits megapixels megapixel millimetres millimeters "
            "millimetre millimeter grams gram inches inch percent hours watts".split())
_TOKEN = r"(?:i[A-Z][\w+]*|[A-Z][\w+\-]*|\d+[A-Za-z+]*)"
_RUN = re.compile(rf"(?<![\w']){_TOKEN}(?:\s+{_TOKEN})*")
_PRODUCT_WORD = _RX(r"^(pro|max|ultra|fold\d*|flip\d*|plus|mini|air|edge|lite|neo|elite)$")
_SPEC_TOKEN = re.compile(r"^(ip\d\d|[\d.,$]+)$", re.I)
_COMPANY_VERB = _RX(r"^(?:'s\b|\s+(says|said|announced|unveiled|launched|confirmed|introduced|released|calls|claims|dropped|"
                    r"added|made|makes|built|designed|revealed|teased|plans|is (launching|releasing|testing)))")
_REPORTS_AFTER = _RX(r"^\s*(reports?|reported|wrote|writes|tweeted|posted|notes|found|tested)\b")
_PERSON_SAYS = _RX(r"^\s*(says|said|told|explained)\b")
_PLACE_BEFORE = _RX(r"\b(in|at|from|across|near)\s+$")
COMPARE_RX = _RX(r"\b(than|vs\.?|versus|compared (to|with)|up from|down from|previous|predecessor|last year'?s|older|earlier|"
                 r"instead of|unlike|replaces?|successor to|over the)\b")
REFERS_RX = _RX(r"\b(it|its|it's|this|these|that|the (new |same )?(phone|device|model|foldable|laptop|tablet|chip|feature|update|"
                r"company|product|panel)|users?|owners?|in the hand|(demo|review|retail|test) units?)\b")
UI_FEATURE_RULES = [  # (pattern, canonical feature) — the feature words the narration itself uses
    (_RX(r"\bdrag(ging)?( and drop)?\b"), "drag and drop"),
    (_RX(r"\b(split[- ]screen|multitasking|multi-window|three apps|side by side)\b"), "multitasking"),
    (_RX(r"\bcamera controls?\b"), "camera control"),
    (_RX(r"\b(galaxy ai|ai features?)\b"), "AI features"),
    (_RX(r"\b(lock screen|home screen|widgets?)\b"), "lock screen"),
]
UI_NAME_RX = re.compile(r"\b(One UI \d+(?:\.\d+)?|iOS \d+|Android \d+|HyperOS \d*|Windows \d+|macOS \w+)\b")
TOPIC_RULES = [  # hardware/spec topic words from the narration -> a short searchable topic
    (_RX(r"\bhinge\b"), "hinge"), (_RX(r"\bcrease\b"), "crease"), (_RX(r"\b(display|screen|panel|glass)\b"), "display"),
    (_RX(r"\bcameras?\b|megapixels?"), "camera"), (_RX(r"\bbatter(y|ies)|mah\b"), "battery"),
    (_RX(r"\b(chip|processor|snapdragon|soc)\b"), "chip"), (_RX(r"\b(s pen|stylus)\b"), "S Pen"),
    (_RX(r"\b(weighs?|weight|lighter|heavier|grams)\b"), "weight"), (_RX(r"\b(thin|thinner|thinnest|thick|millimet)"), "thickness"),
    (_RX(r"\b(durab\w*|folds?\b.*\bcycles|stronger)\b"), "durability"), (_RX(r"\b(dust|water|ip\d\d)\b"), "dust resistance"),
    (_RX(r"\b(price|costs?|dollars|\$\d)"), "price"),
]
CINEMATIC_RX = _RX(r"\b(cinematic|macro|shot|extreme|dynamic|elegant|rendering|render|high-fidelity|3d|slow|slowly|rotating|"
                   r"studio|clean|prominent|typography|showing|illustrating|interactive|blueprint-style|structural|split|view|"
                   r"comparison|diagram|with|of|the|a|an|and|on|in|to|its|their)\b")


@dataclasses.dataclass
class SceneAnalysis:
    concept: str
    evidence: str  # "" when the line carries no framing
    hook: bool
    subject: str  # the product or company the scene is about ("" when none)
    component: str


@dataclasses.dataclass
class Mention:
    name: str
    product: bool
    comparison: bool  # named against the subject ("than the Fold 6", "up from 50 on the Fold 6")


def _product_key(name: str) -> str:
    """One key for a product's aliases: "Galaxy Z Fold 7", "Z Fold 7", "Fold 7", "Fold7" -> "fold 7"."""
    toks = name.lower().split()
    for i in range(len(toks) - 1, -1, -1):
        m = re.fullmatch(r"([a-z]+)(\d+)", toks[i])
        if m:
            return " ".join([m.group(1), m.group(2)] + toks[i + 1:])
        if toks[i].isdigit():
            return " ".join(toks[max(0, i - 1):])
    return " ".join(toks)


def _is_product(name: str) -> bool:
    toks = name.split()
    return any(re.search(r"\d", t) or re.match(r"i[A-Z]", t) or _PRODUCT_WORD.match(t) for t in toks) or len(toks) >= 2


def _runs(text: str, known: frozenset = frozenset()) -> List[Mention]:
    """Named products/companies in a line. Not a reporting outlet or person, not a place, not a unit, not a capitalised
    sentence opener ("Users", "Imagine", "Unfolded") unless it acts like a company ("Samsung says", "Apple's")."""
    out: List[Mention] = []
    text = text or ""
    for m in _RUN.finditer(text):
        if UI_NAME_RX.search(m.group(0)):
            continue  # software ("One UI 8", "iOS 26") is the UI the story shows, not the product it is about
        raw = m.group(0).split()
        before, after = text[:m.start()], text[m.end():]
        opener = not before.strip() or before.rstrip().endswith((".", "!", "?", ":", ";"))
        toks = [t[:-2] if t.endswith("'s") else t for t in raw]
        while toks and (toks[0].lower() in _STOP or toks[0].lower() in UNITS or _SPEC_TOKEN.match(toks[0])):
            toks = toks[1:]
        toks = [t for t in toks if t.lower() not in UNITS]
        if not toks or toks[0][0].isdigit():
            continue
        name = " ".join(toks)
        if len(toks) == 1 and not _is_product(name):
            if toks[0].lower() in _OPENERS or (opener and not _COMPANY_VERB.match(after) and name not in known):
                continue
        if _PLACE_BEFORE.search(before) or re.search(r"according to\s+$", before, re.I) or _REPORTS_AFTER.match(after):
            continue
        if len(toks) > 1 and _PERSON_SAYS.match(after) and not any(re.search(r"\d", t) for t in toks):
            continue  # a person speaking ("Tim Cook said")
        window = " ".join(before.split()[-8:])
        sentence_start = max(window.rfind("."), window.rfind("!"), window.rfind("?"))
        out.append(Mention(name, _is_product(name), bool(COMPARE_RX.search(window[sentence_start + 1:]))))
    return out


def _without_outlets(text: str) -> str:
    """The line minus its reporting outlets ("Android Authority reported", "according to Android Police"), so an outlet's
    name never reads as a UI/software word."""
    text = text or ""
    for m in reversed(list(_RUN.finditer(text))):
        if _REPORTS_AFTER.match(text[m.end():]) or re.search(r"according to\s+$", text[:m.start()], re.I):
            text = text[:m.start()] + text[m.end():]
    return text


def names(text: str) -> List[str]:
    """Capitalised product/company names in a text (guidance only)."""
    return [m.name for m in _runs(text)]


@dataclasses.dataclass
class StoryContext:
    """The one story a Modern Tech video tells: its primary company/product (locked once established), the products it
    is compared with, and the UI it shows. Built from the script's own words; nothing is invented."""

    primary_company: str = ""
    primary_product: str = ""
    primary_device: str = ""
    known_aliases: List[str] = dataclasses.field(default_factory=list)
    comparison_entities: List[str] = dataclasses.field(default_factory=list)
    ui_name: str = ""
    ui_features: List[str] = dataclasses.field(default_factory=list)
    known_names: frozenset = frozenset()

    @property
    def key(self) -> str:
        return _product_key(self.primary_product) if self.primary_product else ""

    def full(self, company: str, product: str, device: str = "") -> str:
        if product:
            return product if not company or product.lower().startswith(company.lower()) else f"{company} {product}"
        if company and device:
            return f"{company} new {device}" + (" device" if device.startswith("foldable") else "")
        return company


def _device(text: str) -> str:
    m = DEVICE_RX.search(text or "")
    word = m.group(0).lower() if m else ""
    return "" if word in ("technology", "device", "devices", "gadget", "gadgets") else word


def build_story(narrations: List[str]) -> StoryContext:
    """The story context from the whole script: the most-named product (comparisons don't count) is the primary one."""
    script = " ".join(narrations)
    known = set()
    for m in _RUN.finditer(script):  # names the script writes mid-sentence are names everywhere
        before = script[:m.start()].rstrip()
        if before and not before.endswith((".", "!", "?", ":", ";")):
            known.update(t[:-2] if t.endswith("'s") else t for t in m.group(0).split())
    known = frozenset(known)
    counts, display, first, companies, comps = {}, {}, {}, [], []
    for i, line in enumerate(narrations):
        for m in _runs(line, known):
            if not m.product:
                if m.name not in companies:
                    companies.append(m.name)
                continue
            k = _product_key(m.name)
            if len(m.name) > len(display.get(k, "")):
                display[k] = m.name
            if m.comparison:
                comps.append(k)
                continue
            counts[k] = counts.get(k, 0) + 1
            first.setdefault(k, (i, line.find(m.name)))
    if not counts:
        return StoryContext(primary_company=companies[0] if companies else "", known_names=known,
                            primary_device=_device(script))
    best = max(counts, key=lambda k: (counts[k], -first[k][0], -first[k][1]))
    product = display[best]
    company = ""  # the company named with the product ("Samsung's Galaxy Z Fold 7", "Apple announced the iPhone 17 Pro")
    for line in narrations:
        found = _runs(line, known)
        at = [i for i, m in enumerate(found) if m.product and _product_key(m.name) == best]
        if at:
            near = [m.name for m in found[:at[0]] if not m.product] or [m.name for m in found if not m.product]
            if near:
                company = near[-1] if near[-1] in [m.name for m in found[:at[0]]] else near[0]
                break
    aliases = sorted({n for k, n in display.items() if k == best} | {product, _product_key(product).title()}, key=len)
    ui = UI_NAME_RX.search(script)
    return StoryContext(company, product, _device(script), aliases,
                        [display[k] for k in dict.fromkeys(comps) if k != best], ui.group(0) if ui else "", [], known)


@dataclasses.dataclass
class SceneContext:
    company: str = ""
    product: str = ""
    device: str = ""
    topic: str = ""
    comparisons: List[str] = dataclasses.field(default_factory=list)
    ui: bool = False
    about: bool = False  # the line is about a named/inherited subject

    def subject(self, story: StoryContext) -> str:
        return story.full(self.company, self.product, self.device) if self.about else ""


def _topic(text: str, others: List[str]) -> str:
    for rx, feature in UI_FEATURE_RULES:
        if rx.search(text):
            return feature
    for rx, topic in TOPIC_RULES:
        if rx.search(text):
            return topic
    return others[0] if others else ""


def scene_context(story: StoryContext, current: SceneContext, text: str, concept: str) -> SceneContext:
    """This line's subject. The primary product holds unless the line names a different (non-comparison) product or
    company; comparison products are recorded, never adopted; an unnamed line inherits only when it refers back."""
    found = _runs(text, story.known_names)
    comps = [m.name for m in found if m.product and m.comparison]
    products = [m for m in found if m.product and not m.comparison]
    companies = [m.name for m in found if not m.product]
    if story.primary_product and not [c for c in companies if c.lower() != story.primary_company.lower()]:
        # a named part of the story product ("Armor FlexHinge"): a topic, not a new subject (a new model has a number)
        products = [m for m in products if re.search(r"\d", m.name) or re.match(r"i[A-Z]", m.name)
                    or _product_key(m.name) == story.key] + []
        parts = [m.name for m in found if m.product and not m.comparison and m not in products]
    else:
        parts = []
    primary_named = any(_product_key(m.name) == story.key for m in products) or (
        story.primary_company and story.primary_company in companies)
    others = parts + [m.name for m in products if _product_key(m.name) != story.key]
    dev = _device(text)
    ui = bool(UI_RX.search(_without_outlets(text)) or UI_NAME_RX.search(text))
    topic = _topic(text, others)
    if concept == "MARKET_CONTEXT":  # company/market talk: never the product's visual
        c = companies[0] if companies else ""
        return SceneContext(company=c, topic=topic, comparisons=comps, about=bool(c))
    if primary_named and story.primary_product:
        return SceneContext(story.primary_company, story.primary_product, story.primary_device, topic, comps, ui, True)
    if products:
        p = products[0].name
        same = current.product and _product_key(p) == _product_key(current.product)
        return SceneContext(companies[0] if companies else (current.company if same else ""), p, dev, topic, comps, ui, True)
    if companies:
        c = companies[0]
        if current.about and c.lower() == current.company.lower():
            return dataclasses.replace(current, topic=topic or current.topic, comparisons=comps, ui=ui)
        return SceneContext(c, "", dev, topic, comps, ui, True)
    refers = bool(REFERS_RX.search(text) or COMPONENT_RX.search(text) or ui or dev or parts)
    base = current if current.about else (SceneContext(story.primary_company, story.primary_product, story.primary_device)
                                          if story.primary_product else None)
    if refers and base is not None:
        hardware = COMPONENT_RX.search(text) or any(rx.search(text) for rx, _ in TOPIC_RULES)
        follow_ui = ui or (current.ui and not hardware)
        return dataclasses.replace(base, topic=topic or (current.topic if follow_ui else ""), comparisons=comps,
                                   ui=follow_ui, about=True)
    return SceneContext(comparisons=comps)


def classify_concept(text: str) -> str:
    for concept, rx in CONCEPT_RULES:
        if rx.search(text or ""):
            return concept
    return "PRODUCT" if names(text) else "CONTEXT"


def classify_evidence(text: str) -> str:
    """How the narration frames a claim (its wording only; not a fact check)."""
    for level, rx in EVIDENCE_RULES:
        if rx.search(text or ""):
            return level
    return ""


def analyze_scene(text: str, *, start: float = 0.0, story: Optional[StoryContext] = None) -> SceneAnalysis:
    concept = classify_concept(text)
    story = story or build_story([text])
    ctx = scene_context(story, SceneContext(), text, concept)
    comp = COMPONENT_RX.search(text or "")
    return SceneAnalysis(concept, classify_evidence(text), start < HOOK_SECONDS, ctx.subject(story),
                         comp.group(0).lower() if comp else "")


def search_query(story: StoryContext, ctx: SceneContext) -> str:
    """A short, factual, product-first search ("Samsung Galaxy Z Fold 7 hinge") — never the cinematic prompt."""
    subject = ctx.subject(story)
    if not subject:
        return ""
    parts = [subject]
    if ctx.ui and story.ui_name and story.ui_name.lower() not in subject.lower() and ctx.product:
        parts.append(story.ui_name)
    if ctx.topic and ctx.topic.lower() not in " ".join(parts).lower():
        parts.append(ctx.topic)
    return " ".join(parts)


def shorten_query(text: str, limit: int = 6) -> str:
    """A cinematic director prompt cut down to the searchable words (no new words)."""
    words = [w for w in re.findall(r"[\w$'’.-]+", text or "") if not CINEMATIC_RX.fullmatch(w)]
    return " ".join(words[:limit])


def is_relevant(candidate_text: str, story: StoryContext, ctx: SceneContext) -> bool:
    """Modern Tech relevance check for a named-product scene: the candidate's own text (title, alt, tags, page URL)
    must name the company or the product family — a door hinge, a starfield "galaxy" or a random smartphone fails."""
    if not ctx.product:
        return True
    toks = set(re.findall(r"[a-z]+|\d+", (candidate_text or "").lower()))
    if ctx.company and ctx.company.lower() in toks:
        return True
    key = _product_key(ctx.product).split()
    family, number = key[0], (key[1] if len(key) > 1 and key[1].isdigit() else "")
    return family in toks and (not number or number in toks)


def editorial_guidance(script: str = "") -> str:
    """Guidance text for the existing VisualDirector (its one free-text input)."""
    subjects = []
    for n in names(script):
        if n not in subjects and (_is_product(n) or len(subjects) < 6):
            subjects.append(n)
    lines = [
        "EDITING SYSTEM: Modern Tech News — a fast, clean, evidence-driven technology newsroom edit.",
        "Rhythm: the first 15 seconds change visual every 1-2.5 s; the body every 2-4 s; technical explanations 2-5 s; "
        "never longer than about 6 s. Hard cuts; no flashy transitions.",
        "Show the actual product, component, UI, event or report the narration names — never generic technology filler "
        "(no generic robots, server rooms, circuit boards, programmers, laptop users, futuristic backgrounds).",
        "Prefer real sources: official product images and press photos, official launch/keynote footage, real product "
        "photography, real screen recordings for software and UI. Stock only for ordinary real-world context. "
        "AI (flow_image/flow_video) only for unreleased products, internal mechanisms or concepts that cannot be filmed.",
        "Technical explanations progress: product -> component close-up -> technical diagram -> back to the product.",
        "Software, app or UI features: youtube_video searches for the real feature demo, not stock footage.",
        "Searches name the product and the part: '<product name> hinge close-up', not 'modern smartphone technology'.",
    ]
    if subjects:
        lines.append("Named subjects in this script: " + ", ".join(subjects[:12]) + ".")
    return "\n".join(lines)


def _split_narration(text: str, pieces: int) -> List[str]:
    """Split at word boundaries (preferring a comma near each cut), never inside a product name ("Galaxy Z Fold | 7") or
    between a number and its unit ("4,400 | mAh"); the pieces joined by spaces give the text back unchanged."""
    words = text.split()
    if pieces < 2 or len(words) < MIN_PIECE_WORDS * 2:
        return [text]
    pieces = min(pieces, len(words) // MIN_PIECE_WORDS)
    cuts, last = [], 0

    def ok(j):
        return last + MIN_PIECE_WORDS <= j <= len(words) - MIN_PIECE_WORDS

    def protected(j):
        a, b = words[j - 1], words[j]
        if a.endswith((",", ";", ":", ".", "!", "?")):
            return False
        name = bool(re.match(r"[A-Z0-9$]|i[A-Z]", a) and re.match(r"[A-Z0-9]|i[A-Z]", b))
        unit = bool(re.search(r"\d", a) and b.lower().strip(".,;:!?") in UNITS)
        return name or unit

    for k in range(1, pieces):
        target = round(len(words) * k / pieces)
        near = [target + d for d in (0, 1, -1, 2, -2, 3, -3) if ok(target + d)]
        best = next((j for j in near if words[j - 1].endswith((",", ";", ":", "."))), None)
        best = best or next((j for j in near if not protected(j)), None)
        if best is None:
            continue
        cuts.append(best)
        last = best
    bounds = [0] + cuts + [len(words)]
    return [" ".join(words[a:b]) for a, b in zip(bounds, bounds[1:]) if b > a]


def _set_source(scene, asset_type: str, query: str, description: str = "") -> None:
    from visual_director.schema import ASSET_TYPE_TO_PROVIDER

    scene.asset_type = asset_type
    scene.provider_preference = ASSET_TYPE_TO_PROVIDER.get(asset_type, asset_type)
    if asset_type in ("image", "video"):
        scene.visual_description = description or query
        scene.search_queries = [q.strip() for q in query.split("||") if q.strip()] if description else []
    else:
        scene.search_queries = [q.strip() for q in query.split("||") if q.strip()]
        scene.visual_description = description or scene.search_queries[0]


def _prompt_text(scene) -> str:
    if scene.asset_type in ("image", "video"):
        return scene.visual_description or ""
    return " || ".join(scene.search_queries) if scene.search_queries else (scene.visual_description or "")


def _strip_flow_fallbacks(scene) -> None:
    scene.fallbacks = [f for f in scene.fallbacks if f not in FLOW_FALLBACKS]


FLOW_TYPES = ("image", "video")
FLOW_FALLBACKS = {"flow_video", "video", "flow_image", "image", "flow"}
SEARCH_TYPES = ("stock_video", "stock_image", "stock", "youtube_video")


# Lines whose meaning is movement or behaviour — the only lines where real footage beats a still.
MOTION_RX = _RX(r"\b(opens|opening|(not|fails? to|won'?t|can'?t|doesn'?t|didn'?t) open|unfolds|unfolding(?! (screen|phone|display|device|glass))|folds|folding(?! (screen|phone|display|device|smartphone|glass))|folded shut|"
                r"closes|closing|snaps?|in (the|your|a|their|the user'?s) "
                r"hands?|holding|handled|drag\w*|drag and drop|swip\w*|taps?|tapping|scroll\w*|gestures?|demo\w*|demonstrat\w*|"
                r"plays?|playing|records?|recording|moves?|moving|spins?|rotates?|slides?|sliding|bends?|bending|"
                r"multitasking|split[- ]screen|side by side|in action|hands-on)\b")


def needs_motion(text: str, ctx: SceneContext, concept: str, evidence: str) -> str:
    """Why this line needs real footage ("" = a still serves it): a UI interaction, a launch/event, the product handled or
    moving, or reported behaviour that video proves."""
    if ctx.ui:
        return "UI interaction"
    if EVENT_RX.search(text) and concept in ("NEWS", "HOOK", "PRODUCT", "CONTEXT"):
        return "launch/event"
    if MOTION_RX.search(text):
        return "reported behaviour" if evidence in ("REPORTED", "LEAKED", "RUMORED") else "product in motion"
    return ""


def _route(scene, a: SceneAnalysis, story: StoryContext, ctx: SceneContext, log) -> None:
    """Source and search for one shot, by what the line needs, not by the product having a name:
    - no subject: keep the director's visual, but cut a cinematic paragraph down to a short search;
    - a Flow scene stays Flow unless its prompt is truly generic filler (robot, server room...); its fallback search
      becomes the product query;
    - a line that needs motion (UI interaction, launch/event, product handled/moving, behaviour) -> YouTube footage of
      the story product, falling back to a product still;
    - everything static (product still, spec, component, material, comparison) -> a product-first still, no fallback.
    Never creates AI."""
    prompt = _prompt_text(scene)
    query = search_query(story, ctx)
    ai = scene.asset_type in FLOW_TYPES
    searchable = scene.asset_type in SEARCH_TYPES
    before = prompt
    if not query:
        if searchable and len(" ".join(scene.search_queries).split()) > 8:
            short = shorten_query(scene.search_queries[0] if scene.search_queries else scene.visual_description)
            if short:
                scene.search_queries = [short]
                log(scene, "query", "cinematic prompt -> short search", before)
        elif GENERIC_RX.search(prompt):
            log(scene, "filler", "generic visual kept: the narration names no subject to show instead")
        return
    if ai and not GENERIC_RX.search(prompt):  # an allocated Flow visual (diagram, mechanism, reconstruction): keep it
        scene.search_queries = [query]
        scene.fallbacks = ["stock_image"]
        log(scene, "flow", "allocated Flow visual kept; fallback search is the product query", before)
        return
    if not searchable and not ai:
        return  # map, archive, NASA, local: not Modern Tech's to reroute
    motion = needs_motion(scene.narration, ctx, a.concept, a.evidence)
    if motion and (ctx.product or ctx.ui):
        full = story.full(ctx.company, ctx.product) or query
        if ctx.ui:
            qs = [query, f"{query} demo", f"{full} {story.ui_name}".strip()]
        elif motion == "launch/event":
            qs = [f"{full} official launch event", query, f"{full} unveiled"]
        else:
            qs = [query, f"{query} hands-on", f"{full} review"]
        _set_source(scene, "youtube_video", "||".join(dict.fromkeys(q.strip() for q in qs if q.strip())))
        scene.fallbacks = ["stock_image"]  # the first query, a product-specific still
        log(scene, "motion", f"{motion} -> real footage of '{ctx.subject(story)}'", before)
        return
    _set_source(scene, "stock_image", query)
    scene.fallbacks = []
    why = f"compared with {ctx.comparisons[0]}" if ctx.comparisons else (ctx.topic or "product") + " shown as a still"
    log(scene, "still", f"{why} -> product-first still", before)


def _piece_context(ctx: SceneContext, text: str) -> SceneContext:
    """A split piece keeps the story subject but takes its topic (and UI state) from its own words."""
    topic = _topic(text, [])
    ui = bool(UI_RX.search(_without_outlets(text))) or (ctx.ui and not (COMPONENT_RX.search(text) or
                                                                         any(rx.search(text) for rx, _ in TOPIC_RULES)))
    comps = [m.name for m in _runs(text) if m.product and m.comparison]
    return dataclasses.replace(ctx, topic=topic or ctx.topic, ui=ui, comparisons=comps)


def _diagram(scene, story: StoryContext, ctx: SceneContext) -> None:
    part = ctx.topic or "mechanism"
    _set_source(scene, "image", search_query(story, ctx), f"clean technical cutaway diagram of the {part} of the "
                f"{ctx.subject(story)}, neutral grey background, studio lighting, precise engineering illustration, "
                "no text, no logos")
    scene.fallbacks = ["stock_image"]


def refine_plan(plan, *, on_log=None) -> List[dict]:
    """Refine a VisualPlan in place for Modern Tech News: one story context for the whole script, a scene context per
    line (comparison products never take over), rhythm splits that never cut a product name or a unit, and per shot a
    source chosen by need — real footage only where the line needs motion, a product-first still otherwise.
    Cost-neutral: it never adds a Flow video, and each original Flow scene stays at most one Flow generation (a piece
    may use it for a technical diagram only when routing freed it). Runs after the existing allocation, so the user's
    Flow budget stays the ceiling. Returns the decisions and a per-shot context trace (debug)."""
    from visual_director.schema import MAX_DURATION, MIN_DURATION

    changes: List[dict] = []
    story = build_story([s.narration for s in plan.scenes])

    def log(scene, kind, reason, before=None, a=None):
        entry = {"_sc": scene, "kind": kind, "reason": reason, "before": before,
                 "after": _prompt_text(scene) if before is not None else None}
        if a is not None:
            entry.update(concept=a.concept, evidence=a.evidence)
        changes.append(entry)

    out, contexts, clock, ctx = [], [], 0.0, SceneContext()
    for scene in plan.scenes:
        concept = classify_concept(scene.narration)
        ctx = scene_context(story, ctx, scene.narration, concept)
        evidence = classify_evidence(scene.narration)
        comp = COMPONENT_RX.search(scene.narration)
        a = SceneAnalysis(concept, evidence, clock < HOOK_SECONDS, ctx.subject(story), comp.group(0).lower() if comp else "")
        est = len(scene.narration.split()) / WORDS_PER_SECOND
        cap = CAPS["HOOK"] if a.hook else CAPS.get(a.concept, BODY_CAP)
        was_flow = scene.asset_type in FLOW_TYPES
        pieces = [scene.narration]
        if est > cap * TOLERANCE:
            if was_flow and not a.subject:
                log(scene, "pacing", f"~{est:.1f}s AI scene kept as one shot: no real subject to cut to and no extra Flow "
                                     "generation", a=a)
            else:
                pieces = _split_narration(scene.narration, math.ceil(est / cap))
        template = dataclasses.replace(scene, search_queries=list(scene.search_queries), fallbacks=list(scene.fallbacks))
        flow_left = False
        seen_queries = set()
        for i, text in enumerate(pieces):
            sc = scene if i == 0 else dataclasses.replace(template, search_queries=list(template.search_queries),
                                                          fallbacks=list(template.fallbacks))
            sc.narration = text
            sc.duration = round(max(MIN_DURATION, min(MAX_DURATION, len(text.split()) / WORDS_PER_SECOND)), 2)
            pctx = _piece_context(ctx, text) if len(pieces) > 1 else ctx
            pa = dataclasses.replace(a, concept=classify_concept(text) if len(pieces) > 1 else concept,
                                     evidence=classify_evidence(text) if len(pieces) > 1 else evidence)

            def piece_log(s2, kind, reason, before=None, pa=pa):
                log(s2, kind, reason, before, pa)

            if i and sc.asset_type in FLOW_TYPES:  # a later piece of a Flow scene: never another generation by default
                if flow_left and pctx.about and (pa.concept == "TECHNICAL_EXPLAINER" or a.concept == "TECHNICAL_EXPLAINER"):
                    _diagram(sc, story, pctx)
                    flow_left = False
                    piece_log(sc, "diagram", "technical piece uses the original scene's freed Flow generation")
                    out.append(sc)
                    contexts.append((sc, pctx))
                    continue
                sc.asset_type, sc.provider_preference = "stock_image", "stock_image"
                q = search_query(story, pctx)
                sc.search_queries = [q] if q else [shorten_query(sc.visual_description)]
                _strip_flow_fallbacks(sc)
            _route(sc, pa, story, pctx, piece_log)
            if i == 0:
                flow_left = was_flow and sc.asset_type not in FLOW_TYPES  # routing freed the one generation
            if i and sc.asset_type not in FLOW_TYPES:
                _strip_flow_fallbacks(sc)
            if sc.search_queries and sc.search_queries[0] in seen_queries and sc.asset_type == "stock_image":
                base = sc.search_queries[0]  # the next view of the same thing, not a repeat
                sc.search_queries = [next((v for v in (f"{base} close-up", f"{base} detail", f"{base} product photo")
                                           if v not in seen_queries), f"{base} side view")]
            seen_queries.update(sc.search_queries[:1])
            out.append(sc)
            contexts.append((sc, pctx))
        if len(pieces) > 1:
            log(scene, "pacing", f"{'HOOK' if a.hook else a.concept} scene of ~{est:.1f}s split into {len(pieces)} "
                                 f"shots (cap {cap:g}s)", a=a)
        clock += est
    for n, sc in enumerate(out, 1):
        sc.scene_id = n
    for c in changes:  # report final scene numbers
        c["scene"] = c.pop("_sc").scene_id
        c.setdefault("concept", "")
    trace = [{"scene": sc.scene_id, "kind": "context", "primary_company": story.primary_company,
              "primary_product": story.primary_product, "comparison_entities": c.comparisons or story.comparison_entities,
              "scene_subject": c.subject(story), "scene_topic": c.topic, "search_query": _prompt_text(sc),
              "source": sc.asset_type, "fallbacks": list(sc.fallbacks)} for sc, c in contexts]
    plan.scenes = out
    if on_log:
        on_log(f"[MODERN TECH] story: company={story.primary_company!r} product={story.primary_product!r} "
               f"aliases={story.known_aliases} comparisons={story.comparison_entities} ui={story.ui_name!r}")
        for c in changes:
            on_log(_describe(c))
        for t in trace:
            on_log(f"[MODERN TECH] scene {t['scene']} | subject={t['scene_subject'] or '-'} | topic={t['scene_topic'] or '-'} | "
                   f"compare={t['comparison_entities'] or '-'} | {t['source']} | {t['search_query'][:90]}")
    return changes + trace


def flow_generations(plan) -> dict:
    """Flow work a plan can trigger: scenes that ARE Flow, and scenes that could FALL BACK to Flow."""
    return {"video": sum(s.asset_type == "video" for s in plan.scenes),
            "image": sum(s.asset_type == "image" for s in plan.scenes),
            "fallback": sum(any(f in FLOW_FALLBACKS for f in s.fallbacks) for s in plan.scenes if s.asset_type not in FLOW_TYPES)}


def _describe(c: dict) -> str:
    s = f"[MODERN TECH] scene {c['scene']} {c['kind']}: {c['reason']}"
    if c.get("kind") == "context":
        return str(c)
    if c.get("concept"):
        s += f" (concept {c['concept']}{', evidence ' + c['evidence'] if c.get('evidence') else ''})"
    if c.get("before") is not None:
        s += f"\n    before: {c['before'][:90]!r}\n    after:  {c['after'][:90]!r}"
    return s


def smart_editing_settings(base):
    """Modern Tech sound and cut rules on the existing Smart Editing settings: VO + music first, restrained SFX, hard
    cuts dominating (few transitions survive), no ambience bed."""
    return dataclasses.replace(base, intensity="low", sound_effects_intensity="low", visual_transitions_intensity="low",
                               text_effects_intensity="low", scene_ambience=False)
