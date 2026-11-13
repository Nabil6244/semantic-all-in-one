"""Web pictures for the sticker stage (docs/aviation/MASTER_PLAN.md section 4, step 7): fills the stage's `paper` and `photo_card`
elements that the story director asked for, at Generate, before render.

    requests(plan) -> [(shot, element)]            stage elements whose args carry a "capture" request
    plan_with_web(scenes, rows, cache_dir, **kw) -> (plan, report)   first pass (requests) -> resolve -> final plan that places only
                                                   the pictures that passed (no gaps where a failed picture would have been)
    resolve(plan, scenes, cache_dir, *, search=None, capture=None, capture_many=None, library=None, log=print) -> report
        paper:      the CSV url -> page shot (headline box) -> args image / headline_box / source
        photo_card: the line's searches (CSV queries, else webcapture.queries from its own names) -> pages ranked by webcapture.search
                    -> captured lead photos / infoboxes -> the first page that names the line (page_ok) and whose photo passes the
                    livery check when an airline is named (photo_ok) -> args image / credit
        An element nothing passes for is removed from the stage (never a blank card, never someone else's picture).
        Every accepted page / photo also goes into the shared library (aviation.library, unapproved) when it is built.
search / capture / capture_many are injectable (tests run offline); the defaults are aviation.webcapture's.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import router as R

MAX_PAGES = 3
WORKERS = 4
TOTAL_S = 240.0               # all of a film's web pictures within 4 minutes at Generate


def photo_like(path: str) -> bool:
    """A photograph, not a logo / flag / diagram: enough distinct colours and not mostly one flat colour (a Wikipedia airline
    infobox's lead image is often the logo - a darkened logo behind the stage would be a copied logo, not a picture)."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB").resize((64, 64), Image.NEAREST)   # real pixels, not averages
    except Exception:
        return False
    px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
    q = {(r >> 4, g >> 4, b >> 4) for r, g, b in px}
    from collections import Counter
    top = Counter(px).most_common(1)[0][1] / len(px)
    return len(q) >= 120 and top < 0.35


def _year_of_key(req: Dict[str, Any]) -> int:
    import re as _re
    m = _re.search(r"\b(19[2-9]\d|20[0-4]\d)\b", str(req.get("key") or ""))
    return int(m.group(1)) if m else 0


def backdrop_score(caption: str, c: Any, year: int) -> Optional[float]:
    """How well a page photo's caption fits the line: its aircraft / airline named (+), its year near the line's (+); a year more
    than 15 years away rules the photo out (None) - a modern cabin never sits behind a 1970s line. No caption = neutral."""
    import re as _re
    from . import catalog as C
    cap = str(caption or "")
    yrs = [int(y) for y in _re.findall(r"\b(19[2-9]\d|20[0-4]\d)\b", cap)]
    if year and yrs and min(abs(y - year) for y in yrs) > 15:
        return None
    lines_cap = {m.entry["id"] for m in C.find_airlines(cap) if m.entry}
    lines_want = {a["id"] for a in getattr(c, "airlines", [])}
    if lines_want and not (lines_cap & lines_want):
        return None                     # the caption must name the line's airline: an 'Airbus A380' photo on the A380 page was an
                                        # Emirates jet behind a Singapore Airlines line
    sc = 0.0
    types = {m.entry["id"] for m in C.find_aircraft(cap) if m.entry}
    want = {a["id"] for a in getattr(c, "aircraft", [])}
    if want and types and not (want & types):
        sc -= 1.0
    sc += 2.0 * len(want & types)
    sc += 1.0 * len({a["id"] for a in getattr(c, "airlines", [])} & {m.entry["id"] for m in C.find_airlines(cap) if m.entry})
    if year and yrs:
        sc += 1.5
    if _re.search(r"\b(seat|cabin|lounge|menu|meal|suite|logo|livery chart|headquarters|office)\b", cap, _re.I):
        sc -= 1.5                       # a seat / logo / office picture is not what a chapter is about
    return sc


def _best_backdrop(urls, caps, c, req, WC):
    year = _year_of_key(req)
    best, best_sc = None, None
    for u in urls:
        cap = caps.get(u) or {}
        if not cap.get("ok") or not WC.page_ok(cap, c)[0]:
            continue
        for el in cap.get("elements") or []:
            if el.get("kind") not in ("lead", "photo") or not el.get("path") or not photo_like(el["path"]):
                continue
            sc = backdrop_score(el.get("caption", ""), c, year)
            if sc is None:
                continue
            if best_sc is None or sc > best_sc:
                best, best_sc = (cap, el), sc
    return best if best_sc is not None and best_sc > -1.0 else None


def requests(plan: Any) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    out = []
    for sh in plan.shots:
        if sh.get("layer") != "stage.lay_stage":
            continue
        for e in (sh.get("params") or {}).get("elements") or []:
            if isinstance((e.get("args") or {}).get("capture"), dict):
                out.append((sh, e))
    return out


def _scene_text(scenes: Sequence[Dict[str, Any]], shot: Dict[str, Any], e: Dict[str, Any]) -> str:
    t = float(shot["start"]) + float(e["t0"])
    for s in scenes:
        if float(s["start"]) - 1e-6 <= t < float(s["end"]) + 1e-6:
            return str(s.get("text") or "")
    return str((e["args"]["capture"] or {}).get("text") or "")


def _to_library(library: Any, cap: Dict[str, Any], c: Any, log) -> None:
    if library is None or not hasattr(library, "import_capture"):
        return
    try:
        library.import_capture(cap, c)
    except Exception as ex:                               # the library is a bonus: a failure never stops the film
        log(f"library import skipped: {ex}")


def _one(shot, e, scenes, cache_dir, search, capture, capture_many, WC, web_key):
    """(key, update or None, capture or None, classification, reason) for one request."""
    req = e["args"]["capture"]
    text = _scene_text(scenes, shot, e)
    c = R.classify(text)
    if e["kind"] == "paper" and req.get("url"):
        key = web_key("url", req["url"])
        cap = capture(req["url"], cache_dir, wants=("page",), key_sentence=text)
        page = (cap or {}).get("page") or {}
        if cap and cap.get("ok") and page.get("ok", True) and page.get("path"):
            return key, {"image": page["path"], "headline_box": page.get("headline_box"),
                         "source": cap.get("site") or cap.get("credit") or ""}, cap, c, ""
        return key, None, None, c, f"paper sticker dropped ({(cap or {}).get('reason', 'no page')}): {req['url']}"
    key = req.get("key") or web_key("photo", req.get("text") or text)
    qs = list(req.get("queries") or []) or WC.queries(c)
    hits = WC.search(qs, search_fn=search, max_results=8) if qs else []
    urls = [h["url"] for h in hits[:MAX_PAGES]]
    caps = capture_many(urls, cache_dir, wants=("elements",), key_sentence=text) if urls else {}
    if e["kind"] == "backdrop":
        best = _best_backdrop(urls, caps, c, req, WC)
        if best:
            cap, el = best
            return key, {"image": el["path"], "credit": el.get("credit") or cap.get("site") or ""}, cap, c, ""
        return key, None, None, c, f"backdrop left out (no photo of the right era / subject): {text[:70]}"
    for u in urls:
        cap = caps.get(u) or {}
        if not cap.get("ok") or not WC.page_ok(cap, c)[0]:
            continue
        for el in cap.get("elements") or []:
            livery_ok = e["kind"] == "backdrop" or WC.photo_ok(el, c)[0]   # a dim old b/w photo behind the stage needs no livery check
            if el.get("kind") in ("lead", "photo", "infobox") and el.get("path") and photo_like(el["path"]) and livery_ok:
                return key, {"image": el["path"], "credit": el.get("credit") or cap.get("site") or ""}, cap, c, ""
    return key, None, None, c, f"photo card dropped (no page passed the checks): {text[:70]}"


def resolve(plan: Any, scenes: Sequence[Dict[str, Any]], cache_dir: Any, *, search: Optional[Callable] = None,
            capture: Optional[Callable] = None, capture_many: Optional[Callable] = None, library: Any = None,
            log: Callable[[str], None] = lambda m: None, workers: int = WORKERS, total_s: float = TOTAL_S) -> Dict[str, Any]:
    """Requests run WORKERS at a time; whatever is not done after TOTAL_S is left out (the stage plays without it)."""
    import concurrent.futures as cf
    import time
    from . import webcapture as WC
    from .story import web_key
    capture = capture or WC.capture
    capture_many = capture_many or WC.capture_many
    report: Dict[str, Any] = {"paper": 0, "photo": 0, "dropped": [], "web": {}}
    found = report["web"]
    reqs = requests(plan)
    seen: Dict[str, Any] = {}
    pool = cf.ThreadPoolExecutor(max_workers=max(1, workers))
    futs = {}
    for shot, e in reqs:
        futs[pool.submit(_one, shot, e, scenes, cache_dir, search, capture, capture_many, WC, web_key)] = (shot, e)
    deadline = time.monotonic() + total_s
    results = {}
    try:
        for f in cf.as_completed(futs, timeout=max(1.0, total_s)):
            results[f] = f.result() if not f.exception() else None
            if time.monotonic() > deadline:
                break
    except cf.TimeoutError:
        log(f"web pictures: time limit {total_s:.0f} s reached, the rest are left out")
    pool.shutdown(wait=False, cancel_futures=True)
    for f, (shot, e) in futs.items():
        got = results.get(f)
        if not got:
            continue
        key, upd, cap, c, why = got
        found[key] = upd
        if upd:
            e["args"].update(upd)
            report["paper" if e["kind"] == "paper" else "photo"] += 1
            if key not in seen:
                seen[key] = True
                _to_library(library, cap, c, log)
        else:
            log(why)
    for f, (shot, e) in futs.items():
        if not (results.get(f) or (None, None))[1]:
            shot["params"]["elements"] = [x for x in shot["params"]["elements"] if x is not e]
            report["dropped"].append(e["id"])
    return report


def plan_with_web(scenes: Sequence[Dict[str, Any]], rows: Optional[Sequence[dict]], cache_dir: Any, **kw) -> Tuple[Any, Dict[str, Any]]:
    from . import planner as P
    first = P.plan(scenes, rows)
    if not requests(first):
        return first, {"paper": 0, "photo": 0, "dropped": [], "web": {}}
    report = resolve(first, scenes, cache_dir, **kw)
    return P.plan(scenes, rows, web=report["web"]), report
