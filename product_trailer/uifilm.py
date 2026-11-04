"""UI product film (CSV `#pace,ui`): feature blocks of ~7 s that alternate between a light and a dark set. Each block types its title word by word, a phone dollies in
until its interface fills the frame, and the interface is a live, scripted demo (a cursor taps toggles) or exploded into 3D layers; blocks join with full-frame
dissolves (every other one a blur that turns the old phone into the new title). The film opens on a wall of floating lock-screen phones, may build an app icon on
construction lines, and ends on the usual reveal and disclaimer card.

Everything is generic: the interface content comes from the feature row (feature / kicker / value / sub, plus optional `look` tokens), never from a reference video.
Engine side: whatif-engine/lib/uikit.mjs (screen content), lib/product.mjs (demo move, layers3d, wall), page.js (dissolve), layers/pt_words.mjs, layers/pt_iconbuild.mjs.

`look` tokens for a feature (space separated; use _ for a space inside a value):
    ui:settings | ui:lock | ui:widgets | ui:home | ui:notif | ui:list     which interface to show (default: guessed from the words)
    rows:Wi-Fi|Bluetooth|Focus_mode                                         the list rows (default: the `sub` text split on , ; | and "and")
    block:light | block:dark                                                force the set for this block
    style:demo | style:exploded                                            how the interface is shown (default: guessed)
    icon:camera  (or icon:camera:#7a5cff)                                   follow the block with an icon-construction block
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

BLOCK_S = 7.0
WALL_S = 7.0
ICON_S = 5.0
REVEAL_S = 6.0
CARD_S = 3.0
DISSOLVE_S = 0.7
ACCENTS = ["#7a5cff", "#2f7bff", "#14b8a6", "#f0643c", "#e04a8a"]
CATS: List[Tuple[str, Tuple[str, ...]]] = [
    ("lock", ("lock screen", "lockscreen", "wallpaper", "always-on", "always on", "clock")),
    ("widgets", ("widget", "glance", "dashboard")),
    ("home", ("dock", "app ", "apps", "folder", "icon", "home screen", "launcher", "library")),
    ("notif", ("notification", "message", "messages", "chat", "call", "inbox", "mail")),
    ("settings", ("control", "setting", "toggle", "switch", "mode", "privacy", "battery", "focus", "wi-fi", "bluetooth", "network", "sound")),
]
DEFAULT_ROWS = {"settings": ["Wi-Fi", "Bluetooth", "Focus", "Battery", "Privacy"], "list": ["General", "Display", "Sounds", "Privacy"]}


def _tokens(look: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in re.split(r"\s+", (look or "").strip()):
        key, _, val = raw.partition(":")
        if key and val:
            out[key.lower()] = val
    return out


def _words(text: str) -> List[str]:
    parts = [p.strip() for p in re.split(r"[,;|/]|\band\b", text or "") if p.strip()]
    return [p[:22] for p in parts][:5]


def _category(f: Dict[str, Any], tok: Dict[str, str]) -> str:
    if tok.get("ui") in ("settings", "lock", "widgets", "home", "notif", "list"):
        return tok["ui"]
    text = " ".join(str(f.get(k, "")) for k in ("feature", "kicker", "value", "sub")).lower() + " "
    for cat, keys in CATS:
        if any(k in text for k in keys):
            return cat
    return "list"


def _short(v: Any, fallback: str, n: int = 8) -> str:
    """A widget's big number must stay big: a long value (a feature name) is replaced by the fallback."""
    v = str(v or "")
    return v if 0 < len(v) <= n else fallback


def feature_title(f: Dict[str, Any]) -> str:
    head = f.get("value") or (f.get("feature") or "").title()
    return " ".join(p for p in (f.get("kicker"), head) if p).strip() or "New"


def ui_for_feature(f: Dict[str, Any], *, accent: str, time: str = "9:41", date: str = "Tuesday, October 21", theme: str = "dark") -> Tuple[Dict[str, Any], str]:
    """-> (ui spec for whatif-engine/lib/uikit.mjs, category)."""
    tok = _tokens(f.get("look", ""))
    cat = _category(f, tok)
    title = feature_title(f)
    rows = [r.replace("_", " ") for r in tok["rows"].split("|") if r] if tok.get("rows") else _words(f.get("sub", ""))
    comps: List[Dict[str, Any]]
    if cat == "settings":
        rows = rows or DEFAULT_ROWS["settings"]
        comps = [{"type": "header", "text": (f.get("feature") or "settings").title(), "sub": f.get("value") or ""},
                 {"type": "list", "rows": [{"label": r, "toggle": i % 2 == 1} for i, r in enumerate(rows)]},
                 {"type": "slider", "label": (f.get("feature") or "level").title(), "value": 0.62}]
    elif cat == "lock":
        comps = [{"type": "clock", "time": time, "date": date},
                 {"type": "notif", "app": "Messages", "title": title, "body": f.get("sub") or "Now on your lock screen", "icon": "message"},
                 {"type": "widget", "title": (f.get("feature") or "today").title(), "big": _short(f.get("value"), time), "sub": f.get("sub") or "", "tint": accent}]
    elif cat == "widgets":
        comps = [{"type": "header", "text": title, "sub": f.get("sub") or ""},
                 {"type": "widget", "title": (f.get("feature") or "widget").title(), "big": f.get("value") or "64°", "sub": f.get("sub") or "", "tint": accent},
                 {"type": "widget", "title": "Today", "big": time, "sub": date, "tint": "#2f6bff" if accent != "#2f7bff" else "#7a5cff", "h": 130},
                 {"type": "slider", "label": "Brightness", "value": 0.7}]
    elif cat == "home":
        labels = rows or ["Phone", "Messages", "Camera", "Photos", "Music", "Mail", "Settings", "Maps"]
        icons = [{"label": s} for s in (labels + ["Notes", "Clock", "Wallet", "Store"])[:8]]
        comps = [{"type": "header", "text": title, "sub": ""}, {"type": "grid", "icons": icons},
                 {"type": "dock", "icons": [{"label": "Phone"}, {"label": "Mail"}, {"label": "Music"}, {"label": "Camera"}]}]
    elif cat == "notif":
        comps = [{"type": "header", "text": title, "sub": f.get("sub") or ""},
                 {"type": "notif", "app": "Messages", "title": (rows or ["Alex"])[0], "body": f.get("sub") or "New message", "icon": "message"},
                 {"type": "notif", "app": "Mail", "title": (rows + ["Team", "Team"])[1], "body": "Re: " + title, "icon": "mail"},
                 {"type": "list", "rows": [{"label": r, "value": ""} for r in (rows or ["Important", "Unread", "Recent"])[:4]]}]
    else:
        rows = rows or DEFAULT_ROWS["list"]
        comps = [{"type": "header", "text": title, "sub": f.get("sub") or ""},
                 {"type": "list", "rows": [{"label": r, "value": "On" if i % 2 == 0 else ""} for i, r in enumerate(rows)]},
                 {"type": "widget", "title": (f.get("feature") or "feature").title(), "big": _short(f.get("value"), "New"), "sub": f.get("sub") or "", "tint": accent}]
    return {"theme": theme, "accent": accent, "top": 160, "components": comps, "cursor": "touch", "script": []}, cat


def _script(ui: Dict[str, Any], dur: float) -> List[Dict[str, Any]]:
    """Cursor taps on the first list's rows (toggles first), spread through the middle of the shot; empty when the interface has no list."""
    for ci, c in enumerate(ui["components"]):
        if c["type"] == "list" and c["rows"]:
            order = [i for i, r in enumerate(c["rows"]) if "toggle" in r] + [i for i, r in enumerate(c["rows"]) if "toggle" not in r]
            at0 = max(1.6, dur * 0.36)
            return [{"at": round(at0 + n * 1.5, 2), "comp": ci, "row": r} for n, r in enumerate(order[:2]) if at0 + n * 1.5 < dur - 0.9]
    return []


def _blocks(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = [{"kind": "wall", "len": WALL_S}]
    for i, f in enumerate(list(data.get("features") or [])[:10]):
        plan.append({"kind": "feature", "f": f, "i": i, "len": BLOCK_S})
        ic = _tokens(f.get("look", "")).get("icon")
        if ic:
            plan.append({"kind": "icon", "f": f, "icon": ic, "len": ICON_S})
    plan.append({"kind": "reveal", "len": REVEAL_S})
    return plan


def film_length(data: Dict[str, Any]) -> float:
    """Seconds of a UI film without music: every block at its own length plus the disclaimer card."""
    card = CARD_S if [ln for ln in str((data.get("product") or {}).get("disclaimer", "")).split("|") if ln.strip()] else 0.0
    return round(sum(b["len"] for b in _blocks(data)) + card, 3)


def plan_ui(data: Dict[str, Any], beats, *, width: int = 1920, height: int = 1080, fps: int = 30, seed: int = 0, music_path: Optional[str] = None) -> Dict[str, Any]:
    """Music-timed (or the no-music 7 s grid): each block keeps its share of the length, edges snapped to beats."""
    from .planner import _snap

    prod = data.get("product", {})
    card_lines = [ln for ln in str(prod.get("disclaimer", "")).split("|") if ln.strip()]
    D = round(float(beats.duration), 3)
    bl = sorted(b for b in beats.beats if 0.5 < b < D - 0.5)
    plan = _blocks(data)
    body = sum(b["len"] for b in plan)
    card_len = CARD_S if card_lines else 0.0
    scale = (D - card_len) / body if D > 0 and body > 0 else 1.0     # the blocks share the music's length; on the no-music grid scale is 1
    edges, t = [0.0], 0.0
    for k, b in enumerate(plan):
        t += b["len"] * scale
        last = k == len(plan) - 1
        snapped = None if last or beats.source == "grid" or not bl else _snap(bl, t, edges[-1], 3.0, D - card_len - 3.0)
        edges.append(round(D - card_len, 3) if last else round(snapped if snapped is not None and snapped > edges[-1] + 2.5 else t, 3))
    for k, b in enumerate(plan):
        b["a"], b["e"] = edges[k], edges[k + 1]
    spec = build_film(data, plan, D, width=width, height=height, fps=fps, seed=seed)
    spec["product_trailer"].update({"tempo": round(beats.tempo, 2), "beat_source": beats.source, "beats": [round(x, 3) for x in beats.beats],
                                    "music": str(music_path) if music_path else None})
    return spec


# ---------- timed to a voice-over ----------
def _said_at(W: Sequence[Tuple[str, float, float]], text: str, a: float, b: float) -> List[float]:
    """Start time of each word of `text` in order inside [a, b] of the narration, or [] when they are not all said there in that order."""
    from .voiceover import tokens

    want, out, j = tokens(text), [], 0
    for w, t0, _t1 in W:
        if t0 < a - 0.05 or t0 > b:
            continue
        if j < len(want) and w == want[j]:
            out.append(t0)
            j += 1
    return out if want and j == len(want) else []


def _cue_taps(ui: Dict[str, Any], W: Sequence[Tuple[str, float, float]], a: float, b: float) -> List[Dict[str, Any]]:
    """A tap on every list row whose name the narrator says inside the block, at the moment it is said (relative to a); [] when none is said."""
    from .voiceover import tokens

    taps = []
    for ci, c in enumerate(ui.get("components", [])):
        if c.get("type") != "list":
            continue
        for ri, row in enumerate(c.get("rows", [])):
            first = (tokens(row.get("label", "")) or [""])[0]
            hit = next((t0 for w, t0, _ in W if a + 0.9 <= t0 <= b - 0.6 and w == first and len(first) > 2), None)
            if hit is not None:
                taps.append({"at": round(hit - a + 0.15, 2), "comp": ci, "row": ri})
    taps.sort(key=lambda x: x["at"])
    keep: List[Dict[str, Any]] = []
    for x in taps:                                 # the cursor needs ~1 s between taps
        if not keep or x["at"] - keep[-1]["at"] >= 1.0:
            keep.append(x)
    return keep[:3]


def _timed_sentences(words: Sequence[Any], gap: float = 0.45) -> List[Tuple[str, float, float]]:
    """The narrator's sentences with their times, straight from the word times: a sentence ends on . ! ? (as Whisper writes them) once it has 4 words,
    on a pause of `gap` once it has 6, or at 26 words."""
    out: List[Tuple[str, float, float]] = []
    cur: List[Tuple[str, float, float]] = []
    for w in words:
        text, a, b = (str(w.get("text") or w.get("word") or ""), float(w["start"]), float(w["end"])) if isinstance(w, dict) else (str(w[0]), float(w[1]), float(w[2]))
        if not text.strip():
            continue
        if cur and ((a - cur[-1][2] > gap and len(cur) >= 6) or len(cur) >= 26):
            out.append((" ".join(x[0] for x in cur), cur[0][1], cur[-1][2]))
            cur = []
        cur.append((text.strip(), a, b))
        if len(cur) >= 4 and text.strip()[-1:] in ".!?":
            out.append((" ".join(x[0] for x in cur), cur[0][1], cur[-1][2]))
            cur = []
    if cur:
        if out and len(cur) < 3:
            out[-1] = (out[-1][0] + " " + " ".join(x[0] for x in cur), out[-1][1], cur[-1][2])
        else:
            out.append((" ".join(x[0] for x in cur), cur[0][1], cur[-1][2]))
    return out


def plan_ui_timed(data: Dict[str, Any], words: Sequence[Any], voice_seconds: float, *, width: int = 1920, height: int = 1080, fps: int = 30,
                  seed: int = 0) -> Dict[str, Any]:
    """The UI film timed to the narrator: a feature's block starts when its feature is first said and runs until the next one is; joins sit in the
    pause between sentences; a title whose words are spoken types each word as it is said; a list row that is named is tapped when it is named.
    The opening wall runs under the narration before the first feature, the reveal under the last sentence. Unmentioned features take a share of a
    long block. No Gemini: plain word matching (review.feature_matches)."""
    from . import voiceover as vo
    from .review import feature_matches

    prod = data.get("product", {})
    feats = list(data.get("features") or [])[:10]
    card_lines = [ln for ln in str(prod.get("disclaimer", "")).split("|") if ln.strip()]
    W = vo._wtimes(words)
    D_voice = float(voice_seconds or 0.0) or (W[-1][2] if W else 0.0)
    timed = _timed_sentences(words)
    sents, spans = [x[0] for x in timed], [(x[1], x[2]) for x in timed]
    al = {"ok": bool(timed)}
    notes: List[str] = []
    # the first sentence (from the last match on) that names each feature
    hits: List[Tuple[int, Dict[str, Any]]] = []
    unmatched: List[Dict[str, Any]] = []
    j = 1 if len(sents) > 2 else 0                  # the first sentence belongs to the opening
    for f in feats:
        k = next((x for x in range(j, len(sents)) if feature_matches(f, sents[x]) or all(w in sents[x].lower() for w in feature_title(f).lower().split()[-2:])), None)
        if k is None or (hits and k == hits[-1][0]):
            unmatched.append(f)
            continue
        hits.append((k, f))
        j = k + 1
    last = len(sents) - 1
    reveal_k = last if sents and (not hits or hits[-1][0] < last) else None
    edge = lambda k: 0.0 if k <= 0 else round((spans[k - 1][1] + spans[k][0]) / 2 if spans[k][0] > spans[k - 1][1] else spans[k][0], 3)   # in the pause
    starts = [edge(k) for k, _ in hits]
    plan: List[Dict[str, Any]] = []
    wall_end = starts[0] if starts else (edge(reveal_k) if reveal_k else D_voice)
    if wall_end >= 2.0:
        plan.append({"kind": "wall", "a": 0.0, "e": wall_end})
    elif starts:
        starts[0] = 0.0
    rev_a = edge(reveal_k) if reveal_k is not None else D_voice
    if rev_a - (starts[-1] if starts else 0.0) < 3.0:        # too little room after the last feature: it keeps the stretch, no separate reveal
        rev_a = D_voice
    for n, (k, f) in enumerate(hits):
        a, e = starts[n], (starts[n + 1] if n + 1 < len(hits) else rev_a)
        sub = [(f, a, e)]
        while unmatched and e - a > 11.0:                  # a long block shares its time with a feature the narration never names
            mid = round(a + (e - a) / 2, 3)
            sub = [(f, a, mid), (unmatched.pop(0), mid, e)]
            break
        for ff, aa, ee in sub:
            ic = _tokens(ff.get("look", "")).get("icon")
            i = feats.index(ff)
            if ic and ee - aa >= 8.0:                      # room for the icon to be built after the interface
                cut = round(aa + (ee - aa) * 0.6, 3)
                plan.append({"kind": "feature", "f": ff, "i": i, "a": aa, "e": cut})
                plan.append({"kind": "icon", "f": ff, "icon": ic, "a": cut, "e": ee})
            else:
                plan.append({"kind": "feature", "f": ff, "i": i, "a": aa, "e": ee})
    if rev_a < D_voice - 0.5:
        plan.append({"kind": "reveal", "a": rev_a, "e": D_voice})
    elif plan:
        plan[-1]["e"] = D_voice
    if not plan:
        plan = [{"kind": "reveal", "a": 0.0, "e": max(4.0, D_voice)}]
    for f in unmatched:
        notes.append(f"'{feature_title(f)}' is never said in the voice-over: left out")
    for b in plan:                                         # what the narrator says inside each block drives its title and taps
        b["W"] = [w for w in W if b["a"] - 0.05 <= w[1] <= b["e"]]
    D = round(max(p["e"] for p in plan) + (CARD_S if card_lines else 0.0), 3)
    spec = build_film(data, plan, D, width=width, height=height, fps=fps, seed=seed, timed=True)
    spec["whatif"]["notes"] += notes
    spec["product_trailer"].update({"voiceover_timed": True, "voice_matched": bool(al.get("ok"))})
    return spec


def build_film(data: Dict[str, Any], plan: List[Dict[str, Any]], D: float, *, width: int = 1920, height: int = 1080, fps: int = 30, seed: int = 0,
               timed: bool = False) -> Dict[str, Any]:
    """Blocks with times ({"kind", "a", "e", ...}) -> the spec. Shared by the music / grid timing and the voice-over timing."""
    from .planner import LOOK, _tone

    rng = random.Random(seed)
    prod = data.get("product", {})
    feats = list(data.get("features") or [])[:10]
    phone = prod.get("phone") or prod.get("name", "phone").lower()
    cols = [c for c in prod.get("colors") or [] if c] or [str(prod.get("colour") or "titanium")]
    name = prod.get("name") or "New phone"
    time, date = prod.get("time", "9:41"), prod.get("date", "Tuesday, October 21")
    card_lines = [ln for ln in str(prod.get("disclaimer", "")).split("|") if ln.strip()]
    shots: List[Dict[str, Any]] = []
    layers: List[Dict[str, Any]] = []
    notes: List[str] = []
    n_block = 0

    def add_shot(start: float, end: float, theme: str, move: str, **extra) -> Dict[str, Any]:
        colour = cols[len(shots) % len(cols)]
        s = {"id": f"s{len(shots) + 1:02d}", "start": round(start, 3), "end": round(end, 3), "kind": "product", "object": "phone", "phone": phone, "color": colour, "tone": _tone(colour),
             "move": move, "backdrop": "daylight" if theme == "light" else "charcoal", "seed": rng.randrange(1, 10_000), "cam_side": "left" if len(shots) % 2 else "right", "exit": "cut"}
        if theme == "dark":
            s["glow"] = True
        s.update(extra)
        if shots:   # every block after the first joins the one before with a full-frame dissolve; every other join also defocuses
            s["dissolve_in"] = DISSOLVE_S
            s["dissolve_style"] = "blur" if len(shots) % 2 == 1 else "fade"
        shots.append(s)
        return s

    def title(text: str, b: Dict[str, Any], theme: str) -> None:
        start, end = b["a"], b["e"]
        L = {"type": "pt_words", "text": text, "start": round(start + 0.25, 3), "end": round(min(end - 0.3, start + 4.4), 3), "y": 0.12, "ink": "dark" if theme == "light" else "light"}
        said = _said_at(b.get("W") or [], text, start, end) if timed else []
        if said:                                           # the narrator says the title: each word types on as it is spoken
            L["start"] = round(min(said[0], start + 0.25), 3)
            L["times"] = [round(t - L["start"], 3) for t in said]
            L["end"] = round(min(end - 0.3, max(L["end"], said[-1] + 2.0)), 3)
        layers.append(L)

    for b in plan:
        a, e = b["a"], b["e"]
        dur = e - a
        theme = "dark" if b["kind"] == "reveal" else "light" if n_block % 2 == 0 else "dark"   # the reveal's white name needs a dark set
        if b["kind"] == "wall":
            ui = {"theme": "dark", "accent": ACCENTS[0], "components": [{"type": "clock", "time": time, "date": date}], "top": 150}
            add_shot(a, e, theme, "demo", screen={"wallpaper": "wave", "tint": _tone(cols[0]), "clock": False, "time": time, "date": date, "ui": ui},
                     wall={"cols": 4, "rows": 3, "out_at": round(dur * 0.5, 2), "speed": 0.34, "time": time, "date": date, "seed": rng.randrange(1, 999)},
                     cam={"z0": 6.1, "z1": 5.2, "y0": -0.2, "y1": 0.08, "ay0": 0.3, "ay1": 0.4, "cy0": 0.0, "cy1": 0.05})
            title(f"{prod.get('intro') or 'Meet'} {name}", b, theme)
        elif b["kind"] == "feature":
            f = b["f"]
            tok = _tokens(f.get("look", ""))
            theme = tok.get("block") if tok.get("block") in ("light", "dark") else theme
            accent = ACCENTS[b["i"] % len(ACCENTS)]
            ui, cat = ui_for_feature(f, accent=accent, time=time, date=date)
            style = tok.get("style") if tok.get("style") in ("demo", "exploded") else ("exploded" if cat in ("lock", "widgets", "home", "notif") else "demo")
            screen = {"wallpaper": "wave", "tint": accent, "clock": False, "time": time, "date": date, "ui": ui}
            if style == "exploded":
                s = add_shot(a, e, theme, "demo", screen=screen, layers3d={"explode": [1, 0], "start": 0.5, "dur": round(dur * 0.78, 2), "depth": 0.4, "fan": 0.42},
                             cam={"p0": 0.16, "p1": 0.03, "y0": -0.62, "y1": 0.05, "z0": 5.3, "z1": 3.0, "ay0": 0.22, "ay1": 0.4})
            else:
                ui["script"] = (_cue_taps(ui, b.get("W") or [], a, e) if timed else []) or _script(ui, dur)
                s = add_shot(a, e, theme, "demo", screen=screen, cam={"p0": 0.07, "p1": 0.02, "y0": -0.34, "y1": 0.1, "z0": 5.0, "z1": 2.4, "ay0": 0.3, "ay1": 0.62})
            title(feature_title(f), b, theme)
            s["ui_style"] = style
        elif b["kind"] == "icon":
            f = b["f"]
            ic, _, col = b["icon"].partition(":")
            shots.append({"id": f"s{len(shots) + 1:02d}", "start": round(a, 3), "end": round(e, 3), "kind": "plate", "tint": "paper" if theme == "light" else "ink", "exit": "cut",
                          "dissolve_in": DISSOLVE_S, "dissolve_style": "fade"})
            layers.append({"type": "pt_iconbuild", "icon": ic, "label": ic.replace("_", " ").title(), "color": col or ACCENTS[(n_block + 1) % len(ACCENTS)],
                           "start": round(a + 0.2, 3), "end": round(e - 0.2, 3), "ink": "dark" if theme == "light" else "light", "build": round(min(2.8, dur * 0.55), 2), "y": 0.56, "size": 0.34})
            title(feature_title(f), b, theme)
        else:   # reveal: the back turns to the front and the screen powers on, the name beside it
            add_shot(a, e, theme, "reveal", screen={"wallpaper": "wave", "tint": _tone(cols[0]), "time": time, "date": date, "power_on": round(dur * 0.45 + 0.4, 2)}, turn_at=0.45, frame_side="right")
            layers.append({"type": "pt_reveal", "kicker": prod.get("intro", "Introducing"), "name": name, "side": "left", "start": round(a + dur * 0.5, 3), "end": round(e - 0.1, 3)})
        n_block += 1

    end = plan[-1]["e"] if plan else 0.0
    if card_lines:
        shots.append({"id": f"s{len(shots) + 1:02d}", "start": round(end, 3), "end": D, "kind": "black", "exit": "cut", "dissolve_in": 0.6, "dissolve_style": "fade"})
        layers.append({"type": "pt_card", "lines": card_lines, "start": round(end + 0.2, 3), "end": D})
    if len(feats) == 0:
        notes.append("no features in the CSV: the film is the opening wall and the reveal only")
    return {"width": int(width), "height": int(height), "fps": int(fps), "duration": D, "look": dict(LOOK), "shots": shots, "layers": layers,
            "whatif": {"title": name, "notes": notes},
            "product_trailer": {"seed": seed, "pace": "ui", "product": prod}}
