"""Story Motion continuity: how does each shot JOIN the one before it?

    plan_edits(shots, settings=None, images=None) -> [edit, ...]       one edit per shot (edit i = the join from shot i-1 INTO shot i)
    apply(shots, edits, settings=None)               -> shots (same dicts): sets shot["continuity_edit"] and the hard-cut transition_in
    camera_joins(shots, edits, fps)                  -> {shot_id: {"out": spec|None, "in": spec|None, "D": seconds, "w": 0..1, "blur": {...}}}
    link_pairs(shots, edits, fps)                    -> {shot_id: frames}  dissolves that become a short real cross-dissolve clip (bridge.py)

An edit is {"type", "reason", "strength", "realize", "from", ...} and type is one of EDITS:
    follow_into_location     the character/camera travels and arrives somewhere else: lateral travel continues across the cut
    object_closeup_to_context  a close/object shot opens out to the place it lives in: A pushes toward the object, B starts tight and eases out
    screen_or_chart_focus    the story goes to a screen / chart / phone: A pushes into it, B starts on it and settles
    wide_to_close            a wide / establishing shot cuts to the person or detail: A pushes in gently, B starts a little tight
    action_continues         the same action goes on in the next shot: a whip in the direction of travel (A out, B in) with motion blur
    match_cut                the same object in both shots: its centre lands on the same spot of the frame at the same size
    simple_cut               nothing links them: a plain hard cut (the shots' own moves carry it)
    dissolve                 time of day / lighting moves on in the same place, or two near-identical pictures: a short REAL cross-dissolve (not a dip)
    scene_break              a true break in time/story (flashback, "years later", a pause): the only edit that may dip (to black/white)
Pure python (numpy/PIL only when pictures are given), deterministic, English + Hindi (Devanagari and romanised).
Nothing here renders: compose.py (camera ends) and bridge.py (dissolve clips) realise the edits."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

VERSION = "cont-4"
EDITS = ("follow_into_location", "object_closeup_to_context", "screen_or_chart_focus", "wide_to_close", "action_continues", "match_cut",
         "simple_cut", "dissolve", "scene_break")
CAMERA_EDITS = ("follow_into_location", "object_closeup_to_context", "screen_or_chart_focus", "wide_to_close", "action_continues", "match_cut")
DIPS = ("dissolve", "soft", "fade", "dip_black", "dip")
MIN_STRENGTH = 0.55            # weaker wishes stay plain cuts
MAX_CAMERA_RUN = 3             # at most this many camera-realised joins in a row
MAX_CAMERA_SHARE = 0.32
MAX_LINK_SHARE = 0.10
MIN_LINK_GAP = 6               # shots between two real dissolves
MIN_SHOT_FOR_JOIN = 0.7        # seconds: a join needs room to be seen
LINK_SECONDS = 0.27            # 8 frames at 30 fps (the clips carry 0.3 s of margin past the shot end)
LINK_MIN_NEXT = 0.8            # the shot after a dissolve must be at least this long


# ------------------------------------------------------------------ lexicons
def _words(en: str = "", dev: str = "", rom: str = "") -> re.Pattern:
    """en/rom: space separated whole words (a plural s/es is allowed); dev: space separated whole Devanagari words (list the inflections you want)."""
    parts = []
    for grp in (en, rom):
        ws = [w for w in grp.split() if w]
        if ws:
            parts.append(r"\b(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in ws) + r")(?:s|es)?\b")
    ds = [w for w in dev.split() if w]
    if ds:
        parts.append(r"(?<![ऀ-ॿ])(?:" + "|".join(re.escape(w) for w in ds) + r")(?![ऀ-ॿ])")
    return re.compile("|".join(parts), re.I) if parts else re.compile(r"(?!x)x")


def _stems(en: str = "", dev_sub: str = "") -> re.Pattern:
    """English word-start stems + Devanagari substrings (for verb forms that inflect: चलता, चलते, चली ...)."""
    parts = []
    ws = [w for w in en.split() if w]
    if ws:
        parts.append(r"\b(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in ws) + ")")
    ds = [w for w in dev_sub.split() if w]
    if ds:
        parts.append("(?:" + "|".join(re.escape(w) for w in ds) + ")")
    return re.compile("|".join(parts), re.I) if parts else re.compile(r"(?!x)x")


_SCREEN = _words("screen monitor display dashboard chart graph app smartphone phone laptop computer tablet spreadsheet statement portfolio ticker candlestick "
                 "notification website webpage terminal tv television",
                 "स्क्रीन चार्ट ग्राफ मोबाइल फोन फ़ोन लैपटॉप कंप्यूटर ऐप डैशबोर्ड पोर्टफोलियो स्टेटमेंट वेबसाइट टीवी",
                 "skrin mobile")
_TRAVEL = _words("walk walked walking drive drove driving enter entered entering arrive arrived arriving step stepped stepping leave leaving climb climbed approach approached "
                 "reach reached reaching travel traveled travelled return returned fly flew head headed heading stroll strolled hurry hurried follow followed ride rode riding "
                 "cross crossed depart departed commute commuted",
                 "चलता चलते चला चली पहुँचा पहुंचा पहुँची पहुंची पहुँचे पहुंचे घुस गया गई गए आया आई निकला निकली निकले उतरा दौड़ा भागा चढ़ा लौटा",
                 "chala chali chalte pahuncha pahunch pahunche gaya gayi gaye aaya aayi nikla nikli ghusa lauta")
_TRAVEL_ROM = _TRAVEL
_ACTION = _words("run ran running chase chased chasing race raced racing ride rode riding rush rushed rushing fight fought fighting jump jumped jumping dash dashed fly flew "
                 "escape escaped gallop galloped charge charged drive drove driving sprint sprinted climb climbed",
                 "दौड़ा दौड़ता दौड़ते भागा भागता भागते लड़ा लड़ता कूदा कूद घुड़सवारी",
                 "daud daudta bhaga bhaagta ladai ladna kooda")
_ACTION_ROM = _ACTION
_ENTRY = _words("door doorway gate enter entered entering inside lobby threshold doorstep arrive arrived arrives",
                "दरवाज़ा दरवाजा दरवाज़े दरवाजे द्वार दाख़िल दाखिल अंदर भीतर", "darwaza andar")
_CLOSE = _words("close-up closeup detail macro hands hand fingers eyes face", "हाथ हाथों आँख आंख आँखें चेहरा", "chehra")
_WIDE = _words("wide establishing aerial landscape panorama vista skyline expanse overview", "नज़ारा नजारा")
_TOD = {
    "morning": _words("morning dawn sunrise daybreak breakfast", "सुबह सवेरे भोर सूर्योदय", "subah savere"),
    "day": _words("noon midday afternoon lunch daytime", "दोपहर दिन", "dopahar"),
    "evening": _words("evening sunset dusk twilight dinner", "शाम संध्या सूर्यास्त", "shaam"),
    "night": _words("night midnight bedtime overnight", "रात रातें रातों आधी", "raat"),
}
_TOD_ORDER = ("morning", "day", "evening", "night")
_PASSAGE = re.compile(r"\b(?:later\s+that\s+(?:day|evening|night|morning|afternoon)|that\s+(?:evening|night|afternoon)|by\s+(?:evening|night|nightfall|noon|morning)|"
                      r"hours?\s+later|a\s+few\s+hours|the\s+same\s+(?:evening|night)|as\s+(?:night|evening|dusk|dawn)\s+(?:fell|came|arrived)|nightfall|"
                      r"by\s+the\s+time\s+(?:the\s+)?(?:sun|night))\b|उसी\s+(?:शाम|रात)|उस\s+(?:रात|शाम)|कुछ\s+घंटे|घंटों\s+बाद|देर\s+रात|शाम\s+तक|रात\s+तक", re.I)
_BREAK = re.compile(r"\b(?:years?\s+later|(?:centuries|decades)\s+later|flashback|long\s+ago|once\s+upon|weeks?\s+later|months?\s+later|years?\s+earlier|epilogue|prologue|"
                    r"chapter\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)|part\s+(?:one|two|three|four|five|\d+))\b|(?:^|[.!?]\s*)(?:the\s+)?next\s+(?:day|morning|week|year)\b|"
                    r"\bthe\s+next\s+(?:day|morning)\b|"
                    r"सालों\s+बाद|साल\s+बाद|सदियों\s+बाद|अगले\s+दिन|बहुत\s+पहले|दशकों\s+बाद|कुछ\s+दिन\s+बाद|अध्याय|इसी\s+बीच|उन\s+दिनों|फ़्लैशबैक|फ्लैशबैक|"
                    r"\b(?:saalon\s+baad|agle\s+din|bahut\s+pehle|kuch\s+saal\s+baad)\b", re.I)
_MEMORY = re.compile(r"\b(?:flashback|memory|remember(?:ed|s)?|recall(?:ed)?|dream(?:t|ed)?|used\s+to)\b|याद|यादों|सपना|सपने|\b(?:yaad|sapna)\b", re.I)
_LIGHT = {
    "dark": _words("dark dim gloomy shadowy shadow moonlit moonlight candlelit murky unlit blackout", "अंधेरा अंधेरे अँधेरा अँधेरे अंधकार", "andhera"),
    "bright": _words("bright sunny sunlit sunlight daylight dazzling glaring luminous", "धूप रोशनी उजाला चमकदार", "roshni dhoop"),
    "warm": _words("golden warm amber candle lamp lamplight firelight glow cozy cosy sunset", "सुनहरी सुनहरा गर्म", "sunehri"),
    "cool": _words("cold blue icy fluorescent frosty moonlit neon", "ठंडी ठंडा नीला नीली", "thanda"),
}
_LIGHT_CLASS = {"dark": "dark", "bright": "bright", "warm": "warm", "cool": "cool"}
_OBJECTS = {
    "coin": _words("coin coins penny pennies stack gold bullion", "सिक्का सिक्के सिक्कों"),
    "money": _words("money cash dollar dollars bill bills banknote banknotes rupee rupees paycheck salary", "पैसा पैसे पैसों रुपये रुपया रुपए नोट नोटों नकद"),
    "phone": _words("phone smartphone mobile cellphone", "फोन फ़ोन मोबाइल", "mobile"),
    "laptop": _words("laptop computer notebook", "लैपटॉप कंप्यूटर"),
    "chart": _words("chart graph diagram plot", "चार्ट ग्राफ"),
    "key": _words("key keys keychain", "चाबी चाबियाँ चाबियां"),
    "door": _words("door doorway gate", "दरवाज़ा दरवाजा दरवाज़े दरवाजे द्वार"),
    "clock": _words("clock watch timer hourglass calendar", "घड़ी घड़ियाँ घंटा कैलेंडर"),
    "suitcase": _words("suitcase luggage bag backpack trunk", "सूटकेस बैग"),
    "ticket": _words("ticket tickets passport boarding", "टिकट पासपोर्ट"),
    "letter": _words("letter envelope note document contract paper papers page", "चिट्ठी पत्र लिफ़ाफ़ा दस्तावेज़ दस्तावेज कागज़ कागज"),
    "map": _words("map maps compass globe", "नक्शा नक़्शा नक्शे"),
    "book": _words("book books diary ledger notebook journal", "किताब किताबें किताबों डायरी बही"),
    "ring": _words("ring rings necklace jewel jewellery jewelry crown", "अंगूठी हार गहने ताज"),
    "house": _words("house home apartment cottage", "घर मकान"),
    "car": _words("car cars truck taxi bus vehicle", "कार गाड़ी गाड़ियाँ बस"),
    "train": _words("train trains railway station platform", "ट्रेन रेल स्टेशन"),
    "plane": _words("plane airplane aeroplane jet flight airport", "विमान हवाई जहाज़ जहाज"),
    "ship": _words("ship boat vessel yacht", "जहाज़ नाव"),
    "sword": _words("sword swords spear shield blade dagger", "तलवार भाला ढाल"),
    "flag": _words("flag banner", "झंडा ध्वज"),
    "cup": _words("cup mug coffee tea glass bottle", "चाय कप कॉफ़ी कॉफी गिलास"),
    "tree": _words("tree trees flower flowers plant garden", "पेड़ पेड़ों फूल बगीचा"),
    "bank": _words("bank vault safe piggy", "बैंक तिजोरी गुल्लक"),
    "food": _words("food meal bread plate dish", "खाना रोटी थाली"),
    "camera": _words("camera microphone mic", "कैमरा माइक"),
    "medicine": _words("pill pills medicine syringe", "दवा दवाई गोली"),
    "lamp": _words("lamp candle torch lantern", "दीया दीपक मशाल लालटेन"),
}
_ROLES = {
    "king": ("king queen emperor sultan prince princess", "राजा रानी सम्राट बादशाह राजकुमार राजकुमारी"),
    "soldier": ("soldier soldiers warrior knight general commander army", "सैनिक सिपाही योद्धा सेनापति सेना"),
    "child": ("child boy girl kid kids baby", "बच्चा बच्चे बच्ची लड़का लड़की बालक"),
    "mother": ("mother mom mum", "माँ माता मां"), "father": ("father dad", "पिता पापा"),
    "elder": ("elder grandfather grandmother grandpa grandma", "बुज़ुर्ग बुजुर्ग दादा दादी नाना नानी"),
    "monk": ("monk sage priest saint", "साधु संत ऋषि पुजारी"),
    "merchant": ("merchant trader shopkeeper vendor", "व्यापारी दुकानदार"),
    "farmer": ("farmer", "किसान"),
    "traveler": ("traveler traveller wanderer rider", "यात्री मुसाफ़िर मुसाफिर"),
    "woman": ("woman women lady", "औरत महिला स्त्री"), "man": ("man men gentleman", "आदमी पुरुष"),
    "hero": ("hero heroine protagonist", "नायक नायिका"),
    "teacher": ("teacher professor doctor nurse engineer", "शिक्षक अध्यापक डॉक्टर इंजीनियर"),
}
_ROLE_RE = {k: _words(en, dv) for k, (en, dv) in _ROLES.items()}
_STOPCAPS = frozenset("""The A An He She They It We You I This That These Those There Then When What Why How Who Where But And So Or If As At In On Of For To From With
By Not No Yes Now Here Just Even Still Also After Before While Because Since Until Once Every Each Some Any All One Two Three Four Five Six Seven Eight Nine Ten
His Her Their Our Your My Its Mr Mrs Ms Dr Meanwhile Today Yesterday Tomorrow Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March
April May June July August September October November December Let Maybe Perhaps Suddenly Finally Instead Another Other Most Many Much More Less""".split())
_NAME_RE = re.compile(r"(?<![\w'])([A-Z][a-z]{2,})\b")


# ------------------------------------------------------------------ per shot features
def _scene_part(shots: Sequence[dict]) -> List[str]:
    """prompt_en minus what most prompts share (style preamble, host description, 'if on-screen text appears ...' tail): what is specific to the shot.
    A sentence that appears in more than a quarter of the prompts (at least 4) is boilerplate."""
    ps = [str(s.get("prompt_en") or s.get("prompt") or "") for s in shots]
    n = len(ps)
    if n < 4 or not any(ps):
        return ps
    split = [[q.strip() for q in re.split(r"(?<=[.!?])\s+|\n+", p) if q.strip()] for p in ps]
    from collections import Counter
    df = Counter(q for sents in split for q in set(sents))
    lim = max(3, int(0.25 * n))
    return [" ".join(q for q in sents if df[q] <= lim) for sents in split]


def _found(rx: re.Pattern, text: str) -> List[str]:
    return [m.group(0).lower() for m in rx.finditer(text)] if text else []


def _names(text: str) -> set:
    out = set()
    for m in _NAME_RE.finditer(text or ""):
        w = m.group(1)
        if w not in _STOPCAPS:
            out.add(w.lower())
    return out


def _features(sh: dict, scene_prompt: str) -> dict:
    text = str(sh.get("text") or "")
    subj = str(sh.get("subject") or "")
    blob = (text + " " + scene_prompt + " " + subj).lower().replace("on-screen", " ").replace("onscreen", " ")
    narr = text.lower()
    tod = [k for k in _TOD_ORDER if _TOD[k].search(narr) or _TOD[k].search(scene_prompt.lower())]
    light = [k for k, rx in _LIGHT.items() if rx.search(blob)]
    objs = {k for k, rx in _OBJECTS.items() if rx.search(blob)}
    roles = {k for k, rx in _ROLE_RE.items() if rx.search(blob)}
    if len(roles) > 1:
        roles = {r for r in roles if r not in ("man", "woman")} or roles
    cont = sh.get("continuity") or {}
    roles |= {str(r) for r in (cont.get("characters") or [])}
    sp = scene_prompt.lower()
    travel = _found(_TRAVEL, narr) + _found(_TRAVEL_ROM, narr) + _found(_TRAVEL, sp)
    action = _found(_ACTION, narr) + _found(_ACTION_ROM, narr) + _found(_ACTION, sp)
    shape = "close" if (_CLOSE.search(sp) or _CLOSE.search(narr)) else "wide" if (_WIDE.search(sp) or _WIDE.search(narr)) else ""
    return {
        "text": text, "objs": objs, "roles": roles, "names": _names(text) | _names(scene_prompt),
        "screen": _found(_SCREEN, blob), "travel": travel, "action": action, "entry": _found(_ENTRY, blob), "shape": shape,
        "tod": tod[-1] if tod else "", "light": light[0] if light else "", "passage": bool(_PASSAGE.search(narr)),
        "brk": bool(_BREAK.search(narr)), "memory": bool(_MEMORY.search(narr)),
        "loc": cont.get("location"), "same_loc": bool(cont.get("same_location_as_prev")), "carry": cont.get("carry_dir"),
        "genre": sh.get("genre"), "energy": int(sh.get("energy") or 0),
        "start": float(sh.get("start") or 0.0), "end": float(sh.get("end") or 0.0),
        "run": (sh.get("same_run") or {}).get("id"),
    }


def _edit(kind: str, reason: str, strength: float, **kw) -> dict:
    d = {"type": kind, "reason": reason, "strength": round(float(strength), 2), "realize": "none"}
    d.update(kw)
    return d


def _first(lst):
    return lst[0] if lst else ""


# ------------------------------------------------------------------ the decision for one join
def _classify(i: int, fa: Optional[dict], fb: dict) -> dict:
    if fa is None:
        return _edit("simple_cut", "first shot", 0.0)
    if fb["brk"] or fb["memory"]:
        why = "narration marks a jump in time/story" if fb["brk"] else "memory / flashback"
        return _edit("scene_break", why, 0.9, realize="dip")
    if fa["run"] and fa["run"] == fb["run"]:
        return _edit("simple_cut", "the same picture reframed (the director's jump cut)", 0.0)
    # time of day / lighting move on in the same place
    if fb["passage"] and fb["same_loc"]:
        return _edit("dissolve", "time passes in the same place (" + (_first(_found(_PASSAGE, fb["text"].lower())) or "time marker") + ")", 0.75, realize="link")
    if fa["tod"] and fb["tod"] and fa["tod"] != fb["tod"] and fb["same_loc"]:
        return _edit("dissolve", f"time of day moves on in the same place ({fa['tod']} -> {fb['tod']})", 0.75, realize="link")
    if fa["light"] and fb["light"] and fa["light"] != fb["light"] and fb["same_loc"] and (fa["names"] & fb["names"] or fa["roles"] & fb["roles"]) and {fa["light"], fb["light"]} != {"warm", "bright"}:
        return _edit("dissolve", f"lighting changes in the same place ({fa['light']} -> {fb['light']})", 0.6, realize="link")
    sa, sb = fa["screen"], fb["screen"]
    if (sa or sb) and (fb["same_loc"] or sb):
        who = "both shots" if (sa and sb) else ("shot A" if sa else "shot B")
        return _edit("screen_or_chart_focus", f"{who} is about a screen/chart ({_first(sa or sb)})", 0.85 if (sa and not sb) or (sb and not sa) else 0.7,
                     into_screen=bool(sb), target_a="object" if sa else "main", target_b="object" if sb else "main")
    if fa["action"] and fb["action"] and fb["same_loc"]:
        return _edit("action_continues", f"the action goes on ({_first(fa['action'])} -> {_first(fb['action'])})", 0.8, dir=fa["carry"] or fb["carry"] or ("l" if i % 2 else "r"))
    if fb["action"] and fa["travel"] and fb["same_loc"]:
        return _edit("action_continues", f"travel turns into action ({_first(fa['travel'])} -> {_first(fb['action'])})", 0.65, dir=fa["carry"] or fb["carry"] or "r")
    if not fb["same_loc"] and (fa["travel"] or fb["travel"] or fb["entry"]):
        cue = _first(fa["travel"] or fb["travel"] or fb["entry"])
        return _edit("follow_into_location", f"movement to a new place ({fa['loc']} -> {fb['loc']}; '{cue}')", 0.75, dir=fa["carry"] or fb["carry"] or ("l" if i % 2 else "r"))
    if not fb["same_loc"] and (fa["names"] & fb["names"] or fa["roles"] & fb["roles"]):
        shared = _first(sorted(fa["names"] & fb["names"] or fa["roles"] & fb["roles"]))
        return _edit("follow_into_location", f"{shared} continues into a new place ({fa['loc']} -> {fb['loc']})", 0.5, dir=fa["carry"] or fb["carry"] or ("l" if i % 2 else "r"))
    if fa["shape"] == "close" and fb["shape"] != "close":
        return _edit("object_closeup_to_context", "close-up opens out to its context", 0.72)
    if fa["objs"] and not fb["objs"] and fb["shape"] == "wide":
        return _edit("object_closeup_to_context", f"the {_first(sorted(fa['objs']))} gives way to the wider place", 0.6)
    if fa["shape"] == "wide" and (fb["shape"] == "close" or ((fb["roles"] or fb["names"]) and not (fa["roles"] or fa["names"]))):
        return _edit("wide_to_close", "wide / establishing shot cuts in to the person or detail", 0.68)
    shared = sorted(fa["objs"] & fb["objs"])
    if shared:
        return _edit("match_cut", f"the same {shared[0]} in both shots", 0.62, obj=shared[0])
    return _edit("simple_cut", "same place and beat, nothing links the pictures: a plain cut", 0.0)


def plan_edits(shots: Sequence[dict], settings: Optional[dict] = None, images: Optional[dict] = None) -> List[dict]:
    """One edit per shot: the join from the previous shot into this one. `images` ({shot_id|scene_no: path}) refines with the pictures; optional."""
    st = settings or {}
    shots = list(shots or [])
    sp = _scene_part(shots)
    feats = [_features(s, p) for s, p in zip(shots, sp)]
    n = len(feats)
    if n >= 10:      # a cue that most shots have is the video's subject, not a link between two shots (finance video: money / screens everywhere)
        from collections import Counter
        df = Counter(o for f in feats for o in f["objs"])
        common = {o for o, c in df.items() if c > 0.3 * n}
        for f in feats:
            f["objs"] = f["objs"] - common
            if sum(1 for g in feats if g["screen"]) > 0.35 * n:
                f["screen"] = []
    edits = [_classify(i, feats[i - 1] if i else None, feats[i]) for i in range(len(shots))]
    for i, e in enumerate(edits):
        e["from"] = str(shots[i - 1].get("shot_id")) if i else None
        e["to"] = str(shots[i].get("shot_id"))
    if images:
        _refine(shots, edits, images)
    _pace(shots, edits, st)
    return edits


# ------------------------------------------------------------------ the pictures
def _pic(images: dict, sh: dict) -> Optional[str]:
    if isinstance(images, (list, tuple)):
        return None
    for k in (sh.get("shot_id"), sh.get("scene_no"), str(sh.get("scene_no"))):
        if k is not None and images.get(k):
            return str(images[k])
    return None


def _refine(shots, edits, images) -> None:
    """Pictures: the very same picture is a reframe (no camera join); near-identical pictures dissolve; unrelated text but alike compositions match-cut."""
    try:
        from story_fast import similar
    except Exception:       # noqa: BLE001
        return
    fps_ = [similar.fingerprint(p) if p else None for p in (_pic(images, s) for s in shots)]
    pics = [_pic(images, s) for s in shots]
    for i in range(1, len(shots)):
        e = edits[i]
        if not pics[i] or not pics[i - 1]:
            continue
        e["picture_a"], e["picture_b"] = pics[i - 1], pics[i]
        if pics[i] == pics[i - 1]:
            if e["type"] in CAMERA_EDITS + ("dissolve",):
                e.update(_edit("simple_cut", "the same picture continues: the camera reframes it", 0.0, **{k: e[k] for k in ("from", "to", "picture_a", "picture_b")}))
            continue
        a, b = fps_[i - 1], fps_[i]
        if a is None or b is None:
            continue
        d = similar.distance(a, b)
        e["distance"] = round(d, 3)
        if e["type"] == "scene_break":
            continue
        if d < 0.045:
            e.update(_edit("dissolve", f"two near-identical pictures (distance {d:.3f}): a real cross-dissolve hides the swap", 0.65, realize="link",
                           **{k: e[k] for k in ("from", "to", "picture_a", "picture_b", "distance")}))
        elif e["type"] == "simple_cut" and d < 0.2:
            try:
                from story_fast import focus
                ma, mb = focus.find_focus(pics[i - 1]).get("main") or {}, focus.find_focus(pics[i]).get("main") or {}
                near = bool(ma and mb) and max(abs(ma["x"] - mb["x"]), abs(ma["y"] - mb["y"])) < 0.12
            except Exception:       # noqa: BLE001
                near = False
            if near:
                e.update(_edit("match_cut", f"alike compositions (distance {d:.3f}) with the subject in the same place: it keeps its spot in the frame", 0.6, obj="composition",
                               **{k: e[k] for k in ("from", "to", "picture_a", "picture_b", "distance")}))


# ------------------------------------------------------------------ pacing
def _pace(shots, edits, st) -> None:
    """Keep the film from becoming a tic. Weak wishes stay cuts; the strongest wishes win when there are too many (never more than a share of the cuts,
    never more than MAX_CAMERA_RUN in a row, never both sides of a very short shot); dissolves are rare and spaced."""
    n = len(edits)
    share = float(st.get("story_continuity_share", MAX_CAMERA_SHARE))
    dur = [max(0.0, float(s.get("end") or 0) - float(s.get("start") or 0)) for s in shots]

    def drop(e, want, why):
        e["wanted"] = want
        e.update({"type": "simple_cut", "realize": "none", "strength": 0.0, "reason": f"{e['reason']} - kept a plain cut ({why})"})

    cam, dis = [], []
    for i, e in enumerate(edits):
        if e["type"] in ("scene_break", "simple_cut"):
            continue
        want = e["type"]
        if want == "dissolve":
            (dis if (i and dur[i] >= LINK_MIN_NEXT and dur[i - 1] >= MIN_SHOT_FOR_JOIN) else []).append(i)
            if not (i and dur[i] >= LINK_MIN_NEXT and dur[i - 1] >= MIN_SHOT_FOR_JOIN):
                drop(e, want, "shots too short for a dissolve")
        elif e["strength"] < MIN_STRENGTH:
            drop(e, want, "too weak")
        elif dur[i - 1] < MIN_SHOT_FOR_JOIN or dur[i] < MIN_SHOT_FOR_JOIN:
            drop(e, want, "a shot is too short to show it")
        else:
            cam.append(i)
    # dissolves: rare and spaced, strongest first
    cap_l = max(1, int(MAX_LINK_SHARE * n))
    keep_l: List[int] = []
    for i in sorted(dis, key=lambda k: (-edits[k]["strength"], k)):
        if len(keep_l) >= cap_l:
            drop(edits[i], "dissolve", "dissolves are kept rare")
        elif any(abs(i - k) < MIN_LINK_GAP for k in keep_l):
            drop(edits[i], "dissolve", "another dissolve is too close")
        else:
            keep_l.append(i)
    # camera joins: strongest first within the budget
    budget = int(share * n) + 1
    acc = set()
    for i in sorted(cam, key=lambda k: (-edits[k]["strength"], k)):
        run = 1
        j = i - 1
        while j in acc:
            run += 1
            j -= 1
        j = i + 1
        while j in acc:
            run += 1
            j += 1
        short_both = (i - 1 in acc and dur[i - 1] < 1.5) or (i + 1 in acc and dur[i] < 1.5)
        if len(acc) >= budget:
            drop(edits[i], edits[i]["type"], "camera joins are kept to a share of the cuts")
        elif run > MAX_CAMERA_RUN:
            drop(edits[i], edits[i]["type"], f"already {run - 1} camera joins in a row")
        elif short_both:
            drop(edits[i], edits[i]["type"], "the shot between is too short for two joins")
        else:
            acc.add(i)
            edits[i]["realize"] = "camera"


# ------------------------------------------------------------------ apply
def apply(shots: Sequence[dict], edits: Sequence[dict], settings: Optional[dict] = None) -> List[dict]:
    """Writes shot["continuity_edit"] and turns every plain dip into a hard cut: only a scene_break keeps the director's dip (default 'fade'). A dissolve is
    a hard cut here too: bridge.py inserts the real cross-dissolve clip. Explicit CSV hints and the director's flash / zoom_blur are left alone."""
    for sh, e in zip(shots, edits):
        sh["continuity_edit"] = dict(e)
        tr = sh.get("transition_in") or "cut"
        if e["type"] == "scene_break":
            if tr not in DIPS and tr not in ("flash", "zoom_blur"):
                sh["transition_in"] = "fade"
        elif tr in DIPS or e.get("realize") in ("camera", "link"):
            sh["transition_in"] = "cut"          # the camera ends / the dissolve clip make this join; no dip or blur-zoom on top
    return list(shots)


def edit_into(shot: dict) -> dict:
    return dict(shot.get("continuity_edit") or {"type": "simple_cut", "reason": "no continuity pass", "strength": 0.0, "realize": "none"})


# ------------------------------------------------------------------ what the renderer needs
def _env(dur: float, strength: float, scale: float = 1.0) -> float:
    return round(max(0.35, min(1.0, 0.5 + 0.5 * strength)) * min(1.0, dur / 2.0 + 0.35) * scale, 3)


def camera_joins(shots: Sequence[dict], edits: Optional[Sequence[dict]] = None, fps: int = 30) -> Dict[str, dict]:
    """{shot_id: {"out": spec, "in": spec, "D": shot seconds, "w": envelope share, "blur": ...}} for the camera-realised edits.
    spec = {"pt": "main"|"object", "z": absolute zoom} (centre that point at that zoom) or {"dx", "dy", "zb"} (lateral travel + zoom boost)."""
    edits = list(edits) if edits is not None else [edit_into(s) for s in shots]
    out: Dict[str, dict] = {}

    def slot(i):
        sh = shots[i]
        d = max(0.2, float(sh.get("end") or 0) - float(sh.get("start") or 0))
        return out.setdefault(str(sh.get("shot_id")), {"D": round(d, 4), "w": round(min(0.5, 1.0 / d), 3)})

    for i in range(1, len(shots)):
        e = edits[i]
        if e.get("realize") != "camera" or e["type"] not in CAMERA_EDITS:
            continue
        a, b = slot(i - 1), slot(i)
        s = float(e.get("strength") or 0.6)
        da, db = a["D"], b["D"]
        k = e["type"]
        if k == "object_closeup_to_context":
            a["out"] = {"pt": "main", "z": round(1.2 + 0.24 * s, 3), "k": _env(da, s)}
            b["in"] = {"pt": "main", "z": round(1.22 + 0.26 * s, 3), "k": _env(db, s)}
        elif k == "screen_or_chart_focus":
            a["out"] = {"pt": e.get("target_a", "main"), "z": round(1.24 + 0.28 * s, 3), "k": _env(da, s)}
            b["in"] = {"pt": e.get("target_b", "main"), "z": round(1.18 + 0.22 * s, 3), "k": _env(db, s)}
        elif k == "wide_to_close":
            a["out"] = {"pt": "main", "z": round(1.12 + 0.14 * s, 3), "k": _env(da, s, 0.8)}
            b["in"] = {"pt": "main", "z": round(1.1 + 0.14 * s, 3), "k": _env(db, s, 0.8)}
        elif k == "match_cut":
            z = round(1.2 + 0.14 * s, 3)
            a["out"] = {"pt": "main", "z": z, "k": _env(da, s)}
            b["in"] = {"pt": "main", "z": z, "k": _env(db, s)}
        else:               # follow_into_location / action_continues: the camera keeps travelling the same way across the cut
            sgn = 1.0 if e.get("dir", "r") in ("r", "right") else -1.0
            whip = k == "action_continues"
            sh = (0.09 if whip else 0.06) * (0.7 + 0.6 * s)
            zb = (0.20 if whip else 0.14)
            a["out"] = {"dx": round(sgn * sh, 4), "dy": 0.0, "zb": zb, "k": _env(da, s)}
            b["in"] = {"dx": round(-sgn * sh, 4), "dy": 0.0, "zb": zb, "k": _env(db, s)}
            if whip:
                a["blur"] = dict(a.get("blur") or {}, out=1)
                b["blur"] = dict(b.get("blur") or {}, in_=1)
                a["w"] = min(a["w"], 0.28)
                b["w"] = min(b["w"], 0.28)
        a["edit_out"] = k
        b["edit_in"] = k
    return out


def link_pairs(shots: Sequence[dict], edits: Optional[Sequence[dict]] = None, fps: int = 30) -> Dict[str, dict]:
    """{shot_id of A: {"to": shot_id of B, "frames": k}} for the dissolves that get a real cross-dissolve clip."""
    edits = list(edits) if edits is not None else [edit_into(s) for s in shots]
    out: Dict[str, dict] = {}
    for i in range(1, len(shots)):
        e = edits[i]
        if e.get("type") == "dissolve" and e.get("realize") == "link":
            out[str(shots[i - 1].get("shot_id"))] = {"to": str(shots[i].get("shot_id")), "frames": max(2, int(round(LINK_SECONDS * fps)))}
    return out


def summary(edits: Sequence[dict]) -> dict:
    from collections import Counter
    c = Counter(e["type"] for e in edits)
    r = Counter(e.get("realize", "none") for e in edits)
    return {"types": dict(c), "realized": dict(r), "version": VERSION}
