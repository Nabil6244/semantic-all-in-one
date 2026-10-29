"""LLM scene-writer for Review films: one request asks the app's AI router (Gemini, then Groq) to write the scene for each sentence of the script, the way
the reference explainers show what each sentence says. The answer is JSON; every field is checked and clamped here, so a wrong or partial answer
never reaches the renderer, and any failure returns None so the caller falls back to the rule-based writer (`director.auto_direct`).

    llm_direct(parsed, phone, run, say=print) -> parsed with directive items inserted, or None
    router_run(settings, state_dir)           -> run(system, user) -> text, through ai_router (task "director")
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable, Dict, List, Optional

from .director import COLOURS

SYSTEM = """You are the scene director of a phone-news explainer video. The narration is given as numbered sentences. For each CLAIM write the picture that shows
what the sentence says, as the best YouTube phone explainers do: one sentence, one literal visual. Reply with JSON only: {"scenes":[{"line":N,"type":T,...}]}.
"line" is the 1-based sentence the scene starts on; the scene stays on screen over the next sentences until another scene starts. Use about one scene per
1-2 sentences, never the same scene twice in a row, and skip a sentence that adds no new fact (leave it covered by the scene before it).

Types (use exactly these fields):
- "phones": flat phone cut-outs on paper. {"title":str,"phones":[{"label":str,"color":"black|blue|light pink|white|purple|red|green|silver|#hex","cams":2-4,"text":"figure on the body, e.g. 60W","top":"small label above","badge":"e.g. +700mAh","side":{"text":"big figure beside the phone"} or {"from":n,"to":n,"suffix":"%"},"fill_from":0-1,"fill":0-1,"cutaway":bool,"cell_from":0-1,"cell":0-1,"cable":bool}]}  1-4 phones. fill = a battery capsule beside the phone; cutaway = the battery cell shown inside the body.
- "doc": a certification / database page with the matching row highlighted. {"chip":"BIS CERTIFICATION","title":str,"highlight":0-6}
- "tweet": a quote card for a named source. {"author":str,"handle":str,"text":the claim, as the narration says it,"highlight":phrase}
- "curve": a line chart. {"title":str,"x_label":str,"y_label":str,"points":[[x,y],...2-8 points],"marks":[{"x":n,"text":str}]}
- "footage": real footage from a stock library, for real-world moments (a hand holding a phone, a launch stage, a store, a crowd, a teardown, a screen being used). {"query":"3-7 concrete words, e.g. hand holding white smartphone back camera close up"}
- "bench": a review-lab set with phones on stands showing charts, and glass cards comparing 2-3 figures. {"heading":str,"items":[{"label":"iPhone 18 Pro","value":1.2,"unit":"ms"},...]}  Use it for benchmark, speed, latency, battery-life or any measured comparison between phones.
- "xray" | "fold" | "chip" | "macro" | "lineup": 3D renders. {"text":caption (2-3 words)}; macro also "move":"island|edge|screen|port"; chip also "label":str; lineup also "room":"loft|gallery|studio|terrace|desk".

Rules: use only numbers and names that are in the sentence; if a picture needs a number the sentence does not give (a curve), put "(illustrative)" in its title.
Certification, regulator, database or listing sentences -> "doc". A named tipster, leaker or account -> "tweet". Spec comparisons -> "phones" with the figures on the phones and a badge for the difference.
Colour lists -> "phones" in those colours in the order named. Mix the types: phones and doc and footage and 3D, not only one kind.
Balance: use every type the script gives a reason for, never the same type three times in a row, and no type for more than 40% of the scenes. A longer script (6+ scenes)
should have at least one 3D render, one bench set and one footage scene wherever a sentence fits them."""

KINDS_3D = ("xray", "fold", "chip", "macro", "lineup")
ROOMS = ("loft", "gallery", "studio", "terrace", "desk")
MOVES = ("island", "edge", "screen", "port", "buttons", "monolith")


def _num(v: Any, lo: float, hi: float, default: Optional[float] = None) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, x))


def _s(v: Any, n: int = 80) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def _colour(v: Any, default: str) -> str:
    t = _s(v, 20).lower()
    if re.fullmatch(r"#[0-9a-f]{6}", t):
        return t
    return COLOURS.get(t, default)


def _phone(p: Any, i: int) -> Optional[Dict[str, Any]]:
    if not isinstance(p, dict):
        return None
    out: Dict[str, Any] = {"label": _s(p.get("label"), 32), "color": _colour(p.get("color"), ["#5b5a86", "#2b2b2e", "#7a2f45", "#cfc9de"][i % 4]), "cams": int(_num(p.get("cams"), 2, 4, 3))}
    for k in ("text", "top", "badge"):
        if p.get(k) not in (None, "", False):
            out[k] = _s(p[k], 24)
    side = p.get("side")
    if isinstance(side, dict):
        if side.get("text"):
            out["side"] = {"text": _s(side["text"], 24), "size": 72}
        elif side.get("to") is not None:
            out["side"] = {"from": _num(side.get("from"), -1e6, 1e6, 0), "to": _num(side.get("to"), -1e6, 1e6, 0), "suffix": _s(side.get("suffix"), 4), "size": 90}
    for k in ("fill_from", "fill", "cell_from", "cell"):
        v = _num(p.get(k), 0, 1)
        if v is not None:
            out[k] = v
    if p.get("cutaway"):
        out["cutaway"] = True
        out.setdefault("cell", out.get("fill", 0.8))
    if p.get("cable"):
        out["cable"] = True
    return out


def to_item(sc: Dict[str, Any], line: str = "") -> Optional[Dict[str, Any]]:
    """One scene from the answer as a directive item the planner understands, or None when it is unusable."""
    t = _s(sc.get("type"), 12).lower()
    if t == "phones":
        ph = [x for x in (_phone(p, i) for i, p in enumerate((sc.get("phones") or [])[:4])) if x]
        return {"kind": "scene", "layer": {"title": _s(sc.get("title"), 40), "phones": ph}} if ph else None
    if t == "doc":
        chip = _s(sc.get("chip"), 28)
        word = chip.split()[0].lower() if chip else ""
        if line and word not in line.lower():            # a regulator name that is not in the sentence is the model's guess
            chip = "CERTIFICATION" if "certif" in line.lower() else "LISTING"
        return {"kind": "scene", "layer": {"type": "pt_doc", "title": _s(sc.get("title") or "Listing", 40), "chip": chip, "rows": 7, "highlight": int(_num(sc.get("highlight"), 0, 6, 3))}}
    if t == "tweet":
        if not _s(sc.get("text"), 400):
            return None
        author, handle = _s(sc.get("author") or "As reported", 30), _s(sc.get("handle"), 24)
        if line and handle and handle.lower() not in line.lower():     # never show an account name the narration did not give
            handle = ""
        if line and author.lower() not in line.lower():
            author = "As reported"
        return {"kind": "tweet", "author": author, "handle": handle, "text": _s(sc.get("text"), 220), "highlight": _s(sc.get("highlight"), 60)}
    if t == "curve":
        pts = [[float(a), float(b)] for a, b in (q for q in (sc.get("points") or []) if isinstance(q, (list, tuple)) and len(q) == 2 and all(isinstance(z, (int, float)) for z in q))][:8]
        if len(pts) < 2:
            return None
        marks = [{"x": float(m["x"]), "text": _s(m.get("text"), 30)} for m in (sc.get("marks") or []) if isinstance(m, dict) and isinstance(m.get("x"), (int, float))][:3]
        return {"kind": "curve", "title": _s(sc.get("title"), 50), "x_label": _s(sc.get("x_label"), 24), "y_label": _s(sc.get("y_label"), 24), "points": pts, "marks": marks}
    if t == "bench":
        its = [{"label": _s(x.get("label"), 24), "value": float(x["value"]), "unit": _s(x.get("unit"), 8)} for x in (sc.get("items") or [])[:3]
               if isinstance(x, dict) and isinstance(x.get("value"), (int, float))]
        return {"kind": "bench", "heading": _s(sc.get("heading"), 30), "items": its} if len(its) >= 2 else None
    if t == "footage":
        q = _s(sc.get("query"), 80)
        return {"kind": "footage", "query": q, "text": ""} if len(q.split()) >= 2 else None
    if t in KINDS_3D:
        it: Dict[str, Any] = {"kind": t, "text": _s(sc.get("text"), 30)}
        if t == "macro":
            it["move"] = sc.get("move") if sc.get("move") in MOVES else "island"
        if t == "chip":
            it["label"] = _s(sc.get("label") or "CHIP", 20).upper()
        if t == "lineup":
            it["room"] = sc.get("room") if sc.get("room") in ROOMS else None
            it["pose"] = None
        return it
    return None


def parse_reply(text: str, n_lines: int, lines: Optional[List[str]] = None) -> Optional[Dict[int, Dict[str, Any]]]:
    """{line number: item} from the model's answer; None when no JSON scene list could be read."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    scenes = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(scenes, list):
        return None
    out: Dict[int, Dict[str, Any]] = {}
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        n = sc.get("line")
        if not isinstance(n, int) or not 1 <= n <= n_lines or n in out:
            continue
        it = to_item(sc, lines[n - 1] if lines else "")
        if it:
            out[n] = it
    return out or None


def llm_direct(parsed: Dict[str, Any], phone: str, run: Callable[[str, str], str], say: Callable[[str], None] = print) -> Optional[Dict[str, Any]]:
    """`parsed` with the model's scenes inserted before the sentences they start on; None (so the caller uses the rules) when the call or answer fails."""
    lines = [it["text"] for c in parsed["chapters"] for it in c["items"] if it["kind"] == "line"]
    if not lines:
        return None
    user = f"Phone: {phone or 'the phone'}\nNarration:\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(lines))
    try:
        reply = run(SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 -- a down provider must never stop the film
        say(f"The AI scene-writer was not available ({type(exc).__name__}); using the built-in rules.")
        return None
    got = parse_reply(reply, len(lines), lines)
    if not got:
        say("The AI scene-writer's answer could not be read; using the built-in rules.")
        return None
    out = copy.deepcopy(parsed)
    n = 0
    for ch in out["chapters"]:
        items: List[Dict[str, Any]] = []
        for it in ch["items"]:
            if it["kind"] == "line":
                n += 1
                if n in got:
                    items.append(got[n])
            items.append(it)
        ch["items"] = items
    say(f"AI scene-writer: {len(got)} scenes for {len(lines)} sentences.")
    return out


def router_run(settings: Dict[str, Any], state_dir: Any = None) -> Callable[[str, str], str]:
    """A `run(system, user) -> text` that asks the app's AI router (task "director": Gemini first, Groq as the fallback)."""
    from ai_router import router_from_settings

    router = router_from_settings(settings, state_dir=state_dir)

    def run(system: str, user: str) -> str:
        def ok(t: str) -> bool:
            return parse_reply(t, 10_000) is not None

        return router.run_task("director", system, user, accept=ok, label="scene-writer")

    return run
