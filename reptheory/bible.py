"""The script bible: one reading of the WHOLE script before any picture is described, so every beat's picture knows what the video is about.

A beat is 2-4 seconds of narration. Drawn on its own words alone it loses the video: "make the Cup Hold your focus" became a man holding a drinking cup,
"10 seconds in, your forearm burns" lost the backpack and the table, and a gym bro losing to a construction worker became our trainee beating a rival.
The bible (rules only, no Gemini, the same on every machine) gives each scene:
  cast     the people THIS script sets against each other ("a 200-pound gym bro with huge biceps" vs "a 150-pound construction worker"), and who wins
  section  the exercise / move being taught ("angle number two: the cup hold") and its setup sentences (props, body position)
  mode     setup (doing the exercise), explain (why it works), study (a study and its numbers), cta, score, plan
  terms    the script's own names ("the cup", "the twist"): a later mention means the move, never the everyday object
  context  the sentence the picture needs to make sense (the setup, the study, the earlier line about the people)
build(scenes) stores it on each scene as sc["_bible"]; beat_art.prompt_for(text, hook, ctx) uses it. A script with none of these gets no bible and the old prompt."""
from __future__ import annotations
import re
from typing import Dict, List, Optional

# ---- people ---------------------------------------------------------------------------------------------------------------------------------------------
MUSCLE = ("gym bros?", "gym guys?", "gym rats?", "gym lifters?", "bodybuilders?", "powerlifters?", "lifters?", "big guys?", "jacked guys?", "muscle guys?")
WORKER = ("construction workers?", "mechanics?", "carpenters?", "roofers?", "farmers?", "farm boys?", "bricklayers?", "plumbers?", "welders?", "tradesm[ae]n", "labou?rers?",
          "builders?", "movers?", "lumberjacks?", "blue[- ]collar workers?", "warehouse workers?", "factory workers?", "electricians?", "dock workers?")
OTHER = ("rock climbers?", "climbers?", "boxers?", "wrestlers?", "arm wrestlers?", "sprinters?", "runners?", "swimmers?", "gymnasts?", "soldiers?", "office workers?", "nurses?",
         "grandmas?", "grandpas?", "grandmothers?", "grandfathers?", "dads?", "moms?", "fathers?", "mothers?", "old m[ae]n", "old wom[ae]n", "seniors?", "dancers?", "monks?")
_ARCH = [(p, "muscle") for p in MUSCLE] + [(p, "worker") for p in WORKER] + [(p, "other") for p in OTHER]
_PEOPLE_RX = re.compile(r"\b(" + "|".join(p for p, _ in sorted(_ARCH, key=lambda a: -len(a[0]))) + r")(?:'s)?\b", re.I)
_MOD = r"(?:(?:\d+|[a-z]+)[- ](?:pound|lb|kilo|kg|year[- ]old)s?[- ]|big |huge |massive |small |skinny |lean |tiny |short |tall |old |young |wiry |jacked |ripped |heavier |lighter |average |normal |regular |real )*"
LOSE_RX = re.compile(r"\b(pinned|pins? him|loses?|lost|folds?|folded|gets? beat(?:en)?|beaten|crushed|slammed|gives? up|tapped out|collapses?|fails?)\b", re.I)
WIN_RX = re.compile(r"\b(wins?|won|beats?|pins?(?! him)|destroys?|outlasts?|outpulls?)\b", re.I)

def _arch(label: str) -> str:
    for p, a in _ARCH:
        if re.fullmatch(p, label, re.I): return a
    return "other"

def _key(label: str) -> str: return re.sub(r"(?<=[a-z])s$", "", re.sub(r"\s+", " ", label.lower().replace("-", " "))).replace("men", "man").replace("women", "woman")

LOOK = {"muscle": "a big heavily muscled man with a buzz cut, huge arms and chest, plain grey tank top",
        "worker": "a wiry, ordinary-sized working man (not bulky), thick calloused hands and corded forearms, work shirt with rolled-up sleeves and work trousers",
        "other": ""}

def find_cast(sentences: List[str]) -> List[dict]:
    """The people the script talks about, in order of first mention: [{key, label, phrase, arch, desc, aliases, role}]. 'A or B' (construction worker or mechanic) is one person."""
    cast: Dict[str, dict] = {}; alias: Dict[str, str] = {}
    for s in sentences:
        for m in _PEOPLE_RX.finditer(s):
            k = _key(m.group(1))
            if k in alias or k in cast: continue
            before = s[:m.start()]
            orm = re.search(r"\b(" + "|".join(p for p, _ in _ARCH) + r")\s+(?:or|and/or|/)\s*$", before, re.I)      # "construction worker or mechanic": the same man
            if orm and _key(orm.group(1)) in cast: alias[k] = _key(orm.group(1)); cast[_key(orm.group(1))]["aliases"].append(k); continue
            mod = re.search(r"(?:\b(?:a|an|the|this|that|one)\s+)(" + _MOD + r")$", before, re.I)
            after = re.match(r"(?:'s)?\s+with\s+((?:big|huge|massive|thick|skinny|bigger|giant|strong|calloused|tiny)\s+[a-z]+)", s[m.end():], re.I)
            phrase = ((mod.group(1) if mod else "") + m.group(1).lower() + (f" with {after.group(1).lower()}" if after else "")).strip()
            cast[k] = {"key": k, "label": m.group(1).lower(), "phrase": phrase, "arch": _arch(m.group(1)), "aliases": [], "role": "", "first": len(cast)}
    people = list(cast.values())
    for c in people:
        look = LOOK[c["arch"]]
        c["desc"] = f"{c['phrase']}" + (f": {look}" if look else "") + ", drawn in the same manga ink style"
    if len(people) >= 2:      # who wins: the first sentence that has one of the first two people losing (or winning)
        a, b = people[0], people[1]
        for s in sentences:
            ha, hb = bool(names_rx(a).search(s)), bool(names_rx(b).search(s))
            if ha == hb: continue
            who, other = (a, b) if ha else (b, a)
            if LOSE_RX.search(s): who["role"], other["role"] = "loses", "wins"; break
            if WIN_RX.search(s): who["role"], other["role"] = "wins", "loses"; break
    return people

def names_rx(c: dict):
    words = [c["key"]] + c["aliases"]
    return re.compile(r"\b(?:" + "|".join(re.escape(w).replace(r"\ ", r"[\s-]+") + r"(?:s|'s)?" for w in words) + r")\b", re.I)

# ---- sections, modes, terms -----------------------------------------------------------------------------------------------------------------------------
_N = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|first|second|third|fourth|fifth|last|final|\d+)"
HEADER_RX = re.compile(r"(?:\b(?:angle|movement|move|step|exercise|drill|hold|position|technique|trick|tip|rule|level|phase|part|stage|habit|method)\s+(?:number\s+)?" + _N +
                       r"|\bthe\s+(?:first|second|third|fourth|fifth|sixth|seventh|next|last)(?:\s+and\s+(?:final|last))?\s+(?:movement|move|exercise|drill|hold|position|step))"      # "Movement number one is ...", "the fifth and final movement: ..."
                       r"\s*[:,.\-–—]?\s*(?:is\s+)?(?:the\s+)?([a-z0-9][a-z0-9'\-]*(?:\s+[a-z][a-z'\-]*){0,3})", re.I)
MOVE_END = {"snatch", "catch", "hold", "lock", "drop", "press", "pull", "push", "carry", "hang", "sit", "raise", "curl", "walk", "squeeze", "pinch", "row", "dip", "plank", "bridge", "snap", "flick"}
PAREN_HEADER_RX = re.compile(r"(?:\(\s*|\bfor (?:your|the) [a-z ,'\-]{3,50}?\s\(?)the\s+([a-z0-9][a-z0-9'\-]*(?:\s+[a-z][a-z'\-]*){0,3})\s*\)?\s*:"
                             r"|^for (?:your|the) [a-z ,'\-]{3,50}?\sthe\s+([a-z0-9][a-z0-9'\-]*(?:\s+[a-z][a-z'\-]*){0,3})\b", re.I)      # a transcript: "for your hands and elbows the backpack drop snatch" (no brackets, no colon)      # "For your hands (The Backpack Drop Snatch): ..." names the drill it teaches
AFTER_COLON_RX = re.compile(r":\s*(?:the\s+)?([a-z0-9][a-z0-9'\-]*(?:\s+[a-z][a-z'\-]*){0,3})", re.I)      # "Movement number four pairs two holds: the multi-angle wall sit ..." -> the name after the colon
HEADER_STOP = {"and", "for", "paired", "pairs", "with", "goes", "this", "is", "it", "you", "your", "so", "now", "but", "which", "that", "here", "we", "i", "let's", "lets", "try", "stay", "sit", "stand", "put", "grab", "loop", "rest"}
GENERIC = {"the", "a", "an", "hold", "holds", "move", "exercise", "drill", "angle", "position", "test", "of", "and", "your", "my"}
END_RX = re.compile(r"\b(how all (?:\w+ )?(?:moves|movements|exercises|holds) fit|before you copy|mistakes? to (?:skip|avoid)|questions everyone asks|a full week|weekly plan|test from the start|to sum (?:it )?up|in summary|quick recap|let'?s recap)\b", re.I)
EXPLAIN_RX = re.compile(r"^(?:and\s+)?(?:here'?s|that'?s|this is) why\b|^why\b|^look at\b|^think of\b|^imagine\b|\bhere'?s why\b|^(?:and\s+)?here'?s the (?:science|reason|thing)\b", re.I)
STUDY_RX = re.compile(r"\b(stud(?:y|ies|ied)|researchers?|scientists?|a (?:\d{4} )?review (?:of|in)|meta[- ]analys[ie]s|trials?|experiments?|doctors and researchers|analy[sz]ed|lab test)\b", re.I)
SETUP_RX = re.compile(r"^(?:now,?\s+|then,?\s+|next,?\s+|first,?\s+)?(?:to train it|do \d|do (?:one|two|three|four|five)|hold|rest|sit|stand|put|loop|grab|start|place|lie|lay|"
                      r"keep|squeeze|pull|push|twist|turn|curl|bend|lift|raise|lower|slide|wrap|go from|without|stay|too (?:hard|easy)|don'?t have|take|get into|get in|stack|tuck|step|open your|suddenly|"
                      r"the (?:most )?common mistake|\d+ seconds|(?:ten|twenty|thirty|five) seconds|by rep|add)\b", re.I)
CTA_RX = re.compile(r"\b(subscribe|tap like|hit like|smash (?:the )?like|comment (?:your|below|the)|pause and comment|in the comments|link in the description|first link|telegram|discord|patreon|share this)\b", re.I)
SCORE_RX = re.compile(r"^(?:under|over|more than|less than|below|above)?\s*\d+(?:\s*(?:to|-)\s*\d+)?\s*(?:seconds?|reps?|pounds?|minutes?)\s*:", re.I)      # "Under 10 seconds: ..." (a score band, not "20 seconds, a deep ache")
PLAN_RX = re.compile(r"\b(\d+ sets? of|days? a week|monday|wednesday|friday|per arm|per hand|minute version|whole session)\b", re.I)
VERSUS_RX = re.compile(r"\b(arm[- ]?wrestl\w*|versus|vs\.?|against|the other guy|his hand|his wrist|his palm|opponent|rival|match(?:es)?|pinned|the table)\b", re.I)
PRONOUN_RX = re.compile(r"\b(he|him|his|they|them|their)\b", re.I)

def _term_rx(name: str):
    words = [w for w in re.findall(r"[a-z]+", name.lower()) if w not in GENERIC]
    if not words: return None
    return re.compile(r"\b" + r"[\s-]+".join(re.escape(w) + r"(?:e?s)?" for w in words) + r"\b", re.I)

def split_sentences(text: str) -> List[tuple]:
    """[(start, end, sentence)] over the joined narration."""
    out = []
    for m in re.finditer(r"[^.!?]+(?:[.!?]+|$)", text):
        s = m.group(0).strip()
        if s: out.append((m.start() + (len(m.group(0)) - len(m.group(0).lstrip())), m.end(), s))
    return out

def build(scenes: List[dict]) -> Optional[dict]:
    """Reads every scene's narration once and stores the picture context on each scene (sc["_bible"]). Returns the bible, or None when the script gives nothing to adapt to."""
    texts = [re.sub(r"\s+", " ", str(sc.get("text") or "")).strip() for sc in scenes]
    joined, offs = "", []
    for t in texts:
        if joined and t: joined += " "
        offs.append(len(joined)); joined += t
    if not joined: return None
    sents = split_sentences(joined)
    if len(sents) <= 1 and len(texts) > 3: sents = [(o, o + len(t), t) for o, t in zip(offs, texts) if t]      # narration without punctuation: one scene, one sentence
    cast = find_cast([s for _, _, s in sents])
    # sections: each header opens one, the next header or a wrap-up line closes it
    secs: List[dict] = []; pending: List[str] = []
    for i, (a, b, s) in enumerate(sents):
        m = HEADER_RX.search(s) or PAREN_HEADER_RX.search(s)
        if m:
            raw = m.group(1) or m.group(m.lastindex)
            if re.match(r"\s*(?:pairs?|combines?|has|covers?|is (?:two|a pair))\b", raw, re.I):      # a header that names its parts later ("... pairs two holds: the wall sit ..."; a transcript has no colon)
                mc = AFTER_COLON_RX.search(s, m.start()) or re.compile(r"\bthe\s+((?!same\b)[a-z0-9][a-z0-9'\-]*(?:\s+[a-z][a-z'\-]*){0,3})", re.I).search(s, m.end(m.lastindex))
                if mc: raw = mc.group(1)
            ends = [k for k, w in enumerate(raw.split()) if k and w.lower() in MOVE_END]
            if ends and m.re is PAREN_HEADER_RX and not m.group(1): raw = " ".join(raw.split()[:ends[-1] + 1])      # "the one inch drop catch start at the top" -> "one inch drop catch"
            name = re.split(r"(?<!wall )\b(?:" + "|".join(HEADER_STOP) + r")\b", raw, flags=re.I)[0].strip(" -'")      # "wall sit" is one exercise
            if name and _term_rx(name) and not re.match(r"(?:seconds?|secs?|minutes?|mins?|reps?|sets?|rounds?|times?|days?|weeks?|percent|inch(?:es)?|feet|pounds?|kilos?)\b", name, re.I):      # "suitcase hold 45 seconds" is a time, not a move named "seconds"
                if secs and secs[-1]["end"] is None: secs[-1]["end"] = i
                secs.append({"name": name.lower(), "start": i, "end": None, "setup": [], "rx": _term_rx(name)})
                pending = [p for p in (re.split(r"\b(?:" + "|".join(HEADER_STOP) + r")\b", x, flags=re.I)[0].strip(" .,-") for x in re.findall(r"\b(?:and|paired with|plus|followed by)\s+the\s+([a-z0-9][a-z0-9'\-]*(?:\s+[a-z][a-z'\-]*){0,3})", s[m.end():], re.I)) if _term_rx(p) and p.lower() != name.lower()]      # "...: the wall sit for your knees, and the 4-second heel drop for your ankles"
                continue
        sub = next((p for p in (pending if secs and secs[-1]["end"] is None else []) if _term_rx(" ".join(p.split()[-2:])).search(s)), None)      # "heel drop" also in "the 4-second single-leg heel drop"
        if sub:      # the second move of a paired movement opens where it is named again ("... for the 4-second single-leg heel drop")
            secs[-1]["end"] = i; secs.append({"name": sub.lower(), "start": i, "end": None, "setup": [], "rx": _term_rx(sub)}); pending.remove(sub); continue
        if secs and secs[-1]["end"] is None and END_RX.search(s): secs[-1]["end"] = i
    for sec in secs:
        sec["end"] = sec["end"] if sec["end"] is not None else len(sents)
        rest = sents[sec["start"]:sec["end"]]; head = rest[0][2]; hm = HEADER_RX.search(head) or PAREN_HEADER_RX.search(head); after = head[hm.end():].strip(" .,:") if hm else head.strip(" .,:")      # "Angle number two: the cup hold. Stay at the table..."
        pool = ([after] if len(after.split()) >= 4 else []) + [s for _, _, s in rest[1:]]
        for s in pool[:12]:
            if EXPLAIN_RX.search(s) or STUDY_RX.search(s):
                if sec["setup"]: break
                continue      # a move that opens on its reason or a study ("In a study of trained men ...") still has its setup a few lines on
            if SETUP_RX.search(s) and not CTA_RX.search(s) and len(sec["setup"]) < 3: sec["setup"].append(s.rstrip("."))
        sec["setup_text"] = _cap(". ".join(sec["setup"]), 360)
    if not cast and not secs: return None
    # one pass over the sentences: section, mode, study context, carried term, last line about the people
    info = []; mode = "intro"; study = ""; carry = None; carry_i = 0; people_line = ""
    for i, (a, b, s) in enumerate(sents):
        sec = next((x for x in secs if x["start"] <= i < x["end"]), None)
        if sec and i == sec["start"]: mode = "setup"; study = ""
        elif not sec: mode = "intro" if not secs or i < secs[0]["start"] else "after"
        if sec and EXPLAIN_RX.search(s): mode = "explain"
        if STUDY_RX.search(s) and re.search(r"\d|one|two|three|four|five|six|seven|eight|nine|ten|dozen|hundred", s, re.I): mode, study = "study", s.rstrip(".")
        elif mode == "study" and sec and SETUP_RX.search(s) and not re.search(r"\d+ out of \d+|\d+%|percent", s): mode = "setup"
        elif mode == "study" and not sec and not re.search(r"\d", s) and not STUDY_RX.search(s) and (PLAN_RX.search(s) or END_RX.search(s)): mode = "after"
        elif mode == "study" and not STUDY_RX.search(s) and not re.search(r"\d|percent|\b(?:in plain words|that means|which means|the result|to be fair)\b", s, re.I) and i > 0 and not STUDY_RX.search(sents[i - 1][2]) and not re.search(r"\d", sents[i - 1][2]): mode = "explain" if sec else "after"      # two lines on from the study and saying nothing about it: the study is over
        elif mode in ("explain",) and sec and SETUP_RX.search(s) and re.match(r"(?:to train it|do |hold |too |don'?t have|the (?:most )?common mistake|rest )", s, re.I): mode = "setup"
        kind = "cta" if CTA_RX.search(s) else "score" if SCORE_RX.search(s) else "study" if mode == "study" else "plan" if PLAN_RX.search(s) and not sec else mode
        terms = [x for x in secs if x is not sec and x["start"] < i and x["rx"].search(s)]      # named after it was taught; the roadmap ("The Twist, The Cup...") comes before
        if terms and not sec: carry, carry_i = terms[0], i
        elif sec or END_RX.search(s) or (carry and i - carry_i > 1): carry = None      # "it" in the next line may be that move; three lines on it is not
        named = [c for c in cast if names_rx(c).search(s)]
        if named: people_line = s.rstrip(".")
        info.append({"i": i, "section": sec, "mode": mode, "kind": kind, "study": study if mode == "study" else "", "terms": terms or ([carry] if carry and not sec else []),
                     "named": named, "people_line": people_line, "s": s})
    bible = {"cast": cast, "sections": [{k: v for k, v in x.items() if k != "rx"} for x in secs]}
    for sc, o, t in zip(scenes, offs, texts):
        if not t: continue
        mid = o + len(t) // 2; k = next((j for j, (a, b, _) in enumerate(sents) if a <= mid < b + 1), len(sents) - 1)      # the sentence most of the scene is in
        sc["_bible"] = _ctx(t, info[k], cast)
    return bible

def _cap(s: str, n: int) -> str: return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "..."

def _ctx(text: str, inf: dict, cast: List[dict]) -> dict:
    """What one scene's picture needs: who is in it, the setup or study it belongs to, and what the script's own words mean."""
    sec = inf["section"]; ctx = {"kind": inf["kind"], "mode": inf["mode"], "section": sec["name"] if sec else "", "people": [], "context": "", "means": []}
    own = [c for c in cast if names_rx(c).search(text)]; named = own or inf["named"]
    if own and sec:      # "why construction workers have an unfair advantage here": the people the line names, even inside an exercise
        ctx["people"] = [c["desc"] for c in own]
    elif named and not sec:
        ctx["people"] = [c["desc"] + (f" (he {c['role']} the match)" if c["role"] else "") for c in (cast[:2] if (VERSUS_RX.search(inf["s"]) or len(named) > 1 or (cast[0]["role"] and (LOSE_RX.search(inf["s"]) or WIN_RX.search(inf["s"])))) else named)]      # the contest: both men
    elif not sec and inf["mode"] == "intro" and cast and (VERSUS_RX.search(text) or PRONOUN_RX.search(text) or not named):      # "That's not luck." right after the gym bro got pinned
        ctx["people"] = [c["desc"] + (f" (he {c['role']} the match)" if c["role"] else "") for c in cast[:2]]
        if inf["people_line"] and inf["people_line"].lower() not in text.lower(): ctx["context"] = f"the moment this line is about: {_cap(inf['people_line'], 220)}"
    big = next((c for c in cast if c["arch"] == "muscle"), None)
    if big: ctx["opponent"] = big["desc"]
    if sec and inf["mode"] == "setup" and sec.get("setup_text") and not _same_words(text, sec["setup_text"]):      # a setup fragment ("and rest your forearm flat") still gets the whole setup
        ctx["context"] = f"the exercise being taught is {sec['name']}: {sec['setup_text']}"
    elif sec and inf["mode"] == "explain":
        ctx["context"] = f"this line explains why {sec['name']} works; draw what the line describes, not the exercise"
    elif inf["kind"] == "study" and inf["study"] and not _same_words(text, inf["study"]):
        ctx["context"] = f"part of this study: {_cap(inf['study'], 240)}"
    elif inf["kind"] in ("cta", "score", "plan") and sec and sec.get("setup_text"):
        ctx["context"] = f"show the trainee doing {sec['name']}: {sec['setup_text']}"
    for t in inf["terms"]:
        if t and t.get("setup_text"):
            ctx["means"].append(f"\"{t['name']}\" is the name of an exercise in this video, not an everyday object: {t['setup_text']}")
    if inf["kind"] in ("cta", "score", "plan") and not ctx["context"] and ctx["means"]:
        ctx["context"] = "show the trainee doing the exercise this line names"
    return ctx if (ctx["people"] or ctx["context"] or ctx["means"] or ctx.get("opponent")) else {}

def _same_words(text: str, context: str) -> bool:
    """The scene already says the whole context (most of its words): no need to repeat it."""
    wa = set(re.findall(r"[a-z]+", text.lower())); wb = set(re.findall(r"[a-z]+", context.lower()))
    return bool(wb) and len(wa & wb) / len(wb) > 0.8
