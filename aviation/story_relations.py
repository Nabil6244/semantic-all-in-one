"""Story-mode relations on the sticker stage (docs/aviation/MASTER_PLAN.md S4, S5, S8, S12): who split from whom, who owns whom,
who argued, who got what. Registered as stage sprite kinds (the stage imports this module on demand), so they float, glide and leave
like every other sticker. Positions are in 1280 x 720 units. Names, numbers and words come only from args (narration / CSV / catalog).

    split_tree   (animated) args {parent: {airline, name?, years?}, children: [{airline, name?, years?}, ...], merge: bool}
                 one white logo card, coloured lines drawing out to 2-3 child cards (merge: the children are the sources and the
                 lines join into the single card below); a child pops when its line arrives.
    ownership    (animated) args {airline, owners: [{name, code?, airline?, pct?}], name?, years?}
                 logo card on top, arrows down to the owners (flag sticker or tail mark + name + percentage counting up).
    split_board  (animated) args {sides: [{code? | airline?, name?, items: [{icon, caption}]}]}
                 a flag on top of each column, item stickers popping in one by one with captions. icon: a stickers.prop kind or
                 'aircraft:<type id>'.

    tree_from_catalog(airline_id, year=None) -> args | None   catalog parent / successors (msa -> singapore_airlines + malaysia_airlines)
    owners_from(text) -> [owner]                              "Malaysia 42.79% / Singapore 42.79% / BOAC" or "a 49% stake held by X"
    sides_from_line(text, countries) -> (left, right) | None  "Malaysia wanted X, while Singapore wanted Y" -> two {code, text, bold}
    split_from(csv_value) -> sides                            "Singapore: international routes, 707s | Malaysia: domestic network"
    country_code(name) -> 'MY' | ''                           names / adjectives of the ~43 flags in stickers.FLAGS

    add_argument(st, at, left, right, aircraft=None, step=1.2) -> ids
        left / right {code, text, bold}; aircraft {type, airline} | None. Hand-flag stickers slide in from each side, a speech bubble
        above each carries that side's clause (bold words yellow), the aircraft sticker in the middle is tugged toward the speaker.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from cinematic_explainer.war import motion as M

from . import catalog as C
from . import stage as G
from . import storycards as K
from . import style as S

LINE_COLORS = (S.YELLOW, S.GREEN, S.RED, (92, 160, 250, 255))


# ---------------------------------------------------------------------------------------------------------------- countries

_COUNTRIES: Dict[str, Tuple[str, ...]] = {
    "SG": ("Singapore", "Singaporean"), "MY": ("Malaysia", "Malaysian"), "GB": ("Britain", "United Kingdom", "UK", "British", "England", "English"),
    "FR": ("France", "French"), "NL": ("Netherlands", "Holland", "Dutch"), "DE": ("Germany", "German"),
    "US": ("United States", "USA", "America", "American", "US"), "IN": ("India", "Indian"),
    "AE": ("United Arab Emirates", "UAE", "Emirati"), "QA": ("Qatar", "Qatari"), "AU": ("Australia", "Australian"),
    "JP": ("Japan", "Japanese"), "CN": ("China", "Chinese"), "HK": ("Hong Kong",), "KR": ("South Korea", "Korea", "Korean"),
    "TH": ("Thailand", "Thai"), "ID": ("Indonesia", "Indonesian"), "PH": ("Philippines", "Filipino"), "VN": ("Vietnam", "Vietnamese"),
    "TR": ("Turkey", "Turkish"), "IT": ("Italy", "Italian"), "ES": ("Spain", "Spanish"), "PT": ("Portugal", "Portuguese"),
    "IE": ("Ireland", "Irish"), "CH": ("Switzerland", "Swiss"), "AT": ("Austria", "Austrian"), "BE": ("Belgium", "Belgian"),
    "DK": ("Denmark", "Danish"), "SE": ("Sweden", "Swedish"), "NO": ("Norway", "Norwegian"), "FI": ("Finland", "Finnish"),
    "PL": ("Poland", "Polish"), "RU": ("Russia", "Russian", "Soviet Union", "USSR"), "CA": ("Canada", "Canadian"),
    "BR": ("Brazil", "Brazilian"), "MX": ("Mexico", "Mexican"), "AR": ("Argentina", "Argentine"), "ZA": ("South Africa",),
    "EG": ("Egypt", "Egyptian"), "SA": ("Saudi Arabia", "Saudi"), "NZ": ("New Zealand",), "PK": ("Pakistan", "Pakistani"),
    "LK": ("Sri Lanka", "Ceylon"),
}
_NAME2CODE = {n.lower(): c for c, ns in _COUNTRIES.items() for n in ns}


def country_code(name: Any) -> str:
    """ISO-2 code of a country name / adjective / code ('Malaysia', 'Malaysian', 'MY' -> 'MY'); '' when unknown."""
    t = str(name or "").strip()
    if not t:
        return ""
    if len(t) == 2 and t.upper() in _COUNTRIES:
        return t.upper()
    return _NAME2CODE.get(t.lower().strip(".,;:"), "")


def _mention(text: str, code: str) -> Optional[Tuple[int, int]]:
    """First place in text where the country (any name / adjective / stem) is mentioned."""
    best = None
    for n in _COUNTRIES.get(code, ()):
        pat = r"(?<![A-Za-z])" + re.escape(n) + (r"\w*" if len(n) > 3 else r"(?![A-Za-z])")
        m = re.search(pat, text, re.I if len(n) > 3 else 0)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), m.end())
    return best


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip(" \t\n,;:-–—")


def _fmt_pct(v: float, places: int) -> str:
    return f"{v:.{places}f}%"


def _places(v: Any) -> int:
    s = str(v)
    return len(s.split(".")[1]) if "." in s and not s.endswith(".0") else 0


# ---------------------------------------------------------------------------------------------------------------- shared drawing

def _card(entry: Dict[str, Any], width: int) -> Image.Image:
    a = {"airline": entry.get("airline", ""), "width": width}
    for k in ("name", "years"):
        if entry.get(k):
            a[k] = entry[k]
    return K.logo_card(a)


def _line_color(airline: str, i: int) -> Tuple[int, int, int, int]:
    al = C.get_airline(airline) or {}
    for h in al.get("colors") or []:
        try:
            rgb = tuple(int(str(h).lstrip("#")[j:j + 2], 16) for j in (0, 2, 4))
        except ValueError:
            continue
        if sum(rgb) > 330 and not all(c > 235 for c in rgb):
            return rgb + (255,)
    return LINE_COLORS[i % len(LINE_COLORS)]


def _poly_len(pts: Sequence[Tuple[float, float]]) -> float:
    return sum(((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5 for i in range(len(pts) - 1))


def _partial(pts: Sequence[Tuple[float, float]], f: float) -> List[Tuple[float, float]]:
    """The first fraction f (0..1) of a polyline."""
    f = M.clamp01(f)
    total, goal = _poly_len(pts), _poly_len(pts) * f
    out, acc = [pts[0]], 0.0
    for i in range(len(pts) - 1):
        seg = ((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5
        if acc + seg >= goal:
            r = (goal - acc) / seg if seg else 0
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * r, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * r))
            return out
        out.append(pts[i + 1])
        acc += seg
    return out


def _thick(d: ImageDraw.ImageDraw, pts: Sequence[Tuple[float, float]], col, w: int) -> None:
    if len(pts) < 2:
        return
    d.line([tuple(p) for p in pts], fill=col, width=w, joint="curve")
    r = w / 2.0
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=col)


def _paste_scaled(im: Image.Image, sprite: Image.Image, cx: float, cy: float, s: float) -> None:
    if s <= 0.02:
        return
    if abs(s - 1) > 0.01:
        sprite = sprite.resize((max(1, int(sprite.width * s)), max(1, int(sprite.height * s))), Image.BILINEAR)
    im.alpha_composite(sprite, (int(cx - sprite.width / 2), int(cy - sprite.height / 2)))


def _pop(q: float) -> float:
    return max(0.0, G._back_out(M.clamp01(q)))


def _wrap(d: ImageDraw.ImageDraw, text: str, font, maxw: float) -> List[str]:
    lines, cur = [], ""
    for wd in str(text).split():
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=font) > maxw and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


def _centered(d: ImageDraw.ImageDraw, cx: float, y: float, lines: Sequence[str], font, fill, lh: float = 1.15) -> float:
    for ln in lines:
        d.text((cx - d.textlength(ln, font=font) / 2, y), ln, font=font, fill=fill)
        y += font.size * lh
    return y


def _flag_sticker(code: str, width: int) -> Image.Image:
    from . import stickers
    return stickers.die_cut(stickers.flag(code, width), 7, shadow=False)


# ---------------------------------------------------------------------------------------------------------------- S4 split tree

def tree_from_catalog(airline_id: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """split_tree args from the catalog: the airline and its successors (a split); with no successors but a parent, the parent and
    the airline. Names are those of `year` when given. None when the catalog has nothing to branch."""
    al = C.get_airline(airline_id)
    if not al:
        return None

    def node(i: str) -> Dict[str, Any]:
        e = C.get_airline(i) or {}
        nm = (C.name_in_year(i, year) if year else None) or e.get("name", i)
        f, dd = e.get("founded"), e.get("defunct")
        yrs = f"{f}–{dd}" if f and dd else (f"since {f}" if f else "")
        return {"airline": i, "name": nm, "years": yrs}

    succ = [s for s in (al.get("successors") or []) if C.get_airline(s)]
    if succ:
        return {"parent": node(airline_id), "children": [node(s) for s in succ[:3]], "merge": False}
    if al.get("parent") and C.get_airline(al["parent"]):
        return {"parent": node(al["parent"]), "children": [node(airline_id)], "merge": False}
    return None


def split_tree(a: Dict[str, Any]) -> Image.Image:
    k = float(a.get("_k", 1.0))
    parent = a.get("parent") or {}
    kids = list(a.get("children") or [])[:3]
    merge = bool(a.get("merge"))
    n = max(1, len(kids))
    cw = 300 if n >= 3 else 340
    gap = 40
    Wd = max(cw * n + gap * (n - 1), cw) + 60
    def small(im: Image.Image) -> Image.Image:       # keep the whole tree under ~620 units tall
        return im.resize((int(im.width * 0.82), int(im.height * 0.82)), Image.LANCZOS)

    pc = small(_card(parent, cw))
    kc = [small(_card(c, cw)) for c in kids]
    ph, kh = pc.height, max([c.height for c in kc] or [0])
    drop = 100
    Hd = ph + drop + kh + 20
    im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    px = Wd / 2
    xs = [Wd / 2 + (i - (n - 1) / 2.0) * (cw + gap) for i in range(n)]
    if merge:      # sources on top, joined into the single card below
        top_y, bot_y = 10 + kh / 2, 10 + kh + drop + ph / 2
        kid_y, par_y = top_y, bot_y
        lines = [[(x, 10 + kh), (x, 10 + kh + drop / 2), (px, 10 + kh + drop / 2), (px, 10 + kh + drop)] for x in xs]
    else:
        par_y, kid_y = 10 + ph / 2, 10 + ph + drop + kh / 2
        lines = [[(px, 10 + ph), (px, 10 + ph + drop / 2), (x, 10 + ph + drop / 2), (x, 10 + ph + drop)] for x in xs]
    span = 0.55 / n
    for i, (ln, c) in enumerate(zip(lines, kids)):
        s0 = (0.08 + i * span * 0.8) if not merge else (0.30 + i * span * 0.6)
        f = M.ease_in_out(M.clamp01((k - s0) / (0.4 if not merge else 0.3)))
        if f > 0:
            _thick(d, _partial(ln, f), _line_color(c.get("airline", ""), i), 10)
    if merge:                       # sources pop in turn, then the lines, then the merged card
        for i, c in enumerate(kc):
            _paste_scaled(im, c, xs[i], kid_y, _pop((k - i * 0.1) / 0.12))
        _paste_scaled(im, pc, px, par_y, _pop((k - 0.72) / 0.14))
    else:                           # parent first, each child pops as its line arrives
        _paste_scaled(im, pc, px, par_y, _pop(k / 0.1))
        for i, c in enumerate(kc):
            arrive = 0.08 + i * span * 0.8 + 0.4
            _paste_scaled(im, c, xs[i], kid_y, _pop((k - arrive) / 0.12))
    return im


# ---------------------------------------------------------------------------------------------------------------- S8 ownership

_NAME = r"([A-Z][\w'’&.\-]*(?:\s+(?:of|and|&|de|the)?\s*[A-Z][\w'’&.\-]*)*)"
_PCT = r"(\d+(?:\.\d+)?)\s*(?:%|per\s?cent|percent)"
_OWN_PATTERNS = (
    re.compile(_PCT + r"\s+(?:\w+\s+)?(?:stake|share|shares|shareholding|ownership|interest|holding)?\s*(?:was\s+|is\s+|being\s+)?"
               r"(?:held|owned|controlled|bought|taken|acquired)\s+by\s+" + _NAME),
    re.compile(_NAME + r"\s+(?:held|owned|controlled|bought|took|acquired|retained|had)\s+(?:a\s+|an\s+|the\s+)?(?:about\s+|around\s+)?" + _PCT),
    re.compile(_NAME + r",?\s+(?:which|who)\s+(?:held|owned|controlled|had)\s+(?:a\s+|an\s+)?" + _PCT),
    re.compile(_PCT + r"\s+(?:stake|share|shares)?\s*(?:in\s+[\w\s\-]+?\s+)?(?:to|for)\s+" + _NAME),
    re.compile(_PCT + r"\s+(?:owned|held)\s+by\s+" + _NAME),
)


_PEOPLE = re.compile(r"\b(employees?|staff|workers?|pilots?|crew|unions?|investors?|shareholders?|public|private|funds?|"
                     r"management|founders?|families|family)\b", re.I)


def _owner(name: str, pct: Optional[float] = None) -> Dict[str, Any]:
    name = _clean(name)
    o: Dict[str, Any] = {"name": name}
    code = country_code(name)
    if _PEOPLE.search(name):
        o["people"] = True            # 'TAP employees' are people, not the airline TAP: their own label and a people icon
    elif code:
        o["code"] = code
    else:
        hits = [m for m in C.find_airlines(name) if m.entry]
        if hits:
            o["airline"] = hits[0].entry["id"]
            o["name"] = hits[0].entry.get("name") or name
    if pct is not None:
        o["pct"] = pct
    return o


def owners_from(text: Any) -> List[Dict[str, Any]]:
    """Owners from a CSV value ('Malaysia 42.79% / Singapore 42.79% / BOAC / Qantas') or a narration line ('a 49% stake held by
    Singapore Airlines'). [] when none is found."""
    t = str(text or "").strip()
    if not t:
        return []
    out: List[Dict[str, Any]] = []
    seen = set()

    def push(name: str, pct: Optional[str]) -> None:
        o = _owner(name, float(pct) if pct is not None else None)
        key = o["name"].lower()
        if o["name"] and key not in seen:
            seen.add(key)
            out.append(o)

    parts = [p for p in re.split(r"\s*[/|;\n]\s*", t) if p.strip()]
    if len(parts) > 1 or (len(parts) == 1 and len(t.split()) <= 4):
        for p in parts:
            m = re.search(_PCT, p)
            name = _clean(re.sub(_PCT, "", p))
            if name and len(name.split()) <= 5:
                push(name, m.group(1) if m else None)
        if out:
            return out
    for pat in _OWN_PATTERNS:
        for m in pat.finditer(t):
            g = m.groups()
            pct, name = (g[0], g[1]) if re.fullmatch(r"\d+(?:\.\d+)?", g[0]) else (g[1], g[0])
            name = re.sub(r"^(?:The|A|An)\s+", "", name)
            push(name, pct)
    return out


def _owner_icon(o: Dict[str, Any], size: int) -> Image.Image:
    from . import stickers
    if o.get("people"):                                   # employees / investors / the public: three heads in a white disc
        disc = Image.new("RGBA", (size + 24, size + 24), (0, 0, 0, 0))
        dd = ImageDraw.Draw(disc)
        dd.ellipse((0, 0, disc.width - 1, disc.height - 1), fill=S.WHITE)
        cx, cy, u = disc.width / 2, disc.height / 2, size / 9.0
        for dx, sc_, col in ((-2.6, 0.82, (120, 126, 138)), (2.6, 0.82, (120, 126, 138)), (0.0, 1.0, S.INK)):
            hx, r = cx + dx * u, 1.5 * u * sc_
            dd.ellipse((hx - r, cy - 2.6 * u * sc_ - r, hx + r, cy - 2.6 * u * sc_ + r), fill=col)
            dd.pieslice((hx - 2.6 * u * sc_, cy - 0.6 * u, hx + 2.6 * u * sc_, cy + 4.2 * u * sc_), 180, 360, fill=col)
        return disc
    if o.get("code"):
        return _flag_sticker(o["code"], int(size * 1.15))
    if o.get("airline"):
        m = stickers.tail_mark(o["airline"], size)
        disc = Image.new("RGBA", (size + 24, size + 24), (0, 0, 0, 0))
        ImageDraw.Draw(disc).ellipse((0, 0, disc.width - 1, disc.height - 1), fill=S.WHITE)
        disc.alpha_composite(m, ((disc.width - m.width) // 2, (disc.height - m.height) // 2))
        return disc
    t = "".join(w[0] for w in str(o.get("name", "?")).split()[:2]).upper() or "?"
    disc = Image.new("RGBA", (size + 24, size + 24), (0, 0, 0, 0))
    dd = ImageDraw.Draw(disc)
    dd.ellipse((0, 0, disc.width - 1, disc.height - 1), fill=S.WHITE)
    f = S.font("title", int(size * 0.5))
    dd.text((disc.width / 2, disc.height / 2), t, font=f, fill=S.INK, anchor="mm")
    return disc


def ownership(a: Dict[str, Any]) -> Image.Image:
    k = float(a.get("_k", 1.0))
    owners = list(a.get("owners") or [])[:5]
    n = max(1, len(owners))
    colw = min(280, 1100 // n)
    Wd = max(colw * n, 400) + 40
    top = _card({"airline": a.get("airline", ""), "name": a.get("name"), "years": a.get("years")}, 340)
    icon_sz = 110 if n <= 3 else 90
    arrow_h = 110
    f_name, f_pct = S.font("body", 30), S.font("heavy", 44)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    cols = []
    for o in owners:
        cols.append((_owner_icon(o, icon_sz), _wrap(probe, str(o.get("name", "")), f_name, colw - 24)))
    col_h = max([ic.height + 12 + len(ls) * int(f_name.size * 1.15) for ic, ls in cols] or [0]) + 16 + int(f_pct.size * 1.2)
    Hd = top.height + arrow_h + col_h + 20
    im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx0 = Wd / 2
    _paste_scaled(im, top, cx0, 10 + top.height / 2, 1.0)
    ay0, ay1 = 10 + top.height + 6, 10 + top.height + arrow_h
    span = 0.45 / n
    for i, (o, (ic, ls)) in enumerate(zip(owners, cols)):
        x = cx0 + (i - (n - 1) / 2.0) * colw
        s0 = 0.06 + i * span * 0.7
        f = M.ease_out(M.clamp01((k - s0) / 0.3))
        col = _line_color(o.get("airline", ""), i)
        if f > 0:
            pts = _partial([(cx0, ay0), (cx0, ay0 + 16), (x, ay0 + 16), (x, ay1 - 8)], f)
            _thick(d, pts, col, 8)
            if f >= 0.98:
                d.polygon([(x - 17, ay1 - 20), (x + 17, ay1 - 20), (x, ay1 + 4)], fill=col)
        q = (k - s0 - 0.22) / 0.14
        if q > 0:
            y = ay1 + 14
            _paste_scaled(im, ic, x, y + ic.height / 2, _pop(q))
            ty = y + ic.height + 12
            _centered(d, x, ty, ls, f_name, S.WHITE)
            if o.get("pct") is not None:
                v = float(o["pct"]) * M.ease_out(M.clamp01((k - s0 - 0.3) / 0.5))
                txt = _fmt_pct(v, _places(o["pct"]))
                ty2 = ty + len(ls) * int(f_name.size * 1.15) + 6
                d.text((x - d.textlength(txt, font=f_pct) / 2, ty2), txt, font=f_pct, fill=S.YELLOW)
    return im


# ---------------------------------------------------------------------------------------------------------------- S5 argument

_SEP = re.compile(r"(?:\s*[,;]\s*(?:while|whereas|but|yet|and|though|although)\b\s*|\s*[;,]\s*|\s+(?:while|whereas|but)\s+)", re.I)
_LEAD = re.compile(r"^(?:while|whereas|although|though|but|and|when|as)\s+", re.I)


def sides_from_line(text: Any, countries: Sequence[Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Split a line with two sides into (left, right) = {code, text, bold} in the order the countries are first mentioned.
    'Malaysia wanted X, while Singapore wanted Y' and 'X wanted ..., but Y ...' work; None when the line has one side only."""
    t = _clean(text)
    codes = []
    for c in countries or []:
        cc = country_code(c)
        if cc and cc not in codes:
            codes.append(cc)
    if len(codes) < 2 or not t:
        return None
    hits = [(c, _mention(t, c)) for c in codes]
    hits = sorted([(c, m) for c, m in hits if m], key=lambda h: h[1][0])
    if len(hits) < 2:
        return None
    (ca, ma), (cb, mb) = hits[0], hits[1]
    seps = [m for m in _SEP.finditer(t) if ma[1] <= m.start() and m.end() <= mb[0] + 1]
    seps = [m for m in seps if len(t[m.end():mb[0]].split()) <= 4]       # the second side starts right after the separator
    if not seps:
        return None
    sp = seps[0] if len(seps) == 1 else min(seps, key=lambda m: mb[0] - m.end())
    left, right = _LEAD.sub("", t[:sp.start()]), t[sp.end():]
    left, right = _clean(left), _clean(right)
    if len(left.split()) < 3 or len(right.split()) < 3:
        return None
    if _mention(left, ca) is None or _mention(right, cb) is None:
        return None

    def side(code: str, clause: str) -> Dict[str, Any]:
        clause = clause[0].upper() + clause[1:]
        bold = [w.strip(".,;:!?\"'()") for w in clause.split() if re.search(r"\d", w)]
        return {"code": code, "text": clause, "bold": bold}

    return side(ca, left), side(cb, right)


def add_argument(st: G.Stage, at: float, left: Dict[str, Any], right: Dict[str, Any], aircraft: Optional[Dict[str, Any]] = None,
                 step: float = 1.2) -> List[str]:
    """Two flag characters argue over an aircraft: each slides in from its side with a speech bubble; the aircraft is tugged to
    the speaker (small x shifts, alternating)."""
    ids: List[str] = []
    ax, ay = 640.0, 440.0
    plane = None
    if aircraft:
        plane = st.add("aircraft", at, {"type": aircraft.get("type", ""), "airline": aircraft.get("airline", ""), "width": 380},
                       pos=(ax, ay), scale=1.0)
        ids.append(plane)
    for i, (side, name, d) in enumerate(((left, "left", -1), (right, "right", 1))):
        t = at + 0.2 + i * step
        bold = side.get("bold") or []
        if isinstance(bold, str):
            bold = [bold]
        fx = 640.0 + d * 470.0
        ids.append(st.add("hand_flag", t, {"code": side.get("code", ""), "width": 250, "side": "left" if d < 0 else "right"},
                          pos=(fx, 520.0), enter="slide_left" if d < 0 else "slide_right"))
        ids.append(st.add("bubble", t + 0.35, {"text": side.get("text", ""), "width": 470, "bold": list(bold),
                                               "tail": "left" if d < 0 else "right"},
                          pos=(640.0 + d * 360.0, 190.0), enter="pop", edge=False))
        if plane:
            st.move(plane, t + 0.6, pos=(ax + d * 70.0, ay), dur=0.5)
    if plane:
        st.move(plane, at + 0.2 + 2 * step, pos=(ax, ay), dur=0.6)
    return ids


# ---------------------------------------------------------------------------------------------------------------- S12 split board

_ICON_WORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("building", ("hq", "headquarters", "head office", "office", "building", "hub")),
    ("cash", ("money", "cash", "profit", "profits", "revenue", "dollar", "dollars", "payment", "compensation")),
    ("coins", ("debt", "debts", "loan", "loans", "shares", "stake", "assets", "fund")),
    ("cargo", ("cargo", "freight", "parcels", "mail")),
    ("ticket", ("ticket", "tickets", "fare", "fares", "booking")),
    ("timetable", ("schedule", "schedules", "timetable", "timetables")),
    ("contract", ("contract", "agreement", "deal", "treaty", "rights", "licence", "license")),
    ("chart", ("traffic", "growth", "profitability", "market share", "passengers")),
    ("route_icon", ("route", "routes", "network", "destinations", "flights", "service", "services", "sectors")),
    ("globe", ("international", "world", "global", "overseas", "abroad")),
    ("crown", ("flag carrier", "national", "brand", "name", "identity")),
)


def _aircraft_id(item: str) -> str:
    cand = [item]
    plain = re.sub(r"(\d)s\b", r"\1", item)
    cand.append(plain)
    for m in re.finditer(r"\b(7\d7)\b", plain):
        cand.append("Boeing " + m.group(1))
    for c in cand:
        for m in C.find_aircraft(c):
            if m.entry:
                return m.entry["id"]
    return ""


def _guess_icon(item: str) -> str:
    ac = _aircraft_id(item)
    if ac:
        return "aircraft:" + ac
    low = " " + item.lower() + " "
    if "$" in item or "£" in item:
        return "cash"
    for prop, words in _ICON_WORDS:
        for w in words:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
                return prop
    if re.search(r"\b(jets?|aircraft|planes?|fleet|airliners?|turboprops?|[A-Z][a-z]+ \d{2,3}s?)\b", item):
        return "plane_icon"
    return "plane_icon"


def split_from(csv_value: Any) -> List[Dict[str, Any]]:
    """'Singapore: international routes, 707s, HQ | Malaysia: domestic network, Fokker 27s' -> split_board sides. [] when empty."""
    sides: List[Dict[str, Any]] = []
    for part in re.split(r"\s*(?:\||\n)\s*", str(csv_value or "")):
        if ":" not in part:
            continue
        label, rest = part.split(":", 1)
        label = _clean(label)
        items = [{"icon": _guess_icon(x), "caption": x} for x in (_clean(x) for x in rest.split(",")) if x]
        if not label or not items:
            continue
        side: Dict[str, Any] = {"name": label, "items": items}
        code = country_code(label)
        if code:
            side["code"] = code
        else:
            hits = [m for m in C.find_airlines(label) if m.entry]
            if hits:
                side["airline"] = hits[0].entry["id"]
                side["name"] = hits[0].entry.get("name") or label
        sides.append(side)
    return sides


def _item_icon(icon: str, airline: str, size: int) -> Image.Image:
    from . import stickers
    if icon.startswith("aircraft:"):
        im = stickers.aircraft(icon.split(":", 1)[1], airline, int(size * 1.9))
    else:
        im = stickers.prop(icon, size)
    return stickers.die_cut(im, 6, shadow=False)


def split_board(a: Dict[str, Any]) -> Image.Image:
    k = float(a.get("_k", 1.0))
    sides = list(a.get("sides") or [])[:3]
    n = max(1, len(sides))
    colw = min(520, 1160 // n)
    Wd = colw * n + 40
    f_cap = S.font("body", 30 if n <= 2 else 26)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    isz = 100 if n <= 2 else 84
    rows_h: List[List[int]] = []
    laid = []
    for sd in sides:
        items = list(sd.get("items") or [])[:5]
        col = []
        for it in items:
            ic = _item_icon(str(it.get("icon", "plane_icon")), sd.get("airline", ""), isz)
            capw = colw - 40 - max(ic.width, isz + 20) - 16
            ls = _wrap(probe, str(it.get("caption", "")), f_cap, capw)
            col.append((ic, ls, max(ic.height, len(ls) * int(f_cap.size * 1.15)) + 14))
        laid.append(col)
    head = 170
    body = max([sum(r[2] for r in col) for col in laid] or [0])
    Hd = head + body + 24
    im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    total = max(1, sum(len(c) for c in laid))
    rows = max([len(c) for c in laid] or [0])
    order = [(c, r) for r in range(rows) for c in range(n) if r < len(laid[c])]
    for c, sd in enumerate(sides):
        cx = 20 + colw * c + colw / 2
        if c:
            x = 20 + colw * c
            d.line((x, 20, x, Hd - 20), fill=(60, 62, 72, 255), width=3)
        if sd.get("code"):
            hd = _flag_sticker(sd["code"], 190 if n <= 2 else 160)
        elif sd.get("airline"):
            hd = _owner_icon({"airline": sd["airline"], "name": sd.get("name", "")}, 110)
        else:
            hd = _owner_icon({"name": sd.get("name", "?")}, 110)
        _paste_scaled(im, hd, cx, head / 2, _pop((k - 0.02 * c) / 0.1))
    for idx, (c, r) in enumerate(order):
        ic, ls, rh = laid[c][r]
        q = (k - (0.14 + 0.8 * idx / total)) / 0.1
        if q <= 0:
            continue
        y = head + sum(x[2] for x in laid[c][:r])
        x0 = 20 + colw * c + 20
        _paste_scaled(im, ic, x0 + max(ic.width, isz + 20) / 2, y + rh / 2, _pop(q))
        tx = x0 + max(ic.width, isz + 20) + 16
        ty = y + (rh - len(ls) * int(f_cap.size * 1.15)) / 2
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for ln in ls:
            ld.text((tx, ty), ln, font=f_cap, fill=S.WHITE)
            ty += int(f_cap.size * 1.15)
        layer.putalpha(layer.getchannel("A").point(lambda v, a=M.clamp01(q * 1.5): int(v * a)))
        im.alpha_composite(layer)
    return im


G.register("split_tree", split_tree)
G.register("ownership", ownership)
G.register("split_board", split_board)
