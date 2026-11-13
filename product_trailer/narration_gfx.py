"""Graphics drawn from what the narration says (Review films), after the director has placed its scenes.

The director (AI or rules) mostly knows phone hardware: the lines of a software / news explainer then fall back to plain 3D phone shots.
This pass reads the sentences and gives the ones with a clear shape a graphic or a 3D prop of their own:

    "One: install Samsung Members ..."               -> pt_steps     step n of a how-to, tapped on a drawn phone screen
    "Here's your quick checklist. Update ... Back up" -> pt_list      a checklist that builds sentence by sentence
    "Betas can have bugs. Battery life can be worse." -> pt_list      the risks, with warning marks
    "limited to ...: Germany, India, Poland, ..."     -> pt_list      the names as chips
    "fixes 179 ...: 155 Android fixes, ..., 24 ..."   -> pt_breakdown a total split into its parts (a part of a part bracketed)
    "Known: ... Reported but unconfirmed: ... Unknown:" -> pt_ledger  three columns, the one being read lit
    a build on the servers / firmware                 -> 3D server rack with the build rising out of it
    a security update / patch / vulnerabilities       -> 3D shield catching the flaws
    months and dates of a timeline                    -> 3D desk calendar flipping to them
    apps and features by name                         -> 3D app icons, one per app named

Variety (the user's rule): a graphic may come back, but not often. Each kind has a cap per film, the same kind never opens two runs in a row,
3D props rotate their camera move and never reuse a move back to back. A run (a checklist read over five sentences) is one use: it is one
canvas that keeps building, not five graphics.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Sequence

CAP = {"steps": 1, "check": 1, "risk": 1, "chips": 2, "breakdown": 2, "ledger": 1, "server": 2, "shield": 1, "calendar": 2, "apps": 2}
GAP = 2                                    # the same kind is not used again within this many runs
PROP_MOVES = ("prop_turn", "prop_low", "prop_top", "prop_push")
APP_ICON = (("calendar", "calendar", "#e5484d"), ("health", "heart", "#22b573"), ("memory", "memory", "#7a5cff"), ("note", "note", "#f5a524"),
            ("setting", "gear", "#6b7686"), ("cloud", "cloud", "#3a8dff"), ("member", "people", "#1f6fff"), ("galaxy store", "people", "#c43cff"))
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
       "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "twentieth": 20, "thirtieth": 30}
STEP_WORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
TITLE_RUN = re.compile(r"(?:[A-Z][A-Za-z0-9]*|\d+(?:\.\d+)?)(?:\s+(?:for\s+|and\s+|of\s+)?(?:[A-Z][A-Za-z0-9]*|\d+(?:\.\d+)?))+")


def _clip(text: str, n: int = 7) -> str:
    w = re.sub(r"\s+", " ", text.strip(" .,:;!?")).split(" ")
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def _first_clause(text: str) -> str:
    return re.split(r",\s+(?:and\s+)?|\s+and\s+(?=sign|tap|then)|\s+or\s+|;|\.\s", text.strip(), maxsplit=1)[0]


def _title_runs(text: str) -> List[str]:
    out = []
    for m in TITLE_RUN.finditer(text):
        r = m.group(0).strip()
        if r.split(" ")[0] in ("One", "Two", "Three", "Four", "Five", "Six") and len(r.split(" ")) > 1 and not re.match(r"One UI", r):
            r = r.split(" ", 1)[1]
        if len(r) > 2:
            out.append(r)
    return out


def os_name(lines: Sequence[str]) -> str:
    """The software the film is about: the most named "One UI 9.5" / "Android 17" / "iOS 27" / "HyperOS 3" in the narration."""
    counts: Dict[str, int] = {}
    for t in lines:
        for m in re.finditer(r"\b(One UI|Android|iOS|iPadOS|HyperOS|OxygenOS|ColorOS|Pixel Feature Drop|macOS|watchOS|Wear OS)\s+(\d+(?:\.\d+)?)", t):
            k = f"{m.group(1)} {m.group(2)}"
            counts[k] = counts.get(k, 0) + 1
    return max(counts, key=counts.get) if counts else ""


# ---------------------------------------------------------------------------------------------------------------------------------- detectors
VERB = r"(install|tap|select|choose|go|open|download|sign|enable|turn|press|update|back|check|find|scroll|join|register)"
UI_NOUN = r"(?:\s+(banner|card|button|tab|menu|option|page|toggle|section|app))?"


def step_of(text: str) -> Optional[Dict[str, Any]]:
    m = re.match(r"\s*(?:step\s+)?(one|two|three|four|five|six|seven|eight|\d)[:.)]\s+(.+)", text, re.I)
    if not m:
        return None
    n = STEP_WORD.get(m.group(1).lower()) or int(m.group(1))
    body = m.group(2).strip().rstrip(".")
    v = re.search(r"\b" + VERB + r"\b", body, re.I)
    act = body[v.start():] if v else body
    path = [re.sub(r"^(?:and\s+)?(?:tap|select|choose|press|open|go to)\s+", "", x.strip(), flags=re.I) for x in act.split(",")]
    path = [x for x in path if x[:1].isupper()]
    if re.match(r"go\b", act, re.I) and path:              # "go to Settings, Software update, and tap Download and install": a path through the menus
        app, target = (path[-2] if len(path) > 1 else path[0]), path[-1]
        text_ = "Go to " + " > ".join(path[:-1] or path) + (f", tap {path[-1]}" if len(path) > 1 else "")
    else:
        rm = None
        for r in TITLE_RUN.finditer(act):
            rm = r
            break
        target = (rm.group(0) + (" " + re.match(UI_NOUN, act[rm.end():]).group(1) if re.match(UI_NOUN, act[rm.end():]) and re.match(UI_NOUN, act[rm.end():]).group(1) else "")) if rm else _clip(act, 4)
        fm = re.search(r"\bfrom (?:the\s+)?(" + TITLE_RUN.pattern + r")", act)
        app = fm.group(1) if fm else ""
        text_ = _first_clause(act)
    return {"n": n, "text": _clip(text_[:1].upper() + text_[1:], 8), "target": _clip(target, 6), "app": app}


def list_items(text: str) -> Optional[Dict[str, Any]]:
    """"... limited to certain countries: Germany, India, Poland, South Korea, the UK and the US." -> chips."""
    m = re.search(r"([A-Za-z ]{3,60}):\s*(.+)$", text.strip().rstrip("."))
    if not m:
        return None
    parts = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(2)) if p.strip()]
    parts = [re.sub(r"^(?:the|a|an)\s+", "", p, flags=re.I) for p in parts]
    if len(parts) < 4 or any(len(p.split()) > 3 for p in parts) or not all(p[:1].isupper() for p in parts):
        return None
    head = re.sub(r"^(?:to|of|in|for|from|on|at|is|are|the)\s+", "", " ".join(m.group(1).split()[-3:]), flags=re.I)
    return {"title": head, "items": parts[:10]}


NUM = r"(\d{1,3}(?:,\d{3})+|\d+)"


def breakdown_of(text: str) -> Optional[Dict[str, Any]]:
    nums = [(int(m.group(1).replace(",", "")), m.start(), m.end()) for m in re.finditer(NUM + r"(?![\d.])", text)]
    nums = [n for n in nums if not (1900 <= n[0] <= 2100)]                 # years are not counts
    if len(nums) < 3:
        return None
    tot = max(nums, key=lambda n: n[0])
    rest = [n for n in nums if n is not tot and n[1] > tot[1]]

    def label(n):
        seg = re.split(r"[,:;.]|\bincluding\b|\band\b", text[n[2]:n[2] + 60])[0]
        return _clip(seg, 4)

    for i in range(len(rest)):
        for j in range(i + 1, len(rest)):
            a, b = rest[i], rest[j]
            if a[0] + b[0] == tot[0]:
                parts = [{"value": a[0], "label": label(a)}, {"value": b[0], "label": label(b)}]
                inner = None
                for c in rest:
                    if c not in (a, b) and re.search(r"including\s+$", text[max(0, c[1] - 12):c[1]]):
                        host = 0 if a[1] < c[1] and (b[1] > c[1]) else 1
                        if c[0] < parts[host]["value"]:
                            inner = {"of": host, "value": c[0], "label": label(c)}
                return {"total": tot[0], "label": label(tot), "parts": parts, "inner": inner}
    return None


LEDGER = (("known", "green", "Known"), ("confirmed", "green", "Confirmed"), ("reported", "amber", "Reported"), ("rumou?red", "amber", "Rumored"),
          ("unknown", "red", "Unknown"), ("unconfirmed", "amber", "Unconfirmed"))


def ledger_col(text: str) -> Optional[Dict[str, Any]]:
    m = re.match(r"\s*((?:[A-Za-z]+\s+){0,3}[A-Za-z]+):\s+(.+)$", text.strip().rstrip("."))
    if not m:
        return None
    head = m.group(1).lower()
    for key, tone, name in LEDGER:
        if re.match(key, head.split()[0]):
            items = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+(?=a |an |the |whether )", m.group(2)) if p.strip()]
            return {"title": name, "tone": tone, "items": [_clip(re.sub(r"^(?:a|an|the)\s+", "", p, flags=re.I), 6).capitalize() for p in items][:5]}
    return None


RISK = re.compile(r"\b(can|could|may|might)\s+(?:be\s+|have\s+|mean\s+|misbehave|break|fail|drain|lose)|\bbugs?\b|\bwors[et]\b|\bwip(?:e|ing)\b|\bunsafe\b|\brisk", re.I)


def is_risk(text: str) -> bool:
    return bool(RISK.search(text)) and len(text.split()) <= 16


def is_short_order(text: str) -> bool:
    w = text.strip().split()
    if re.match(r"(let me|so|here|now|that|this|which|in short|to recap)\b", text.strip(), re.I):
        return False
    return 1 < len(w) <= 12 and w[0][:1].isupper() and not text.strip().endswith("?")


def _no_and(t: str) -> str:
    t = re.sub(r"^(?:and|but|so|also)\s+", "", t.strip(), flags=re.I)
    return t[:1].upper() + t[1:]


def dates_of(text: str) -> List[Dict[str, str]]:
    out = []
    for m in re.finditer(r"\b(early|late|mid|the second half of|the first half of)?\s*(" + "|".join(x.title() for x in MONTHS) + r")\b(?:\s+(\d{1,2}|" + "|".join(ORD) + r")\b)?", text, re.I):
        if not m.group(2)[:1].isupper():
            continue                                   # "may" the verb is not May
        mo = m.group(2).title()[:3]
        d = (m.group(3) or "").lower()
        if m.group(1):
            m1 = m.group(1).lower()
        else:
            m1 = ""
        day = str(ORD.get(d, d)) if d else {"early": "Early", "late": "Late", "mid": "Mid", "the second half of": "2nd half", "the first half of": "1st half"}.get(m1, "")
        if not any(o["month"] == mo and o["day"] == day for o in out):
            out.append({"month": mo, "day": day})
    return out


def apps_in(text: str) -> List[Dict[str, str]]:
    out = []
    for m in re.finditer(r"((?:[A-Z][A-Za-z]+\s+){0,2}[A-Z][A-Za-z]+)\s+(app|feature|design)\b", text):
        name = m.group(1)
        if name.split()[0] in ("A", "The", "New", "Redesigned", "Refreshed"):
            name = " ".join(name.split()[1:]) or name
        low = name.lower()
        icon, col = next(((i, c) for k, i, c in APP_ICON if k in low), ("gear", "#3a7bff"))
        if not any(a["name"] == name for a in out):
            out.append({"name": name, "icon": icon, "color": col})
    return out


# ---------------------------------------------------------------------------------------------------------------------------------- the pass
def plan(lines: Sequence[str]) -> Dict[int, Dict[str, Any]]:
    """{line index: directive} for the sentences that get a graphic of their own (see the module text)."""
    osn = os_name(lines)
    got: Dict[int, Dict[str, Any]] = {}
    used: Dict[str, int] = {}
    recent: List[str] = []                 # the kinds of the last runs, newest last
    move_i = [0]

    def may(kind: str) -> bool:
        return used.get(kind, 0) < CAP[kind] and kind not in recent[-GAP:]

    def open_run(kind: str) -> None:
        used[kind] = used.get(kind, 0) + 1
        recent.append(kind)

    def prop(obj: str, **kw) -> Dict[str, Any]:
        mv = PROP_MOVES[move_i[0] % len(PROP_MOVES)]
        move_i[0] += 1
        return {"kind": "prop", "object": obj, "move": mv, "_own": True, "_stay": True, **kw}

    def gfx(layer: Dict[str, Any]) -> Dict[str, Any]:
        return {"kind": "gfx", "layer": layer, "_own": True, "_stay": True}

    n = len(lines)
    i = 0
    while i < n:
        t = lines[i]
        low = t.lower()
        # how-to steps: a run of "One: ... Two: ..."
        st = step_of(t)
        if st and may("steps"):
            run = []
            j = i
            while j < n and step_of(lines[j]):
                run.append((j, step_of(lines[j])))
                j += 1
            if len(run) >= 2:
                open_run("steps")
                head = next((lines[k] for k in range(max(0, i - 2), i) if re.search(r"\bhow to\b|sign up|set up|install", lines[k], re.I)), "")
                title = "How to sign up" if re.search(r"sign up|register", head, re.I) else "How to"
                app = ""
                for j2, s in run:
                    if s["n"] == 1 and s["app"]:
                        app = s["target"]                       # step one installs the app the next steps happen in
                        shown = s["app"]
                    else:
                        shown = s["app"] or app or "Settings"
                    got[j2] = gfx({"type": "pt_steps", "title": title, "n": s["n"], "total": len(run), "text": s["text"], "target": s["target"], "app": shown})
                i = j
                continue
        # a checklist: the line names it, the short orders after it are its items
        if re.search(r"\bcheck\s?list\b", low) and may("check"):
            j, items = i + 1, []
            while j < n and is_short_order(lines[j]) and len(items) < 7:
                items.append(_clip(_no_and(lines[j]), 6))
                j += 1
            if len(items) >= 3:
                open_run("check")
                for k, j2 in enumerate(range(i + 1, j)):
                    got[j2] = gfx({"type": "pt_list", "mode": "check", "title": "Checklist",
                                   "items": [{"text": x, **({"done": True} if q < k else {})} for q, x in enumerate(items[:k + 1])]})
                i = j
                continue
        # known / reported / unknown
        lc = ledger_col(t)
        if lc and may("ledger"):
            run, j = [], i
            while j < n and ledger_col(lines[j]):
                run.append((j, ledger_col(lines[j])))
                j += 1
            if len(run) >= 2:
                open_run("ledger")
                cols = [c for _, c in run]
                for k, (j2, _) in enumerate(run):
                    got[j2] = gfx({"type": "pt_ledger", "active": k,
                                   "cols": [{**c, "done": q < k, "items": [{"text": x["text"] if isinstance(x, dict) else x, **({"done": True} if q < k else {})} for x in c["items"]]}
                                            for q, c in enumerate(cols)]})
                i = j
                continue
        # risks: two or more warning sentences in a row
        if is_risk(t) and i + 1 < n and is_risk(lines[i + 1]) and may("risk"):
            j, items = i, []
            while j < n and is_risk(lines[j]) and len(items) < 6:
                items.append(_clip(_no_and(re.split(r",\s+so\b", lines[j])[0]), 6))
                j += 1
            open_run("risk")
            for k, j2 in enumerate(range(i, j)):
                got[j2] = gfx({"type": "pt_list", "mode": "risk", "title": "The risks",
                               "items": [{"text": x, **({"done": True} if q < k else {})} for q, x in enumerate(items[:k + 1])]})
            i = j
            continue
        # names after a colon
        li = list_items(t)
        if li and may("chips"):
            open_run("chips")
            got[i] = gfx({"type": "pt_list", "mode": "chips", "title": li["title"], "items": [{"text": x} for x in li["items"]]})
            i += 1
            continue
        bd = breakdown_of(t)
        if bd and may("breakdown"):
            open_run("breakdown")
            subj = re.sub(r"^(?:that|this|the|a|an)\s+", "", _clip(re.split(r"\s(?:fixes|has|have|is|are|includes?|contains?)\b|:", t)[0], 4), flags=re.I)
            got[i] = gfx({"type": "pt_breakdown", "title": subj, **bd})
            i += 1
            continue
        # 3D props
        if re.search(r"\bservers?\b|\bfirmware\b|\bbuild (?:number|has|just|for)\b|\bbeta build\b|\bnewer build\b", low) and may("server"):
            open_run("server")
            got[i] = prop("server", label=osn or "New build", sublabel=("Newer build" if re.search(r"\bnewer\b|\bsecond\b", low) else "Beta build"))
            i += 1
            continue
        if re.search(r"\bsecurity\b|\bpatch\b|\bvulnerabilit", low) and may("shield"):
            m = re.search(NUM + r"\s+vulnerabilit", t)
            open_run("shield")
            got[i] = prop("shield", label=(f"{m.group(1)} fixes" if m else "Security update"), sublabel=_clip(next((r for r in _title_runs(t) if re.search(r"\d", r)), ""), 4))
            i += 1
            continue
        ds = dates_of(t)
        if len(ds) >= 1 and re.search(r"\b(opened|launch|beta|expect|expected|estimate|showed up|start|debut|target|released?|rumou?red for|arriv\w*|come around|announce\w*)\b", low) and may("calendar"):
            open_run("calendar")
            pages, j = [], i
            while j < n and j - i < 3:                    # a timeline told over several sentences is one calendar that keeps flipping
                d2 = dates_of(lines[j])
                if j > i and not d2:
                    break
                for d in d2:
                    if d in pages:
                        pages.remove(d)
                    pages.append(d)
                got[j] = prop("calendar", pages=pages[-4:])
                j += 1
            i = j
            continue
        ap = apps_in(t)
        if ap and may("apps"):
            run, j, apps = [], i, []
            while j < n and apps_in(lines[j]) and j - i < 3:
                for a in apps_in(lines[j]):
                    if not any(b["name"] == a["name"] for b in apps):
                        apps.append(a)
                run.append((j, list(apps)))
                j += 1
            open_run("apps")
            for j2, aps in run:
                got[j2] = prop("apps", apps=aps[:6])
            i = j
            continue
        i += 1
    return got


def apply(parsed: Dict[str, Any], log=print) -> Dict[str, Any]:
    """`parsed` with the narration graphics put before their sentences; a scene the director put on the same sentence (not the author's) gives way."""
    out = copy.deepcopy(parsed)
    lines = [it["text"] for c in out["chapters"] for it in c["items"] if it["kind"] == "line"]
    got = plan(lines)
    if not got:
        return out
    n = -1
    for ch in out["chapters"]:
        items: List[Dict[str, Any]] = []
        for it in ch["items"]:
            if it["kind"] == "line":
                n += 1
                if n in got:
                    while items and items[-1]["kind"] != "line" and not items[-1].get("_own"):
                        items.pop()                 # the director's pick for this sentence: the narration graphic is more specific
                    items.append(got[n])
            items.append(it)
        ch["items"] = items
    kinds: Dict[str, int] = {}
    for d in got.values():
        k = d.get("object") or d["layer"]["type"]
        kinds[k] = kinds.get(k, 0) + 1
    log("Narration graphics: " + ", ".join(f"{k} x{v}" for k, v in kinds.items()) + f" on {len(got)} of {len(lines)} sentences.")
    return out
