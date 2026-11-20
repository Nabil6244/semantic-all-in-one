"""The director: spoken lines + word times -> timed shots, pictures to make, card reveal times and sound cues.

Rhythm (from the reference study): a new shot every ~3-6 s, hard cuts, the host on screen at least every 3 shots, every
number a card, every named product a photo card, a chapter bumper when the list moves on.
"""
import hashlib
import re

from . import csvplan
from .host import shows_host

MAX_SHOT = {"host": 7.0, "split": 6.5, "pip": 6.5, "broll": 6.0, "product": 7.0, "compare": 8.0, "data": 9.0,
            "checklist": 10.0, "bars": 9.0, "big": 7.0}
MIN_SHOT = 2.2
MOVES = ("push_in", "pan_right", "pull_out", "pan_left", "push_in_low", "drift")
HOSTY = ("host", "split", "pip")
CYCLE = ("split", "broll", "pip", "broll", "broll", "split", "pip", "broll")
STOP = {"the", "a", "an", "of", "in", "on", "to", "and", "or", "x", "your", "you", "for", "per", "it"}
LOOK = ("Photorealistic photo, natural light, shallow depth of field, true-to-life textures, documentary style, "
        "no text, no captions, no logos, no watermark")


def key_of(prompt):
    return hashlib.sha1(str(prompt).encode()).hexdigest()[:12]


def _tok(w):
    return re.sub(r"[^a-z0-9$]", "", str(w).lower())


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def align(rows, words, duration):
    """Each row's [t0, t1) and its word slice, by walking the spoken words in order (the CSV lines are the voice)."""
    toks = [_tok(w["word"]) for w in words]
    i = 0
    spans = []
    for r in rows:
        n = len([t for t in (_tok(x) for x in r["line"].split()) if t])
        j = min(len(words), i + n)
        # tolerate small drift: look a few words ahead for the row's first word
        first = next((_tok(x) for x in r["line"].split() if _tok(x)), "")
        for k in range(i, min(len(words), i + 4)):
            if toks[k] == first:
                i, j = k, min(len(words), k + n)
                break
        spans.append((i, j))
        i = j
    starts = [0.0 if k == 0 else (words[a]["start"] if a < len(words) else duration) for k, (a, _b) in enumerate(spans)]
    out = []
    for k, (a, b) in enumerate(spans):
        t0 = starts[k]
        t1 = starts[k + 1] if k + 1 < len(starts) else duration
        out.append({"t0": t0, "t1": max(t1, t0 + 0.5), "w0": a, "w1": b})
    return out


def auto_visual(line):
    """A picture prompt for a line with no visual: first-person lines put the host in it."""
    l = line.strip().rstrip(".")
    first_person = re.search(r"\b(i|i'd|i'm|i've|my|me)\b", l.lower())
    who = "{host} " if first_person else ""
    return f"{who}A real-life scene that shows: {l}. American home, garage, store or ranch setting"


def pick_shot(r, history, k):
    if r["shot"]:
        return r["shot"]
    if r["product"]:
        return "compare" if len(csvplan.products_of(r["product"])) > 1 else "product"
    if r["rows"]:
        items = csvplan.parse_rows(r["rows"])
        if len(items) == 1 and items[0]["value"]:
            return "big"
        return "data" if any(it["value"] for it in items) else "checklist"
    if k < 2:
        return "host"
    if not any(s in HOSTY for s in history[-3:]):
        return "split" if len(history) % 2 else "pip"
    s = CYCLE[k % len(CYCLE)]
    if history and s == history[-1] and s != "broll":
        s = "broll"
    return s


def _word_time(words, w0, w1, label, t0, t1, frac):
    """When the first word of `label` is said inside the row; else a share of the shot."""
    want = [_tok(x) for x in str(label).split() if _tok(x) and _tok(x) not in STOP]
    want.sort(key=len, reverse=True)
    for k in range(w0, w1):
        if want and _tok(words[k]["word"]) == want[0]:
            return max(t0, words[k]["start"] - 0.15)
    return t0 + (t1 - t0) * frac


def direct(rows, words, duration, *, size=(1920, 1080), fps=30, host_meta=None, title=""):
    rows = [r for r in rows if r.get("shot") != "thumbnail"]
    spans = align(rows, words, duration)
    pictures = {}                    # key -> {"prompt", "host"}
    shots, sfx, chapters, history = [], [], [], []
    last_pic = None

    hname = (host_meta or {}).get("name", "")

    def pic_for(prompt):
        full = f"{prompt}. {LOOK}."
        k = key_of(f"{hname}|{full}")
        pictures.setdefault(k, {"prompt": full, "host": shows_host(prompt)})
        return k

    def product_pic(name):
        prompt = (f"Studio product photo of {name}, the whole product centred on a pure white background, soft shadow, sharp focus, "
                  f"catalogue packshot, no people")
        k = key_of(prompt)
        pictures.setdefault(k, {"prompt": prompt, "host": False, "product": name})
        return k

    move_i = 0
    for k, (r, sp) in enumerate(zip(rows, spans)):
        kind = pick_shot(r, history, k)
        if kind == "chapter":            # a chapter row: bumper over a b-roll of its line
            chapters.append({"t": sp["t0"], "text": r["title"] or r["line"][:40]})
            kind = "broll"
        if r.get("chapter"):
            chapters.append({"t": sp["t0"], "text": r["chapter"]})
        if kind in csvplan.CARD_SHOTS and not (r["rows"] or r["product"]):
            kind = "broll"
        visual = r["visual"] or (auto_visual(r["line"]) if kind in ("split", "pip", "broll") or kind in csvplan.CARD_SHOTS else "")
        main = pic_for(visual) if visual else None
        t0, t1 = sp["t0"], sp["t1"]
        # pieces: a long row becomes 2-3 shots (cards keep the first piece; the rest is b-roll / pip of the same scene)
        cap = MAX_SHOT.get(kind, 6.5)
        n = max(1, int(round((t1 - t0) / cap + 0.35))) if (t1 - t0) > cap else 1
        bounds = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
        for i in range(n):
            a, b = bounds[i], bounds[i + 1]
            sk = kind if i == 0 else ("pip" if kind in ("broll", "host") and i % 2 else ("broll" if kind != "broll" else "split"))
            if sk in ("split", "pip", "broll") and main is None:
                main = pic_for(auto_visual(r["line"]))
            pic = main
            if i > 0 and sk in ("split", "pip", "broll") and visual:
                pic = pic_for(f"{visual}. A different camera angle: {'close-up detail' if i % 2 else 'wide shot'}")
            shot = {"t0": round(a, 3), "t1": round(b, 3), "kind": sk, "row": k, "pic": pic, "move": MOVES[move_i % len(MOVES)]}
            move_i += 1
            if sk in csvplan.CARD_SHOTS:
                shot["bg"] = pic or last_pic
                card = {"title": r["title"].upper(), "items": [], "products": []}
                if sk in ("product", "compare"):
                    for nm in csvplan.products_of(r["product"])[:3]:
                        card["products"].append({"name": nm, "pic": product_pic(nm)})
                    labels = csvplan.parse_rows(r["rows"])
                    for j, p in enumerate(card["products"]):
                        p["label"] = (labels[j]["label"] if j < len(labels) else (p["name"] if sk == "compare" else "")).upper()
                        p["at"] = round(_word_time(words, sp["w0"], sp["w1"], p["name"], a, b, 0.05 + 0.25 * j), 3)
                else:
                    items = csvplan.parse_rows(r["rows"])
                    for j, it in enumerate(items):
                        frac = 0.08 + 0.7 * j / max(1, len(items))
                        it["at"] = round(_word_time(words, sp["w0"], sp["w1"], it["label"] or it["value"], a, b, frac), 3)
                        it["label"], it["value"] = it["label"].upper(), it["value"].upper()
                        it["num"] = csvplan.number_of(it["value"])
                    # reveals never run backwards
                    for j in range(1, len(items)):
                        items[j]["at"] = max(items[j]["at"], items[j - 1]["at"] + 0.35)
                    card["items"] = items
                shot["card"] = card
                sfx.append({"t": a, "name": "whoosh"})
                for it in card["items"] + card["products"]:
                    sfx.append({"t": it["at"], "name": "tick" if sk in ("checklist", "data", "bars") else "pop"})
            shots.append(shot)
            history.append(sk)
            if pic and sk in ("split", "pip", "broll"):
                last_pic = pic
    # merge shots shorter than MIN_SHOT into the one before (no flicker)
    merged = []
    for s in shots:
        if merged and (s["t1"] - s["t0"]) < MIN_SHOT and s["kind"] not in csvplan.CARD_SHOTS:
            merged[-1]["t1"] = s["t1"]
        else:
            merged.append(s)
    for c in chapters:
        sfx.append({"t": c["t"], "name": "chapter"})
    # the first card background may still be empty: borrow the next picture
    pics_in_order = [s["pic"] for s in merged if s.get("pic")]
    for s in merged:
        if "bg" in s and not s["bg"]:
            s["bg"] = pics_in_order[0] if pics_in_order else None
    return {"size": list(size), "fps": fps, "duration": round(duration, 3), "title": title, "shots": merged, "chapters": chapters,
            "sfx": sorted(sfx, key=lambda e: e["t"]), "pictures": pictures, "rows": rows}
