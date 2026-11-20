"""The Prepper Host CSV: one row per spoken line (the lines, in order, ARE the narration).

Columns (only `line` is required; empty cells = the director decides):
  line      the words spoken over this shot
  shot      host | split | pip | broll | product | compare | data | checklist | bars | big | chapter | thumbnail
  visual    the Flow picture prompt for split / pip / broll (write {host} where the host is in the picture)
  product   product name(s) for product / compare cards, "Rice | Beans | Oats"
  title     the chip title on a card ("THE WATER MATH"); for a thumbnail row, its 2 lines "90 DAYS | NO POWER"
  rows      card rows, ";" between rows:
              data:      "4 PEOPLE x 90 DAYS = 1 GAL/DAY; WATER YOU NEED = 360 GAL !red"
              checklist: "PORCH; OPEN GARAGE; ~THE ATTIC; -BACKYARD"   (~ struck out, - no tick)
              bars:      "CASES = 100 GAL; JUGS = 35 GAL; WATER HEATER = 50 GAL"
              big:       "360 GAL = WATER YOU NEED"
              compare:   labels under the cards, "RICE; BEANS; OATS"
            colours: !red !green !yellow !white at the end of a row
  chapter   optional bumper shown as this line starts ("ITEM 1 · WATER")
A thumbnail row has no line: shot=thumbnail, title = 2 lines of text, visual = the picture prompt, product = what he holds.
"""
import csv
import io
import re
from pathlib import Path

SHOTS = ("host", "split", "pip", "broll", "product", "compare", "data", "checklist", "bars", "big", "chapter", "thumbnail")
CARD_SHOTS = ("product", "compare", "data", "checklist", "bars", "big")
COLS = ("line", "shot", "visual", "product", "title", "rows", "chapter")
ALIASES = {"text": "line", "narration": "line", "sentence": "line", "voice": "line", "type": "shot", "layout": "shot",
           "prompt": "visual", "image": "visual", "picture": "visual", "products": "product", "items": "rows", "card": "rows"}
COLOURS = ("red", "green", "yellow", "white")


def _norm(h):
    h = re.sub(r"[^a-z_]", "", str(h or "").strip().lower())
    return ALIASES.get(h, h)


def read(path_or_text):
    """-> (rows, problems). rows: list of dicts with COLS keys (+ 'n' = CSV row number). Thumbnail rows are kept apart."""
    s = str(path_or_text)
    text = Path(s).read_text(encoding="utf-8-sig") if "\n" not in s and Path(s).is_file() else s
    rd = csv.reader(io.StringIO(text))
    rows, problems, head = [], [], None
    for n, cells in enumerate(rd, 1):
        if not any(c.strip() for c in cells):
            continue
        if head is None:
            head = [_norm(c) for c in cells]
            if "line" not in head:
                raise ValueError("the Prepper Host CSV needs a 'line' column (the spoken words)")
            continue
        r = {k: "" for k in COLS}
        for k, v in zip(head, cells):
            if k in COLS:
                r[k] = v.strip()
        r["n"] = n
        r["shot"] = r["shot"].lower().replace(" ", "")
        if r["shot"] and r["shot"] not in SHOTS:
            problems.append(f"row {n}: unknown shot '{r['shot']}' (the director picks one)")
            r["shot"] = ""
        if not r["line"] and r["shot"] != "thumbnail":
            problems.append(f"row {n}: no line, skipped")
            continue
        rows.append(r)
    return rows, problems


def script_of(rows):
    return " ".join(r["line"] for r in rows if r["line"])


def parse_rows(text):
    """'A = 1; ~B; -C !red' -> [{"label","value","colour","strike","tick"}]."""
    out = []
    for part in str(text or "").split(";"):
        p = part.strip()
        if not p:
            continue
        colour = None
        m = re.search(r"\s*!(\w+)\s*$", p)
        if m and m.group(1).lower() in COLOURS:
            colour, p = m.group(1).lower(), p[:m.start()].strip()
        strike = p.startswith("~")
        tick = not p.startswith("-") and not strike
        p = p.lstrip("~-+✓ ").strip()
        label, _, value = p.partition("=")
        out.append({"label": label.strip(), "value": value.strip(), "colour": colour, "strike": strike, "tick": tick})
    return out


def number_of(value):
    """'~4,000 CAL' -> 4000.0, '$1,600' -> 1600.0, none -> None."""
    m = re.search(r"(\d[\d,]*\.?\d*)", str(value or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def products_of(text):
    return [p.strip() for p in str(text or "").split("|") if p.strip()]


def from_plan(spec):
    """The planned shots back as a CSV (to tune by hand and Generate again)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLS)
    first = {}
    for sh in spec.get("shots", []):
        first.setdefault(sh.get("row"), sh.get("kind"))
    for k, r in enumerate(spec.get("rows", [])):
        r = dict(r)
        if not r.get("shot"):
            r["shot"] = first.get(k, "")   # the director's pick, written down so it can be tuned by hand
        w.writerow([r.get(c, "") for c in COLS])
    if spec.get("thumbnail"):
        t = spec["thumbnail"]
        w.writerow(["", "thumbnail", t.get("visual", ""), t.get("product", ""), t.get("title", ""), "", ""])
    return buf.getvalue()
