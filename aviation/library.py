"""Aviation shared library (docs/aviation/MASTER_PLAN.md sections 4-5): everything approved once is reused by every film.
Same idea as the War b-roll library (index.json + files), extended to stickers, hero aircraft, cast sheets, place plates, photos,
captured pages, scroll captures, clips, Flow pictures / videos and data.

    <root>/index.json                                  {version, entries: [entry, ...]}
    <root>/<airline|generic>/<era|any>/<kind>/<id>.<ext>      (rejected files move to <root>/_rejected/<same path>, never deleted)
    entry = {id, kind, airline, era, subject, path (relative to root), source, credit, url, ai, approved, added, used_in[],
             tags[], w, h, duration?, hash}
    kinds: sticker hero cast place photo page scroll clip flow_image flow_video data

Every function takes an optional keyword `lib=` (a root path); without it root(settings) is used.

    root(settings=None) -> Path          settings['aviation_library_dir'] or env AVIATION_LIBRARY_DIR or <repo>/assets/aviation/library
    era_of(year) -> '1940s'..'2020s' ('any' when unknown; <1940 -> '1940s'; > 2029 -> '2020s')
    add(kind, path, *, airline, era, subject, source, credit, ai, url=None, tags=(), approved=False, copy=True, lib=None) -> entry
        copies the file in; the same content hash + kind + airline + era + subject returns the existing entry (no second copy)
    approve(ids) / reject(ids) -> [entries]    reject moves the file to _rejected/ and marks approved False, rejected True
    find(kind, *, airline=None, era=None, subject=None, approved_only=True) -> [entries]   most specific first:
        airline+era+subject > airline+subject > generic subject > airline+era > airline (kind only); rejected never returned
    best(kind, ...) -> entry | None
    mark_used(id, project) -> entry
    import_capture(capture_result, meta, lib=None) -> [entries]   aviation.webcapture.capture() result into page / scroll / photo / data
        entries (unapproved, credit + url kept). meta: {airline, era, subject, tags} or a classification object with .airlines etc.
    import_clip(clip_dict, meta, lib=None) -> entry               a captured YouTube clip (local_path, source_url, channel, ...)
    contact_sheet(entries, out_png, cols=5, thumb=(256, 144)) -> Path    PIL grid: thumbnail + id + credit + approved mark
    stats(lib=None) -> {total, approved, rejected, by_kind, by_airline}
    build_list(bible, lib=None) -> [{kind, airline, era, subject, prompt?}]   what the film needs that is not approved yet

Thread safe: one lock around index read-modify-write; the index is written to a temp file and replaced atomically.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

KINDS = ("sticker", "hero", "cast", "place", "photo", "page", "scroll", "clip", "flow_image", "flow_video", "data")
SETTING = "aviation_library_dir"
ENV_DIR = "AVIATION_LIBRARY_DIR"
REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO / "assets" / "aviation" / "library"
REJECTED = "_rejected"
VERSION = 1
_LOCK = threading.RLock()


# ------------------------------------------------------------------------------------------------------------------ basics

def root(settings: Optional[Dict[str, Any]] = None) -> Path:
    p = os.environ.get(ENV_DIR) or (settings or {}).get(SETTING) or ""
    return Path(p).expanduser() if p else DEFAULT_ROOT


def _root(lib: Any) -> Path:
    return Path(lib) if lib else root()


def era_of(year: Any) -> str:
    try:
        y = int(str(year).strip()[:4])
    except (TypeError, ValueError):
        return "any"
    if y <= 0:
        return "any"
    return f"{min(max(y, 1940), 2029) // 10 * 10}s"


def _slug(s: Any, default: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")
    return s[:60] or default


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _load(r: Path) -> Dict[str, Any]:
    try:
        d = json.loads((r / "index.json").read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("entries"), list):
            return d
    except (OSError, ValueError):
        pass
    return {"version": VERSION, "entries": []}


def _save(r: Path, data: Dict[str, Any]) -> None:
    r.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".index_", suffix=".tmp", dir=str(r))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, r / "index.json")
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe(path: Path) -> Dict[str, Any]:
    """w, h (and duration for video) - PIL for images, ffprobe for video; empty when unknown."""
    out: Dict[str, Any] = {}
    ext = path.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
        try:
            from PIL import Image
            with Image.open(path) as im:
                out["w"], out["h"] = im.size
        except Exception:
            pass
    elif ext in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                                "-of", "json", str(path)], capture_output=True, text=True, timeout=20)
            d = json.loads(r.stdout or "{}")
            st = (d.get("streams") or [{}])[0]
            if st.get("width"):
                out["w"], out["h"] = int(st["width"]), int(st["height"])
            dur = float((d.get("format") or {}).get("duration") or 0)
            if dur > 0:
                out["duration"] = round(dur, 2)
        except Exception:
            pass
    return out


def _public(e: Dict[str, Any]) -> Dict[str, Any]:
    return dict(e)


# ------------------------------------------------------------------------------------------------------------------ add / approve

def add(kind: str, path: Any, *, airline: str = "", era: str = "", subject: str = "", source: str = "", credit: str = "",
        ai: bool = False, url: Optional[str] = None, tags: Iterable[str] = (), approved: bool = False, copy: bool = True,
        lib: Any = None, duration: Optional[float] = None) -> Dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; one of {KINDS}")
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    r = _root(lib)
    airline_s, era_s = _slug(airline, "generic"), (str(era).strip().lower() or "any")
    era_s = _slug(era_s, "any")
    subject_s = str(subject or "").strip()
    digest = _hash(src)
    with _LOCK:
        data = _load(r)
        for e in data["entries"]:
            if (e.get("hash") == digest and e["kind"] == kind and e["airline"] == airline_s and e["era"] == era_s
                    and _norm(e.get("subject")) == _norm(subject_s) and not e.get("rejected")):
                if approved and not e.get("approved"):
                    e["approved"] = True
                    _save(r, data)
                return _public(e)
        eid = f"{kind}_{digest[:10]}"
        n = 1
        ids = {e["id"] for e in data["entries"]}
        while eid in ids:
            n += 1
            eid = f"{kind}_{digest[:10]}_{n}"
        rel = Path(airline_s) / era_s / kind / f"{eid}{src.suffix.lower()}"
        dst = r / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copy2(src, dst)
        else:
            if src.resolve() != dst.resolve():
                shutil.move(str(src), str(dst))
        entry = {"id": eid, "kind": kind, "airline": airline_s, "era": era_s, "subject": subject_s, "path": rel.as_posix(),
                 "source": source, "credit": credit, "url": url, "ai": bool(ai), "approved": bool(approved), "added": time.time(),
                 "used_in": [], "tags": [str(t) for t in tags], "hash": digest}
        entry.update(_probe(dst))
        if duration is not None:
            entry["duration"] = round(float(duration), 2)
        data["entries"].append(entry)
        _save(r, data)
        return _public(entry)


def _ids(ids: Any) -> List[str]:
    if isinstance(ids, str):
        return [ids]
    return [i["id"] if isinstance(i, dict) else str(i) for i in (ids or [])]


def approve(ids: Any, lib: Any = None) -> List[Dict[str, Any]]:
    want, r, out = set(_ids(ids)), _root(lib), []
    with _LOCK:
        data = _load(r)
        for e in data["entries"]:
            if e["id"] in want and not e.get("rejected"):
                e["approved"] = True
                out.append(_public(e))
        _save(r, data)
    return out


def reject(ids: Any, lib: Any = None) -> List[Dict[str, Any]]:
    """Moves the file to <root>/_rejected/ (kept, never deleted); the entry stays in the index as rejected."""
    want, r, out = set(_ids(ids)), _root(lib), []
    with _LOCK:
        data = _load(r)
        for e in data["entries"]:
            if e["id"] in want and not e.get("rejected"):
                src = r / e["path"]
                dst = r / REJECTED / e["path"]
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                e["path"] = (Path(REJECTED) / e["path"]).as_posix()
                e["approved"], e["rejected"] = False, True
                out.append(_public(e))
        _save(r, data)
    return out


def mark_used(eid: str, project: str, lib: Any = None) -> Optional[Dict[str, Any]]:
    r = _root(lib)
    with _LOCK:
        data = _load(r)
        for e in data["entries"]:
            if e["id"] == eid:
                if project not in e.setdefault("used_in", []):
                    e["used_in"].append(project)
                    _save(r, data)
                return _public(e)
    return None


def path_of(entry: Dict[str, Any], lib: Any = None) -> Path:
    return _root(lib) / entry["path"]


# ------------------------------------------------------------------------------------------------------------------ find

def _rank(e: Dict[str, Any], airline: str, era: str, subject: str) -> int:
    """Higher = more specific; 0 = no match."""
    ea, ee, es = e.get("airline", "generic"), e.get("era", "any"), _norm(e.get("subject"))
    sa = ea == airline if airline else False
    se = ee == era if era else False
    ss = bool(subject) and (es == subject or subject in es or (es and es in subject))
    if airline and ea not in (airline, "generic"):
        return 0
    if era and ee not in (era, "any"):
        return 0
    if subject and not ss:
        return 0
    if sa and se and ss:
        return 60
    if sa and ss:
        return 50
    if ea == "generic" and ss:
        return 40 + (5 if se else 0)
    if sa and se:
        return 30
    if sa:
        return 20
    return 10  # generic, nothing asked or only the kind


def find(kind: str, *, airline: Optional[str] = None, era: Optional[str] = None, subject: Optional[str] = None,
         approved_only: bool = True, lib: Any = None) -> List[Dict[str, Any]]:
    a = _slug(airline, "") if airline else ""
    er = _slug(era, "") if era else ""
    s = _norm(subject)
    scored = []
    for e in _load(_root(lib))["entries"]:
        if e["kind"] != kind or e.get("rejected") or (approved_only and not e.get("approved")):
            continue
        sc = _rank(e, a, er, s)
        if sc:
            exact = 1 if _norm(e.get("subject")) == s and s else 0
            scored.append((sc, exact, -len(e.get("used_in") or []), e.get("added", 0), e))
    scored.sort(key=lambda t: (-t[0], -t[1], -t[2], t[3]))
    return [_public(t[4]) for t in scored]


def best(kind: str, **kw: Any) -> Optional[Dict[str, Any]]:
    got = find(kind, **kw)
    return got[0] if got else None


# ------------------------------------------------------------------------------------------------------------------ imports

def _meta(meta: Any) -> Dict[str, Any]:
    if isinstance(meta, dict):
        return meta
    out: Dict[str, Any] = {}
    airlines = list(getattr(meta, "airlines", None) or [])
    aircraft = list(getattr(meta, "aircraft", None) or [])
    if airlines:                          # router entries are dicts: the id, never the whole record as a folder name
        out["airline"] = airlines[0].get("id", "") if isinstance(airlines[0], dict) else str(airlines[0])
    if aircraft:
        out["subject"] = aircraft[0].get("id", "") if isinstance(aircraft[0], dict) else str(aircraft[0])
    year = getattr(meta, "year", None) or ((getattr(meta, "values", None) or {}).get("years") or [None])[0]
    if year:
        out["era"] = era_of(year)
    return out


def import_capture(capture: Dict[str, Any], meta: Any = None, lib: Any = None) -> List[Dict[str, Any]]:
    """Files from aviation.webcapture.capture() -> page / scroll / photo / data entries, all unapproved."""
    if not capture or not capture.get("ok"):
        return []
    m = _meta(meta)
    base = dict(airline=m.get("airline", ""), era=m.get("era", ""), subject=m.get("subject", "") or capture.get("title", ""),
                source=capture.get("site") or "web", credit=capture.get("credit", ""), url=capture.get("url"),
                ai=False, approved=False, lib=lib)
    tags = list(m.get("tags") or [])
    out: List[Dict[str, Any]] = []

    def put(kind: str, p: Any, extra_tags: Sequence[str] = (), **kw: Any) -> None:
        if p and Path(str(p)).is_file():
            out.append(add(kind, p, tags=tags + list(extra_tags), **{**base, **kw}))

    page = capture.get("page")
    if isinstance(page, dict):
        put("page", page.get("png") or page.get("path"))
    elif isinstance(page, str):
        put("page", page)
    sc = capture.get("scroll")
    if isinstance(sc, dict):
        put("scroll", sc.get("path"), ["found"] if sc.get("found") else [], duration=sc.get("duration"))
    for el in capture.get("elements") or []:
        put("photo", el.get("path"), [el.get("kind", "")], credit=el.get("credit") or base["credit"],
            subject=el.get("caption") or base["subject"])
    facts = capture.get("data") or []
    if facts:
        r = _root(lib)
        tmpd = Path(tempfile.mkdtemp(prefix="avlib_"))
        try:
            f = tmpd / "data.json"
            f.write_text(json.dumps({"url": capture.get("url"), "title": capture.get("title"), "date": capture.get("date"),
                                     "facts": facts}, indent=1, ensure_ascii=False), encoding="utf-8")
            put("data", f, sorted({str(x.get("kind", "")) for x in facts if x.get("kind")}))
        finally:
            shutil.rmtree(tmpd, ignore_errors=True)
        del r
    return out


def import_clip(clip: Dict[str, Any], meta: Any = None, lib: Any = None) -> Dict[str, Any]:
    """A captured YouTube clip (aviation.director record: local_path, source_url, channel, video_title, duration)."""
    m = _meta(meta)
    p = clip.get("local_path") or clip.get("path")
    ch = clip.get("channel") or clip.get("author") or ""
    return add("clip", p, airline=m.get("airline", ""), era=m.get("era", ""), subject=m.get("subject", "") or clip.get("prompt", ""),
               source="youtube", credit=f"{ch} (YouTube)".strip(), ai=False, url=clip.get("source_url"), tags=m.get("tags") or (),
               approved=False, lib=lib, duration=clip.get("duration"))


# ------------------------------------------------------------------------------------------------------------------ contact sheet

def _thumb(path: Path, size: Any) -> Any:
    from PIL import Image
    im = None
    if path.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        tmp = Path(tempfile.mkdtemp(prefix="avthumb_"))
        try:
            f = tmp / "f.png"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(path), "-frames:v", "1", str(f)],
                           capture_output=True, timeout=30)
            if not f.exists():
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-frames:v", "1", str(f)], capture_output=True, timeout=30)
            if f.exists():
                im = Image.open(f).convert("RGB")
                im.load()
        except Exception:
            im = None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
        try:
            raw = Image.open(path)
            if raw.mode in ("RGBA", "LA", "P"):
                raw = raw.convert("RGBA")
                bg = Image.new("RGBA", raw.size, (90, 90, 90, 255))
                bg.alpha_composite(raw)
                raw = bg
            im = raw.convert("RGB")
        except Exception:
            im = None
    if im is None:
        im = Image.new("RGB", size, (60, 60, 60))
    im.thumbnail(size)
    return im


def contact_sheet(entries: Sequence[Dict[str, Any]], out_png: Any, cols: int = 5, thumb: Any = (256, 144), lib: Any = None) -> Path:
    from PIL import Image, ImageDraw
    r = _root(lib)
    entries = list(entries)
    cols = max(1, min(cols, max(1, len(entries))))
    rows = max(1, -(-len(entries) // cols))
    tw, th = thumb
    cw, ch = tw + 12, th + 48
    sheet = Image.new("RGB", (cols * cw, rows * ch), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for i, e in enumerate(entries):
        x, y = (i % cols) * cw, (i // cols) * ch
        t = _thumb(r / e["path"], thumb)
        sheet.paste(t, (x + 6 + (tw - t.width) // 2, y + 6 + (th - t.height) // 2))
        mark = "APPROVED" if e.get("approved") else ("REJECTED" if e.get("rejected") else "pending")
        col = (80, 220, 120) if e.get("approved") else ((230, 90, 90) if e.get("rejected") else (230, 200, 80))
        d.text((x + 6, y + th + 8), str(e["id"])[:38], fill=(235, 235, 235))
        d.text((x + 6, y + th + 20), str(e.get("credit") or e.get("source") or "")[:40], fill=(160, 160, 170))
        d.text((x + 6, y + th + 32), mark + (" AI" if e.get("ai") else ""), fill=col)
        if e.get("approved"):
            d.rectangle([x + 4, y + 4, x + cw - 6, y + th + 8], outline=col, width=2)
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


# ------------------------------------------------------------------------------------------------------------------ stats / build list

def stats(lib: Any = None) -> Dict[str, Any]:
    ents = _load(_root(lib))["entries"]
    by_kind: Dict[str, int] = {}
    by_air: Dict[str, int] = {}
    for e in ents:
        if e.get("rejected"):
            continue
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        by_air[e["airline"]] = by_air.get(e["airline"], 0) + 1
    return {"total": len(ents), "approved": sum(1 for e in ents if e.get("approved")),
            "rejected": sum(1 for e in ents if e.get("rejected")), "by_kind": by_kind, "by_airline": by_air}


def _items(v: Any) -> List[Any]:
    if not v:
        return []
    if isinstance(v, dict):
        return [dict(val, **({"name": k} if isinstance(val, dict) else {})) if isinstance(val, dict) else {"name": k, "value": val}
                for k, val in v.items()]
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


def _g(d: Any, *keys: str) -> str:
    if isinstance(d, str):
        return d
    if isinstance(d, dict):
        for k in keys:
            if d.get(k):
                return str(d[k])
    return ""


def build_list(bible: Optional[Dict[str, Any]], lib: Any = None) -> List[Dict[str, Any]]:
    """What the film needs that the library does not hold (approved) yet. Lenient: any of fleet / liveries / cast / places may be
    missing or shaped as list-of-dicts, dict-of-dicts or plain strings."""
    b = bible or {}
    needs: List[Dict[str, Any]] = []
    seen = set()

    def need(kind: str, airline: str, era: str, subject: str, prompt: str = "") -> None:
        airline, era, subject = _slug(airline, "generic") if airline else "", _slug(era, "any") if era else "", str(subject or "").strip()
        key = (kind, airline, era, _norm(subject))
        if key in seen or not subject:
            return
        seen.add(key)
        if find(kind, airline=airline or None, era=era or None, subject=subject, lib=lib):
            exact = [e for e in find(kind, airline=airline or None, era=era or None, subject=subject, lib=lib)
                     if (not airline or e["airline"] == airline) and (not era or e["era"] in (era, "any"))]
            if exact:
                return
        item = {"kind": kind, "airline": airline or "generic", "era": era or "any", "subject": subject}
        if prompt:
            item["prompt"] = prompt
        needs.append(item)

    for f in _items(b.get("fleet")):
        airline = _g(f, "airline", "airline_id", "operator")
        aircraft = _g(f, "aircraft", "type", "subject", "name")
        era = _g(f, "era") or (era_of(_g(f, "year", "from", "introduced")) if _g(f, "year", "from", "introduced") else "")
        livery = _g(f, "livery", "livery_notes")
        if not aircraft:
            continue
        pr = f"{aircraft} in {airline} livery" + (f", {livery}" if livery else "") + (f", {era}" if era else "")
        need("hero", airline, era, aircraft, pr)
        need("sticker", airline, era, aircraft, pr)
    for f in _items(b.get("liveries")):
        airline = _g(f, "airline", "airline_id")
        aircraft = _g(f, "aircraft", "type", "subject")
        era = _g(f, "era")
        if airline and aircraft:
            need("hero", airline, era, aircraft, f"{aircraft} in {airline} livery {_g(f, 'livery', 'notes', 'livery_notes')}".strip())
    for c in _items(b.get("cast")):
        role = _g(c, "role", "name", "subject")
        need("cast", _g(c, "airline", "airline_id"), _g(c, "era"), role, f"{role}, {_g(c, 'look', 'description', 'prompt')}".strip(", "))
    for p in _items(b.get("places")):
        name = _g(p, "name", "airport", "city", "subject")
        need("place", _g(p, "airline", "airline_id"), _g(p, "era"), name, f"{name} {_g(p, 'landmark', 'landmarks', 'description')}".strip())
    return needs


def needs_from_bible(bible: Any, lib: Any = None) -> List[Dict[str, Any]]:
    """The film's make-once list from the bible (aviation.bible.Bible or its dict): hero aircraft per airline x era, cast sheets
    per role, place plates per airport, each with its Flow prompt (aviation.flow_prompts). Items the library already holds approved
    (same kind, airline, era, subject) are left out. Eras are the bible's (pre1960, 1960s, 1970s, ...)."""
    from . import bible as BB
    from . import flow_prompts as FP
    b = BB.Bible.from_dict(bible) if isinstance(bible, dict) else bible
    out: List[Dict[str, Any]] = []
    for h in FP.hero_list(b):
        item = {"kind": "hero", "airline": h["airline"], "era": h["era"], "subject": h.get("aircraft") or "", "prompt": h["prompt"],
                "ref_id": h["id"], "assumed": bool(h.get("assumed"))}
        out.append(item)
        out.append(dict(item, kind="sticker", ref_id=h["id"].replace("hero:", "sticker:", 1)))
    for c in FP.cast_list(b):
        out.append({"kind": "cast", "airline": c.get("airline") or "generic", "era": c.get("era") or "any", "subject": c["role"],
                    "prompt": c["prompt"], "ref_id": c["id"]})
    for p in FP.place_list(b):
        out.append({"kind": "place", "airline": "generic", "era": p.get("era") or "any", "subject": p["airport"], "prompt": p["prompt"],
                    "ref_id": p["id"]})
    def have(n: Dict[str, Any]) -> bool:          # an approved item of exactly this airline and era (find() ranks looser ones too)
        return any(e.get("airline") == n["airline"] and e.get("era") == n["era"]
                   for e in find(n["kind"], airline=n["airline"], era=n["era"], subject=n["subject"], lib=lib))
    return [n for n in out if not have(n)]
