"""The Food Files CSV: one row per spoken line, in order (the lines ARE the narration).

Columns (only `line` is required; an empty cell = the director decides):
  line    the words spoken over this shot
  shot    host | title | number | next | photo | scene | map | folder | headline | quote | tweet | big | flow | explain |
          timeline | page | clip | split | pip | thumbnail
  item    the list number on a `number` card ("3")
  title   header pill on a card ("HOW JAWBREAKERS ARE MADE"); number card: the small line above the name
          ("THE CANDY AISLE CLASSIC"); headline: "OUTLET · DATE"; quote / tweet: who said it; title card: the 2-3 title
          lines "THE DEADLIEST | CANDY | EVER SOLD"; next card: the teaser ("A SPLIT SECOND...")
  name    number card: the product ("WONKA EVERLASTING GOBSTOPPER"); host shot: a person's name bar
          "WILLIAM HARDAKER | candy stall owner, Bradford"; tweet: the display name
  year    year pill on a number card; the date on a map / headline / tweet ("2003", "SEP 2020")
  place   map: "Starke, Florida" / "Florida" / "Japan" (the state or country fills red, a pin on the city)
  visual  the Flow picture prompt (photo, scene, split, pip, headline photo, card background); {host} = the host is in it
  stamp   a red rubber stamp slammed on at its word ("SETTLED", "RECALLED", "ALLEGEDLY EXPLODED")
  note    a handwritten side note on a host shot ("DOESN'T LAST FOREVER", "...KINDA")
  rows    card rows, ";" between them:
            folder:   "FILED BY = THE GIRL'S FAMILY; AGAINST = NESTLE; OUTCOME = SETTLED OUT OF COURT"
            big:      "141,850,885 = BOXES RECALLED"          (one row; several rows = several numbers)
            flow:     "SUGAR = EXPENSIVE; BULK IT UP; DAFF = CHEAP FILLER"
            explain:  "fridge = REFRIGERATED; sun = LEFT IN THE SUN; fridge = BACK IN THE FRIDGE"  (icon = label)
                      start with "+" to put a step on the same row as an "=" sign: "turkey = FROZEN SOLID; +ball = BOWLING BALL"
            timeline: "2003 = FIRST CASE; 2004 = MYTHBUSTERS TEST; 2005 = SETTLED"
            headline / quote / tweet: the text; *stars* mark the highlighted words
            map:      a label pill under the map ("9-YEAR-OLD GIRL")
            photo:    the caption pill ("A REAL-LIFE CANDY")
          colours: !red !green !yellow !white at the end of a row
  source  tiny credit line on the card (filled in by itself for real photos, pages and clips)
  find    words to search for the REAL thing: a Wikimedia Commons photo for photo / number / headline rows
          ("Wonka Everlasting Gobstopper"), a news / TV video for clip rows ("MythBusters jawbreaker microwave").
          Empty on a photo row = the item's name. Flow paints only what Commons has nothing for.
  url     a real page to screenshot for page / headline rows (a recall notice, a news article); the headline is
          highlighted. No url on a headline row = the typed headline card.
  page    shot=page: the screenshot of `url` in a browser frame, slowly scrolling, the headline highlighted
  compare shot=compare: two coloured halves, rows = "FRANCHISE OWNERS = man; CORPORATE = money" (label = icon)
  evidence shot=evidence: 2-3 evidence bags, rows = "METH = pill; MARIJUANA = germ", title = "FOUND INSIDE THE HOME"
  symptoms shot=symptoms: a person (name = icon, default kid) and red-cross pills, rows = "SHORTNESS OF BREATH; NAUSEA"
  states  shot=states: several states / countries lit, place = "Illinois; Connecticut", rows = one label per place
  browser shot=browser: a web page mock, title = the site ("company website · FAQ"), name = the page heading,
          rows = the text with *stars* highlighted
  scale   shot=scale: the thing on a scale, the dial turns; find = a real photo of it (or name = an icon), rows = the
          big words beside it ("A LOT HEAVIER")
  beforeafter shot=beforeafter: two real photos with a wipe, find = "THEN | NOW" searches, rows = "BEFORE; AFTER"
  tally   shot=tally: icons appear one by one and count, rows = "kid x 4 = KIDS HOSPITALIZED"
  scene2d shot=scene2d: a flat cartoon mini scene; place = classroom / kitchen / store / supermarket / street /
          night_road / hospital / doctor_office / living_room / dining_room / factory / lab / courtroom / office /
          playground / backyard / candy_shop / market_1850 / restaurant / news_studio; rows = "man: carry turkey; say = HEAVY!"
          (who: kid man woman doctor worker teen old; action: stand walk run carry eat sick fall point cheer sit shock wave
          talk + a prop icon) and say = / list = A | B / monitor / count / label =
  banner  title on a host row: a red banner across the top ("BUT IT STILL WASN'T ENOUGH")
  clip    shot=clip: ~7 s of the video `find` finds, cut where its transcript says this row's words (muted under the
          voice), framed with a strap: title = "OUTLET · DATE"; falls back to a photo of `find`
A thumbnail row has no line: shot=thumbnail, title = 2 lines "DEADLIEST | CANDY", visual = the picture prompt.
"""
import csv
import io
import re
from pathlib import Path

SHOTS = ("host", "title", "number", "next", "photo", "scene", "map", "folder", "headline", "quote", "tweet", "big", "flow",
         "explain", "timeline", "page", "clip", "compare", "evidence", "symptoms", "states", "browser", "scale",
         "beforeafter", "tally", "scene2d", "split", "pip", "thumbnail")
CARD_SHOTS = ("title", "number", "next", "photo", "map", "folder", "headline", "quote", "tweet", "big", "flow", "explain",
              "timeline", "page", "clip", "compare", "evidence", "symptoms", "states", "browser", "scale", "beforeafter", "tally",
              "scene2d")
PICTURE_SHOTS = ("scene", "split", "pip")
COLS = ("line", "shot", "item", "title", "name", "year", "place", "visual", "stamp", "note", "rows", "source", "find", "url")
ALIASES = {"text": "line", "narration": "line", "sentence": "line", "voice": "line", "type": "shot", "layout": "shot",
           "prompt": "visual", "image": "visual", "picture": "visual", "number": "item", "rank": "item", "header": "title",
           "product": "name", "person": "name", "date": "year", "location": "place", "scribble": "note", "card": "rows",
           "items": "rows", "credit": "source", "broll": "visual", "search": "find", "query": "find", "link": "url",
           "page_url": "url", "website": "url"}
SHOT_ALIASES = {"broll": "scene", "b-roll": "scene", "picture": "photo", "image": "photo", "countdown": "number",
                "item": "number", "nextup": "next", "case": "folder", "lawsuit": "folder", "news": "headline",
                "statement": "quote", "post": "tweet", "stat": "big", "chart": "flow", "steps": "explain",
                "diagram": "explain", "dates": "timeline", "open": "title", "screenshot": "page", "webpage": "page",
                "notice": "page", "video": "clip", "newsclip": "clip", "footage": "clip", "vs": "compare", "versus": "compare",
                "splitcompare": "compare", "bags": "evidence", "evidencebags": "evidence", "symptom": "symptoms",
                "multistate": "states", "statesmap": "states", "faq": "browser", "website": "browser", "weight": "scale",
                "dial": "scale", "before": "beforeafter", "before/after": "beforeafter", "count": "tally", "counter": "tally",
                "cartoon": "scene2d", "mini": "scene2d", "miniscene": "scene2d", "flatscene": "scene2d", "flat": "scene2d"}
COLOURS = ("red", "green", "yellow", "white")


def _norm(h):
    h = re.sub(r"[^a-z_]", "", str(h or "").strip().lower())
    return ALIASES.get(h, h)


def norm_shot(s):
    s = str(s or "").strip().lower().replace(" ", "").replace("_", "")
    return SHOT_ALIASES.get(s, s)


def read(path_or_text):
    """-> (rows, problems). rows: dicts with COLS keys (+ 'n' = CSV row number); the thumbnail row is kept in the list."""
    s = str(path_or_text)
    text = Path(s).read_text(encoding="utf-8-sig") if "\n" not in s and Path(s).is_file() else s
    rows, problems, head = [], [], None
    for n, cells in enumerate(csv.reader(io.StringIO(text)), 1):
        if not any(c.strip() for c in cells):
            continue
        if head is None:
            head = [_norm(c) for c in cells]
            if "line" not in head:
                raise ValueError("the Food Files CSV needs a 'line' column (the spoken words)")
            continue
        r = {k: "" for k in COLS}
        for k, v in zip(head, cells):
            if k in COLS:
                r[k] = v.strip()
        r["n"] = n
        r["shot"] = norm_shot(r["shot"])
        if r["shot"] and r["shot"] not in SHOTS:
            problems.append(f"row {n}: unknown shot '{r['shot']}' (the director picks one)")
            r["shot"] = ""
        if not r["line"] and r["shot"] != "thumbnail":
            problems.append(f"row {n}: no line, skipped")
            continue
        rows.append(r)
    return rows, problems


def script_of(rows):
    return " ".join(r["line"] for r in rows if r["line"] and r.get("shot") != "thumbnail")


def parse_rows(text):
    """'A = 1; +B = 2 !red' -> [{"label","value","colour","join"}] (label = left of '=', value = right)."""
    out = []
    for part in str(text or "").split(";"):
        p = part.strip()
        if not p:
            continue
        colour = None
        m = re.search(r"\s*!(\w+)\s*$", p)
        if m and m.group(1).lower() in COLOURS:
            colour, p = m.group(1).lower(), p[:m.start()].strip()
        join = p.startswith("+")
        p = p.lstrip("+").strip()
        label, eq, value = p.partition("=")
        out.append({"label": label.strip(), "value": value.strip(), "colour": colour, "join": join, "eq": bool(eq)})
    return out


def highlights(text):
    """'a *b c* d' -> ('a b c d', [(start, end)]) character spans of the starred words in the clean text."""
    clean, spans, pos = "", [], 0
    for m in re.finditer(r"\*([^*]+)\*", str(text or "")):
        clean += text[pos:m.start()]
        a = len(clean)
        clean += m.group(1)
        spans.append((a, len(clean)))
        pos = m.end()
    clean += str(text or "")[pos:]
    return clean, spans


def number_of(value):
    m = re.search(r"(\d[\d,]*\.?\d*)", str(value or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def name_bar(text):
    """'WILLIAM HARDAKER | candy stall owner' -> ('WILLIAM HARDAKER', 'candy stall owner')."""
    a, _, b = str(text or "").partition("|")
    return a.strip(), b.strip()


def from_plan(spec):
    """The planned rows back as a CSV with the director's shot picks written in (to tune by hand and Generate again)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLS)
    first = {}
    for sh in spec.get("shots", []):
        first.setdefault(sh.get("row"), sh.get("kind"))
    for k, r in enumerate(spec.get("rows", [])):
        r = dict(r)
        if not r.get("shot"):
            r["shot"] = first.get(k, "")
        w.writerow([r.get(c, "") for c in COLS])
    t = spec.get("thumbnail")
    if t:
        w.writerow(["", "thumbnail", "", " | ".join(t.get("lines", [])), "", "", "", t.get("visual", ""), "", "", "", "", "", ""])
    return buf.getvalue()
