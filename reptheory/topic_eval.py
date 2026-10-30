"""New-topic test set for Rep Theory (docs/rep_theory/UPGRADE_LIST.md, section 0, Rule 6). The channel posts a new topic every day, so every planner / effect change is judged on
scripts it was not designed around: test_fixtures/rep_theory_topics/*.txt (12 topics written only for this test + render 046's script). No render, no Flow call, no network: each
script is planned (beat planner + variety director, 3D and Flow looks allowed as decisions only) and measured. `python -m reptheory.topic_eval` prints the table;
`--write-baseline` records today's numbers, which test_rep_theory_topics.py then holds as a floor (a change may improve them, never make them worse).
Metrics, per script:
  picture_share     share of narration time on a picture tied to the words (a depiction, a card built from the sentence, a 3D clip or a Flow picture); text-only callouts,
                    the generic standing figure and takeaway word cards do not count
  fallback_share    share of beats the planner could not ground (continued, captioned, weak callout, generic fallback)
  anatomy_unnamed   anatomy / 3D scenes whose own words name no body part (render 046 showed the forearm for food and sleep); a 3D clip may come from a named exercise
  still_share       share of time inside gaps longer than 4 s in which nothing meaningful changes on screen
  held_no_change    scenes longer than 4 s with no meaningful change after they open
  looks             distinct looks used
  bad_headlines     on-screen texts that are not a phrase of the script: crossing a clause boundary, cut out of a longer noun run, ending on a verb or a dangling
                    word, starting on a conjunction, or a contraction spelled without its apostrophe ("CANT")
  empty_scenes      text-only scenes with nothing on them (no headline, number or chip): only the accent bar would render
  repeat_headlines  a headline already shown in one of the two scenes before
Across scripts: opening_overlap = how alike two different scripts' first 60 s look sequences are (position by position), max and mean over all pairs."""
from __future__ import annotations
import itertools, json, re, sys
from pathlib import Path
from typing import Dict, List

from . import beats as B, blueprint as BP, cadence as C, clip3d as C3, planner as P, states as ST, variety as V

ROOT = Path(__file__).resolve().parent.parent
TOPICS = ROOT / "test_fixtures" / "rep_theory_topics"; BASELINE = TOPICS / "baseline.json"
SHIPPED = ROOT / "assets" / "reptheory"
WPS = 2.6      # narration speed for the synthetic word timings (≈156 words a minute)
STILL_S, OPENING_S = 4.0, 60.0
IS_PICTURE = lambda l: l in PICTURE or l.startswith("pose:")
PICTURE = {"anatomy", "prop", "hold", "pose", "tier", "equation", "3d", "flow", "stat", "versus", "steps", "sketch", "illus", "clip3d", "timeline", "mistake", "slider", "dial", "study", "graph", "bars", "calendar", "result", "warning", "engage", "myth", "question", "checklist"}
TARGETS = {"bad_headlines": ("<=", 0), "empty_scenes": ("<=", 0), "repeat_headlines": ("<=", 0), "picture_share": (">=", 0.80), "fallback_share": ("<=", 0.10), "anatomy_unnamed": ("<=", 0), "still_share": ("<=", 0.05), "held_no_change": ("<=", 0), "opening_overlap_max": ("<=", 0.30)}
BODY_RX = re.compile(r"\b(" + "|".join([      # named body parts, organs and tissues; "muscle" / "body" alone name nothing
    r"neck", r"shoulders?", r"delts?", r"deltoids?", r"traps?", r"trapezius", r"chest", r"pecs?", r"pectorals?", r"arms?", r"biceps?", r"triceps?", r"elbows?", r"forearms?", r"wrists?", r"hands?",
    r"fingers?", r"thumbs?", r"grip", r"back", r"lats?", r"spine", r"shoulder blades?", r"core", r"abs", r"stomach", r"belly", r"waist", r"obliques?", r"hips?", r"hip flexors?", r"glutes?",
    r"legs?", r"thighs?", r"quads?", r"quadriceps", r"hamstrings?", r"knees?", r"calf", r"calves", r"shins?", r"ankles?", r"feet", r"foot", r"toes?", r"heart", r"lungs?", r"brain",
    r"kidneys?", r"liver", r"gut", r"tendons?", r"ligaments?", r"joints?", r"bones?", r"nervous system", r"head", r"jaw"]) + r")\b", re.I)
LABELS = B.LABEL_WORDS | B.STRUCTURAL | P.LABELS | {w for lab, _r, _a in B.FOCUS.values() for w in lab.split()}      # the planner's own labels ("BAR HANG", "NO GYM") are not cut from the script
TEXT_LOOKS = {"callout", "trainee", "stock"}
EVAL_STOP = set("a an the and or but so if of to in on at by for with from as is are was were be it its this that these those you your we our they them their what when while not no one each every more most than then just up down over under into onto again back away out off around through across about after before until without".split())
VERB_END = set("give gives get gets make makes take takes beat beats feel want wants need needs go goes keep keeps lose loses eat eats burn burns help helps grow grows say says will would can could should has have had do does like slightly really very".split())
LEAD_BAD = {"that", "and", "but", "so", "or", "then", "also", "plus"}
NUMBER_WORDS = set("one two three four five six seven eight nine ten eleven twelve fifteen twenty thirty forty fifty sixty hundred thousand half".split())
MODIFIER_END = set("lower upper front inner outer left right".split())
NO_APOSTROPHE = {"cant", "dont", "wont", "isnt", "arent", "doesnt", "didnt", "theyre", "youre", "thats", "whats", "shouldnt", "wouldnt", "couldnt", "hasnt", "havent"}
REFERENCE_ONLY = ("supernatural", "isometric", "26 studies", "oranchuk", "l-sit", "hollow body", "split squat")      # words of the studied reference video: never constants in reptheory/

def scripts() -> Dict[str, str]:
    return {p.stem: p.read_text() for p in sorted(TOPICS.glob("*.txt"))}

def sentences(text: str) -> tuple:
    """(title, [{text, start, end, words}]) with even word timings at WPS; the first line `Title: …` is the title, not narration."""
    lines = text.strip().splitlines(); title = lines[0].split(":", 1)[1].strip() if lines and lines[0].lower().startswith("title:") else ""
    body = " ".join(l.strip() for l in (lines[1:] if title else lines) if l.strip()); out, t = [], 0.0
    for s in re.split(r"(?<=[.!?])\s+", body):
        toks = s.split()
        if not toks: continue
        ws = [{"w": w, "t0": round(t + i / WPS, 3), "t1": round(t + (i + 0.85) / WPS, 3)} for i, w in enumerate(toks)]
        out.append({"text": s, "start": round(t, 3), "end": round(t + len(toks) / WPS, 3), "words": ws}); t += len(toks) / WPS + 0.25
    return title, out

def transcript_words(ss: List[dict]) -> List[dict]:
    """The app's CSV path: each row keeps the script's text, its words come from the voiceover transcript (lowercase, no apostrophes, no punctuation)."""
    out = []
    for s in ss:
        ws = [dict(w, w=re.sub(r"[^a-z0-9%-]", "", w["w"].lower())) for w in s["words"]]; out.append(dict(s, words=[w for w in ws if w["w"]]))
    return out

_norm = lambda t: re.sub(r"[^a-z0-9%]", "", t.lower())

def headline_fault(head: str, text: str) -> str:
    """Why an on-screen text is not a phrase of the script ("" when it is). One-word labels and numbers are structural and pass; anything longer must be a run of one clause of the script."""
    toks = head.split()
    if len(toks) < 2 or any(c.isdigit() for c in head) or {t.upper() for t in toks} <= LABELS: return ""
    if any(re.sub(r"[^a-z]", "", t.lower()) in NO_APOSTROPHE and "'" not in t for t in toks): return "contraction without its apostrophe"
    if any(_norm(t) in NUMBER_WORDS for t in toks): return ""      # "CHANGE NUMBER ONE", "FIVE HUNDRED CALORIES": counted things are labels
    h = [_norm(t) for t in toks]
    if any([_norm(t) for t in c.split() if _norm(t)] == h for c in re.split(r"[,.;:?!]+", text)): return ""      # a whole clause of the script is a phrase
    if h[0] in LEAD_BAD: return "starts on a conjunction"
    for clause in re.split(r"[,.;:?!]+", text):
        c = [_norm(t) for t in clause.split() if _norm(t)]
        for i in range(len(c) - len(h) + 1):
            if c[i:i + len(h)] == h:
                nxt = c[i + len(h)] if i + len(h) < len(c) else ""
                if nxt and (h[-1] in VERB_END or h[-1] in EVAL_STOP or h[-1] in MODIFIER_END): return "ends on a dangling word"      # running to the clause's end is not dangling ("AS LONG AS YOU CAN")
                return "cut out of a longer phrase" if nxt and nxt not in EVAL_STOP and nxt not in VERB_END and len(h) >= 3 else ""
    return "not one clause of the script"

def art_ok(a: str) -> bool: return bool(a) and (SHIPPED / f"{a}.png").exists()      # only the art that ships with the app, so the numbers are the same on every machine

def look_of(sc: dict) -> str:
    lk = sc.get("look") or sc["kind"]; lk = sc["kind"] if lk == "stock" else lk
    return f"pose:{sc['art']}" if lk == "pose" else lk      # 30 pose pictures (Step 5): a squat and a sleeping figure are different pictures

def plan(text: str) -> tuple:
    title, ss = sentences(text); res = B.plan(transcript_words(ss), title=title, art_ok=art_ok); scenes = res["scenes"]
    ST.apply(scenes, art_ok); V.direct(scenes, total_s=scenes[-1]["end"], three_d=True, flow=True); scenes = P.never_empty(scenes); ST.develop(scenes); BP.apply(scenes)      # the engine's order
    return title, ss, res, scenes

def measure(text: str) -> dict:
    title, ss, res, scenes = plan(text); script = " ".join(s["text"] for s in ss)
    total = scenes[-1]["end"]; beats = res["beats"]
    looks = [look_of(sc) for sc in scenes]; dur = [sc["end"] - sc["start"] for sc in scenes]
    pic = sum(d for d, l, sc in zip(dur, looks, scenes) if IS_PICTURE(l) or (l == "trainee" and (sc.get("glows") or sc.get("morph")))) / total      # the figure with a named part lit, or gaining / leaning out on the word, is a picture of the words
    unground = sum(1 for b in beats if b["status"] != "grounded") / max(1, len(beats))
    named = lambda sc, l: BODY_RX.search(sc.get("text", "")) or (l in ("3d", "clip3d") and C3.groups_for(sc.get("text", ""))[0])      # a 3D clip may also come from a named exercise's muscles (pull-up -> lats)
    anat = [sc["no"] for sc, l in zip(scenes, looks) if l in ("anatomy", "3d", "clip3d") and not named(sc, l)]
    ev = C.events(scenes); marks = sorted({round(e["t"], 3) for e in ev if e["type"] == "primary" or e["meaningful"] or e["what"] == "spoken word lights"} | {0.0, round(total, 3)})      # a takeaway card lighting its words as they are said is moving
    still = sum(b - a for a, b in zip(marks, marks[1:]) if b - a > STILL_S) / total
    held = [sc["no"] for sc in scenes if sc["end"] - sc["start"] > STILL_S and not any(e["meaningful"] and e["type"] == "secondary" and sc["start"] + 0.05 < e["t"] < sc["end"] for e in ev)]
    shown = [(sc["no"], t) for sc in scenes for pg in sc.get("pages", []) for t in [pg.get("headline", "")] + [c["text"] for c in pg.get("chips", [])] if t]
    bad = [f"{n}: {t} ({headline_fault(t, script)})" for n, t in shown if headline_fault(t, script)]
    empty = [sc["no"] for sc, l in zip(scenes, looks) if l in TEXT_LOOKS and sc["kind"] == "callout" and not any(pg.get("headline") or pg.get("value") or pg.get("chips") for pg in sc.get("pages", []))]
    heads = [[pg["headline"] for pg in sc.get("pages", []) if pg.get("headline")] for sc in scenes]
    rep = [sc["no"] for i, sc in enumerate(scenes) for h in heads[i] if any(h in heads[j] for j in range(max(0, i - 2), i))]
    return {"title": title, "duration_s": round(total, 1), "scenes": len(scenes), "picture_share": round(pic, 3), "fallback_share": round(unground, 3), "anatomy_unnamed": len(anat),
            "anatomy_unnamed_scenes": anat, "still_share": round(still, 3), "held_no_change": len(held), "looks": len(set(looks)), "bad_headlines": len(bad), "bad_headline_list": bad, "empty_scenes": len(empty), "repeat_headlines": len(rep), "look_counts": {l: looks.count(l) for l in sorted(set(looks))},
            "opening": [l for sc, l in zip(scenes, looks) if sc["start"] < OPENING_S]}

def overlap(a: List[str], b: List[str]) -> float:
    n = max(len(a), len(b)); return sum(x == y for x, y in zip(a, b)) / n if n else 0.0

def reference_strings() -> List[str]:
    hits = []
    for p in sorted((ROOT / "reptheory").glob("*")):
        if p.suffix not in (".py", ".txt") or p.name == "topic_eval.py": continue
        low = p.read_text().lower(); hits += [f"{p.name}: {w}" for w in REFERENCE_ONLY if w in low]
    return hits

def run() -> dict:
    per = {k: measure(t) for k, t in scripts().items()}
    pairs = [overlap(per[a]["opening"], per[b]["opening"]) for a, b in itertools.combinations(per, 2)]
    mean = lambda k: round(sum(m[k] for m in per.values()) / len(per), 3)
    agg = {"scripts": len(per), "picture_share_mean": mean("picture_share"), "picture_share_min": min(m["picture_share"] for m in per.values()), "fallback_share_mean": mean("fallback_share"),
           "fallback_share_max": max(m["fallback_share"] for m in per.values()), "anatomy_unnamed_total": sum(m["anatomy_unnamed"] for m in per.values()), "still_share_mean": mean("still_share"),
           "held_no_change_total": sum(m["held_no_change"] for m in per.values()), "looks_mean": mean("looks"), "bad_headlines_total": sum(m["bad_headlines"] for m in per.values()), "empty_scenes_total": sum(m["empty_scenes"] for m in per.values()),
           "repeat_headlines_total": sum(m["repeat_headlines"] for m in per.values()), "opening_overlap_max": round(max(pairs), 3) if pairs else 0.0,
           "opening_overlap_mean": round(sum(pairs) / len(pairs), 3) if pairs else 0.0, "reference_strings": reference_strings()}
    return {"per_script": per, "aggregate": agg}

def table(r: dict) -> str:
    rows = ["script                     dur  scn  picture  fallback  anat?  still  held  looks  badtxt  empty  rpt", "-" * 100]
    for k, m in r["per_script"].items():
        rows.append(f"{k[:26]:26} {m['duration_s']:5.0f} {m['scenes']:4d}  {m['picture_share']:6.0%}  {m['fallback_share']:7.0%}  {m['anatomy_unnamed']:5d}  {m['still_share']:5.0%}  {m['held_no_change']:4d}  {m['looks']:5d}  {m['bad_headlines']:6d}  {m['empty_scenes']:5d}  {m['repeat_headlines']:3d}")
    a = r["aggregate"]; rows.append("-" * 100)
    rows.append(f"mean picture {a['picture_share_mean']:.0%} (min {a['picture_share_min']:.0%}) | fallback mean {a['fallback_share_mean']:.0%} (max {a['fallback_share_max']:.0%}) | anatomy unnamed {a['anatomy_unnamed_total']}"
                f" | still {a['still_share_mean']:.0%} | held {a['held_no_change_total']} | opening overlap max {a['opening_overlap_max']:.0%} mean {a['opening_overlap_mean']:.0%} | reference strings {len(a['reference_strings'])}"
                f" | bad texts {a['bad_headlines_total']} | empty {a['empty_scenes_total']} | repeats {a['repeat_headlines_total']}")
    gaps = []
    for k, (op, v) in TARGETS.items():
        cur = {"picture_share": a["picture_share_min"], "fallback_share": a["fallback_share_max"], "anatomy_unnamed": a["anatomy_unnamed_total"], "still_share": a["still_share_mean"],
               "held_no_change": a["held_no_change_total"], "opening_overlap_max": a["opening_overlap_max"], "bad_headlines": a["bad_headlines_total"],
               "empty_scenes": a["empty_scenes_total"], "repeat_headlines": a["repeat_headlines_total"]}[k]
        ok = cur >= v if op == ">=" else cur <= v; gaps.append(f"{'ok ' if ok else 'GAP'} {k} {op} {v}: now {cur}")
    return "\n".join(rows + ["", "targets (section 0, Rule 6):"] + ["  " + g for g in gaps])

if __name__ == "__main__":
    r = run(); print(table(r))
    if "--write-baseline" in sys.argv: BASELINE.write_text(json.dumps(r["aggregate"], indent=1) + "\n"); print(f"baseline written: {BASELINE}")
    if "--json" in sys.argv: print(json.dumps(r, indent=1))
