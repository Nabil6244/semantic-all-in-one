"""Story director (docs/aviation/MASTER_PLAN.md section 3): a stretch of `story` lines -> ONE evolving sticker stage.

    build(scenes, cls, rows, i, j) -> (shot, log)      shot = {"layer": "stage.lay_stage", start, end, scene, full_frame, params, cues}

Per line, in this order (first rule that fits adds the line's element; the year badge ticks on every dated line):
  CSV graphic      hook / split / ownership / argument / timeline / map / routes / fleet / portrait / paper / stat
  split, merge     split_tree from the catalog's parent / successors           (a full card: the stage clears first)
  stake / shares   ownership from the CSV `owners` or the line's "% stake" phrases
  CSV split        who-got-what board
  two countries    flags arguing in speech bubbles, the aircraft tugged between them
  renamed / names  logo cards on the timeline (catalog previous_names), once per airline
  independence ... political map of the countries named
  routes / network route-map card from the airline's hub to the airports named
  money            cash pile (sticker skin) or icon stat
  fleet count      fleet card
  aircraft/airline that airline's aircraft sticker in its livery (era type when none is named)
  person (CSV)     portrait + quote
  countries        hand-held flag stickers
Stickers stay and glide aside; at most MAX_STICKERS sit in the row (the oldest slides out). A full card clears the stage and the next
sticker clears the card. A kind whose module is not built simply is not used (the next rule takes the line). Nothing is invented:
every name, number and word is the narration's, the CSV's or the catalog's.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import catalog as C
from . import stage as G

MAX_STICKERS = 3
PHOTO_GAP_S = 15.0            # at most one web photo card per this many seconds of a stage
CUT_EVERY_S = 7.0             # the stage never runs longer than this without cutting to a full-screen picture
CUT_MIN_EVERY_S = 4.5         # the tightest cadence the balance pass may use
CUT_S = 4.5                   # how long the full-screen picture holds
BALANCE = 0.35                # a story chapter is at least this share full-screen pictures (when the film has pictures for it)
NO_CUT = ("split tree", "ownership", "who got what", "argument", "timeline", "political map", "route map", "hook",
          "paper sticker")     # never cut away while these animate / carry the words
BACKDROP_S = 14.0             # a new real photo behind the stage at most this often (a chapter's subject changes)
FULL = ("split_tree", "ownership", "split_board", "political_map", "route_map", "timeline", "argument")
_SPLIT = re.compile(r"\bsplit\w*|\bbroke up\b|\bbreak[- ]?up\b|\bseparat\w*|\bdissolv\w*|\bdivided\b|\bmerg\w*|\bjoined forces\b", re.I)
_STAKE = re.compile(r"\bstake\b|\bshares?\b|\bowned\b|\bowners?\w*|\bequity\b", re.I)
_ARGUE = re.compile(r"\bwant\w*|\bdemand\w*|\bargu\w*|\bdisagree\w*|\binsist\w*|\brefus\w*|\bclash\w*|\bdispute\w*", re.I)
_RENAME = re.compile(r"\brenam\w*|\brebrand\w*|\bnew name\b|\bfounded\b|\bformed\b|\bestablished\b", re.I)
# not 'became' / 'called': 'Changi became a hub', 'Singapore became independent' are not an airline's names over time
_STAKE_IN = re.compile(r"(?P<owner>[A-Z][\w\-]*(?:\s+[A-Z][\w\-]*)*)\s+(?:received|got|took|bought|acquired|holds?|held|kept|owns?|"
                       r"owned)\s+(?:a|an|its)?\s*(?P<pct>\d+(?:\.\d+)?)\s*(?:%|percent|per cent)\s+(?:stake|share)\s+in\s+"
                       r"(?:the\s+)?(?:merged\s+|new\s+|combined\s+)?(?P<target>[A-Z][\w\-]*(?:\s+[A-Z][\w\-]*)*)")
_POLITY = re.compile(r"\bindependen\w*|\bcolon\w*|\bfederation\b|\bborders?\b|\bexpelled\b|\bunion\b|\bnation\b|\bempire\b", re.I)
_ROUTES = re.compile(r"\broutes?\b|\bnetwork\b|\bdestinations?\b|\bflew to\b|\bflights? to\b", re.I)
_MERGE = re.compile(r"\bmerg\w*|\bjoined forces\b|\bcombined\b", re.I)
_COUNTRIES = {"malaysia": "MY", "malaya": "MY", "singapore": "SG", "britain": "GB", "united kingdom": "GB", "england": "GB",
              "france": "FR", "netherlands": "NL", "germany": "DE", "united states": "US", "america": "US", "india": "IN",
              "australia": "AU", "japan": "JP", "china": "CN", "hong kong": "HK", "thailand": "TH", "indonesia": "ID",
              "qatar": "QA", "emirates": "AE", "dubai": "AE", "turkey": "TR", "italy": "IT", "spain": "ES", "ireland": "IE",
              "switzerland": "CH", "canada": "CA", "brazil": "BR", "south korea": "KR", "philippines": "PH", "vietnam": "VN",
              "pakistan": "PK", "sri lanka": "LK", "new zealand": "NZ", "saudi arabia": "SA", "russia": "RU", "portugal": "PT"}


def countries_in(text: str) -> List[str]:
    """ISO codes of the countries a line names, in order of mention (story_relations.country_code when it is built)."""
    chars = list(text)
    spans = list(C.find_airlines(text))                           # 'Malaysia-Singapore Airlines' is not a country
    for m in C.find_airports(text):                               # 'flew to Hong Kong' is a destination, 'Singapore wanted' a country
        if re.search(r"(?:\bto|\bfrom|\bvia|\binto|\band|,)\s*$", text[:m.start], re.I):
            spans.append(m)
    for m in spans:
        for x in range(max(0, m.start), min(len(chars), m.end)):
            chars[x] = " "
    low = "".join(chars).lower()
    hits = []
    for name, code in _COUNTRIES.items():
        m = re.search(r"\b" + re.escape(name) + r"(?:n|ns|'s)?\b", low)
        if m and not re.match(r"\s+(?:airlines?|airways|air)\b", low[m.end():]):   # 'Singapore Airlines' is an airline, not a country
            hits.append((m.start(), code))
    seen: List[str] = []
    for _, code in sorted(hits):
        if code not in seen:
            seen.append(code)
    return seen


def era_type(year: int) -> str:
    """An airliner of the line's era when the line names an airline but no type (a sticker, never a claim about the fleet)."""
    if not year:
        return "a350"
    return "dc3" if year < 1958 else "b707" if year < 1972 else "b747" if year < 1995 else "b777" if year < 2010 else "a350"


def has(kind: str) -> bool:
    if kind not in G._FACTORIES:
        G.load_kinds()
    return kind in G._FACTORIES


def _mod(name: str):
    try:
        import importlib
        return importlib.import_module(f"{__package__}.{name}")
    except ImportError:
        return None


def _row(rows, k):
    return dict(rows[k]) if rows and k < len(rows) and rows[k] else {}


class _Director:
    def __init__(self, t0: float):
        self.st = G.Stage()
        self.t0 = t0
        self.full: Optional[str] = None           # the full card on screen, if any
        self.row: List[Tuple[str, str]] = []      # (element id, identity) of live row stickers, oldest first
        self.shown: set = set()
        self.year = 0
        self.last_photo = -1e9
        self.caption_id: Optional[str] = None
        self.bd_id: Optional[str] = None
        self.bd_at = -1e9
        self.bd_subject = ""
        self.web: Optional[Dict[str, Optional[Dict[str, Any]]]] = None
        self.bible: Any = None
        self.k = 0

    def type_for(self, c: Any, airline: str) -> Tuple[str, str]:
        """(aircraft id, why) for this line's sticker: the type the line names; else the type the script names for this airline
        in the same era (the bible's fleet, from any line); else an airliner of the era (era_type, the last fallback)."""
        if c.aircraft:
            return c.aircraft[0]["id"], "named in the line"
        b = self.bible
        if b is not None and airline:
            rec = b.lines[self.k] if 0 <= self.k < len(b.lines) else {}
            from . import bible as BB
            era = BB.era_of(self.year) if self.year else rec.get("era")
            e = (b.fleet.get(airline) or {}).get(era) or {}
            if e.get("types") and not e.get("assumed"):
                return e["types"][0], "named in the script"
        return era_type(self.year), "era guess"

    def picture(self, key: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """args for a web picture: the request on the first pass, the resolved picture after, None when it failed."""
        if self.web is None:
            return args
        got = self.web.get(key)
        return dict(args, **got) if got else None

    def _clear(self, at: float) -> None:
        if self.full or self.row:
            self.st.clear(at, exit="slide_left")
        self.full, self.row = None, []

    def card(self, at: float, kind: str, args: Dict[str, Any], anim: float = 2.4, enter: str = "rise") -> str:
        self._clear(at)
        el = self.st.add(kind, at + 0.25, args, pos=(640, 380), enter=enter, anim=anim, float_=False, edge=False)
        self.full = el
        return el

    def sticker(self, at: float, kind: str, args: Dict[str, Any], ident: str, **kw) -> Optional[str]:
        if ident in [i for _, i in self.row]:
            return None                            # already on stage: it stays, nothing new pops
        if self.full:
            self._clear(at)
        if len(self.row) >= MAX_STICKERS:
            old, _ = self.row.pop(0)
            self.st.remove(old, at, exit="slide_left")
        el = self.st.add(kind, at, args, **kw)
        self.row.append((el, ident))
        return el


def _web_q(r: dict) -> List[str]:
    """Web photo searches for a line: the CSV's `search` column, else its YouTube searches (never a Flow prompt)."""
    if r.get("web_queries"):
        return list(r["web_queries"])
    return list(r.get("queries") or []) if str(r.get("asset_type") or "").lower() == "youtube_video" else []


def web_key(kind: str, value: str) -> str:
    return f"{kind}:{value.strip()}"


def build(scenes: Sequence[Dict[str, Any]], cls: Sequence[Any], rows: Optional[Sequence[dict]], i: int, j: int,
          web: Optional[Dict[str, Optional[Dict[str, Any]]]] = None, bible: Any = None
          ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """web: storyweb.resolve's results {web_key: args to use | None}. None = first pass (pictures are requested); with results,
    only pictures that passed are placed and a request that failed leaves the line to the next rule."""
    t0, t1 = float(scenes[i]["start"]), float(scenes[j]["end"])
    d = _Director(t0)
    beats: List[Dict[str, Any]] = []
    d.web = web
    d.bible = bible
    log: List[Dict[str, Any]] = []
    rel, maps, cards2, skin = _mod("story_relations"), _mod("story_maps"), _mod("story_cards2"), _mod("gfx_sticker")
    for k in range(i, j + 1):
        s, c, r = scenes[k], cls[k], _row(rows, k)
        a = float(s["start"]) - t0
        text = c.text
        g = str(r.get("graphic") or "").strip().lower()
        years = c.values.get("years") or []
        if years:
            d.year = int(years[0])
            d.st.year(a, d.year)
        airline = r.get("airline") or (c.airlines[0]["id"] if c.airlines else "")
        al = C.get_airline(airline) or {}
        d.k = k
        _backdrop(d, a, c, r, airline, text)
        why = _line(d, a, c, r, g, airline, al, text, rel, maps, cards2, skin)
        _caption(d, a, text, why)
        beats.append({"a": a, "b": float(s["end"]) - t0, "why": why or "", "c": c, "airline": airline, "year": d.year,
                      "bd": d.bd_id})
        log.append({"scene": s.get("scene_no", k + 1), "stage": why or "keeps the stage"})
    _cutaways(d, beats)
    params = d.st.params()
    if not params["elements"] and not params["years"]:          # a stretch that named nothing still never goes blank
        d.st.add("text", 0.2, {"text": _short(cls[i].text), "size": 54}, enter="fade")
        params = d.st.params()
    shot = {"layer": "stage.lay_stage", "start": t0, "end": t1, "scene": scenes[i].get("scene_no", i + 1), "full_frame": True,
            "params": params, "cues": [(t0 + t, n) for t, n in d.st.cues()]}
    return shot, log


NO_CAPTION = ("argument", "hook", "timeline")


def _cut_sources(d: "_Director", bt: Dict[str, Any], els: Dict[str, Any], used: set) -> List[Dict[str, Any]]:
    """Every full-screen picture this beat could cut to: its chapter's backdrop photo (undimmed), library real photos of its
    airline, and the Flow era picture of its airline x era. Each {image, credit, ai, kind}."""
    from . import bible as BB
    from . import sticker_flow as SF
    out = []
    bd = els.get(bt["bd"]) if bt["bd"] else None
    if bd and (bd.get("args") or {}).get("image"):
        out.append({"image": bd["args"]["image"], "credit": bd["args"].get("credit", ""), "ai": False, "kind": "photo"})
    lb = _library_backdrop(bt["airline"], bt["c"], bt["year"])
    if lb:
        out.append({"image": lb["path"], "credit": lb.get("credit", ""), "ai": False, "kind": "photo"})
    era = BB.era_of(bt["year"]) if bt["year"] else "modern"
    pl = SF.plate(bt["airline"], era) if bt["airline"] else None
    if pl:
        out.append({"image": pl, "credit": "", "ai": True, "kind": "plate"})
    return [x for x in out if x["image"]]


def _cutaways(d: "_Director", beats: List[Dict[str, Any]], every: float = CUT_EVERY_S) -> None:
    """Full-screen pictures cut into the stage so a chapter is balanced, not one long sticker block: whenever `every` seconds
    passed without one, the next beat cuts to a full-screen picture for CUT_S, then back. Choice: a Flow era picture not used yet
    first (every era picture made for the chapter is shown), then alternating real photo / Flow picture, never the same picture
    twice. A full card (timeline, map, split ...) is never interrupted while it animates: a long enough line gets its cutaway in
    its second half instead. Then the chapter's share of full-screen pictures is measured; under BALANCE it runs again tighter."""
    els = {e["id"]: e for e in d.st._els}
    placed: List[str] = []
    last_cut, last_kind, last_img, used = -1e9, "", "", set()
    for bt in beats:
        a, b = bt["a"], bt["b"]
        full_card = any(bt["why"].startswith(x) for x in NO_CUT)
        start = a + (max(2.4, (b - a) * 0.5) if full_card else 0.15)
        if start - last_cut < every or b - start < 2.2 or bt["why"].startswith(("argument", "hook", "paper sticker")):
            continue
        cands = [x for x in _cut_sources(d, bt, els, used) if x["image"] != last_img]
        if not cands:
            continue
        unused_plate = [x for x in cands if x["kind"] == "plate" and x["image"] not in used]
        other = [x for x in cands if x["kind"] != last_kind]
        pick = (unused_plate or other or cands)[0]
        al = C.get_airline(bt["airline"]) or {}
        title = ((al.get("name") or "") + (f", {bt['year']}" if bt["year"] else "")).strip(", ")
        end = min(b, start + CUT_S)
        el = d.st.add("photo_full", start, {"image": pick["image"], "credit": pick["credit"], "title": title, "ai": pick["ai"]},
                      pos=(640, 360), enter="fade", float_=False, edge=False, z=880, anim=end - start)
        d.st.remove(el, end, exit="fade")
        placed.append(el)
        last_cut, last_kind, last_img = start, pick["kind"], pick["image"]
        used.add(pick["image"])
    if beats and every > CUT_MIN_EVERY_S:
        span = max(1e-6, beats[-1]["b"] - beats[0]["a"])
        shown = sum(min(CUT_S, (e.get("t1") or 0) - e["t0"]) for e in d.st._els if e["id"] in placed)
        if shown / span < BALANCE:
            d.st._els = [e for e in d.st._els if e["id"] not in placed]
            _cutaways(d, beats, every=max(CUT_MIN_EVERY_S, every - 2.0))


def _backdrop(d: "_Director", a: float, c: Any, r: dict, airline: str, text: str) -> None:
    """A real photo of what the chapter is about behind the stage: at the stretch's start and whenever the line names a new
    airline / aircraft (at most every BACKDROP_S). Found on the web at Generate (storyweb); none passes -> the plain stage."""
    al = C.get_airline(airline) or {}
    subject = (al.get("name") or "") + (" " + c.aircraft[0]["name"] if c.aircraft else "")
    subject = subject.strip()
    if not subject or subject == d.bd_subject or (a - d.bd_at < BACKDROP_S and d.bd_id):
        return
    q = [f"{subject} {d.year}".strip() if d.year else subject, f"{al.get('name') or subject} aircraft"]
    key = web_key("backdrop", subject + (f" {d.year}" if d.year else ""))
    pa = d.picture(key, {"capture": {"queries": _web_q(r) or q, "text": text, "key": key}, "credit": ""})
    if not pa and d.web is not None and (not d.year or d.year >= 2000):
        lb = _library_backdrop(airline, c, d.year)   # modern line, nothing new on the web: a photo of the airline in the library
        pa = {"image": lb["path"], "credit": lb.get("credit", "")} if lb else None
    if not pa:
        return
    if d.bd_id:
        d.st.remove(d.bd_id, a, exit="fade")
    d.bd_id = d.st.add("backdrop", a, pa, pos=(640, 360), enter="fade", float_=False, edge=False, z=-1000)
    d.st.move(d.bd_id, a + 0.05, pos=(608, 352), dur=BACKDROP_S * 1.5)        # a slow pan: the photo is alive, never still
    d.bd_at, d.bd_subject = a, subject


def _caption(d: "_Director", a: float, text: str, why: str) -> None:
    """Every stage beat says what it shows in the line's own words, under the stickers (the reference captions nearly every
    sticker). Not over a full card (split tree, maps, ownership carry their own labels), not where bubbles or big type already
    carry the words. The previous line's caption leaves as the new one comes in."""
    if d.caption_id:
        d.st.remove(d.caption_id, a, exit="fade")
        d.caption_id = None
    if d.full or any(why.startswith(x) for x in NO_CAPTION) or text.strip().endswith("?"):
        return                     # a question is big type (retention), never a caption
    cap = caption_of(text)
    if len(cap.split()) >= 3:
        d.caption_id = d.st.add("caption", a + 0.35, {"text": cap}, pos=(640, 606), enter="rise", float_=False, edge=False, z=900)


def _short(text: str, words: int = 7) -> str:
    w = re.split(r"[,.;:—–-]", text.strip())[0].split()
    return " ".join(w[:words])


def _line(d: _Director, a: float, c: Any, r: dict, g: str, airline: str, al: dict, text: str, rel, maps, cards2, skin) -> str:
    v = c.values
    codes = countries_in(text)

    # the article / report the CSV cites -> the newspaper paper sticker (filled by storyweb.resolve at Generate)
    pa = d.picture(web_key("url", r["url"]), {"capture": {"url": r["url"]}, "source": ""}) if r.get("url") else None
    if pa and has("paper"):
        el = d.sticker(a, "paper", pa, f"paper{r['url']}", edge=False, anim=1.6, enter="drop")
        if el:
            return "paper sticker (cited page)"

    # CSV hook: big type of the CSV's words (or the line's first clause)
    if g == "hook" and has("big_type"):
        d.card(a, "big_type", {"text": r.get("title") or _short(text)}, anim=1.2, enter="pop")
        return "hook"
    # split / merger tree from the catalog
    if (g == "split" or _SPLIT.search(text)) and has("split_tree") and al:
        tree = None
        par0 = C.get_airline(al.get("parent") or "") or {}
        root = par0["id"] if (_SPLIT.search(text) and not _MERGE.search(text) and len(par0.get("successors") or []) >= 2
                              and not al.get("successors")) else airline   # 'split into SIA and MAS' names a child: draw the parent
        if rel is not None and hasattr(rel, "tree_from_catalog"):
            try:
                tree = rel.tree_from_catalog(root, d.year or None)
            except Exception:
                tree = None
        if tree is None and (al.get("successors") or al.get("parent")):
            par = C.get_airline(al["parent"]) if (al.get("parent") and not al.get("successors")) else al
            kids = [C.get_airline(x) for x in (par or {}).get("successors") or []]
            kids = [x for x in kids if x]
            if par and kids:
                tree = {"parent": {"airline": par["id"], "name": par["name"]},
                        "children": [{"airline": x["id"], "name": x["name"]} for x in kids], "merge": bool(_MERGE.search(text))}
        if tree:
            d.card(a, "split_tree", tree, anim=2.6)
            return "split tree"
    # ownership
    if (g == "ownership" or (_STAKE.search(text) and (v.get("percent") or r.get("owners")))) and has("ownership") and airline:
        owners = []
        if rel is not None and hasattr(rel, "owners_from"):
            try:
                owners = rel.owners_from(r.get("owners") or text)
            except Exception:
                owners = []
        target = airline
        if not owners:                      # 'Singapore Airlines received a 25.1 percent stake in the merged Air India'
            m = _STAKE_IN.search(text)
            if m:
                own = C.find_airlines(m.group("owner"))
                tgt = C.find_airlines(m.group("target"))
                owners = [{"name": (own[0].entry or {}).get("name", m.group("owner")) if own else m.group("owner"),
                           "airline": (own[0].entry or {}).get("id", "") if own else "", "pct": float(m.group("pct"))}]
                if tgt and tgt[0].entry:
                    target = tgt[0].entry["id"]
        if owners:
            d.card(a, "ownership", {"airline": target, "owners": owners}, anim=2.4)
            return "ownership"
    # who got what (CSV split column)
    if r.get("split") and has("split_board") and rel is not None and hasattr(rel, "split_from"):
        try:
            sides = rel.split_from(r["split"])
        except Exception:
            sides = []
        if sides:
            d.card(a, "split_board", {"sides": sides}, anim=3.0)
            return "who got what"
    # two countries arguing
    if (g == "argument" or (len(codes) >= 2 and _ARGUE.search(text))) and rel is not None and hasattr(rel, "add_argument") \
            and hasattr(rel, "sides_from_line"):
        try:
            sides = rel.sides_from_line(text, codes)
        except Exception:
            sides = None
        if sides:
            d._clear(a)
            try:
                ids = rel.add_argument(d.st, a + 0.2, sides[0], sides[1],
                                       {"type": d.type_for(c, airline)[0], "airline": airline}
                                       if airline else None)
                d.full = ids[0] if ids else None
                d.row = []
                return "argument"
            except Exception:
                pass
    # names over time -> logo cards on the timeline (once per airline)
    from . import storycards as K
    if (g == "timeline" or _RENAME.search(text)) and airline and ("timeline", airline) not in d.shown:
        eras = K.eras(airline)
        if len(eras) >= 2:
            d._clear(a)
            ids = K.add_timeline(d.st, a + 0.2, eras, airline=airline, now=max(d.year, 2026) if d.year else 2026, badge=False)
            d.full = ids[0] if ids else None
            d.shown.add(("timeline", airline))
            return "timeline"
    # political map
    if (g == "map" or (_POLITY.search(text) and codes)) and has("political_map"):
        d.card(a, "political_map", {"countries": [{"code": x} for x in codes], "title": r.get("title") or ""}, anim=2.4, enter="fade")
        return "political map"
    # route map
    aps = [x["id"] for x in c.airports]
    if (g == "routes" or (_ROUTES.search(text) and len(set(aps)) >= 2)) and has("route_map") and al:
        hubs = list(al.get("hubs") or [])[:1] or aps[:1]
        dest = [x for x in dict.fromkeys(aps) if x not in hubs]
        if hubs and dest:
            d.card(a, "route_map", {"hubs": hubs, "destinations": dest, "airline": airline}, anim=2.8,   # the stage badge has the year
                   enter="fade")
            return "route map"
    # the line's own numbers as the built aviation graphics, in the sticker skin (fleet of stickers, cabin, bars, big number ...)
    if skin is not None and hasattr(skin, "add_graphic"):
        from . import planner as P
        for name, params in P._air_graphics(c, r):
            if name in ("gfx_air.lay_network", "gfx_air.lay_timeline"):
                continue                       # the stage has its own route-map card and logo-card timeline
            if name == "gfx_air.lay_fleet":
                params = dict(params, airline=airline, type=d.type_for(c, airline)[0])
            ident = f"{name}{sorted(params.items())}"
            if ident in [i for _, i in d.row]:
                break
            if d.full:
                d._clear(a)
            if len(d.row) >= MAX_STICKERS:
                old, _ = d.row.pop(0)
                d.st.remove(old, a, exit="slide_left")
            el = skin.add_graphic(d.st, a + 0.1, name, params, dur=4.0)
            d.row.append((el, ident))
            return "graphic " + name.split(".")[-1]
    # money
    if v.get("money"):
        cur, amt = v["money"][0]
        if has("cash_pile"):
            d.sticker(a, "cash_pile", {"value": amt, "currency": cur, "label": ""}, f"cash{amt}", anim=1.6, edge=False)
            return "cash pile"
        if has("icon_stat"):
            d.sticker(a, "icon_stat", {"value": amt, "unit": cur, "label": "", "icon": "cash"}, f"stat{amt}", anim=1.4, edge=False)
            return "icon stat"
    # fleet count
    counts = dict((n, x) for x, n in (v.get("counts") or []))
    n = next((counts[w] for w in ("aircraft", "jets", "planes") if counts.get(w)), 0)
    if n and c.aircraft and has("fleet_card"):
        d.sticker(a, "fleet_card", {"count": n, "type": c.aircraft[0]["id"], "airline": airline}, f"fleet{airline}{n}",
                  anim=1.2, edge=False)
        return "fleet card"
    # the airline's aircraft in its livery
    if c.aircraft or airline:
        typ, src = d.type_for(c, airline)
        from . import bible as BB
        el = d.sticker(a, "aircraft", {"type": typ, "airline": airline, "width": 560, "era": BB.era_of(d.year) if d.year else ""},
                       f"ac{airline}{typ}",
                       enter="slide_right")
        if el:
            return f"aircraft sticker ({typ} {src}, {airline or 'no livery'})"
    # a named person (CSV)
    if r.get("person") and has("portrait"):
        d.sticker(a, "portrait", {"name": r["person"], "role": r.get("role", ""), "quote": r.get("quote", "")},
                  f"p{r['person']}", edge=False)
        return "portrait"
    # countries named -> flags held up
    added = []
    for code in codes[:2]:
        el = d.sticker(a + 0.3 * len(added), "hand_flag", {"code": code, "side": "left" if not added else "right"}, f"flag{code}",
                       enter="slide_left" if not added else "slide_right")
        if el:
            added.append(code)
    if added:
        return "flags " + ",".join(added)
    # nothing new for this line: a real photo of what it names, found on the web at Generate (dropped if none passes the checks)
    names = [x["name"] for x in c.airlines] + [x["name"] for x in c.aircraft] + [x["city"] for x in c.airports]
    if names and has("photo_card") and a - d.last_photo >= PHOTO_GAP_S:
        title = names[0] + (f", {d.year}" if d.year else "")
        pa = d.picture(web_key("photo", text), {"capture": {"queries": _web_q(r), "text": text},
                                                "title": title, "credit": ""})
        el = d.sticker(a, "photo_card", pa, f"photo{title}", edge=False, anim=6.0, enter="pop") if pa else None
        if el:
            d.last_photo = a
            return "photo card (web)"
    return ""


def caption_of(text: str, words: int = 14) -> str:
    """A caption from the line's own words: the whole sentence when it fits two caption lines (<= `words` words), else its first
    caption - never a phrase cut in the middle ('... further than almost')."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    w = t.split()
    if 3 <= len(w) <= words:
        return t.rstrip(".;:")
    return ""                      # a long line: no caption (its first clause often reads as a cut: 'That is why its home airport')


_WEAK_END = set("the a an and or but of to in on for with from by at as its their his her that which who into".split())


_BD_USED: List[str] = []          # library photos already put behind a stage in this film (no photo twice in a row)


def _library_backdrop(airline: str, c: Any = None, year: int = 0) -> Optional[Dict[str, Any]]:
    """A real photo of this airline the shared library already holds (captured from the web for this or an earlier film):
    photo-like only (never a logo), ranked by its caption like a web backdrop (the line's aircraft / airline up; seats, cabins,
    logos, offices down; a caption year far from the line's rules it out), and not one already used. None when none fits."""
    if not airline:
        return None
    try:
        from . import library as LIB
        from .storyweb import backdrop_score, photo_like
        ranked = []
        for e in LIB.find("photo", airline=airline, approved_only=False):
            if e.get("airline") != airline:
                continue
            pth = str(LIB.path_of(e))
            if pth in _BD_USED or not photo_like(pth):
                continue
            cap = " ".join(str(x) for x in (e.get("subject"), e.get("caption"), " ".join(e.get("tags") or [])) if x)
            sc = backdrop_score(cap, c, year) if c is not None else 0.0
            if c is None or not getattr(c, "airlines", None):      # no airline on the line: judge it against the airline asked for
                from . import router as R
                sc = backdrop_score(cap, R.classify(str((C.get_airline(airline) or {}).get("name") or "")), year)
            if sc is None or sc < -0.5:
                continue
            ranked.append((sc, pth, e.get("credit") or ""))
        if not ranked:
            return None
        ranked.sort(key=lambda x: -x[0])
        _BD_USED.append(ranked[0][1])
        return {"path": ranked[0][1], "credit": ranked[0][2]}
    except Exception:
        return None


def fallback_stage(text: str, dur: float, scene: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A news line with no usable clip, as one short stage beat (never a blue text-only card): its airline's aircraft sticker,
    the line's own words as the caption under it, its year on the badge."""
    from . import router as R
    c = R.classify(text)
    st = G.Stage()
    years = c.values.get("years") or []
    if years:
        st.year(0.0, int(years[0]))
    sc = scene or {}
    al = c.airlines[0]["id"] if c.airlines else (C.get_airline(str(sc.get("airline") or "")) or {}).get("id", "")
    ac = C.find_aircraft(str(sc.get("aircraft") or "")) if sc.get("aircraft") and not c.aircraft else []
    typ = c.aircraft[0]["id"] if c.aircraft else ((ac[0].entry or {}).get("id") if ac and ac[0].entry else
                                                    era_type(int(years[0]) if years else 0))
    bd = _library_backdrop(al, c, int(years[0]) if years else 0)
    if bd:
        st.add("backdrop", 0.0, {"image": bd["path"], "credit": bd.get("credit", "")}, pos=(640, 360), enter="fade",
               float_=False, edge=False, z=-1000)
    st.add("aircraft", 0.15, {"type": typ, "airline": al, "width": 620}, pos=(640, 330), enter="slide_right")
    cap = caption_of(text, words=18)
    if cap:
        st.add("caption", 0.45, {"text": cap}, pos=(640, 560), enter="rise", float_=False, edge=False)
    return st.params()
