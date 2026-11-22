"""Plan checker, run on Generate before anything renders: repairs what it can, reports the rest.

Rules (from the reference formula):
  hook      a title card in the first 30 s
  items     every #N item has a case (year / place / name / map), a number, and a fallout (lawsuit, recall, ban, death...)
  still     no card lasts longer than its builds can carry (last reveal + 3 s); longer -> the tail becomes the host
  host      the host is on screen 25-55 % of the time
  pace      median shot 2.5-6.5 s
  source    photo / headline / quote / tweet cards carry a source line
"""
import re
import statistics

from . import csvplan

FALLOUT = ("sued", "lawsuit", "settled", "recall", "banned", "ban", "fine", "fined", "law", "act", "died", "death", "dead",
           "hospital", "warning", "warned", "cease", "court", "shut down", "bankrupt", "pulled", "closed", "jail", "prison")


def _last_reveal(s):
    c = s.get("card") or {}
    ats = [it.get("at", s["t0"]) for it in c.get("items", [])]
    if s.get("stamp"):
        ats.append(s["stamp"]["at"])
    return max(ats) if ats else s["t0"] + 1.2


def check(spec, repair=True):
    """-> {"ok": bool, "problems": [...], "repaired": [...], "stats": {...}} (repairs edit spec in place)."""
    shots, rows = spec["shots"], spec.get("rows", [])
    problems, repaired = [], []
    # still: a card shot that runs long after its last reveal hands the tail to the host
    out = []
    for s in shots:
        if repair and s["kind"] in csvplan.CARD_SHOTS and s["kind"] not in ("title", "number", "next"):
            end = _last_reveal(s) + 3.0
            if s["t1"] - end > 1.8:
                # the tail shows what the words say (a Flow picture), not a still of the host (owner, 2026-11-23)
                from . import director
                r = rows[s["row"]] if s.get("row") is not None and s["row"] < len(rows) else None
                if r is not None:
                    pic = director.narration_pic(r, spec.setdefault("pictures", {}), spec.get("host_meta"))
                    tail = {"t0": round(end, 3), "t1": s["t1"], "kind": "scene", "row": s["row"], "move": "push_in",
                            "pic": pic, "caps": []}
                else:
                    tail = {"t0": round(end, 3), "t1": s["t1"], "kind": "host", "row": s["row"], "move": "drift",
                            "punch": True, "caps": []}
                s["t1"] = round(end, 3)
                out += [s, tail]
                repaired.append(f"{s['kind']} card at {s['t0']:.1f}s ran long; a {tail['kind']} takes the last {tail['t1'] - end:.1f}s")
                continue
        out.append(s)
    shots[:] = out
    # hook
    if not any(s["kind"] == "title" and s["t0"] < 30 for s in shots):
        problems.append("no title card in the first 30 s (add a row with shot=title after the cold-open teasers)")
    # items
    item_starts = [i for i, s in enumerate(shots) if s["kind"] == "number"]
    for j, i0 in enumerate(item_starts):
        i1 = item_starts[j + 1] if j + 1 < len(item_starts) else len(shots)
        seg = shots[i0:i1]
        rws = sorted({s["row"] for s in seg})
        text = " ".join(f"{rows[k]['line']} {rows[k].get('rows', '')} {rows[k].get('stamp', '')}".lower()
                        for k in rws if k < len(rows))
        label = f"item #{(seg[0].get('card') or {}).get('num', j + 1)}"
        has_case = any(s["kind"] in ("map", "folder", "headline") or s.get("person") for s in seg) or bool(
            re.search(r"\b(1[89]\d\d|20\d\d)\b", text))
        has_num = any(s["kind"] in ("big",) for s in seg) or bool(re.search(r"\d", text))
        has_fallout = any(w in text for w in FALLOUT) or any(s.get("stamp") for s in seg)
        for ok, what in ((has_case, "a real case (year, place or person)"), (has_num, "a number"),
                         (has_fallout, "a fallout (lawsuit, recall, ban, law, injury)")):
            if not ok:
                problems.append(f"{label} is missing {what}")
    # host share and pace
    total = max(0.1, spec["duration"])
    host_t = sum(s["t1"] - s["t0"] for s in shots if s["kind"] in ("host", "split"))
    share = host_t / total
    if not 0.25 <= share <= 0.55 and total > 60:
        problems.append(f"host on screen {share:.0%} of the time (aim for 35-40 %)")
    lens = [s["t1"] - s["t0"] for s in shots]
    med = statistics.median(lens) if lens else 0
    if lens and not 2.5 <= med <= 6.5 and total > 60:
        problems.append(f"median shot {med:.1f}s (aim for 4-5 s)")
    for s in shots:
        real = (spec.get("pictures") or {}).get(s.get("pic")) or {}
        if real.get("find") or s.get("page") or s.get("clip"):
            continue                       # a real photo / page / clip writes its own credit after it is fetched
        if s["kind"] in ("photo", "headline", "quote", "tweet") and not s.get("source"):
            r = rows[s["row"]] if s["row"] < len(rows) else {}
            if not r.get("source"):
                problems.append(f"{s['kind']} at {s['t0']:.1f}s has no source line")
    stats = {"shots": len(shots), "host_share": round(share, 3), "median_shot": round(med, 2), "items": len(item_starts)}
    return {"ok": not problems, "problems": problems, "repaired": repaired, "stats": stats}
