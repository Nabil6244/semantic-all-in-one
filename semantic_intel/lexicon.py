"""Environment and event vocabulary for the deterministic planners, in English and Hindi (Devanagari). A term is (text, weight): weight is
how strongly it names the thing (1.0 = names it outright, 0.5 = only suggests it). Latin terms match whole words (with a plural s/es/ed/ing
tail), Devanagari terms match as a stem. The planners combine them with context (neighbouring scenes, the picture's own description), so a
single word is evidence, never the decision."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

Term = Tuple[str, float]

# ---- where the scene is (ambience beds) ------------------------------------------------------------------------------------------
ENVIRONMENT: Dict[str, List[Term]] = {
    "rain": [("rain", 1.0), ("rainy", 0.9), ("stormy", 0.8), ("storm", 0.9), ("thunder", 1.0), ("drizzle", 1.0), ("downpour", 1.0), ("lightning", 0.8), ("monsoon", 1.0),
             ("flood", 0.6), ("बारिश", 1.0), ("बरसात", 1.0), ("तूफ़ान", 0.9), ("तूफान", 0.9), ("मानसून", 1.0), ("बाढ़", 0.6), ("आंधी", 0.7)],
    "water": [("ocean", 1.0), ("sea", 0.8), ("shore", 0.9), ("shoreline", 1.0), ("beach", 1.0), ("waves", 0.9), ("river", 1.0), ("lake", 1.0),
              ("underwater", 1.0), ("waterfall", 1.0), ("harbor", 0.8), ("harbour", 0.8), ("ship", 0.5), ("boat", 0.6), ("coast", 0.8),
              ("समुद्र", 1.0), ("सागर", 1.0), ("महासागर", 1.0), ("नदी", 1.0), ("झील", 1.0), ("लहर", 0.9), ("तट", 0.7), ("झरना", 1.0), ("जहाज़", 0.5), ("जहाज", 0.5)],
    "fire": [("fireplace", 1.0), ("campfire", 1.0), ("bonfire", 1.0), ("embers", 1.0), ("flames", 0.9), ("blaze", 0.9), ("wildfire", 0.9),
             ("burning", 0.5), ("आग", 0.9), ("ज्वाला", 1.0), ("अलाव", 1.0), ("लपटें", 1.0)],
    "transport": [("train", 1.0), ("subway", 1.0), ("metro", 1.0), ("airport", 1.0), ("railway", 1.0), ("railroad", 1.0),
                  ("airplane", 0.8), ("aircraft", 0.8), ("aeroplane", 0.8), ("ट्रेन", 1.0), ("रेल", 1.0), ("मेट्रो", 1.0),
                  ("हवाई अड्डा", 1.0), ("विमान", 0.9), ("स्टेशन", 0.8)],
    "traffic": [("highway", 1.0), ("freeway", 1.0), ("motorway", 1.0), ("intersection", 0.8), ("traffic", 1.0), ("cars", 0.6), ("vehicles", 0.6),
                ("ट्रैफिक", 1.0), ("हाईवे", 1.0), ("राजमार्ग", 1.0), ("गाड़ियाँ", 0.6), ("गाड़ियां", 0.6), ("वाहन", 0.6)],
    "city": [("city", 0.8), ("cityscape", 1.0), ("street", 0.8), ("streets", 0.8), ("urban", 1.0), ("skyline", 1.0), ("downtown", 1.0),
             ("skyscraper", 0.9), ("towers", 0.6), ("metropolis", 1.0), ("शहर", 0.8), ("नगर", 0.7), ("महानगर", 1.0), ("गली", 0.7), ("इमारतें", 0.6)],
    "crowd": [("crowd", 1.0), ("crowds", 1.0), ("audience", 0.9), ("stadium", 1.0), ("protest", 1.0), ("rally", 1.0), ("market", 0.7),
              ("bazaar", 1.0), ("festival", 0.8), ("parade", 0.9), ("mob", 0.8), ("spectators", 1.0), ("भीड़", 1.0), ("दर्शक", 0.9), ("बाज़ार", 0.8),
              ("प्रदर्शन", 0.8), ("रैली", 1.0), ("मेला", 1.0), ("जुलूस", 1.0)],
    "nature": [("forest", 1.0), ("mountain", 0.9), ("mountains", 0.9), ("meadow", 1.0), ("wildlife", 1.0), ("jungle", 1.0), ("valley", 0.9),
               ("desert", 0.9), ("field", 0.5), ("fields", 0.6), ("farm", 0.6), ("hills", 0.8), ("lawn", 0.7), ("garden", 0.7), ("trees", 0.7),
               ("birds", 0.8), ("bird", 0.7), ("wind", 0.6), ("countryside", 1.0), ("wilderness", 1.0), ("जंगल", 1.0), ("पहाड़", 0.9), ("घाटी", 0.9),
               ("रेगिस्तान", 0.9), ("खेत", 0.6), ("पक्षी", 0.8), ("बगीचा", 0.7), ("मैदान", 0.6), ("हवा", 0.3), ("पेड़", 0.7), ("गाँव", 0.6), ("गांव", 0.6)],
    "technology": [("computer", 1.0), ("computers", 1.0), ("server", 1.0), ("servers", 1.0), ("laboratory", 1.0), ("lab", 0.9), ("circuit", 1.0),
                   ("circuits", 1.0), ("chip", 0.8), ("chips", 0.8), ("robot", 0.9), ("robots", 0.9), ("data center", 1.0), ("machine", 0.6),
                   ("machines", 0.6), ("digital", 0.7), ("screen", 0.5), ("software", 0.8), ("algorithm", 0.7), ("neural network", 0.9),
                   ("processor", 0.9), ("electronics", 0.9), ("mainframe", 1.0), ("vacuum tubes", 1.0), ("gears", 0.6), ("mechanical", 0.5), ("rocket", 0.9), ("rockets", 0.9), ("engine", 0.6), ("engines", 0.6), ("satellite", 0.9), ("spacecraft", 0.9),
                   ("orbit", 0.7), ("launch pad", 0.9), ("रॉकेट", 0.9), ("उपग्रह", 0.9), ("इंजन", 0.6),
                   ("कंप्यूटर", 1.0), ("कम्प्यूटर", 1.0), ("मशीन", 0.6), ("प्रयोगशाला", 1.0), ("एल्गोरिदम", 0.7), ("सर्वर", 1.0), ("रोबोट", 0.9),
                   ("चिप", 0.8), ("सॉफ़्टवेयर", 0.8), ("सॉफ्टवेयर", 0.8), ("डेटा", 0.5), ("न्यूरल", 0.8), ("प्रोग्राम", 0.7), ("डिजिटल", 0.7)],
    "atmospheric": [("ominous", 1.0), ("eerie", 1.0), ("haunting", 1.0), ("sinister", 1.0), ("mysterious", 0.9), ("mystery", 0.7), ("dread", 0.9),
                    ("fog", 0.7), ("abyss", 0.9), ("ruins", 0.7), ("graveyard", 0.9), ("darkness", 0.8), ("dark", 0.5), ("shadowy", 0.8),
                    ("अंधेरा", 0.8), ("अँधेरा", 0.8), ("रहस्य", 0.8), ("रहस्यमय", 0.9), ("खौफ", 0.8), ("भयावह", 0.9), ("कोहरा", 0.7), ("खंडहर", 0.8)],
    "room": [("desk", 0.6), ("office", 0.8), ("study", 0.5), ("library", 1.0), ("classroom", 1.0), ("lecture hall", 0.9), ("bedroom", 1.0), ("hallway", 1.0),
             ("indoor", 0.8), ("interior", 0.7), ("room", 0.6), ("notebook", 0.4), ("typewriter", 0.6), ("candle", 0.4), ("कमरा", 0.8), ("कमरे", 0.8),
             ("दफ़्तर", 0.8), ("दफ्तर", 0.8), ("पुस्तकालय", 1.0), ("कक्षा", 0.9), ("मेज़", 0.5), ("मेज", 0.5)],
}

# ---- what happens (sound effects): event -> (terms, which library category/tags can voice it, how long a hit should be) -------------------
EVENTS: Dict[str, Dict] = {
    "impact": {"terms": [("explosion", 1.0), ("exploded", 1.0), ("blast", 0.9), ("crash", 1.0), ("crashed", 1.0), ("collapse", 0.8), ("collapsed", 0.8),
                         ("collided", 0.9), ("smashed", 0.9), ("shattered", 0.9), ("gunshot", 1.0), ("detonat", 0.9), ("धमाका", 1.0),
                         ("विस्फोट", 1.0), ("टक्कर", 0.9), ("ढह", 0.7), ("गिर गया", 0.4), ("टूट गया", 0.6)],
               "category": "impact", "tags": ("impact", "hit", "boom", "punch", "heavy", "deep"), "max_s": 1.6, "gain": 1.0},
    "machinery": {"terms": [("engine", 0.8), ("engines", 0.8), ("motor", 0.7), ("machinery", 1.0), ("factory", 0.9), ("assembly line", 1.0), ("gears", 0.7),
                            ("turbine", 0.9), ("generator", 0.8), ("rocket launch", 1.0), ("launched", 0.5), ("इंजन", 0.8), ("फैक्ट्री", 0.9), ("कारख़ाना", 0.9),
                            ("कारखाना", 0.9), ("मशीनरी", 1.0), ("टर्बाइन", 0.9)],
                  "category": "impact", "tags": ("machinery", "mechanical", "motor"), "max_s": 2.0, "gain": 0.9},
    "click": {"terms": [("clicked", 0.9), ("click", 0.8), ("typed", 0.7), ("typing", 0.7), ("keyboard", 0.8), ("switch", 0.5), ("button", 0.7),
                        ("टाइप", 0.7), ("कीबोर्ड", 0.8), ("बटन", 0.7), ("क्लिक", 0.9)],
              "category": "technology", "tags": ("mechanical_click", "computer_interface", "click", "tick"), "max_s": 0.5, "gain": 0.8},
    "water": {"terms": [("splash", 1.0), ("splashed", 1.0), ("tsunami", 1.0), ("waterfall", 0.9), ("flood", 0.8), ("dive", 0.5), ("sank", 0.7), ("sinking", 0.7),
                        ("छपाक", 1.0), ("सुनामी", 1.0), ("डूब", 0.7)],
              "category": "whoosh", "tags": ("water", "ocean"), "max_s": 2.2, "gain": 0.9},
    "movement": {"terms": [("sprinted", 0.9), ("raced", 0.7), ("swept", 0.6), ("rushed", 0.7), ("surged", 0.7), ("flew", 0.6), ("zoomed", 0.7),
                           ("दौड़", 0.7), ("भागा", 0.7), ("झपट", 0.7), ("उड़", 0.5)],
                 "category": "whoosh", "tags": ("movement", "sweep", "whoosh"), "max_s": 1.6, "gain": 0.8},
    "tension": {"terms": [("suddenly", 0.5), ("shock", 0.7), ("shocked", 0.7), ("warning", 0.6), ("danger", 0.6), ("threat", 0.6), ("alarm", 0.8),
                          ("अचानक", 0.5), ("चेतावनी", 0.6), ("ख़तरा", 0.6), ("खतरा", 0.6), ("झटका", 0.7)],
                "category": "riser", "tags": ("tension", "riser", "short"), "max_s": 3.0, "gain": 0.7},
}


def _is_dev(s: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in s)


@lru_cache(maxsize=4096)
def _pattern(term: str) -> "re.Pattern[str]":
    t = re.escape(term.lower())
    if _is_dev(term):
        return re.compile(t)
    # whole word, allowing a plural / past / -ing tail ("waves", "crashed", "burning")
    return re.compile(rf"(?<![a-z0-9]){t}(?:s|es|ed|d|ing)?(?![a-z0-9])")


def find_terms(text: str, terms: Sequence[Term]) -> List[Tuple[str, float, int]]:
    """[(term, weight, char position of the first match)] for every term of `terms` found in `text`."""
    low = (text or "").lower()
    out = []
    for term, weight in terms:
        m = _pattern(term).search(low)
        if m:
            out.append((term, weight, m.start()))
    return out


def score_terms(text: str, terms: Sequence[Term]) -> float:
    """Evidence in `text` for one thing: the weights of its distinct terms, the strongest in full and each further one at a third (so a
    sentence that says 'ocean, sea, waves' is not three times surer than one that says 'ocean')."""
    ws = sorted((w for _t, w, _p in find_terms(text, terms)), reverse=True)
    return (ws[0] + sum(ws[1:]) / 3.0) if ws else 0.0
