"""Editorial director: turns the planner's scenes into an edit decision list (shots, transitions, caption phrases, audio cues).

Deterministic, rule-based and explicit (no model call here; the scene grouping and footage choice already come from the app's visual director).
For each scene it decides narrative role, tone and intensity, the key phrase, and then the treatment: layout, camera move, grade, shot splits,
overlays and the transition into the next shot. Treatments rotate (no two neighbours get the same camera move; transitions are rationed), and every
decision is recorded in `why` so the report can show it. Text it puts on screen is the narration's own words."""
from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple

from . import media, typo
from .transitions import Transition

FPS = media.FPS
DATA = {"counter", "bar", "timeline", "statement", "stat", "evidence", "chapter"}
KIND_MAP = {"counter_card": "counter", "bar_card": "bar", "timeline_card": "timeline", "text_card": "statement", "stat_card": "stat", "evidence_card": "evidence",
            "chapter_card": "chapter", "footage": "footage", "anatomy_3d": "anatomy"}
STORY_RE = re.compile(r"\b(he|she|his|her|him|frank|picture this|a man|a woman|named)\b", re.I)
TENSE_RE = re.compile(r"\b(dark|never|closed|major|ischemic|stroke|dismiss\w*|ignore\w*|suddenly|gone|lost)\b", re.I)
HOPE_RE = re.compile(r"\b(preventable|prevent|recover\w*|safe|early|window)\b", re.I)
REVEAL_RE = re.compile(r"\b(goes dark|went dark|suddenly|not eye strain|what happened)\b", re.I)
BASE_INTENSITY = {"hook": 0.7, "statistic": 0.6, "explanation": 0.4, "personal_story": 0.35, "reveal": 0.85, "consequence": 0.8, "conclusion": 0.6, "transition": 0.3}
LEVEL_DB = {"hook": -1.0, "statistic": 0.0, "explanation": -2.0, "personal_story": -4.0, "reveal": 1.0, "consequence": -1.0, "conclusion": -2.0, "transition": -2.0}

SKIP = {"sometimes", "most", "people", "either", "just", "about", "major", "maybe", "probably"}

def f(t: float) -> float: return round(t * FPS) / FPS

def analyze(sc, idx: int, n: int) -> dict:
    text = sc.text; kind = KIND_MAP.get(sc.kind, "statement")
    if idx == 0: role = "hook"
    elif kind in ("counter", "bar", "stat", "evidence"): role = "statistic"
    elif REVEAL_RE.search(text) and (kind in ("anatomy", "statement") or idx == n - 1): role = "reveal"
    elif idx == n - 1: role = "conclusion"
    elif kind == "timeline": role = "consequence"
    elif kind == "anatomy": role = "explanation"
    elif STORY_RE.search(text): role = "personal_story"
    else: role = "transition"
    if kind == "footage" and role == "personal_story" and re.search(r"\b(never fully recovers|major|stroke|closed)\b", text, re.I): role = "consequence"
    inten = min(1.0, BASE_INTENSITY[role] + 0.08 * len(TENSE_RE.findall(text)))
    tone = "tense" if (TENSE_RE.search(text) and inten >= 0.6) else "hopeful" if HOPE_RE.search(text) and role in ("hook", "statistic", "transition") else "warm" if role == "personal_story" else "clinical" if role == "explanation" else "neutral"
    words = text.split(); em = typo.emphasis_indices(words, 1); key = re.sub(r"[^\w%' -]", "", words[min(em)]) if em else ""
    return {"scene_no": sc.scene_no, "role": role, "tone": tone, "intensity": round(inten, 2), "key_phrase": key, "kind": kind}

def look_for(a: dict) -> str:
    return {"tense": "tense", "warm": "warm_memory", "clinical": "cool_clinical", "hopeful": "hopeful"}.get(a["tone"], "neutral")

class _Rot:
    """Rotating camera choice that never repeats the previous move and alternates pan direction."""
    def __init__(self): self.last = None; self.pan = 1
    def pick(self, role: str, inten: float, dur: float) -> dict:
        seq = {"personal_story": ["drift", "push_in", "pan_right"], "consequence": ["push_in", "tilt_down"], "reveal": ["push_in"], "conclusion": ["pull_back"],
               "explanation": ["pan_left", "pull_back", "tilt_up"], "hook": ["push_in", "pull_back"], "statistic": ["push_in", "drift"], "transition": ["pull_back", "pan_right", "push_in"]}[role]
        move = next((m for m in seq if m != self.last), seq[0]) if self.last in seq else seq[0]
        if move.startswith("pan"):
            move = "pan_right" if self.pan > 0 else "pan_left"; self.pan = -self.pan
            if move == self.last: move = "push_in"
        self.last = move; amount = round(0.08 + 0.10 * inten + (0.02 if dur > 6 else 0), 3)
        return {"move": move, "amount": amount, "focus": [0.5, 0.5]}

def _profile_rows(sc) -> Optional[dict]:
    """A named person plus a comma list of short facts in the narration ('A man named Frank. He's 67 years old, retired teacher, in reasonable health.') -> a profile panel."""
    m = re.search(r"\b(?:man|woman|person|patient)\s+named\s+([A-Z][a-z]+)", sc.text)
    if not m: return None
    for s in sc.sentences:
        parts = [p.strip(" .") for p in s["text"].split(",")]
        if len(parts) >= 3 and all(len(p.split()) <= 5 for p in parts):
            rows = []; ph = typo.build_phrases([s])
            for p, c in zip(parts, ph + [None] * len(parts)):
                p = re.sub(r"^(he|she|they)('s| is| was)\s+", "", p, flags=re.I); rows.append(p[:1].upper() + p[1:])
            return {"name": m.group(1), "rows": rows, "sentence": s}
    return None

def build(scenes, accent, silences=(), src_duration=None) -> dict:
    n = len(scenes); ana = [analyze(sc, i, n) for i, sc in enumerate(scenes)]; shots: List[dict] = []; rot = _Rot(); why_all: List[str] = []
    allsent = [s for sc in scenes for s in sc.sentences] or [{"text": sc.text, "start": sc.start, "end": sc.end} for sc in scenes]
    phrases = typo.build_phrases(allsent, silences); last_title_end = -99.0; last_layout = "full"; seed = 0
    footage_scenes = [(i, sc) for i, sc in enumerate(scenes) if sc.kind == "footage" and sc.visual.get("path")]
    def plate_for(i):
        for j in (i + 1, i - 1, i + 2, i - 2):
            if 0 <= j < n and scenes[j].kind == "footage" and scenes[j].visual.get("path"): return scenes[j].visual["path"]
        return None
    for i, (sc, a) in enumerate(zip(scenes, ana)):
        seed += 1; kind = a["kind"]; t0, t1 = f(sc.start), f(sc.end); dur = t1 - t0; look = look_for(a); why = [f"{a['role']}/{a['tone']} intensity {a['intensity']}"]
        base = {"scene_no": sc.scene_no, "role": a["role"], "intensity": a["intensity"], "accent": list(accent), "seed": seed, "why": why}
        if kind == "footage":
            src = sc.visual["path"]; sd = (src_duration or (lambda p: media.probe(p)["duration"]))(src) or 10.0
            prof = _profile_rows(sc); cuts = [t0, t1]
            if prof:      # the split-screen profile still needs its own shot, but the footage under both shots is ONE continuous run of the clip
                cut = f(prof["sentence"]["start"])
                if t0 + 1.8 <= cut <= t1 - 1.8: cuts = [t0, cut, t1]; why.append(f"profile split at {cut:.2f}s (same clip, no jump)")
            # a stock clip plays straight through for the whole scene: no cut inside it, no skipped seconds, no restart. A clip shorter than the scene is slowed
            # (up to 2.5x) to cover it instead of looping or repeating an earlier part.
            need = (t1 - t0) + 1.2; start = max(0.0, min(1.0, sd - need)); speed = 1.0
            if sd - start < need: start = 0.0 if sd < need else start; speed = min(2.5, need / max(1.0, sd)); why.append(f"the clip ({sd:.1f}s) is shorter than the scene: played {speed:.2f}x slower, not looped")
            seg_in = [round(start + (cuts[k] - t0) / speed, 3) for k in range(len(cuts) - 1)]
            for k in range(len(cuts) - 1):
                s0, s1 = cuts[k], cuts[k + 1]; d = s1 - s0; cam = rot.pick(a["role"], a["intensity"], d); sh = dict(base, kind="footage", t0=s0, t1=s1, src=src, src_in=seg_in[k], speed=speed, look=look, camera=cam, layout="full", overlays=[], dust=True, why=list(why))
                if k == 1: cam["base"] = 1.3; cam["focus"] = [0.56, 0.46]; sh["why"].append("closer framing than the first shot (wide -> medium)")
                sh["overlays"].append({"type": "tag", "text": "Illustrative stock footage", "t0": 0.4, "t1": min(3.6, d - 0.2), "quiet": True})
                if prof and k == len(cuts) - 2:
                    sh["layout"] = "split"; rows = []; ph = [p for p in phrases if abs(p.t0 - prof["sentence"]["start"]) < 0.01 or prof["sentence"]["start"] - 0.01 <= p.t0 < prof["sentence"]["end"]]
                    for ri, txt in enumerate(prof["rows"]):
                        pt = ph[ri].t0 - s0 if ri < len(ph) else 1.2 + 0.6 * ri; rows.append({"text": txt, "t0": round(max(1.3, pt), 3)})
                    sh["profile"] = {"kicker": "A composite example", "title": prof["name"], "rows": rows, "note": "Illustrative footage. Not a patient record.", "title_t0": 0.45}
                    sh["overlays"] = [o for o in sh["overlays"] if o["type"] != "tag"]; sh["why"].append("split screen: footage beside a profile built from the narration's own facts")
                elif a["role"] == "personal_story" and d >= 3.5 and last_layout == "full" and k == 0 and not prof and a["key_phrase"]:
                    sh["layout"] = "framed"; sh["why"].append("footage framed over a blurred plate (parallax between layers) with the key phrase beside it")
                    sh["overlays"].append({"type": "title", "text": a["key_phrase"].capitalize(), "t0": 0.5, "t_out": d - 0.4, "px": 96, "max_w": 0.30, "y": 0.4, "emph": [0]})
                elif a["key_phrase"] and a["role"] in ("statistic", "hook", "transition", "consequence") and d >= 3.0 and s0 - last_title_end > 8:
                    sh["overlays"].append({"type": "title", "text": a["key_phrase"].capitalize(), "t0": 0.7, "t_out": min(d - 0.5, 3.4), "px": 150, "max_w": 0.6, "y": 0.34, "emph": [0]}); last_title_end = s0 + min(d - 0.5, 3.4)
                    sh["why"].append("key word set large over the picture, then cleared")
                last_layout = sh["layout"]; shots.append(sh)
        elif kind == "anatomy":
            sh = dict(base, kind="anatomy", t0=t0, t1=t1, template=sc.visual.get("template"), variant=sc.visual.get("variant", 0), body_rows=sc.visual.get("body_rows"), scene_start=sc.start, illustrative=sc.illustrative or "3D illustration. Not clinical imagery.", overlays=[], why=list(why) + ["3D journey kept as one continuous camera move; chips mark the key phrases"])
            used = 0; last_c = -9.0
            for p in phrases:
                if not (t0 + 1.0 < p.t0 < t1 - 2.5) or used >= 2: continue
                words = [w for w, _, _ in p.words]
                if not p.emph or p.t0 - last_c < 3.5: continue
                i0 = max(typo.emphasis_indices(words, 1) or {min(p.emph)}); prev = re.sub(r"\W", "", words[i0 - 1]).lower() if i0 > 0 else ""
                lo = i0 - 1 if prev and prev not in typo.STOP and prev not in SKIP and not prev.endswith("ly") else i0; hi = lo + 2 if lo == i0 and any(ch.isdigit() for ch in words[i0]) else i0 + 1
                if hi == lo + 1 and hi < len(words) and re.sub(r"\W", "", words[hi]).lower() in typo.EMPH_WORDS: hi += 1
                txt = re.sub(r"[^\w%' -]", "", " ".join(words[lo:hi])).strip(); txt = txt[:1].upper() + txt[1:]
                if len(txt.split()) < 2 and len(txt) < 6: continue
                at = max(p.words[lo][1] - 0.15, p.t0) - t0; sh["overlays"].append({"type": "chip", "text": txt, "t0": round(at, 3), "t1": round(at + 2.6, 3), "pos": "tl"}); used += 1; last_c = p.t0
            shots.append(sh)
        else:
            sh = dict(base, kind=kind, t0=t0, t1=t1, overlays=[], why=list(why)); v = sc.visual; pl = plate_for(i)
            if pl and kind in ("bar", "counter", "statement"):
                sh["plate"] = pl; sh["plate_t"] = 2.0; sh["why"].append("blurred plate from neighbouring footage for colour continuity")
            src_line = _source_line(sc)
            if kind == "counter":
                ctx = re.sub(r"^\s*every\s+\d+\s+\w+,?\s*", "", v.get("context", ""), flags=re.I).strip(); ctx = ctx[:1].upper() + ctx[1:] if ctx else ""
                sh["gfx"] = {"interval": v["interval"], "unit": v["unit"], "context": ctx, "event": v.get("event", "events"), "source_line": src_line}
            elif kind == "bar": sh["gfx"] = {"value": v["value"], "qualifier": v.get("qualifier", ""), "context": v.get("context", ""), "source_line": src_line}
            elif kind == "timeline":
                ev = []; last = -1.0
                for e in v.get("events", []):
                    tt = max(e["t0"], 0.05, last + 0.38); ev.append(dict(e, t0=round(tt, 3))); last = tt
                sh["gfx"] = {"events": ev, "source_line": v.get("source_line") or src_line, "kicker": v.get("kicker") or "What happened, in order"}; sh["why"].append("events revealed progressively; planner times spaced at least 0.38 s apart")
            elif kind == "statement": sh["gfx"] = {"beats": v.get("beats") or [{"text": sc.text, "t0": 0.0}]}
            elif kind == "stat": sh["gfx"] = {"number": v.get("number", ""), "unit": v.get("unit") or ("%" if "%" in sc.text else ""), "context": v.get("context") or sc.text, "source_line": v.get("source_line") or src_line, "kicker": v.get("kicker") or "The figure"}
            elif kind == "evidence": sh["gfx"] = {"claim": v.get("claim", sc.text), "heading": v.get("heading", "What the evidence says"), "level": sc.evidence_level, "source_line": src_line}
            else: sh["gfx"] = {"title": v.get("title") or sc.chapter or sc.text[:80], "kicker": v.get("kicker") or "Chapter"}
            if sc.illustrative: sh["illustrative"] = sc.illustrative
            shots.append(sh)
    shots[0]["t0"] = 0.0
    trans = _transitions(shots, accent)
    cues = _cues(shots, trans)
    return {"shots": shots, "transitions": trans, "phrases": phrases, "cues": cues, "analysis": ana}

def _source_line(sc) -> str:
    if not sc.sources: return ""
    s = sc.sources[0]; return " · ".join(b for b in [s.get("title") or s.get("citation") or "", str(s.get("year") or ""), s.get("population") or s.get("context") or ""] if b)

def _transitions(shots: List[dict], accent) -> List[Transition]:
    out: List[Transition] = []; recent: List[str] = []
    for a, b in zip(shots, shots[1:]):
        ka, kb = a["kind"], b["kind"]; same = a["scene_no"] == b["scene_no"]; dmin = min(a["t1"] - a["t0"], b["t1"] - b["t0"]); why = ""
        if same: name, fr, d, why = "cut", 0, "l2r", "motivated cut inside a scene, at a sentence boundary, with a reframe"
        elif ka in DATA and kb == "footage" and b["role"] == "consequence": name, fr, d, why = "cut", 0, "l2r", "hard cut from graphic to the consequence beat"
        elif ka in DATA and kb == "footage": name, fr, d, why = ("bar_wipe", 18, "l2r", "graphic bridge: an accent bar carries the graphic into the footage") if "bar_wipe" not in recent[-2:] else ("dissolve", 18, "l2r", "soft join from graphic into footage")
        elif ka in DATA and kb in DATA: name, fr, d, why = ("bar_wipe", 16, "l2r", "graphic bridge between two graphics") if "bar_wipe" not in recent[-2:] else ("dissolve", 16, "l2r", "soft join between graphics")
        elif ka == "footage" and kb == "anatomy": name, fr, d, why = ("iris", 22, "l2r", "iris opens into the eye scene (motivated by the narration)") if b.get("template") == "eye_journey" else ("zoom_through", 22, "l2r", "camera carries the viewer into the anatomy")
        elif ka == "anatomy" and kb == "footage": name, fr, d, why = "drift_dissolve", 20, "l2r", "camera keeps drifting through the join back to the story"
        elif kb == "statement": name, fr, d, why = "dissolve", 20, "l2r", "soft join into the statement"
        elif kb in DATA: name, fr, d, why = ("bar_wipe", 18, "l2r", "graphic bridge into the data scene") if "bar_wipe" not in recent[-2:] else ("dissolve", 18, "l2r", "soft join into the data scene")
        elif ka == "footage" and kb == "footage" and b["intensity"] >= 0.8 and b["role"] == "consequence": name, fr, d, why = "cut", 0, "l2r", "hard cut for the consequence beat"
        elif kb == "footage" and ka == "footage": name, fr, d, why = "dissolve", 20, "l2r", "slow dissolve marks a change of moment"
        else: name, fr, d, why = "dissolve", 20, "l2r", "default soft join"
        if b["role"] == "conclusion" and name == "dissolve": fr, why = 26, "slow dissolve into the closing statement"
        fr = min(fr, int(dmin * FPS * 0.45) // 2 * 2, 24)
        if fr < 6 and name != "cut": name, fr = "cut", 0
        if name == "zoom_through" and a.get("camera"): pass
        pt = (0.5, 0.5)
        out.append(Transition(name, fr, d, pt, tuple(accent), why)); recent.append(name)
    return out

def _cues(shots, trans) -> List[dict]:
    """Audio accents tied to picture events: a soft whoosh under a few bridging transitions, one low impact for a hard consequence cut. Rationed on purpose."""
    cues: List[dict] = []; last = -99.0
    for k, tr in enumerate(trans):
        cut = shots[k + 1]["t0"]; kind = None
        if tr.name in ("bar_wipe", "zoom_through", "iris"): kind, t = "whoosh", cut - tr.frames / FPS / 2
        elif tr.name == "cut" and shots[k + 1]["intensity"] >= 0.8 and shots[k]["scene_no"] != shots[k + 1]["scene_no"]: kind, t = "impact", cut
        if kind and cut - last >= 7.0 and len(cues) < 6: cues.append({"kind": kind, "t": round(t, 3), "db": -20.0 if kind == "whoosh" else -17.0, "why": tr.why}); last = cut
    return cues
