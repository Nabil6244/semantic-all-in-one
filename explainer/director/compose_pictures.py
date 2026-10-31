"""Real pictures for thin boards (opt-in, DirectorOptions.pictures). Nothing here fetches anything: a picture is only a REFERENCE "<source>:<query>" that the application's own "Get the scenes"
step resolves later (stock_image, stock_video ...), exactly like the footage beats and the map photo cards. With the switch off none of this runs and the plan is byte for byte today's.

Four parts:
  1. thin_beat_metrics(items, dur): how thin a FINISHED board beat is (occupancy, distinct elements, longest still gap, text-only share). Used for the report.
  2. upgrade_boards / upgrade_thin_board: before the boards are drawn, a board beat that is predicted thin (few things a picture can show) AND whose narration names a pictureable subject (a named
     person / place / event, a camera-filmable object, an evidence word) becomes a footage beat (a still by default) with a good query. The hook, questions, numbers, the share cap and "no three in
     a row" are the footage rules of select.py (footage_blocked, footage_run_blocked), not copies.
     Order of preference: (a) a local archive picture of the subject when archive.json has one (the existing archive beat, Ken Burns), (b) a still/footage beat with a query, (c) the board stays
     (compose_fill and the recipes handle it). A board clip is drawn before assets exist, so a board cannot hold a not-yet-fetched picture: a placeholder-free design keeps (b) as a beat of its own.
  3. build_query: queries made of words the beat SPEAKS (relevance.py demands it): full proper names from the script, a disambiguating spoken context word for a weak name, no vague words.
  4. map_card_wants: the names for the photo cards of a map beat.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ..beats.relevance import beat_tokens, find_phrase, toks as _toks
from . import lexicon as LX
from . import meaning as MN

PICTURE_SHARE = 0.18                 # the largest share of the runtime the picture pass may turn into picture beats (on top of footage_share's own beats)
MAX_QUERY_WORDS = 4
QUERY_MAX_USES = 2                   # one subject's picture is not shown more than twice in a video
STILL_SOURCE = "stock_image"
THIN_OCCUPANCY = 0.16                # a finished board whose busiest instant covers less than this share of the content area is thin
THIN_STILL_S = 2.6
THIN_TEXT_ONLY = 0.75
THIN_ELEMENTS = 3

CONNECTORS = frozenset("of de del da von van la le the du des al".split())
VAGUE = frozenset("""remote small big large great old new many several certain some other such very whole entire little long huge tiny distant far strange unusual local famous important main major
first last next early late various different same own other another one two three few""".split())
GENERIC_ALONE = frozenset("""island islands sea ocean city cities town river coast mountain mountains ship ships boat boats army soldiers troops king queen emperor people man men woman women place land
country countries world war battle empire kingdom port harbour harbor road street field fields forest desert""".split())
WEAK_NAMES = frozenset("""prussia russia austria france spain britain england germany italy portugal europe asia africa america china india empire kingdom republic state nation world""".split())
CONTEXT = frozenset("""army armies navy fleet troops soldiers king queen emperor capital palace castle city port harbour harbor flag battle war treaty cannon cathedral parliament church government
revolution coup siege fortress ships ship island coast river bridge""".split())
EVIDENCE_WORDS = frozenset("portrait painting photograph photo letter treaty document map flag statue monument manuscript diary".split())
PICTURE_KINDS_STYLES = ("tile", "circle", "figure", "crowd", "prop", "photo", "set", "node")


# ------------------------------------------------------------------ 1. thin metrics (a finished board beat)

def _drawn(it) -> bool:
    return it.kind not in ("narrator", "arrow") and it.style != "set"


def _is_picture(it) -> bool:
    return bool(it.asset) or it.kind == "icon" or it.style in PICTURE_KINDS_STYLES


def thin_beat_metrics(items: Sequence[Any], dur: float) -> Dict[str, Any]:
    """Deterministic thinness of a finished board beat from its dry_build items (`dur` = beat length in s). Thin = at least two of: low occupancy, few distinct elements, a long still gap, text only."""
    from .compose_fill import beat_occupancy
    drawn = [it for it in items if _drawn(it)]
    onsets = sorted({0.0, *[round(float(it.onset), 3) for it in drawn], float(dur)})
    gap = max((b - a for a, b in zip(onsets, onsets[1:])), default=float(dur))
    pics = [it for it in drawn if _is_picture(it)]
    n = len(drawn)
    text_only = round((n - len(pics)) / n, 3) if n else 1.0
    occ = beat_occupancy(items)
    why: List[str] = []
    if occ < THIN_OCCUPANCY:
        why.append(f"occupancy {occ:.2f} below {THIN_OCCUPANCY}")
    if n < THIN_ELEMENTS:
        why.append(f"{n} visual element(s)")
    if gap > THIN_STILL_S:
        why.append(f"a {gap:.1f} s gap without a change")
    if text_only >= THIN_TEXT_ONLY and n:
        why.append(f"text-only share {text_only:.2f}")
    return {"occupancy": occ, "elements": n, "pictures": len(pics), "longest_still_s": round(gap, 2), "text_only_share": text_only, "thin": len(why) >= 2, "why": why}


# ------------------------------------------------------------------ 5. period (era) relevance

ORDINALS = {w: n for n, w in enumerate("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth "
                                       "nineteenth twentieth".split(), 1)}
ORDINAL_DIGITS = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)$")
ERA_WORDS = {"ancient": -300, "antiquity": -300, "roman": 200, "rome": 200, "byzantine": 700, "medieval": 1000, "viking": 900, "vikings": 900, "crusade": 1150, "crusades": 1150, "crusaders": 1150,
             "crusading": 1150, "renaissance": 1500, "feudal": 1100, "pharaoh": -1500, "pharaohs": -1500, "caliphate": 800, "samurai": 1400}
ERA_RESET = frozenset("today nowadays modern present currently".split())          # the narration comes back to the present: a photograph is right again
ERA_BEFORE_YEAR = 1800                  # before this a photograph of the subject cannot be period-correct: the picture must be historical art, an old map ... or the scene stays illustrated
ERA_LOOKBACK_S = 75.0                   # the last date the narration gave, at most this far back, still sets the period of a beat that names none
ERA_MODIFIERS = (("historical", "painting"), ("antique", "engraving"))      # (before 1500, 1500-1800): words a search engine understands as "old art", appended to the spoken query
ERA_QUERY_WORDS = frozenset(w for m in ERA_MODIFIERS for w in m)
HISTORIC_HEADS = frozenset("""empire empires kingdom kingdoms dynasty dynasties republic caliphate sultanate battle battles siege war wars treaty crusade crusades conquest invasion rebellion revolution
council coronation emperor emperors king queen pharaoh sultan caesar legion legions knights knight cathedral basilica fortress castle temple pyramid pyramids ruins manuscript fresco mosaic""".split())
MODERN_WORDS = frozenset("""vaporetto vaporettos ferry ferries cruise cruiseship tourist tourists tourism modern skyline skyscraper skyscrapers drone aerial car cars bus buses traffic train tram airport
airplane plane motorboat speedboat yacht yachts jetski kayak kayaks paddleboard cafe restaurant hotel shopping smartphone selfie neon nightlife wedding bride fashion business office laptop cityscape
urban apartment toy toys model models diorama dioramas reenactment reenactments reenactor reenactors reenacting figurine figurines lego cosplay costume costumes replica replicas souvenir souvenirs
gladiators-show actor actors actress""".split())
ART_WORDS = frozenset("""painting paintings painted engraving engravings etching etchings woodcut woodcuts lithograph lithographs illustration illustrations drawing drawings sketch fresco frescoes mural mosaic
manuscript tapestry portrait portraits artwork oil canvas parchment map maps print prints""".split())     # what a fetched picture must SAY it is: "historic"/"antique" alone also describe a modern photo of ruins or a toy army
PERIOD_WORDS = frozenset("""painting paintings painted engraving engravings etching etchings illustration illustrations drawing drawings sketch fresco mosaic manuscript miniature tapestry sculpture sculpted statue
bust relief antique vintage old ancient historic historical medieval renaissance roman ruins ruin map maps cartography parchment oil canvas gallery museum artwork art""".split())


def era_year(tokens: Sequence[str], resets: bool = True) -> Optional[int]:
    """The year a run of spoken tokens speaks of, or None. A four-digit year (800-2100), "fifth and sixth centuries" (the middle of the latest one named), or an era word (ancient, medieval, Roman,
    Byzantine ...). A return to the present ("today", "modern") answers 2026 unless `resets` is False. The LAST such mention in the run wins (the narration moves on), but a date or a century
    beats an era word: "the western roman empire collapsed" in the 5th century is the 5th century, and "in 1204 ... the byzantine empire" is 1204."""
    t = list(tokens)
    found: List[Tuple[int, int]] = []                  # (position, year)
    words_only: List[Tuple[int, int]] = []             # era words: only when no date or century is spoken
    for i, w in enumerate(t):
        if w.isdigit() and len(w) == 4 and 800 <= int(w) <= 2100:
            found.append((i, int(w)))
        elif w in ("century", "centuries"):
            ns = []
            for k in range(max(0, i - 4), i):
                if t[k] in ORDINALS:
                    ns.append(ORDINALS[t[k]])
                else:
                    m = ORDINAL_DIGITS.match(t[k])
                    if m:
                        ns.append(int(m.group(1)))
            if ns:
                bc = i + 1 < len(t) and t[i + 1] in ("bc", "bce")
                n = max(ns)
                found.append((i, -(n * 100 - 50) if bc else (n - 1) * 100 + 50))
        elif w in ERA_WORDS:
            words_only.append((i, ERA_WORDS[w]))
        elif w in ERA_RESET and resets:
            found.append((i, 2026))
    found = found or words_only
    return max(found)[1] if found else None


def era_of_beat(words, b) -> Dict[str, Any]:
    """{"year", "why"} for beat b: the last period its own words name, else the last period the narration named in the ERA_LOOKBACK_S before it; {"year": None} when the narration names none."""
    own = era_year([t["tok"] for t in beat_tokens(words, b.start, b.end)])
    if own is not None:
        return {"year": own, "why": "named in the beat's own words"}
    before = [t["tok"] for t in beat_tokens(words, max(0.0, b.start - ERA_LOOKBACK_S), b.start)]
    y = era_year(before, resets=False)                  # "today" speaks of its own sentence; it does not make the next beats modern
    return {"year": y, "why": "the last period named earlier in the narration" if y is not None else "no period named"}


def era_modifier(year: Optional[int]) -> List[str]:
    """Words that turn a query into a search for old art: [] when the period is unknown or 1800 and later."""
    if year is None or year >= ERA_BEFORE_YEAR:
        return []
    return list(ERA_MODIFIERS[0 if year < 1500 else 1])


def relevance_accepts_era() -> bool:
    """The relevance gate (explainer/beats/relevance.py) wants every query word spoken. The era words are accepted only when that module says so (ERA_QUERY_WORDS); until then the planner keeps
    the plan valid by choosing only subjects that are historic by themselves and by vetting the fetched picture."""
    from ..beats import relevance as R
    return bool(getattr(R, "ERA_QUERY_WORDS", None)) and ERA_QUERY_WORDS <= set(getattr(R, "ERA_QUERY_WORDS"))


def history_safe(words_: Sequence[str]) -> bool:
    """A subject that stock search returns as history without help ("Western Roman Empire", "Battle of Waterloo", "Byzantine Empire"): it names an empire, battle, ruler or monument."""
    ws = set(words_)
    return bool(ws & HISTORIC_HEADS) or bool(ws & set(ERA_WORDS))


SUBJECT_GENERIC = frozenset("""the a an of and in on at to for with from by western eastern northern southern central great late early upper lower new old ancient medieval historical historic painting
engraving antique empire empires kingdom kingdoms state states era age period history war wars city town region land people world""".split())
SUBJECT_ALIASES = {"roman": {"rome", "romans", "forum", "colosseum", "coliseum", "pantheon", "latin", "pompeii", "caesar", "aqueduct"}, "byzantine": {"constantinople", "hagia", "sophia"},
                   "greek": {"greece", "athens", "parthenon", "acropolis"}, "egyptian": {"egypt", "pharaoh", "pyramid", "pyramids", "sphinx", "nile"}, "venetian": {"venice", "venezia"}}


def subject_words(query: str) -> Set[str]:
    """The distinctive words of a picture request ("Western Roman Empire historical painting" -> {roman} plus its aliases): the words that say WHAT it is about, not the era or the kind of art."""
    base = {w for w in re.findall(r"[a-z]+", str(query or "").lower()) if len(w) > 2 and w not in SUBJECT_GENERIC}
    out = set(base)
    for w in base:
        out |= SUBJECT_ALIASES.get(w, set())
    return out


def request_year(prompt: str) -> Optional[int]:
    """The period a picture REQUEST asks for: the planner ends the query with ERA_MODIFIERS ("... historical painting" before 1500, "... antique engraving" 1500-1800). None for any other request."""
    p = " ".join(str(prompt or "").lower().split())
    for (a, b), yr in zip(ERA_MODIFIERS, (1000, 1650)):
        if p.endswith(f"{a} {b}"):
            return yr
    return None


def request_subject(prompt: str) -> str:
    """The query without its two era words."""
    return " ".join(str(prompt or "").split()[:-2])


def vet_picture(meta: Mapping[str, Any], year: Optional[int], subject: Optional[str] = None, curated: bool = False) -> Tuple[bool, str]:
    """Cheap period check of a FETCHED picture from what the provider says about it (the words of its page URL, its alt text/tags/title as recorded by the application's manifest). For a beat before
    ERA_BEFORE_YEAR the picture must say it is old art or a historic place (PERIOD_WORDS) and must not say it is modern (MODERN_WORDS); otherwise any picture passes. Unknown metadata fails: a
    picture nobody can vouch for does not replace an illustration."""
    if year is None or year >= ERA_BEFORE_YEAR:
        return True, "the narration is not before 1800"
    blob = " ".join(str(meta.get(k, "") or "") for k in ("source_url", "alt", "tags", "title", "description", "prompt_text"))
    ws = set(re.findall(r"[a-z]+", blob.lower()))
    if not ws:
        return False, "the provider recorded nothing about the picture, so it cannot be checked against the period"
    bad = sorted(ws & MODERN_WORDS)
    if bad:
        return False, f"it looks modern for a narration about the year {year}: {', '.join(bad)}"
    good = sorted(ws & ART_WORDS)
    if curated and not good:                      # a Wikimedia Commons result found for "<subject> painting/engraving": its title rarely says "painting", so subject + nothing modern is the test
        good = ["wikimedia commons"]
    if not good:
        return False, f"nothing says it is a painting, engraving or other period artwork (year {year})"
    want = subject_words(subject) if subject else set()
    if want and not (ws & want):
        return False, f"it is old art but nothing says it shows the subject ({', '.join(sorted(want)[:4])})"
    return True, "period words: " + ", ".join(good)


def vet_plan_pictures(plan: Mapping[str, Any], pic_report: Mapping[str, Any], meta_by_asset: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """After "Get the scenes": checks each picture beat of the plan against the era the picture pass recorded (report["pictures"]["era"]) and the metadata of the file that was fetched for its
    reference (`meta_by_asset`: the clip's asset text -> manifest metadata). Returns {"ok": [...], "refused": [{"beat", "asset", "year", "why", "fallback"}]}. A refused beat that carries a
    `fallback_clip` (the illustration the planner drew for it) is switched back to it IN PLACE; one without stays listed so the caller keeps the scene illustrated or stops: a modern photograph is never kept."""
    out: Dict[str, Any] = {"ok": [], "refused": []}
    eras = pic_report.get("era", {}) if pic_report else {}
    for b in plan.get("beats", []):
        clips = (b.get("footage") or {}).get("clips", [])
        for c in clips:
            a = c.get("asset", "")
            src = a.partition(":")[0]
            if src not in ("stock_image", "stock_video") or a not in meta_by_asset:
                continue
            year = (eras.get(b["id"]) or {}).get("year")
            ok, why = vet_picture(meta_by_asset[a], year)
            if ok:
                out["ok"].append({"beat": b["id"], "asset": a, "why": why})
                continue
            fb = b.get("fallback_clip") or (b.get("footage") or {}).get("fallback_clip")
            rec = {"beat": b["id"], "asset": a, "year": year, "why": why, "fallback": bool(fb)}
            if fb:
                c.clear()
                c.update(dict(fb))
            out["refused"].append(rec)
    return out


# ------------------------------------------------------------------ 3. query quality

OPENERS = frozenset("""later then soon today now after before eventually meanwhile finally once however still also yet thus instead afterwards next first second third earlier suddenly
tomorrow yesterday often usually perhaps maybe even only just""".split())      # a capitalised word that only opens the sentence is not part of a name


def cased_phrases(script: Optional[str]) -> List[str]:
    """Proper names of two or more words as the script writes them ("Napoleon Bonaparte", "Saint Helena", "Battle of Waterloo"), in order of first appearance. A leading function word
    (The, In, After) is not part of a name."""
    out: List[str] = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", script or ""):
        ws = re.findall(r"[A-Za-z][A-Za-z\-]*", sent)
        i = 0
        while i < len(ws):
            if i == 0 and len(ws) > 1 and ws[i].lower() in OPENERS:
                i += 1
                continue
            if ws[i][0].isupper() and ws[i].lower() not in LX.STOP:
                j = i + 1
                while j < len(ws) and (ws[j][0].isupper() and ws[j].lower() not in LX.STOP or (ws[j].lower() in CONNECTORS and j + 1 < len(ws) and ws[j + 1][0].isupper())):
                    j += 1
                seq = ws[i:j]
                content = [w for w in seq if w.lower() not in CONNECTORS]
                if len(content) >= 2 and seq[0].lower() not in CONNECTORS:
                    ph = " ".join(seq)
                    if ph not in out:
                        out.append(ph)
                i = j
            else:
                i += 1
    return out


DIRECTIONS = frozenset("north south east west northern southern eastern western northeast northwest southeast southwest".split())


def _head_of_unspoken_phrase(t: str, phrases: Sequence[str], toks_: Sequence[str]) -> bool:
    """`t` is the LAST word of a multi-word proper name of the script (East of "Middle East", Empire of "Roman Empire") whose full name is not spoken in this beat."""
    for ph in phrases:
        ws = _toks(ph)
        if len(ws) >= 2 and ws[-1] == t and _find(toks_, ws) < 0:
            return True
    return False


def _find(tokens: Sequence[str], want: Sequence[str]) -> int:
    n = len(want)
    for i in range(len(tokens) - n + 1):
        if list(tokens[i:i + n]) == list(want):
            return i
    return -1


def build_query(tokens: Sequence[str], phrases: Sequence[str] = (), named: Set[str] = frozenset(), cased: Optional[Mapping[str, str]] = None, *, avoid: Optional[Mapping[str, int]] = None,
                max_words: int = MAX_QUERY_WORDS) -> Optional[Dict[str, Any]]:
    """A stock query for a beat. `tokens` = the beat's spoken tokens in order; `phrases` = cased_phrases(script); `named` = select.named_subjects; `cased` = segment.casing(script); `avoid` = uses so far per
    query (a query used QUERY_MAX_USES times is skipped). Every word of the answer is a token of the beat (relevance.py's rule), so nothing is ever invented.
    Returns {"query", "kind": name | phrase | noun, "vague": bool, "words": [...], "why": str} or None. `vague` = too general for a good picture (a lone generic noun, a bare country): the picture
    pass declines it, other callers may still use it. Deterministic."""
    cased = cased or {}
    avoid = avoid or {}
    toks_ = list(tokens)
    spoken = set(toks_)

    def used(q: str) -> bool:
        return avoid.get(q.lower(), 0) >= QUERY_MAX_USES

    def fmt(ws: Sequence[str], proper: bool) -> str:
        return " ".join((cased.get(w) or w.capitalize()) if proper and w not in CONNECTORS and (w in named or w in cased) else w for w in ws)

    def ok(ws: Sequence[str]) -> bool:
        return bool(ws) and all(w in spoken for w in ws) and not used(" ".join(ws))

    cands: List[Tuple[int, int, Dict[str, Any]]] = []         # (class rank, position, answer): the lowest rank, then the earliest, wins
    # (1) full proper names from the script, spoken one after another in the beat
    for ph in phrases:
        ws = _toks(ph)
        while len(ws) > max_words:
            ws = ws[:-1]
        while ws and ws[-1] in CONNECTORS:
            ws = ws[:-1]
        i = _find(toks_, ws)
        if len(ws) >= 2 and i >= 0 and ok(ws):
            cands.append((0, i, {"query": " ".join((w if w in CONNECTORS else w.capitalize()) for w in ws), "kind": "phrase", "vague": False, "words": ws, "why": f"the full name {ph!r} is spoken in the beat"}))
    # (2) one or two adjacent named words (the script writes them with a capital)
    i = 0
    while i < len(toks_):
        t = toks_[i]
        if t in named:
            ws = [t] + ([toks_[i + 1]] if i + 1 < len(toks_) and toks_[i + 1] in named and toks_[i + 1] != t else [])
            if len(ws) == 1 and (t in DIRECTIONS or _head_of_unspoken_phrase(t, phrases, toks_)):         # "east" of "Middle East", "sea" of "Adriatic Sea": half a name is not a subject
                i += 1
                continue
            if ok(ws):
                weak = len(ws) == 1 and (t in WEAK_NAMES or len(t) < 4)
                if weak:                                   # an ambiguous name needs a spoken word to say which one: a context noun or a year within three words, never an invented one
                    near = [k for k in range(max(0, i - 3), min(len(toks_), i + 4)) if k != i and (toks_[k] in CONTEXT or (toks_[k].isdigit() and len(toks_[k]) == 4 and 1000 <= int(toks_[k]) <= 2100))]
                    if near:
                        k = min(near, key=lambda k_: (abs(k_ - i), k_))
                        pair = sorted([i, k])
                        w2 = [toks_[pair[0]], toks_[pair[1]]]
                        if ok(w2):
                            cands.append((1, i, {"query": fmt(w2, True), "kind": "name", "vague": False, "words": w2, "why": f"{t!r} is ambiguous: the spoken word {toks_[k]!r} next to it says which"}))
                    else:
                        cands.append((3, i, {"query": fmt(ws, True), "kind": "name", "vague": True, "words": ws, "why": f"{t!r} is an ambiguous name and no spoken word near it says which one"}))
                else:
                    cands.append((1, i, {"query": fmt(ws, True), "kind": "name", "vague": False, "words": ws, "why": "a named person, place or event is spoken"}))
            i += len(ws)
        else:
            i += 1
    # (3) a noun phrase a camera can film or a picture can show; vague adjectives are dropped; a lone generic noun is vague
    conc = LX.CONCRETE_STRONG | LX.CONCRETE_WEAK
    for i, t in enumerate(toks_):
        if t in conc or t in EVIDENCE_WORDS:
            ws = [t]
            if i > 0 and toks_[i - 1] not in LX.STOP and toks_[i - 1] not in VAGUE and not toks_[i - 1].isdigit() and toks_[i - 1] not in CONNECTORS and toks_[i - 1] not in conc and len(toks_[i - 1]) > 2:
                ws.insert(0, toks_[i - 1])
            if i + 1 < len(toks_) and toks_[i + 1] in conc and toks_[i + 1] not in VAGUE and len(ws) < 3:
                ws.append(toks_[i + 1])
            if ok(ws):
                vague = len(ws) == 1 and (t in GENERIC_ALONE or t in LX.CONCRETE_WEAK and t not in EVIDENCE_WORDS)
                cands.append((2 if not vague else 4, i, {"query": " ".join(ws), "kind": "noun", "vague": vague, "words": ws, "why": "a thing a picture can show is spoken" + (" (too general alone)" if vague else "")}))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]))
    best = dict(cands[0][2])
    # a spoken evidence word makes the picture more exact ("Napoleon portrait"), if it still fits
    if best["kind"] in ("phrase", "name") and not best["vague"]:
        ev = next((t for t in toks_ if t in EVIDENCE_WORDS and t not in best["words"]), None)
        if ev and len(best["words"]) + 1 <= max_words and ok(best["words"] + [ev]):
            best["words"] = best["words"] + [ev]
            best["query"] = best["query"] + " " + ev
            best["why"] += f"; the spoken evidence word {ev!r} makes it exact"
    return best


# ------------------------------------------------------------------ 2. choosing the upgrade

def _beat_toks(b, words) -> List[str]:
    return [t["tok"] for t in beat_tokens(words, b.start, b.end)]


def predict_thin(toks: Sequence[str]) -> Tuple[bool, str]:
    """Before the board is drawn: how many different things the words give a picture to? (keywords of the icon table, filmable nouns, evidence words). Two or fewer = a thin board."""
    vis = {t for t in toks if t in LX.ICONS or t in LX.CONCRETE or t in EVIDENCE_WORDS}
    return len(vis) <= 2, f"{len(vis)} word(s) with a picture of their own"


def upgrade_thin_board(beats: List[Any], k: int, words, ctx: Dict[str, Any], opt, info: Dict[str, Any]) -> Dict[str, Any]:
    """Decide beat k (a board). Returns {"beat", "decision": footage|archive|board, "reason", ...}; mutates the beat only for footage/archive. `ctx` carries the shared state of the pass
    (phrases, cased, named, queries used, seconds used, cap, library). Never forces: every refusal is a reason in the record."""
    from . import select as SL
    b = beats[k]
    toks = _beat_toks(b, words)
    rec: Dict[str, Any] = {"beat": b.id, "decision": "board"}
    if b.dur < opt.min_beat_s - 1e-6:
        rec["reason"] = "too short"
        return rec
    if SL.footage_blocked(b, toks):
        rec["reason"] = "an opening, a question or a number: it stays a board"
        return rec
    if opt.meaning and b.idea in MN.NOT_FOOTAGE:
        rec["reason"] = f"meaning: a {b.idea} idea is shown by a diagram"
        return rec
    thin, thin_why = predict_thin(toks)
    named = ctx["named"]
    subject = [t for t in toks if t in named]
    thing = [t for t in toks if t in LX.CONCRETE_STRONG or t in EVIDENCE_WORDS]
    if not (subject or thing or (opt.meaning and b.idea == "evidence")):
        rec["reason"] = "no named person, place or event, object or evidence word: nothing to show a picture of"
        return rec
    if not thin and not (subject and len(subject) >= 1 and len(set(toks) & (LX.ICONS.keys() | LX.CONCRETE)) <= 3):
        rec["reason"] = f"the board has enough to show ({thin_why})"
        return rec
    rec["thin"] = thin_why
    # (a) a local archive picture of the subject (the existing archive beat, already built to Ken Burns)
    tk = beat_tokens(words, b.start, b.end)
    for it in ctx["library"]:
        if ctx["arch_uses"].get(it["asset"], 0) < 2 and any(find_phrase(tk, s) for s in it["subjects"]):
            if ctx["arch_s"] + b.dur <= opt.max_archive_share * ctx["duration"] + 1e-9:
                b.kind, b.archive = "archive", it
                ctx["arch_uses"][it["asset"]] = ctx["arch_uses"].get(it["asset"], 0) + 1
                ctx["arch_s"] += b.dur
                b.notes.append("picture pass: a local archive picture of the subject replaces a thin board")
                return {**rec, "decision": "archive", "asset": it["asset"], "reason": f"archive picture of {it['subjects'][0]!r}"}
    # (b) a still/footage beat with a good query
    if ctx["used_s"] + b.dur > ctx["cap_s"] + 1e-9:
        rec["reason"] = "the picture share of the runtime is used up"
        return rec
    if SL.footage_run_blocked(beats, k):
        rec["reason"] = "three picture/footage beats in a row"
        return rec
    q = build_query(toks, ctx["phrases"], named, ctx["cased"], avoid=ctx["queries"])
    if q is None:
        rec["reason"] = "no query made of spoken words"
        return rec
    if q["vague"]:
        rec["reason"] = f"the best query {q['query']!r} is too general for a good picture: {q['why']}"
        return rec
    era = era_of_beat(words, b)                        # a narration before 1800: a stock photograph of the place or thing is the modern one (a vaporetto for the 5th century)
    rec["era"] = era
    mod = era_modifier(era["year"])
    if mod:
        if relevance_accepts_era():
            q = {**q, "query": q["query"] + " " + " ".join(mod), "words": list(q["words"]) + mod, "why": q["why"] + f"; the narration is about the year {era['year']}, so the search asks for {' '.join(mod)}"}
        elif not history_safe(q["words"]):
            rec["reason"] = f"the narration is about the year {era['year']} and a stock photograph of {q['query']!r} would show the place as it is today: the illustrated scene stays"
            return rec
    source = STILL_SOURCE if q["kind"] in ("phrase", "name") else (opt.footage_source if opt.footage_source in LX.FOOTAGE_SOURCES else STILL_SOURCE)      # a person or an event is a portrait or a painting: a still
    b.kind, b.source, b.picture_query = "footage", source, q["query"]
    b.notes.append(f"picture pass: thin board -> {source}:{q['query']} ({q['why']})")
    ctx["queries"][q["query"].lower()] = ctx["queries"].get(q["query"].lower(), 0) + 1
    ctx["used_s"] += b.dur
    return {**rec, "decision": "footage", "source": source, "query": q["query"], "query_kind": q["kind"], "reason": q["why"]}


def upgrade_boards(beats: List[Any], words, script: Optional[str], duration: float, opt, info: Dict[str, Any]) -> Dict[str, Any]:
    """The whole pass (called from select.choose_kinds after the cartoon and footage choices). Returns the record for report['pictures']."""
    from . import select as SL
    from .segment import casing
    lib, _n = SL.load_archive(opt)
    ctx = {"phrases": cased_phrases(script), "cased": casing(script or ""), "named": set(info.get("named_subjects", ())), "queries": dict(info.get("footage_query_count", {})), "library": lib,
           "arch_uses": {}, "arch_s": sum(b.dur for b in beats if b.kind == "archive"), "duration": duration, "used_s": sum(b.dur for b in beats if b.kind == "footage"),
           "cap_s": max(max(opt.footage_share, PICTURE_SHARE) * duration, opt.max_beat_s)}      # a short video may still have one picture beat
    for it in lib:                                     # an asset already used by an archive beat counts once
        ctx["arch_uses"][it["asset"]] = sum(1 for b in beats if b.kind == "archive" and b.archive and b.archive["asset"] == it["asset"])
    recs = []
    for k, b in enumerate(beats):
        if b.kind != "board":
            continue
        recs.append(upgrade_thin_board(beats, k, words, ctx, opt, info))
    info.setdefault("footage_query_count", {}).update({q: n for q, n in ctx["queries"].items()})
    return {"phrases": ctx["phrases"], "upgraded": [r for r in recs if r["decision"] != "board"], "kept_board": [{"beat": r["beat"], "reason": r.get("reason", "")} for r in recs if r["decision"] == "board"],
            "queries": {r["beat"]: f"{r['source']}:{r['query']}" for r in recs if r["decision"] == "footage"},
            "era": {r["beat"]: r["era"] for r in recs if r["decision"] == "footage" and r.get("era")}, "share_cap": round(ctx["cap_s"] / max(duration, 1e-9), 3), "cased": ctx["cased"]}


# ------------------------------------------------------------------ 4. names for map photo cards

def map_card_names(btoks: Sequence[str], phrases: Sequence[str], named: Set[str], cased: Mapping[str, str], used: Mapping[str, int]) -> List[Tuple[str, str]]:
    """[(query, label)] for the people and events spoken in a map beat, in spoken order, full names first (a name ambiguous without context is left out)."""
    out: List[Tuple[str, str]] = []
    rest = list(btoks)
    for _ in range(3):
        q = build_query(rest, phrases, named, cased, avoid=used)
        if q is None or q["kind"] == "noun" or q["vague"] or q["query"].lower() in {o[0].lower() for o in out}:
            break
        out.append((q["query"], q["query"].upper()))
        used = {**used, q["query"].lower(): QUERY_MAX_USES}
    return out
