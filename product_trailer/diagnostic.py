"""Phase 1 diagnostic (2026-11-06): what each narrated sentence SHOULD be shown with, against what the existing pipeline shows. Local and deterministic:
no AI, no keys, no downloads, no render. Nothing here is used by the default pipeline; it only reads it.

    kind_of(sentence)                      -> one of KINDS
    proposed(sentence, kind, phone)        -> {"visual", "layer", "reason", "asset_ready"}  (existing layers only)
    old_visual(spec, a, b)                 -> what the existing pipeline put on screen in [a, b] (read from its spec)
    diagnose(script, words, duration, spec, phone) -> rows;  report(rows) -> text

    python -m product_trailer.diagnostic SCRIPT.txt WORDS.json SPEC.json [--phone "iPhone Duo"] [--seconds N]
SPEC.json is the product_trailer_spec.json that studio.plan_film already wrote for that script and voice (style mixed, no AI).
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

KINDS = ("product", "source", "date", "problem", "opinion", "question", "spec", "comparison", "general")

SOURCE = re.compile(r"\b(according to|reports?|reported|reporting|says?|said|told|stated|announced|acknowledg\w+|responded|response|statement|claims?|claimed|"
                    r"leak(?:ed|er|s)?|rumou?rs?|tipster|teardown|ifixit|macworld|reviewers?|analysts?|sources?|in a post|posted|tweet\w*|wrote|published|confirmed|"
                    r"offers? one theory|theory|filed|listing|certification|owners? (?:in|on)|reddit|forum)\b", re.I)
DATE = re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\b|\b(19|20)\d\d\b|"
                  r"\b(launched|released|arrived|went on sale|first shipped)\b|\bwithin days\b|\bless than (?:two|three|\d+) (?:weeks|days|months)\b|\blast (?:week|month|year)\b", re.I)
PROBLEM = re.compile(r"\b(crack\w*|broke\w*|broken|fail\w*|problems?|issues?|defects?|trouble|won['’]t (?:open|close|fold)|stuck|dead pixels?|creas\w+|peel\w*|"
                     r"complain\w*|damage\w*|flaw\w*|worry|worries|concern\w*|risk|weak\w*|disappoint\w*|expensive|costly|repair\w*|replace\w*|warranty|not covered)\b", re.I)
OPINION = re.compile(r"\b(my take|i think|i['’]d|i would|honestly|in my opinion|personally|i believe|i feel|to me|if you ask me|my advice|i['’]m not|i am not|should you|"
                     r"worth it|i wouldn['’]t|i don['’]t think|feels? like|seems? like|looks? like it|bottom line|the real question)\b", re.I)
SPEC = re.compile(r"\d[\d,.]*\s*(?:%|w\b|watts?|mah|mp\b|megapixels?|hz|hertz|gb|tb|nits?|mm\b|inch(?:es)?|\"|hours?|hrs?\b|fps|dollars?|grams?|ghz|gen\b)|\$\s?\d|"
                  r"\b(?:oled|lpddr\w*|ufs ?\d|snapdragon|exynos|a\d{2}|chip|processor|ram|storage|battery|refresh rate|brightness|resolution)\b", re.I)
COMPARE = re.compile(r"\b(vs\.?|versus|compared (?:to|with)|than|instead of|rather than|unlike|same as|different from|more than|less than|bigger|smaller|"
                     r"thinner|thicker|faster|slower|both|while the|whereas|previous|last year|older)\b", re.I)
DESIGN = re.compile(r"\b(design|look|hinge|fold\w*|frame|body|build|colou?rs?|finish|hands|hold|camera|lens|screen|display|inside|crease|thin|slim|shape|size|book[- ]style|"
                    r"what is the)\b", re.I)


def kind_of_v1(sentence: str) -> str:
    """Phase 1 classifier, kept only so Phase 1B can print the before/after comparison."""
    s = (sentence or "").strip()
    if not s:
        return "general"
    if s.endswith("?"):
        return "question"
    if OPINION.search(s):
        return "opinion"
    if SOURCE.search(s):
        return "source"
    if PROBLEM.search(s):
        return "problem"
    nums = re.findall(r"\d[\d,.]*\s*(?:%|mah|mp\b|hz|gb|tb|nits?|inch|hours?|dollars?|watts?)|\$\s?\d", s, re.I)
    if COMPARE.search(s) and len(nums) >= 2:
        return "comparison"
    if DATE.search(s):
        return "date"
    if SPEC.search(s):
        return "spec"
    if COMPARE.search(s):
        return "comparison"
    if DESIGN.search(s):
        return "product"
    return "general"


def proposed_v1(sentence: str, kind: str, phone: str = "", ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The existing layer this kind maps to. asset_ready False = the picture needs material the tool does not have (real photo, source screenshot)."""
    from . import director, sides

    if kind == "source":
        return {"visual": "quote card", "layer": "pt_tweet", "asset_ready": True, "reason": "a claim with a source: the source's name and words on a card"}
    if kind == "date":
        return {"visual": "big date type", "layer": "pt_bigtype", "asset_ready": True, "reason": "a date or time: big type, changes to the next date"}
    if kind in ("spec", "comparison"):
        sc = director.scene_for(sentence, phone or "Galaxy S27 Ultra", ctx if ctx is not None else {})
        if sc:
            layer = (sc.get("layer") or {}).get("type") or {"sides": "pt_sides"}.get(sc.get("kind"), "pt_" + str(sc.get("kind")))
            return {"visual": f"figure scene ({sc.get('kind')})", "layer": layer, "asset_ready": True, "reason": "the director found a figure in the sentence"}
        if sides.sides_for(sentence, phone):
            return {"visual": "two-sided figures", "layer": "pt_sides", "asset_ready": True, "reason": "two figures of one kind"}
        return {"visual": "big figure type", "layer": "pt_bigtype", "asset_ready": True, "reason": "a spec or comparison with no figure the director reads: the key phrase in big type"}
    if kind == "problem":
        return {"visual": "real problem photo or footage", "layer": "footage", "asset_ready": False, "reason": "a problem is shown by the real thing; no such photo source exists yet"}
    if kind == "opinion":
        return {"visual": "hold previous scene", "layer": "hold", "asset_ready": True, "reason": "opinion: no new graphic, the references stay on the scene or the presenter"}
    if kind == "question":
        return {"visual": "hold previous scene", "layer": "hold", "asset_ready": True, "reason": "a question keeps the thing asked about on screen"}
    if kind == "product":
        d = director.three_d_for(sentence)
        return {"visual": "3D phone shot" + (f" ({d['kind']})" if d else ""), "layer": "3d", "asset_ready": True, "reason": "the sentence is about the design itself"}
    return {"visual": "hold previous scene", "layer": "hold", "asset_ready": True, "reason": "general explanation: no picture of its own"}


def old_visual(spec: Dict[str, Any], a: float, b: float) -> Dict[str, Any]:
    """What the existing pipeline put on screen for [a, b]: the dominant shot and the graphic layers over it."""
    best, best_ov = None, 0.0
    for s in spec.get("shots", []):
        ov = min(b, s["end"]) - max(a, s["start"])
        if ov > best_ov:
            best, best_ov = s, ov
    if not best:
        return {"visual": "none", "layer": "none"}
    gfx = []
    for L in spec.get("layers", []):
        t = L.get("type", "")
        if t in ("pt_subtitle", "pt_paper", "tm_title") or not t.startswith("pt_") or min(b, L.get("end", 0)) - max(a, L.get("start", 0)) <= 0.3:
            continue
        gfx.append(t)
    held = best["start"] < a - 0.5 and best["end"] > a
    if gfx:
        return {"visual": gfx[0], "layer": gfx[0], "held": held}
    k = best.get("kind")
    if k in ("image", "video"):
        return {"visual": "footage or picture", "layer": "footage", "held": held}
    if k == "product":
        return {"visual": "generic 3D phone (no graphic)", "layer": "3d", "held": held}
    return {"visual": f"{k} card", "layer": str(k), "held": held}


def _same(new: Dict[str, Any], old: Dict[str, Any]) -> bool:
    if new["layer"] == old["layer"]:
        return True
    if new["layer"] == "hold" and old.get("held"):
        return True
    figures = {"pt_sides", "pt_flatphones", "pt_bench", "pt_compare3", "pt_gauge", "pt_glass", "pt_coststack", "pt_thermal", "pt_lenses", "pt_swatches", "pt_bigtype", "pt_feature"}
    return new["layer"] in figures and old["layer"] in figures



# ---------------------------------------------------------------- Phase 1B: primary purpose, secondary attributes ----------------------------------------------------------------
PRIMARY = ("hook", "signoff", "question", "advice", "test", "date", "price", "spec", "comparison", "reported_problem", "criticism", "source_claim", "product", "lead_in", "explanation")

SIGNOFF = re.compile(r"\b(subscribe|in the comments|thanks for watching|see you (?:in|next)|like the video|hit the bell|let me know|tell me in)\b", re.I)
ADVICE = re.compile(r"\b(i['’]d|i would|i think|honestly|personally|you should|if you['’]re thinking|if you buy|if you(?:['’]re)? (?:want|need)|wait for|consider|my advice|"
                    r"close to essential|worth (?:it|buying)|don['’]t buy|i wouldn['’]t|bottom line)\b", re.I)
TEST = re.compile(r"\b(tests?|tested|testing|demo(?:nstration)?|benchmark(?:ed)?|powder|torture|bend test|drop test|stress|measured|x-?ray|cutaway|hands[- ]on)\b", re.I)
PRICE = re.compile(r"\$\s?\d|\b\d[\d,]*\s*dollars?\b|\b(?:costs?|price[sd]?|priced)\b(?=.*\d)", re.I)
EXPLICIT_DATE = re.compile(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\b|\blaunch day\b", re.I)
FIGURE = re.compile(r"\d[\d,.]*\s*(?:%|percent|w\b|watts?|mah|mp\b|megapixels?|hz|hertz|gb|tb|nits?|mm\b|inch(?:es)?|hours?|hrs?\b|fps|out of \d+)|\b\d+ out of \d+\b", re.I)
PHYSICAL = re.compile(r"\b(cracks?|cracked|broke\w*|won['’]t (?:open|close|fold)|noises?|loose|damaged?|peel\w*|dead pixels?|bright lines?|bent|snapp\w+|failure|failed|particles?)\b", re.I)
CRITIC = re.compile(r"\b(problems?|issues?|trouble|worr\w+|concerns?|risk\w*|weak\w*|disappoint\w*|fell behind|compromises|awkward|lacks?|no telephoto|mixed reviews|tight|expensive|costly|nobody knows|unclear)\b", re.I)
COMPARE2 = re.compile(r"\b(vs\.?|versus|compared (?:to|with)|than|instead of|rather than|unlike|same as|different from|more than|less than|thinner|thicker|bigger|smaller|previous|last year)\b", re.I)
DESIGN2 = re.compile(r"\b(design|hinge|fold\w*|frame|body|colou?rs?|finish|camera\w*|lens\w*|screen|display|inside|crease|thin|slim|shape|book[- ]style|what is the)\b", re.I)
LEAD_IN = re.compile(r"^(?:so |but |and )?(?:let['’]s|here is|here['’]s|first,|now,|next,|so here)\b|\bhere is how\b|\bwhat it said\b|^so my take\b", re.I)
VERB = r"(?:says?|said|reports?|reported|reporting|told|stated|announced|acknowledged|responded|confirmed|published|claims?|gave|offers?|wrote|liked|found|rated|called)"
NOT_NAMES = {"the", "it", "its", "this", "that", "they", "their", "some", "others", "one", "many", "but", "so", "and", "if", "here", "let", "on", "first", "iphone", "duo", "pro", "apple’s", "a", "an", "nobody", "supply", "battery", "there", "tell", "now"}
REPORTER_GROUPS = {"owners", "owner", "customers", "reviewers", "reviewer", "analysts", "tipsters", "leakers", "one outlet", "several outlets"}
GROUPS = re.compile(r"\b(reviewers?|owners?|analysts?|tipsters?|leakers?|one outlet|several outlets|customers)\b", re.I)
MISSING_ASSET = [
    (re.compile(r"crack", re.I), "close-up photo or video of a cracked foldable inner display along the fold line, ideally a real owner's report"),
    (re.compile(r"hinge|won['’]t open|noises?|loose", re.I), "footage of a foldable hinge failing to open or close fully, or a real owner's photo of the damaged hinge"),
    (re.compile(r"dead pixels?|bright lines?", re.I), "photo of bright lines or dead pixels on a foldable inner display"),
]


def source_of(s: str) -> Optional[str]:
    """The named source of an attribution, if the sentence has one ("iFixit", "Apple", "Macworld", "reviewers"), else None."""
    m = re.search(r"\b(?i:according to|per)\s+([a-z]?[A-Z][\w’']*(?:\s[A-Z][\w’']*)?)", s)
    if m:
        return m.group(1)
    m = re.search(r"\b([a-z]?[A-Z][A-Za-z]+)(?:[’']s)\s+(?:teardown|verdict|report|review|statement|score|test)\b", s)
    if m and m.group(1).lower() not in NOT_NAMES:
        return m.group(1)
    for m in re.finditer(r"\b([a-z]?[A-Z][A-Za-z]+)(?:\s+(?:has|have|had|now|not|also|already))*\s+" + VERB + r"\b", s):
        if m.group(1).lower() not in NOT_NAMES and not s[:m.start()].lower().rstrip().endswith((" in", " from", " of")) and s[:m.start()].lower().rstrip() != "in":
            return m.group(1)
    m = GROUPS.search(s)
    if m and re.search(VERB + r"|\bin (?:australia|the)\b|\bowners? in\b", s, re.I):
        return m.group(1).lower().capitalize()
    return None


def _meaningful_claim(s: str, src: Optional[str]) -> bool:
    if not src or LEAD_IN.search(s):
        return False
    return len(re.findall(r"[A-Za-z0-9’']+", s)) >= 7


def classify(sentence: str, index: int = 1, total: int = 0) -> Dict[str, Any]:
    """{"primary", "secondary": {...}, "confidence", "ambiguity": [...]} by the sentence's main editorial purpose; attribution is a secondary property."""
    s = (sentence or "").strip()
    src = source_of(s)
    sec: Dict[str, Any] = {}
    if src:
        sec["source"] = src
    if EXPLICIT_DATE.search(s):
        sec["date"] = EXPLICIT_DATE.search(s).group(0)
    if PRICE.search(s):
        sec["price"] = True
    if FIGURE.search(s):
        sec["figure"] = True
    if PHYSICAL.search(s):
        sec["physical_problem"] = True
    if re.search(r"\b(reports?|reported|reporting|complain\w*)\b", s, re.I):
        sec["reported"] = True
    signals = [k for k, on in (("date", "date" in sec), ("price", "price" in sec), ("figure", "figure" in sec), ("physical_problem", "physical_problem" in sec)) if on]
    amb: List[str] = []
    conf = "high"
    if not s:
        return {"primary": "explanation", "secondary": sec, "confidence": "low", "ambiguity": ["empty"]}
    if index == total and total and SIGNOFF.search(s):
        p = "signoff"
    elif SIGNOFF.search(s):
        p = "signoff"
    elif s.endswith("?"):
        p = "question"
    elif ADVICE.search(s):
        p = "advice"
    elif TEST.search(s) and not PRICE.search(s):
        p = "test"
    elif "date" in sec:
        p = "date"
    elif "price" in sec:
        p = "price"
    elif src and src.lower() not in REPORTER_GROUPS and _meaningful_claim(s, src) and not FIGURE.search(s):
        p = "source_claim"
    elif PHYSICAL.search(s) and (sec.get("reported") or src):
        p = "reported_problem"
    elif FIGURE.search(s):
        p = "comparison" if (COMPARE2.search(s) and len(FIGURE.findall(s)) >= 2) else "spec"
    elif PHYSICAL.search(s):
        p = "reported_problem"
    elif CRITIC.search(s):
        p = "criticism"
    elif LEAD_IN.search(s):
        p = "lead_in"
    elif _meaningful_claim(s, src):
        p = "source_claim"
    elif src:
        p = "lead_in"
    elif DESIGN2.search(s):
        p = "product"
    else:
        p = "explanation"
    if index == 1 and p in ("explanation", "criticism", "product", "date", "source_claim", "reported_problem") and total and total > 3:
        sec["opening"] = True
        amb.append("opening hook")
        p = "hook"
    if len(signals) >= 2 and p in ("date", "price", "reported_problem"):
        amb.append("several strong signals: " + ", ".join(signals))
    if p in ("explanation", "criticism") and not src:
        conf = "medium" if p == "criticism" else "low"
        if p == "explanation":
            amb.append("no signal: general narration")
    if amb:
        conf = "low" if conf == "low" or len(signals) >= 3 else "medium"
    return {"primary": p, "secondary": sec, "confidence": conf, "ambiguity": amb}


def kind_of(sentence: str) -> str:
    return classify(sentence)["primary"]


THREE_D_KINDS = {"xray", "fold", "chip", "macro", "orbit", "hero", "flip"}


def _scene_row(R, sc: Dict[str, Any], reason: str, alt) -> Dict[str, Any]:
    layer = (sc.get("layer") or {}).get("type")
    if layer:
        return R(f"graphic ({layer})", layer, reason, alt)
    if sc.get("kind") in THREE_D_KINDS:
        return R(f"3D phone shot ({sc.get('kind')})", "3d", reason, alt)
    return R("figure graphic (director scene)", "pt_" + str(sc.get("kind")), reason, alt)


def _missing(s: str) -> str:
    for rx, text in MISSING_ASSET:
        if rx.search(s):
            return text
    return "real photo or footage showing: " + " ".join(s.split()[:10])


def proposed(sentence: str, c: Dict[str, Any], seconds: float, phone: str = "", ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from . import director, sides

    p, sec, src = c["primary"], c["secondary"], c["secondary"].get("source")
    R = lambda visual, layer, reason, alt=None, **k: {"visual": visual, "layer": layer, "reason": reason, "alt": alt, "asset_ready": True, "required_asset": "", **k}
    TYPE = ("key-phrase type", "pt_bigtype")
    if p == "signoff":
        return R("end card", "pt_tagline", "sign-off: the call to action on an end card")
    if p == "hook" or sec.get("opening"):
        return R("3D hero phone", "3d", "the opening names the product: the phone is the right first picture", TYPE)
    if p == "advice":
        return R("verdict type", "pt_bigtype", "advice or opinion: the advice itself in big type, no source card", ("3D phone shot", "3d"))
    if p == "test":
        d = director.three_d_for(sentence)
        return R("3D inside shot" + (f" ({d['kind']})" if d else ""), "3d", "a test or demonstration of the product: show the part being tested", TYPE,
                 optional_asset="real test photo or footage would be better" + (f" (by {src})" if src else ""))
    if p == "date":
        return R("big date type", "pt_bigtype", "a dated event" + (f" by {src}" if src else "") + ": the date big, the event under it", ("quote card", "pt_tweet") if _meaningful_claim(sentence, src) else TYPE)
    if p in ("price", "spec", "comparison"):
        what = {"price": "price", "spec": "specification", "comparison": "comparison"}[p] + (f", attributed to {src} as a small label" if src else "")
        if sides.sides_for(sentence, phone):
            return R("two-sided figures", "pt_sides", what + ": two figures of one kind", TYPE)
        sc = director.scene_for(sentence, phone or "Galaxy S27 Ultra", ctx if ctx is not None else {})
        if sc and (sc.get("layer") or {}).get("type") == "pt_tweet":
            sc = None                                    # a quote card is not how a figure is shown
        if sc and sc.get("kind") in THREE_D_KINDS:
            sc = None                                    # a figure is not shown by an unrelated 3D shot
        if sc:
            return _scene_row(R, sc, what + ": the director read the figures", TYPE)
        return R("big figure type", "pt_bigtype", what + ": the figure in big type", TYPE)
    if p == "reported_problem":
        return {"visual": "MISSING ASSET", "layer": "missing", "reason": "a reported physical problem is shown by the real thing; no source for such photos exists in the tool",
                "alt": ("quote card", "pt_tweet") if _meaningful_claim(sentence, src) else TYPE, "asset_ready": False, "required_asset": _missing(sentence)}
    if p == "criticism":
        sc = director.scene_for(sentence, phone or "Galaxy S27 Ultra", ctx if ctx is not None else {})
        if sc:
            return _scene_row(R, sc, "criticism of a spec or part the director can draw", TYPE)
        if DESIGN2.search(sentence):
            d = director.three_d_for(sentence)
            return R("3D phone shot" + (f" ({d['kind']})" if d else ""), "3d", "criticism of a part of the product: show that part", TYPE)
        return R("key-phrase type", "pt_bigtype", "criticism with nothing to draw: the phrase in type", None)
    if p == "source_claim":
        return R("quote card", "pt_tweet", f"a named source ({src}) with a meaningful claim: the claim on a card naming the source", TYPE)
    if p == "product":
        d = director.three_d_for(sentence)
        return R("3D phone shot" + (f" ({d['kind']})" if d else ""), "3d", "the sentence is about the design itself", TYPE)
    if p == "question" and re.search(r"\bwhat is (?:the )?(?:iphone|galaxy|pixel|new)\b", sentence, re.I):
        return R("3D hero phone", "3d", "a question asking what the product is: the product", TYPE)
    if p in ("question", "lead_in") and seconds <= 2.5:
        return R("hold previous scene", "hold", f"a {seconds:.1f} s {p.replace('_', ' ')} that continues the topic before it; too short for its own picture", TYPE)
    if p == "question":
        return R("question type", "pt_bigtype", "the question on screen", ("3D phone shot", "3d"))
    if p == "lead_in":
        label = (src + " responds") if src else "key phrase"
        return R(f"lead-in type ({label})", "pt_bigtype", "a lead-in to the next point: its subject named in type", None)
    return R("key-phrase type", "pt_bigtype", "general narration: its key phrase in type; no picture of its own is implied", None)


def _vary(rows: List[Dict[str, Any]]) -> None:
    """A third identical visual in a row becomes its alternative."""
    for i in range(1, len(rows)):                        # a hold needs a real picture before it, never a missing asset or another hold
        if rows[i]["layer"] == "hold" and rows[i - 1]["layer"] in ("missing", "hold") and rows[i].get("alt"):
            rows[i]["visual"], rows[i]["layer"] = rows[i]["alt"]
            rows[i]["reason"] += " (no hold after a missing asset or another hold)"
    for i in range(2, len(rows)):
        a, b, c = rows[i - 2], rows[i - 1], rows[i]
        if c["visual"] == b["visual"] == a["visual"] and c.get("alt") and c["layer"] not in ("missing", "hold"):
            c["visual"], c["layer"] = c["alt"]
            c["reason"] += " (varied: third identical visual in a row)"
            c["varied"] = True


def diagnose(script: str, words: Sequence[Any], duration: float, spec: Dict[str, Any], phone: str = "") -> List[Dict[str, Any]]:
    from . import review, voiceover as vo

    parsed = review.parse_script(script)
    lines = [i["text"] for c in parsed["chapters"] for i in c["items"] if i["kind"] == "line"]
    spans = vo.align_lines(lines, words, duration)["spans"]
    ctx: Dict[str, Any] = {"unit": None, "topic": None}
    rows, prev_sig = [], None
    for i, text in enumerate(lines):
        a, b = spans[i][0], spans[i][1]
        if i + 1 < len(lines):
            b = max(b, spans[i + 1][0])
        c = classify(text, i + 1, len(lines))
        new = proposed(text, c, b - a, phone, ctx)
        old = old_visual(spec, a, b)
        v1 = kind_of_v1(text)
        rows.append({"n": i + 1, "sentence": text, "primary": c["primary"], "secondary": c["secondary"], "confidence": c["confidence"], "ambiguity": c["ambiguity"],
                     "visual": new["visual"], "layer": new["layer"], "reason": new["reason"], "alt": new.get("alt"), "asset_ready": new["asset_ready"], "required_asset": new["required_asset"],
                     "optional_asset": new.get("optional_asset", ""), "seconds": round(b - a, 1), "old_visual": old["visual"], "old_layer": old["layer"], "old_held": bool(old.get("held")),
                     "old_generic_3d": old["layer"] == "3d" and old["visual"].startswith("generic"), "old_repeat": old["visual"] == prev_sig, "v1_kind": v1})
        prev_sig = old["visual"]
    _vary(rows)
    for r in rows:
        r["same_as_old"] = _same(r, {"layer": r["old_layer"], "held": r["old_held"]})
    return rows


def _secs(rows, key):
    d: Dict[str, float] = {}
    for r in rows:
        d[r[key]] = d.get(r[key], 0.0) + r["seconds"]
    return d


def report(rows: List[Dict[str, Any]], table: bool = True) -> str:
    out: List[str] = []
    tot = sum(r["seconds"] for r in rows) or 1.0
    if table:
        out.append("| # | sec | primary | secondary | proposed visual | conf | required asset / note |")
        out.append("|---|---|---|---|---|---|---|")
        for r in rows:
            sec = ", ".join(f"{k}={v}" if v is not True else k for k, v in r["secondary"].items() if k != "opening")
            note = r["required_asset"] and "MISSING: " + r["required_asset"] or (("optional: " + r["optional_asset"]) if r["optional_asset"] else "")
            if r["ambiguity"]:
                note = (note + " | " if note else "") + "AMBIGUOUS: " + "; ".join(r["ambiguity"])
            out.append(f"| {r['n']} | {r['seconds']} | {r['primary']} | {sec} | {r['visual']} | {r['confidence']} | {note} |")
        out.append("")
    cnt = lambda key, rs: ", ".join(f"{k} {n}" for k, n in sorted(((k, sum(1 for r in rs if r[key] == k)) for k in {r[key] for r in rs}), key=lambda kv: -kv[1]))
    out.append("Sentences by primary kind (v1.5): " + cnt("primary", rows))
    out.append("Sentences by kind (phase 1, before): " + cnt("v1_kind", rows))
    q_old = sum(r["seconds"] for r in rows if r["v1_kind"] == "source")
    q_new = sum(r["seconds"] for r in rows if r["layer"] == "pt_tweet")
    out.append(f"Quote-card seconds: before {q_old:.0f}s ({100 * q_old / tot:.0f}%), now {q_new:.0f}s ({100 * q_new / tot:.0f}%), {sum(r['layer'] == 'pt_tweet' for r in rows)} sentences")
    out.append("Seconds by proposed visual: " + ", ".join(f"{k} {v:.0f}s ({100 * v / tot:.0f}%)" for k, v in sorted(_secs(rows, 'visual').items(), key=lambda kv: -kv[1])))
    out.append("Seconds by old visual: " + ", ".join(f"{k} {v:.0f}s ({100 * v / tot:.0f}%)" for k, v in sorted(_secs(rows, 'old_visual').items(), key=lambda kv: -kv[1])))
    g = sum(r["seconds"] for r in rows if r["old_generic_3d"])
    out.append(f"Old pipeline: generic 3D with no graphic {g:.0f}s = {100 * g / tot:.0f}%")
    p3 = sum(r["seconds"] for r in rows if r["layer"] == "3d")
    h = sum(r["seconds"] for r in rows if r["layer"] == "hold")
    out.append(f"Proposed: 3D phone {p3:.0f}s ({100 * p3 / tot:.0f}%), hold previous {h:.0f}s ({100 * h / tot:.0f}%), varied by the run rule: {sum(bool(r.get('varied')) for r in rows)}")
    longest, run, prev = 1, 1, None
    for r in rows:
        run = run + 1 if r["layer"] == prev else 1
        longest, prev = max(longest, run), r["layer"]
    out.append(f"Longest run of the same visual: proposed {longest}")
    no = [r for r in rows if not r["asset_ready"]]
    out.append(f"Missing assets: {len(no)} sentences, {sum(r['seconds'] for r in no):.0f}s ({100 * sum(r['seconds'] for r in no) / tot:.0f}%): " + ", ".join(str(r["n"]) for r in no))
    amb = [r for r in rows if r["confidence"] != "high"]
    out.append("Ambiguous or low-confidence sentences: " + ", ".join(f"#{r['n']} ({r['confidence']})" for r in amb))
    out.append(f"Same visual as old: {sum(r['same_as_old'] for r in rows)} of {len(rows)} sentences")
    return "\n".join(out)


def main(argv: List[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    phone = argv[argv.index("--phone") + 1] if "--phone" in argv else ""
    if phone in args:
        args.remove(phone)
    script = open(args[0], encoding="utf-8").read()
    words = json.load(open(args[1], encoding="utf-8"))
    spec = json.load(open(args[2], encoding="utf-8"))
    dur = float(spec.get("duration") or words[-1][2])
    print(report(diagnose(script, words, dur, spec, phone)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
