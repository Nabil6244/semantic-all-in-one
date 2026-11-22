"""The Food Files director: spoken lines + word times -> timed shots, pictures to make, reveal times and sound cues.

Rhythm (reference study, docs/food_files/REFERENCE_AND_PLAN.md): a cut every ~4-5 s, host on screen ~35-40 %, every item
opens on a #N card, a year + place line gets a map, money / counts get a big number, "sued / settled / recalled" gets a
stamp, a long host line becomes host + punch-in (a jump cut), captions 2-4 words with one yellow keyword.
An empty cell is decided here; a filled cell always wins.
"""
import re

from prepper_host import director as PD
from . import csvplan, icons

key_of = PD.key_of
MAX_SHOT = {"host": 6.0, "split": 6.0, "pip": 6.0, "scene": 5.5, "photo": 6.5, "map": 7.0, "folder": 11.0, "headline": 8.0,
            "quote": 9.0, "tweet": 9.0, "big": 6.5, "flow": 10.0, "explain": 11.0, "timeline": 11.0, "number": 3.0,
            "next": 4.0, "title": 6.0, "page": 8.0, "clip": 7.0, "compare": 8.0, "evidence": 8.0, "symptoms": 8.0, "states": 8.0,
            "browser": 8.0, "scale": 7.0, "beforeafter": 8.0, "tally": 7.0, "scene2d": 7.0}
MIN_SHOT = 1.6
MOVES = ("push_in", "pan_right", "pull_out", "pan_left", "push_in_low", "drift")
TONES = {"number": "cream", "title": "red", "next": "dark", "map": "dark", "folder": "dark", "headline": "navy",
         "quote": "dark", "tweet": "navy", "big": "dark", "flow": "dark", "explain": "cream", "timeline": "cream", "page": "navy",
         "clip": "dark", "compare": "dark", "evidence": "dark", "symptoms": "dark", "states": "dark", "browser": "navy",
         "scale": "cream", "beforeafter": "dark", "tally": "dark"}
STOP = {"the", "a", "an", "of", "in", "on", "to", "and", "or", "it", "is", "was", "that", "this", "but", "so", "for", "with",
        "at", "by", "from", "as", "be", "are", "were", "they", "he", "she", "you", "we", "i", "its", "it's", "just", "then",
        "had", "has", "have", "their", "his", "her", "them", "there", "what", "which", "who", "if", "not", "do", "did"}
AUTO_STAMPS = (("settled", "SETTLED"), ("sued", "SUED"), ("recalled", "RECALLED"), ("recall", "RECALLED"),
               ("banned", "BANNED"), ("ban ", "BANNED"), ("pulled from", "PULLED"), ("shut down", "SHUT DOWN"),
               ("bankrupt", "BANKRUPT"), ("died", "FATAL"))
CASE_LABELS = ("filed by", "against", "outcome", "plaintiff", "defendant", "why", "claim", "verdict", "settled", "court")
PHOTO_LOOK = ("Photorealistic documentary photo, natural light, true-to-life textures, sharp focus, no text, no captions, "
              "no watermark")
SCENE_LOOK = ("Photorealistic cinematic photo, documentary style, natural light, shallow depth of field, no text, no captions, "
              "no logos, no watermark")


def _tok(w):
    return re.sub(r"[^a-z0-9$%]", "", str(w).lower())


def _when(words, w0, w1, text, t0, t1, frac):
    """When the first meaningful word of `text` is said inside the row; else a share of the shot."""
    want = [_tok(x) for x in str(text).split() if _tok(x) and _tok(x) not in STOP]
    for k in range(w0, min(w1, len(words))):
        if want and _tok(words[k]["word"]) in want[:2]:
            return max(t0, words[k]["start"] - 0.1)
    return t0 + (t1 - t0) * frac


def captions(words, w0, w1, a, b):
    """Word groups (2-4 words, cut at punctuation) said inside [a, b), each with its keyword index."""
    ws = [w for w in words[w0:w1] if w["start"] < b and w["end"] > a]
    groups, cur = [], []
    for w in ws:
        cur.append(w)
        end = re.search(r"[.,!?;:]$", w["word"])
        if len(cur) >= 4 or (end and len(cur) >= 2) or (end and w["word"].endswith((".", "?", "!"))):
            groups.append(cur)
            cur = []
    if cur:
        if groups and len(cur) == 1:
            groups[-1] += cur
        else:
            groups.append(cur)
    out = []
    for g in groups:
        text = " ".join(re.sub(r"[\"“”]", "", w["word"]) for w in g)
        toks = [_tok(w["word"]) for w in g]
        cand = [i for i, t in enumerate(toks) if t and t not in STOP]
        key = max(cand, key=lambda i: (any(c.isdigit() for c in toks[i]), len(toks[i]))) if cand else None
        out.append({"t0": round(max(a, g[0]["start"] - 0.05), 3), "t1": round(min(b, g[-1]["end"] + 0.25), 3), "text": text,
                    "key": key})
    for i in range(len(out) - 1):           # no gaps or overlaps between groups
        out[i]["t1"] = max(out[i]["t0"] + 0.2, min(out[i]["t1"], out[i + 1]["t0"]))
        if out[i + 1]["t0"] - out[i]["t1"] < 0.35:
            out[i]["t1"] = out[i + 1]["t0"]
    return out


def pick_shot(r, k, rows, history):
    if r["shot"]:
        return r["shot"]
    if r["item"]:
        return "number"
    if r.get("url"):
        return "page"
    items = csvplan.parse_rows(r["rows"])
    if r["place"]:
        return "map"
    if items:
        labels = " ".join(i["label"].lower() for i in items)
        if any(c in labels for c in CASE_LABELS):
            return "folder"
        if all(i["eq"] for i in items) and sum(1 for i in items if icons.key_of(i["label"])) >= max(1, len(items) - 1):
            return "explain"
        if len(items) <= 2 and any(csvplan.number_of(i["label"]) is not None or csvplan.number_of(i["value"]) is not None
                                   for i in items):
            return "big"
        if all(re.match(r"^\s*(\d{4}|[a-z]{3,9}\.? \d{4})", i["label"].lower()) for i in items):
            return "timeline"
        return "flow"
    nxt = rows[k + 1] if k + 1 < len(rows) else None
    if nxt and (nxt.get("item") or nxt.get("shot") == "number") and k > 2 and not r["visual"]:
        return "next"
    if r["visual"]:
        return "photo" if history.count("photo") <= history.count("scene") else "scene"
    return "host"


def narration_pic(r, pictures, host_meta=None):
    """A Flow picture of what row `r` says, a different angle from its main one (for the rest of a long line)."""
    from .host import shows_host
    prompt = _visual_prompt(dict(r, visual=(r.get("visual") or r["line"]) + ". A different angle, close-up detail"), "scene")
    host = shows_host(prompt, host_meta)
    k = key_of(f"{(host_meta or {}).get('name', '')}|{prompt}" if host else prompt)
    pictures.setdefault(k, {"prompt": prompt, "host": host})
    return k


def _visual_prompt(r, kind):
    v = r["visual"] or f"A real-life scene that shows: {r['line'].strip().rstrip('.')}"
    look = PHOTO_LOOK if kind == "photo" else SCENE_LOOK
    return f"{v}. {look}."


def direct(rows, words, duration, *, size=(1920, 1080), fps=30, host_meta=None, title="", brand="FOOD FILES"):
    from .host import shows_host
    rows = [r for r in rows if r.get("shot") != "thumbnail"]
    spans = PD.align(rows, words, duration)
    pictures, shots, sfx, history = {}, [], [], []
    hname = (host_meta or {}).get("name", "")
    last_stamp_t = -99.0
    photo_n = 0
    item_find = ""

    def pic_for(prompt):
        k = key_of(f"{hname}|{prompt}" if shows_host(prompt, host_meta) else prompt)
        pictures.setdefault(k, {"prompt": prompt, "host": shows_host(prompt, host_meta)})
        return k

    def real_pic(find, fallback, optional=False):
        """A Commons photo of the real thing first; Flow paints `fallback` only if Commons has nothing (optional = no Flow)."""
        k = key_of("real|" + find.strip().lower())
        pictures.setdefault(k, {"prompt": fallback, "find": find.strip(), "host": False, "optional": optional})
        return k

    move_i = 0
    for k, (r, sp) in enumerate(zip(rows, spans)):
        kind = pick_shot(r, k, rows, history)
        if kind == "thumbnail":
            continue
        if kind == "headline" and r.get("url"):
            kind = "page"                       # the real page beats a typed headline
        if kind == "number":
            item_find = r.get("find") or r["name"]
        t0, t1 = sp["t0"], sp["t1"]
        main_pic = pic_for(_visual_prompt(r, kind)) if kind in ("scene", "split", "pip") else None
        find = r.get("find") or ""
        if kind == "photo":
            find = find or ("" if r["visual"] else item_find)
            main_pic = (real_pic(find, _visual_prompt(dict(r, visual=r["visual"] or find), "photo")) if find
                        else pic_for(_visual_prompt(r, "photo")))
        if kind == "headline" and (r["visual"] or find):
            main_pic = real_pic(find, _visual_prompt(r, "photo")) if find else pic_for(_visual_prompt(r, "photo"))
        if kind == "clip":
            find = find or r["visual"] or item_find or r["line"]
            main_pic = real_pic(find, _visual_prompt(dict(r, visual=r["visual"] or find), "photo"))
        cap = MAX_SHOT.get(kind, 6.0)
        n = max(1, int(round((t1 - t0) / cap + 0.3))) if (t1 - t0) > cap * 1.15 else 1
        if kind in csvplan.CARD_SHOTS and n > 1:   # a card keeps the first `cap` seconds, the rest is the host
            bounds = [t0, min(t1, t0 + cap)] + ([t1] if t1 > t0 + cap else [])
        else:
            bounds = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
        for i in range(len(bounds) - 1):
            a, b = bounds[i], bounds[i + 1]
            # The rest of a long line shows what the words say (a Flow picture of it), not a still of the host: owner
            # 2026-11-23, "still image where it should be a video or Flow image of things that are in narration" (1:24).
            sk = kind if i == 0 else ("host" if kind == "host" else ("scene" if kind in csvplan.CARD_SHOTS else kind))
            shot = {"t0": round(a, 3), "t1": round(b, 3), "kind": sk, "row": k, "move": MOVES[move_i % len(MOVES)]}
            move_i += 1
            if sk == "host" and history and history[-1] == "host":
                shot["punch"] = True              # jump cut: the next host piece is framed tighter
            if sk in ("photo", "scene", "split", "pip"):
                pic = main_pic
                if i > 0 and sk in ("scene", "photo"):
                    pic = pic_for(_visual_prompt(dict(r, visual=(r["visual"] or r["line"]) + ". A different angle, close-up detail"), sk))
                shot["pic"] = pic
                if sk == "photo":
                    photo_n += 1
                    shot["tilt"] = -2.0 if photo_n % 2 else 2.0
            if i == 0:
                card = _card(sk, r, words, sp, a, b, pictures)
                if card is not None:
                    shot["card"] = card
                    if sk in ("headline", "page", "clip"):
                        shot["pic"] = main_pic
                    if sk == "number" and item_find:
                        card["pic"] = real_pic(item_find, f"Studio product photo of {item_find} on a plain white background, "
                                                          f"sharp focus, no people, no text", optional=True)
                    if sk == "next":         # the "?" sits over a silhouette of the next item's food
                        nxt = next((x for x in rows[k + 1:] if x.get("item") or x.get("shot") == "number"), None)
                        if nxt:
                            card["icon"] = icons.key_of(f"{nxt.get('find', '')} {nxt.get('name', '')}") or ""
                    if sk == "scene2d":            # the flat place: made once by Flow, kept for every video
                        from . import scene2d as S2
                        pk = S2.place_key(card["place"])
                        pictures.setdefault(pk, {"prompt": S2.place_prompt(card["place"]), "host": False, "place2d": card["place"]})
                        card["pic"] = pk
                    if sk == "quote" and find:      # the speaker's real portrait; never a painted stand-in of a real person
                        shot["pic"] = real_pic(find, "", optional=True)
                    if sk == "scale" and find:
                        card["pic"] = real_pic(find, _visual_prompt(dict(r, visual=r["visual"] or find), "photo"))
                    if sk == "beforeafter":
                        finds = [x.strip() for x in find.split("|") if x.strip()]
                        vis = [x.strip() for x in (r["visual"] or "").split("|")]
                        card["pics"] = [real_pic(fd, _visual_prompt(dict(r, visual=vis[j] if j < len(vis) and vis[j] else fd), "photo"),
                                                 optional=not (j < len(vis) and vis[j])) for j, fd in enumerate(finds[:2])]
                    if sk == "page":
                        pk = key_of("page|" + r["url"].strip())
                        pictures.setdefault(pk, {"page": r["url"].strip(), "host": False})
                        shot["page"] = pk
                    if sk == "clip":
                        ck = key_of(f"clip|{find}|{r['line']}")
                        pictures.setdefault(ck, {"clip": find, "words": r["line"], "host": False})
                        shot["clip"] = ck
            if sk in csvplan.CARD_SHOTS or sk in ("photo", "scene"):
                shot["tone"] = TONES.get(sk, "dark")
                if sk in ("explain", "flow", "big") and sum(1 for h in history if h == sk) % 2:
                    shot["tone"] = "dark" if TONES.get(sk) == "cream" else "cream"
            if sk in ("host", "split", "scene", "pip"):
                shot["caps"] = captions(words, sp["w0"], sp["w1"], a, b)
            if i == 0 and sk == "host" and r["title"]:
                shot["banner"] = {"text": r["title"], "at": round(a + 0.15, 3)}
            if i == 0:
                if r["note"] and sk not in ("tweet",):
                    shot["note"] = {"text": r["note"], "at": round(_when(words, sp["w0"], sp["w1"], r["note"], a, b, 0.3), 3),
                                    "red": "!" in r["note"] or r["note"].startswith("...")}
                if r["name"] and sk in ("host", "split", "scene", "photo"):
                    nm, role = csvplan.name_bar(r["name"])
                    shot["person"] = {"name": nm, "role": role, "at": round(a + 0.3, 3)}
                stamp = r["stamp"]
                if not stamp and sk in ("host", "split", "photo") and a - last_stamp_t > 20:
                    low = f" {r['line'].lower()} "
                    stamp = next((s for w, s in AUTO_STAMPS if w in low), "")
                if stamp:
                    if sk in ("folder",):
                        at = (max((it["at"] for it in shot.get("card", {}).get("items", [])), default=a) + 0.8)
                    else:
                        at = _when(words, sp["w0"], sp["w1"], stamp, a, b, 0.55)
                    at = min(at, b - 0.6)
                    shot["stamp"] = {"text": stamp.strip(), "at": round(max(a + 0.2, at), 3)}
                    if sk == "folder":
                        shot["stamp"]["xy"] = (size[0] * 0.66, size[1] * 0.72)
                    sfx.append({"t": shot["stamp"]["at"], "name": "stamp"})
                    last_stamp_t = a
                if r["source"]:
                    shot["source"] = r["source"]
            # sound cues
            if sk == "number":
                sfx.append({"t": a, "name": "whoosh"})
                sfx.append({"t": a + 0.2, "name": "number"})
            elif sk in ("next", "title"):
                sfx.append({"t": a, "name": "sting"})
            elif sk in csvplan.CARD_SHOTS or sk == "photo":
                sfx.append({"t": a, "name": "whoosh"})
                for it in shot.get("card", {}).get("items", []):
                    sfx.append({"t": it["at"], "name": "tick" if sk in ("folder", "timeline", "flow") else "pop"})
            shots.append(shot)
            history.append(sk)
    # merge slivers into the shot before (no flicker); cards keep their own time
    merged = []
    for s in shots:
        # A host line with a paid Flow clip keeps its own shot however short (Deadliest Drinks: 6 of 15 clips, the short
        # punch lines like "It builds up.", were merged into the card before and never shown).
        paid = s["kind"] in ("host", "split", "pip") and s.get("row") is not None and s["row"] < len(rows) \
            and rows[s["row"]].get("say")
        if merged and (s["t1"] - s["t0"]) < MIN_SHOT and s["kind"] not in csvplan.CARD_SHOTS and not paid:
            merged[-1]["t1"] = s["t1"]
            if "caps" in merged[-1] and "caps" in s:
                merged[-1]["caps"] += s["caps"]
        else:
            merged.append(s)
    if merged:
        merged[0]["t0"] = 0.0
    return {"size": list(size), "fps": fps, "duration": round(duration, 3), "title": title, "brand": brand, "shots": merged,
            "sfx": sorted(sfx, key=lambda e: e["t"]), "pictures": pictures, "rows": rows, "chapters": []}


def _items(r, words, sp, a, b, spread=0.75):
    items = csvplan.parse_rows(r["rows"])
    for j, it in enumerate(items):
        frac = 0.06 + spread * j / max(1, len(items))
        it["at"] = round(_when(words, sp["w0"], sp["w1"], it["value"] or it["label"], a, b, frac), 3)
    # Word-timed items could land at the end of their shot (Deadliest Drinks: "8,000" at 88 % of a 6.5 s card, empty
    # until then; 14 cards had their first item past 40 %). The first item is up within 0.35 s, the rest by 60 % of it.
    n = len(items)
    for j, it in enumerate(items):
        latest = a + 0.35 + (b - a) * 0.6 * j / max(1, n - 1) if j else a + 0.35
        it["at"] = round(min(it["at"], latest), 3)
    for j in range(1, n):
        items[j]["at"] = max(items[j]["at"], items[j - 1]["at"] + 0.45)
    for it in items:
        it["at"] = min(it["at"], max(a, b - 0.8))
    return items


def _card(kind, r, words, sp, a, b, pictures):
    title = r["title"]
    if kind == "title":
        lines = [x.strip() for x in (title or r["line"]).split("|") if x.strip()]
        return {"lines": lines[:3]}
    if kind == "number":
        return {"num": r["item"] or "?", "sub": title, "name": r["name"] or r["line"][:40], "year": r["year"]}
    if kind == "next":
        return {"text": title}
    if kind == "photo":
        return {"caption": r["rows"] or title, "header": ""}
    if kind == "map":
        place = r["place"]
        city = place.split(",")[0].strip() if "," in place else ""
        head = " · ".join(x for x in (r["year"], place) if x)
        return {"place": place, "city": city, "header": title or head, "label": r["rows"]}
    if kind == "folder":
        return {"tab": title or "THE CASE", "items": _items(r, words, sp, a, b, 0.6)}
    if kind == "clip":
        return {"strap": title}
    if kind in ("headline", "page"):
        outlet, _, date = (title or "").replace("|", "·").partition("·")
        text, spans = csvplan.highlights(r["rows"] or r["line"])
        return {"outlet": outlet.strip(), "date": (date.strip() or r["year"]), "text": text, "spans": spans}
    if kind == "quote":
        text, spans = csvplan.highlights(r["rows"] or r["line"])
        return {"text": text, "spans": spans, "who": title or r["name"]}
    if kind in ("compare", "evidence"):
        items = _items(r, words, sp, a, b, 0.5)
        for it in items:
            it["icon"] = icons.key_of(it["value"]) or icons.key_of(it["label"]) or ""
        return {"items": items[:3 if kind == "evidence" else 2], "header": title}
    if kind == "symptoms":
        return {"items": _items(r, words, sp, a, b, 0.7), "who": icons.key_of(r["name"]) or "kid", "header": title}
    if kind == "states":
        places = [x.strip() for x in r["place"].split(";") if x.strip()]
        labels = [it["label"] for it in csvplan.parse_rows(r["rows"])]
        n = max(1, len(places))
        return {"places": [{"place": p, "label": labels[j] if j < len(labels) else "",
                            "at": round(a + 0.5 + (b - a - 1.5) * j / n, 3)} for j, p in enumerate(places)],
                "header": title or r["year"]}
    if kind == "browser":
        text, spans = csvplan.highlights(r["rows"] or r["line"])
        return {"site": title, "heading": r["name"], "text": text, "spans": spans}
    if kind == "scale":
        return {"text": r["rows"] or title, "icon": icons.key_of(r["name"] or r["find"]) or "box", "header": title if r["rows"] else ""}
    if kind == "beforeafter":
        labels = [it["label"] for it in csvplan.parse_rows(r["rows"])] or ["BEFORE", "AFTER"]
        return {"labels": (labels + ["", ""])[:2], "wipe_at": round(a + (b - a) * 0.45, 3), "header": title}
    if kind == "scene2d":
        from . import scene2d as S2
        sc = S2.parse(r["rows"])
        sc["place"] = S2.norm_place(r["place"] or title)
        n = max(1, len(sc["actors"]))
        for j, ac in enumerate(sc["actors"]):
            ac["at"] = round(a + 0.1 + min(0.5, (b - a) * 0.25) * j / n, 3)
        if not sc["actors"]:
            sc["actors"] = [{"who": "man", "action": "stand", "prop": None, "at": round(a + 0.1, 3)}]
        return sc
    if kind == "tally":
        it = (csvplan.parse_rows(r["rows"]) or [{"label": "kid x 3", "value": ""}])[0]
        m = re.match(r"\s*(.+?)\s*[x×*]\s*(\d+)\s*$", it["label"])
        name, count = (m.group(1), int(m.group(2))) if m else (it["label"], 3)
        count = max(1, min(count, 12))
        return {"icon": icons.key_of(name) or "man", "count": count, "label": it["value"], "header": title,
                "ats": [round(a + 0.3 + (b - a - 1.4) * j / count, 3) for j in range(count)]}
    if kind == "tweet":
        text, spans = csvplan.highlights(r["rows"] or r["line"])
        extra = None
        if r["note"]:
            m = re.match(r"\s*([\d,.]+\+?)\s*(.*)", r["note"])
            extra = {"value": m.group(1), "num": csvplan.number_of(m.group(1)), "label": m.group(2)} if m else None
        return {"text": text, "spans": spans, "name": r["name"] or "user", "handle": title or "@user", "date": r["year"],
                "extra": extra}
    if kind in ("big", "flow", "timeline"):
        return {"items": _items(r, words, sp, a, b), "header": title}
    if kind == "explain":
        items = _items(r, words, sp, a, b, 0.8)
        for it in items:
            it["icon"] = it["label"]
            it["label_text"] = it["value"]
            if not icons.key_of(it["label"]):
                prompt = icons.sticker_prompt(it["label"])
                k = key_of(prompt)
                pictures.setdefault(k, {"prompt": prompt, "host": False, "sticker": it["label"]})
                it["pic"] = k
        return {"items": items, "header": title}
    return None
