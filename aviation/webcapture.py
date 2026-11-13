"""Aviation web search + capture (docs/aviation/MASTER_PLAN.md section 4): find the pages that name a line's airline / aircraft /
event, and take four things from each good page, no Gemini.

    queries(classification, csv_search='', max_q=3) -> ['Air France Joon launch 2017', ...]    from the line's own names
    search(queries, search_fn=None, max_results=8, csv_urls=(), airline_sites=()) -> [{url, title, snippet, rank, domain}]
        keyless DuckDuckGo (research engine) by default; search_fn(query, max_results) -> [{url,title,snippet}|url] is injectable.
        Order: CSV urls, then preferred sites (the airline's own, wikipedia, reuters, apnews, bbc, simpleflying, aviationweek,
        flightglobal, airlinegeeks, planespotters, airliners.net, jetphotos), then the rest in search order.
    capture(url, cache_dir, wants=('page','scroll','elements','data'), key_sentence='', timeout_s=40) -> dict
        {ok, reason, url, site, title, date, credit, cached, text,
         page:     webshot.shot result (png path, headline_box) | None,
         scroll:   {path (mp4, 1280x720, 30 fps, 4 s), duration, found (sentence located and highlighted yellow)} | None,
         elements: [{kind 'lead'|'infobox'|'table', path, caption, credit}],
         data:     [{kind 'founded'|'fleet'|'stake'|'passengers'|'destinations', value, text, source, (type)}]}
        One throwaway headless browser per page (aviation/webcapture.mjs; the page shot uses webshot.mjs in parallel). Overlays are
        hidden by CSS, never accepted. Blank page / cookie wall / paywall / robots.txt disallow / HTTP error -> ok False + reason.
        Cached in cache_dir by URL hash (and by key sentence for the scroll); failures are not cached.
    capture_many(urls, cache_dir, wants=..., key_sentence='', workers=3, total_timeout_s=120) -> {url: capture dict}
    page_ok(capture, classification) -> (ok, score, reason)     the page must name the line's airline / aircraft / event
    photo_ok(element, classification, threshold=0.03) -> (ok, livery)   lead photos count as the airline's own only above the colour check
    facts_agree(facts, classification) -> facts                 drops facts that contradict a number the narration states

Rules: the narration wins (a page fact that disagrees with a number in the sentence is dropped); data are rule-based regexes only.
"""

from __future__ import annotations

import asyncio
import concurrent.futures as _cf
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.robotparser
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from PIL import Image

from . import catalog as C
from . import footage as F
from . import webshot as WS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
USER_AGENT = "Mozilla/5.0 (compatible; SemanticYTStudio/1.0)"

PREFERRED = ("wikipedia.org", "reuters.com", "apnews.com", "bbc.co.uk", "bbc.com", "simpleflying.com", "aviationweek.com",
             "flightglobal.com", "airlinegeeks.com", "planespotters.net", "airliners.net", "jetphotos.com")


# ------------------------------------------------------------------------------------------------------------------ queries

def queries(c: Any, csv_search: str = "", max_q: int = 3) -> List[str]:
    """Search phrases from the line's own names. A CSV search phrase goes first. Never a question, never filler words."""
    out: List[str] = []

    def add(*parts: str) -> None:
        q = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
        if q and q.lower() not in [o.lower() for o in out]:
            out.append(q)

    add(str(csv_search or ""))
    text = c.text
    low = text.lower()
    airline = c.airlines[0]["name"] if c.airlines else ""
    craft = c.aircraft[0]["name"] if c.aircraft else ""
    city = c.airports[0]["city"] if c.airports else ""
    event = F._first(F._EVENTS, low)
    year = F._year(c)
    kws = F._keywords(text, skip=" ".join(a["name"] for a in c.airlines + c.aircraft + c.airports))
    if airline and event:
        add(airline, event, year)
    if airline and craft:
        add(airline, craft, "fleet" if c.mode in ("fleet", "numbers") else "")
    if craft and not airline:
        add(craft, "aircraft")
    if airline and len(kws) >= 2:
        add(airline, " ".join(kws[:2]), year)
    if airline:
        add(airline, "history" if c.mode in ("numbers", "news") or not kws else kws[0])
    if city and not airline:
        add(city, "airport", event)
    if not out and len(kws) >= 2:
        add(" ".join(kws[:3]), year)
    return out[:max_q]


# ------------------------------------------------------------------------------------------------------------------ search

def _domain(url: str) -> str:
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


def _ddg_search(q: str, max_results: int) -> List[dict]:
    p = ROOT / "research" / "engine" / "app" / "discovery" / "search.py"      # loaded by path: 'app' is also this repo's app.py
    spec = importlib.util.spec_from_file_location("_aviation_ddg_search", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    res = asyncio.run(mod.DuckDuckGoSearchProvider().search(q, max_results=max_results))
    return [{"url": r.url, "title": r.title or "", "snippet": r.snippet or ""} for r in res if r.url]


def _wiki_search(q: str, max_results: int) -> List[dict]:
    """Wikipedia's own keyless search API (the fallback when DuckDuckGo answers with its bot check): article titles + urls."""
    import urllib.parse
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": q, "srlimit": max(1, min(10, max_results)), "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for h in (data.get("query") or {}).get("search") or []:
        t = h.get("title") or ""
        out.append({"url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_")), "title": t,
                    "snippet": re.sub(r"<[^>]+>", "", h.get("snippet") or "")})
    return out


def _default_search(q: str, max_results: int) -> List[dict]:
    """DuckDuckGo first; when it gives nothing (its bot check answers automated searches with an empty page), Wikipedia."""
    try:
        got = _ddg_search(q, max_results)
    except Exception:
        got = []
    if got:
        return got
    try:
        return _wiki_search(q, max_results)
    except Exception:
        return []


def search(qs: Sequence[str], search_fn: Optional[Callable[[str, int], Any]] = None, max_results: int = 8,
           csv_urls: Iterable[str] = (), airline_sites: Iterable[str] = ()) -> List[dict]:
    fn = search_fn or _default_search
    own = [_domain(s) if "/" in s else s.lower().removeprefix("www.") for s in airline_sites if s]
    seen: Dict[str, dict] = {}

    def put(item: Any, source: str) -> None:
        d = {"url": item} if isinstance(item, str) else dict(item)
        url = str(d.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://", "file://")):
            return
        key = url.split("#")[0].rstrip("/")
        if key in seen:
            return
        dom = _domain(url)
        if source == "csv":
            rank = 0
        elif any(dom == o or dom.endswith("." + o) for o in own):
            rank = 1
        else:
            pref = [i for i, p in enumerate(PREFERRED) if dom == p or dom.endswith("." + p)]
            rank = 2 + pref[0] if pref else 100
        seen[key] = {"url": url, "title": d.get("title") or "", "snippet": d.get("snippet") or "", "rank": rank, "domain": dom,
                     "order": len(seen)}

    for u in csv_urls:
        put(str(u), "csv")
    for q in qs:
        try:
            got = fn(q, max_results) or []
        except Exception:                                                # a flaky search never breaks a film
            got = []
        for item in got:
            put(item, "web")
    return sorted(seen.values(), key=lambda r: (r["rank"], r["order"]))[:max(max_results, len(list(csv_urls)))]


# ------------------------------------------------------------------------------------------------------------------ capture

def _robots_ok(url: str) -> bool:
    if not url.lower().startswith(("http://", "https://")):
        return True
    p = urlparse(url)
    try:
        req = urllib.request.Request(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=4) as r:
            body = r.read(200000).decode("utf-8", "replace")
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(body.splitlines())
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True                                                      # no robots.txt, no restriction


def _ffmpeg(cmd: List[str], timeout: float) -> bool:
    try:
        from providers.ffmpeg_runner import run_ffmpeg
        r = run_ffmpeg(cmd, owner="aviation_webcapture", timeout=timeout, stall_s=60.0, media_duration_s=5.0)
        return r.returncode == 0 and not r.timed_out
    except Exception:
        try:
            return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode == 0
        except Exception:
            return False


def _scroll_mp4(strip: dict, out: Path, secs: float = 4.0, fps: int = 30) -> bool:
    """Ease the 1280x720 window down the tall strip: hold 0.5 s, glide, hold 0.8 s. One ffmpeg crop with a time expression."""
    d = max(0, int(strip["end"]) - int(strip["start"]))
    hold0, hold1 = 0.5, 0.8
    tm = secs - hold0 - hold1
    u = f"clip((t-{hold0})/{tm},0,1)"
    ease = f"(0.5-0.5*cos(PI*{u}))"
    maxy = max(0, int(strip["h"]) - 720)
    expr = f"min({maxy},{d}*{ease})"
    vf = f"crop=1280:720:0:'{expr}',format=yuv420p"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-framerate", str(fps), "-i", strip["path"],
           "-t", f"{secs}", "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-movflags", "+faststart",
           str(out)]
    return _ffmpeg(cmd, 60.0) and out.is_file()


_FLEET_TYPE = (r"(?:(?:Airbus|Boeing|Embraer|ATR|Bombardier|McDonnell Douglas|Dash 8)\s+)?"
               r"(A3[0-9]{2}(?:-\d+)?(?:neo)?|7[0-9]7(?:-\d+)?(?:\s?MAX)?|E1[79]\d(?:-E\d)?|ATR\s?\d{2}(?:-\d+)?|CRJ-?\d{3}|Q400|MD-?\d{2}|Concorde)")
_YEAR = r"(1[89]\d{2}|20\d{2})"


def _sentence_at(text: str, a: int, b: int) -> str:
    s = max(text.rfind(".", 0, a), text.rfind("\n", 0, a)) + 1
    e = [i for i in (text.find(".", b), text.find("\n", b)) if i >= 0]
    return re.sub(r"\s+", " ", text[s:(min(e) + 1 if e else len(text))]).strip()[:300]


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def extract_data(text: str, source: str) -> List[dict]:
    """Rule-based facts from page text: founded year, fleet counts per type, % stakes, passengers, destinations."""
    out: List[dict] = []
    seen = set()

    def add(kind: str, value: Any, m: re.Match, **extra: Any) -> None:
        k = (kind, json.dumps(value), extra.get("type"))
        if k not in seen:
            seen.add(k)
            out.append({"kind": kind, "value": value, "text": _sentence_at(text, m.start(), m.end()), "source": source, **extra})

    for m in re.finditer(r"\b(?:founded|established|incorporated|began operations|commenced operations|started operations|launched)"
                         r"(?:\s+(?:in|on|by))?[^.\n]{0,40}?\b" + _YEAR + r"\b", text, re.I):
        if re.search(r"found|establish|incorporat|began|commenced|started", m.group(0), re.I):
            add("founded", int(m.group(1)), m)
    for m in re.finditer(r"(?<![\d.,-])(\d{1,4})\s+(?:(?:new|active|stored|in-service|passenger|widebody|narrowbody|firm|more)\s+){0,2}"
                         + _FLEET_TYPE, text):
        n = int(m.group(1))
        if 1 <= n <= 1500 and not (1900 <= n <= 2100):
            add("fleet", n, m, type=re.sub(r"\s+", " ", m.group(2)).upper())
    for m in re.finditer(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s?(?:%|per ?cent)", text, re.I):
        ctx = text[max(0, m.start() - 90):m.end() + 90].lower()
        if re.search(r"\bstake|\bowns?\b|\bowned\b|\bshareholder|\bholds?\b|\bshare(?:s)? in|\bequity", ctx):
            add("stake", _num(m.group(1)), m)
    for m in re.finditer(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(million|billion|m|bn)?\s+(?:annual\s+)?passengers", text, re.I):
        v = _num(m.group(1)) * {"million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9}.get((m.group(2) or "").lower(), 1)
        add("passengers", int(round(v)), m)
    for m in re.finditer(r"(?<![\d.,])(\d{1,4})\s+(?:international\s+|domestic\s+)?(destinations|countries|airports|routes)", text, re.I):
        add("destinations", int(m.group(1)), m, unit=m.group(2).lower())
    return out


def _key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def capture(url: str, cache_dir: Any, wants: Sequence[str] = ("page", "scroll", "elements", "data"), key_sentence: str = "",
            timeout_s: float = 40.0) -> Dict[str, Any]:
    url = str(url or "").strip()
    res: Dict[str, Any] = {"ok": False, "reason": "", "url": url, "site": "", "title": "", "date": "", "credit": "", "cached": False,
                           "text": "", "page": None, "scroll": None, "elements": [], "data": []}
    if not url.lower().startswith(("http://", "https://", "file://")):
        res["reason"] = "not a web address"
        return res
    wants = set(wants)
    root = Path(cache_dir)
    d = root / f"cap_{_key(url)}"
    d.mkdir(parents=True, exist_ok=True)
    meta = d / "result.json"
    kh = hashlib.sha1(key_sentence.strip().lower().encode("utf-8")).hexdigest()[:8] if key_sentence.strip() else "nokey"
    base: Dict[str, Any] = {}
    if meta.is_file():
        try:
            base = json.loads(meta.read_text(encoding="utf-8"))
        except ValueError:
            base = {}
    have_scroll = f"scroll_{kh}" in base and Path(base[f"scroll_{kh}"].get("path", "")).is_file()
    need_browser = base.get("ok") is not True or ("elements" in wants and "elements" not in base) or ("scroll" in wants and not have_scroll)
    need_page = "page" in wants and not (base.get("page") and Path(base["page"].get("path", "")).is_file())
    if not need_browser and not need_page and base.get("ok"):
        return _view(base, wants, kh, cached=True)

    if not _robots_ok(url):
        res["reason"] = "robots.txt disallows this page"
        return res

    def run_browser() -> Dict[str, Any]:
        bw = [w for w in ("scroll", "elements") if w in wants]
        spec = {"url": url, "outdir": str(d), "wants": bw, "key_sentence": key_sentence, "timeout_ms": int(timeout_s * 600)}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(spec, fh)
            sp = fh.name
        try:
            p = subprocess.run(["node", str(HERE / "webcapture.mjs"), sp], capture_output=True, text=True, timeout=timeout_s + 25)
            lines = (p.stdout or "").strip().splitlines()
            return json.loads(lines[-1]) if lines else {"ok": False, "reason": (p.stderr or "no output")[-300:]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "reason": "timed out"}
        except (OSError, ValueError) as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
        finally:
            Path(sp).unlink(missing_ok=True)

    with _cf.ThreadPoolExecutor(max_workers=2) as ex:
        fb = ex.submit(run_browser) if need_browser else None
        fp = ex.submit(WS.shot, url, d / "shot", timeout_s) if need_page else None
        br = fb.result() if fb else {}
        shot = fp.result() if fp else None

    if need_browser and not br.get("ok"):
        res["reason"] = br.get("reason") or "capture failed"
        for k in ("site", "title", "text"):
            res[k] = br.get(k, "")
        return res
    if need_browser:
        base = dict(base, ok=True, site=br.get("site", ""), title=br.get("title", ""), date=WS._date(br.get("date", "")),
                    text=br.get("text", ""), url=url)
        base["credit"] = f"{base['site']}" + (f" ({_domain(url)})" if _domain(url) and _domain(url) not in base["site"].lower() else "")
        if "elements" in wants:
            base["elements"] = [dict(e, credit=base["credit"], source_url=url) for e in br.get("elements", [])]
        if br.get("strip"):
            mp4 = d / f"scroll_{kh}.mp4"
            if _scroll_mp4(br["strip"], mp4):
                base[f"scroll_{kh}"] = {"path": str(mp4), "duration": 4.0, "found": bool(br.get("found"))}
    if "data" in wants and "data" not in base:
        base["data"] = extract_data(base.get("text", ""), base.get("credit") or url)
    if shot is not None:
        if shot.get("ok"):
            base["page"] = shot
        elif "page" not in base:
            base["page"] = None
            base["page_reason"] = shot.get("reason", "")
    if base.get("ok"):
        meta.write_text(json.dumps(base, indent=1), encoding="utf-8")
    return _view(base, wants, kh, cached=False)


def _view(base: Dict[str, Any], wants: set, kh: str, cached: bool) -> Dict[str, Any]:
    r = {"ok": bool(base.get("ok")), "reason": base.get("reason", ""), "url": base.get("url", ""), "site": base.get("site", ""),
         "title": base.get("title", ""), "date": base.get("date", ""), "credit": base.get("credit", ""), "cached": cached,
         "text": base.get("text", ""), "page": base.get("page") if "page" in wants else None,
         "scroll": base.get(f"scroll_{kh}") if "scroll" in wants else None,
         "elements": base.get("elements", []) if "elements" in wants else [],
         "data": base.get("data", []) if "data" in wants else []}
    if r["page"]:
        r["page"] = dict(r["page"], cached=cached)
    return r


def capture_many(urls: Sequence[str], cache_dir: Any, wants: Sequence[str] = ("page", "scroll", "elements", "data"),
                 key_sentence: str = "", workers: int = 3, total_timeout_s: float = 120.0, timeout_s: float = 40.0) -> Dict[str, dict]:
    """Pages in parallel (one throwaway browser each); whatever is not done when the total time is up is reported as timed out."""
    out: Dict[str, dict] = {}
    urls = list(dict.fromkeys(urls))
    ex = _cf.ThreadPoolExecutor(max_workers=max(1, workers))
    futs = {ex.submit(capture, u, cache_dir, wants, key_sentence, timeout_s): u for u in urls}
    t_end = time.monotonic() + total_timeout_s
    try:
        for f, u in futs.items():
            try:
                out[u] = f.result(timeout=max(0.1, t_end - time.monotonic()))
            except _cf.TimeoutError:
                out[u] = {"ok": False, "reason": "total time limit", "url": u}
            except Exception as exc:
                out[u] = {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "url": u}
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out


# ------------------------------------------------------------------------------------------------------------------ checks

def page_ok(cap: Dict[str, Any], c: Any) -> Tuple[bool, float, str]:
    """The page must name the line's airline / aircraft (and, for a news event, that airline); title weighs more than the body."""
    if not cap or not cap.get("ok"):
        return False, 0.0, (cap or {}).get("reason") or "no page"
    title = f"{cap.get('title', '')} {cap.get('site', '')}"
    body = str(cap.get("text") or "")[:20000]
    full = f"{title}\n{title}\n{body}"
    ok, score, reason = F.clip_ok(full, c)
    if not ok:
        return False, 0.0, reason.replace("clip", "page")
    want = {a["id"] for a in c.airlines} | {a["id"] for a in c.aircraft}
    if want:
        got = {m.entry["id"] for m in C.find_airlines(full) + C.find_aircraft(full) if m.entry}
        if not (want & got):
            return False, 0.0, "page does not name " + ", ".join(sorted(a["name"] for a in c.airlines + c.aircraft))
        in_title = {m.entry["id"] for m in C.find_airlines(title) + C.find_aircraft(title) if m.entry}
        score += 1.5 * len(want & in_title)
    return True, round(score, 2), "ok"


def photo_ok(element: Dict[str, Any], c: Any, threshold: float = 0.03) -> Tuple[bool, float]:
    """A captured photo counts as the named airline's own only when its livery colours show; no airline named or no colour signal
    in the catalog (an all-white fleet) -> accepted with score -1."""
    if not c.airlines:
        return True, -1.0
    try:
        im = Image.open(element["path"])
    except Exception:
        return False, 0.0
    best, signal = 0.0, False
    for a in c.airlines:
        cat = C.get_airline(a["id"]) or {}
        if any(not min(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) > 200 for h in cat.get("colors") or []):
            signal = True
            best = max(best, F.livery_score(im, a["id"]))
    if not signal:
        return True, -1.0
    return best >= threshold, round(best, 3)


def facts_agree(facts: Sequence[dict], c: Any) -> List[dict]:
    """The narration wins: a page fact that contradicts a number the sentence states is dropped, never the sentence's number."""
    v = c.values or {}
    low = c.text.lower()
    nar_pct = [float(x) for x in v.get("percent", [])]
    nar_years = {int(y) for y in re.findall(r"\b(1[89]\d{2}|20\d{2})\b", c.text)}
    out: List[dict] = []
    for f in facts:
        k, val = f.get("kind"), f.get("value")
        try:
            if k == "stake" and nar_pct and not any(abs(float(val) - p) < 0.5 for p in nar_pct):
                continue
            if k == "founded" and nar_years and re.search(r"\b(found|establish|began|start|launch|born|created)\w*", low) \
                    and int(val) not in nar_years:
                continue
            if k == "fleet":
                m = re.search(r"(\d[\d,]*)\s+(?:\w+\s+){0,2}" + re.escape(str(f.get("type", ""))).replace(r"\ ", r"\s?"), c.text, re.I)
                if m and int(m.group(1).replace(",", "")) != int(val):
                    continue
            if k == "passengers":
                m = re.search(r"(\d+(?:\.\d+)?)\s*(million|billion)?\s+passengers", low)
                if m:
                    said = float(m.group(1)) * {"million": 1e6, "billion": 1e9}.get(m.group(2) or "", 1)
                    if said and abs(said - float(val)) / said > 0.1:
                        continue
            if k == "destinations":
                m = re.search(r"(\d+)\s+(?:\w+\s+)?(?:destinations|countries|airports|routes)", low)
                if m and int(m.group(1)) != int(val):
                    continue
        except (TypeError, ValueError):
            continue
        out.append(f)
    return out
