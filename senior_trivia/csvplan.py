"""The Senior Trivia CSV: one row per moment of the show, in order.

Columns (header names are forgiving; empty cells = the director decides):
  type          intro | round | question | item | check | host | bonus | outro | thumbnail
  round         round title, on `round` rows ("Around the House"); the difficulty word goes after a bar: "Around the House | easy"
  question      the question text (question / bonus rows)
  options       "Percolator | Toaster | Kettle | Blender"  (2-4 options; empty = a no-options question, answer only)
  answer        the right option: a letter (B), a number (2) or the option text; on `item` rows the item's name
  fact          one short fun fact said after the answer ("Did you know…")
  picture       Flow picture prompt shown with the question (item rows: the object photo)
  fact_picture  Flow picture prompt shown with the answer and fact (optional)
  line          what is said on intro / round / check / outro / host rows (host rows: the host says it in his clip)
  seconds       countdown seconds (default 6 for questions, 7 for items)
A thumbnail row: question = 2 short lines "BORN BEFORE | 1955?", picture = the thumbnail picture prompt.
"""
import csv
import io
import re
from pathlib import Path

TYPES = ("intro", "round", "question", "item", "check", "host", "bonus", "outro", "thumbnail")
COLS = ("type", "round", "question", "options", "answer", "fact", "picture", "fact_picture", "line", "seconds")
ALIASES = {"kind": "type", "shot": "type", "q": "question", "choices": "options", "correct": "answer", "funfact": "fact",
           "fun_fact": "fact", "didyouknow": "fact", "image": "picture", "prompt": "picture", "visual": "picture",
           "factpicture": "fact_picture", "answer_picture": "fact_picture", "say": "line", "narration": "line", "text": "line",
           "timer": "seconds", "time": "seconds", "round_title": "round"}
LETTERS = "ABCD"
HOST_MIN, HOST_MAX = 5, 6


def _norm(h):
    h = re.sub(r"[^a-z_]", "", str(h or "").strip().lower())
    return ALIASES.get(h, ALIASES.get(h.replace("_", ""), h))


def options_of(row):
    return [o.strip() for o in str(row.get("options") or "").split("|") if o.strip()][:4]


def answer_index(row):
    """-> index into options_of(row), or None when the answer does not match an option."""
    opts = options_of(row)
    a = str(row.get("answer") or "").strip()
    if not opts or not a:
        return None
    m = re.fullmatch(r"\(?([A-Da-d])[).:]?", a)
    if m and LETTERS.index(m.group(1).upper()) < len(opts):
        return LETTERS.index(m.group(1).upper())
    if a.isdigit() and 1 <= int(a) <= len(opts):
        return int(a) - 1
    low = [o.lower() for o in opts]
    a2 = re.sub(r"^[A-Da-d][).:]\s*", "", a).lower()
    return low.index(a2) if a2 in low else None


def answer_text(row):
    i = answer_index(row)
    return options_of(row)[i] if i is not None else str(row.get("answer") or "").strip()


def read(path_or_text):
    """-> (rows, problems). rows: dicts with COLS keys + 'n' (the CSV line number)."""
    s = str(path_or_text)
    text = Path(s).read_text(encoding="utf-8-sig") if "\n" not in s and Path(s).is_file() else s
    rdr = csv.reader(io.StringIO(text.strip()))
    rows, problems = [], []
    try:
        head = [_norm(h) for h in next(rdr)]
    except StopIteration:
        return [], ["the CSV is empty"]
    if "type" not in head:
        return [], ["the CSV needs a `type` column (intro, round, question, item, check, host, bonus, outro)"]
    for n, cells in enumerate(rdr, start=2):
        if not any(c.strip() for c in cells):
            continue
        r = {c: "" for c in COLS}
        for h, v in zip(head, cells):
            if h in r:
                r[h] = v.strip()
        r["type"] = r["type"].lower()
        r["n"] = n
        if r["type"] not in TYPES:
            problems.append(f"row {n}: unknown type '{r['type']}' (use {', '.join(TYPES)})")
            continue
        rows.append(r)
    return rows, problems + check(rows)


def check(rows):
    """Plan-level problems: missing answers, answers not among the options, duplicates, thin rounds, host count."""
    out, seen = [], {}
    asked = [r for r in rows if r["type"] in ("question", "bonus", "item")]
    if not asked:
        out.append("no questions: add rows with type question (or item)")
    for r in asked:
        n = r["n"]
        if r["type"] == "item":
            if not r["picture"]:
                out.append(f"row {n}: an item needs a picture prompt")
            if not r["answer"]:
                out.append(f"row {n}: an item needs its name in `answer`")
        else:
            if not r["question"]:
                out.append(f"row {n}: no question text")
            opts = options_of(r)
            if not r["answer"]:
                out.append(f"row {n}: no answer")
            elif opts and answer_index(r) is None:
                out.append(f"row {n}: the answer '{r['answer']}' is not one of the options")
            if len(opts) == 1:
                out.append(f"row {n}: only one option")
            if len({o.lower() for o in opts}) < len(opts):
                out.append(f"row {n}: two options are the same")
        key = re.sub(r"\W+", " ", (r["question"] or r["answer"]).lower()).strip()
        if key in seen:
            out.append(f"row {n}: same question as row {seen[key]}")
        seen.setdefault(key, n)
        if r["seconds"] and not re.fullmatch(r"\d+(\.\d+)?", r["seconds"]):
            out.append(f"row {n}: seconds must be a number")
    count = 0
    for r in rows + [{"type": "round", "n": 0}]:
        if r["type"] == "round":
            if count and count < 3:
                out.append(f"a round before row {r['n'] or 'the end'} has only {count} question(s)")
            count = 0
        elif r["type"] in ("question", "item"):
            count += 1
    hosts = sum(1 for r in rows if r["type"] == "host")
    if len(asked) >= 25 and not HOST_MIN <= hosts <= HOST_MAX:   # a full show; short tests may use fewer
        out.append(f"{hosts} host rows: the show uses {HOST_MIN}-{HOST_MAX} host clips")
    for r in rows:
        if r["type"] in ("host", "check") and not r["line"]:
            out.append(f"row {r['n']}: a {r['type']} row needs its `line`")
    return out


def mode_of(rows):
    """'items' when the show is an old-items picture quiz (silent between intro and outro), else 'rounds'."""
    q = sum(1 for r in rows if r["type"] == "question")
    i = sum(1 for r in rows if r["type"] == "item")
    return "items" if i > q else "rounds"
