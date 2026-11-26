"""Agent Kit: the small set of tools an AI (Claude, Gemini) uses to make a video itself from a script and a voiceover.

    align(project, voice, script)      voice -> words and sentences with times
    find(project, query, kind)         stock video / photo (Pexels) or a Wikimedia photo, downloaded into the project
    scene(project, name, ...)          an HTML scene the AI wrote (window.renderAt(t)) -> clip; or a video/photo -> clip
    look(path)                         a contact sheet of a clip (or stills of an HTML scene) to check the work
    join(project, clips, voice, ...)   clips + voice + music + sound effects -> final.mp4 at -14 LUFS

Every clip is 1920x1080 (or the project's size), 30 fps, H.264, cut to its exact length, so join only concatenates.
A project is a folder: voice/, media/, scenes/, clips/, look/ and final.mp4 live inside it."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SFX_ROOT = Path.home() / ".videogen" / "sfx"
MUSIC_ROOT = REPO / "assets" / "music"
UA = "VideoGenerator/1.0 (agent kit; contact via project page)"
W, H, FPS = 1920, 1080, 30


def _project(project: str) -> Path:
    p = Path(project).expanduser().resolve()
    for sub in ("voice", "media", "scenes", "clips", "look"):
        (p / sub).mkdir(parents=True, exist_ok=True)
    return p


def _run(cmd: list, timeout: int = 3600) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} failed: " + (r.stderr or r.stdout).strip()[-800:])
    return r.stdout


def duration(path: str | Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip() or 0)


_probe = duration      # scene() has a `duration` argument, so it calls this name


def _settings() -> dict:
    try:
        return json.loads((Path.home() / ".videogen" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---- align ------------------------------------------------------------------------------------------------------

def align(project: str, voice: str, script: str = "", language: str = "") -> str:
    """Transcribe the voice with word times. Writes voice/words.json and voice/sentences.json; returns the sentences."""
    P = _project(project)
    src = Path(voice).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"no voice file: {src}")
    dst = P / "voice" / ("voice" + src.suffix.lower())
    if src != dst:
        shutil.copyfile(src, dst)
    script_text = ""
    if script:
        sp = Path(script).expanduser()
        script_text = sp.read_text(encoding="utf-8") if sp.exists() else script
        (P / "voice" / "script.txt").write_text(script_text, encoding="utf-8")
    sys.path.insert(0, str(REPO))
    from whisper_backend import transcribe
    kw = {"word_timestamps": True}
    if language:
        kw["language"] = language
    # No initial_prompt: a long script prompt makes mlx-whisper (Apple GPU) invent a different text with wrong times.
    # The script is used AFTER transcription instead, to fix spellings and punctuation word by word (times kept).
    segs, _info = transcribe(str(dst), "small", log=lambda *_: None, **kw)
    words = []
    for s in segs:
        for w in (s.words or []):
            words.append({"w": w.word.strip(), "s": round(float(w.start), 3), "e": round(float(w.end), 3)})
    match = _respell(words, script_text) if script_text else None
    sentences, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?…]['\"”’)]?$", w["w"]):
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    sent = [{"n": i + 1, "start": c[0]["s"], "end": c[-1]["e"], "text": " ".join(x["w"] for x in c)} for i, c in enumerate(sentences)]
    total = duration(dst)
    (P / "voice" / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    (P / "voice" / "sentences.json").write_text(json.dumps({"voice": str(dst), "duration": total, "sentences": sent},
                                                           ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"voice {dst}  length {total:.2f}s  {len(words)} words  {len(sent)} sentences",
             f"word times: {P / 'voice' / 'words.json'}"]
    if match is not None:
        lines.insert(1, f"script match {match:.0%}" + ("  WARNING: the voice does not follow the script well; check the times"
                                                       if match < 0.6 else ""))
    lines += [f"{s['n']:>3}  {s['start']:7.2f}-{s['end']:7.2f}  {s['text']}" for s in sent]
    return "\n".join(lines)


def _respell(words: list, script_text: str) -> float:
    """Replace heard words with the script's words where they line up (same count in a block), so names, numbers and
    sentence punctuation come from the script while the times stay Whisper's. Returns the share of words matched."""
    import difflib
    norm = lambda s: re.sub(r"[^\w]", "", s.lower())
    sw = script_text.split()
    a, b = [norm(w["w"]) for w in words], [norm(x) for x in sw]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    same = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            same += i2 - i1
        if op in ("equal", "replace") and i2 - i1 == j2 - j1:
            for i, j in zip(range(i1, i2), range(j1, j2)):
                words[i]["w"] = sw[j]
    return same / max(1, len(b))


# ---- find -------------------------------------------------------------------------------------------------------

def _get(url: str, **kw):
    import requests
    r = requests.get(url, timeout=(15, 60), headers={"User-Agent": UA, **kw.pop("headers", {})}, **kw)
    r.raise_for_status()
    return r


def _download(url: str, dst: Path, headers: dict | None = None, max_mb: int = 400) -> Path:
    """Download to <dst>.part, then rename: a broken connection never leaves a half file that looks finished.
    One retry on a dropped connection."""
    import requests
    part = dst.with_name(dst.name + ".part")
    for attempt in (1, 2):
        try:
            with requests.get(url, stream=True, timeout=(15, 120), headers={"User-Agent": UA, **(headers or {})}) as r:
                r.raise_for_status()
                n = 0
                with open(part, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        n += len(chunk)
                        if n > max_mb << 20:
                            raise IOError(f"file over {max_mb} MB")
                        fh.write(chunk)
            part.replace(dst)
            return dst
        except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.Timeout):
            part.unlink(missing_ok=True)
            if attempt == 2:
                raise
        except Exception:
            part.unlink(missing_ok=True)
            raise
    return dst


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "item"


def find(project: str, query: str, kind: str = "video", count: int = 3, min_seconds: float = 0) -> str:
    """kind: video | photo (Pexels) | wiki (Wikimedia Commons photo: people, places, history, science).
    Downloads up to `count` results into media/ and lists them with size, length and source."""
    P = _project(project)
    kind = (kind or "video").lower()
    out = []
    if kind in ("video", "photo"):
        key = os.environ.get("PEXELS_API_KEY") or _settings().get("pexels_api_key", "")
        if not key:
            raise RuntimeError("no Pexels key: add it in the app's settings or set PEXELS_API_KEY")
        hdr = {"Authorization": key}
        if kind == "video":
            data = _get("https://api.pexels.com/videos/search", headers=hdr,
                        params={"query": query, "per_page": 15, "orientation": "landscape", "size": "medium"}).json()
            for v in data.get("videos", []):
                if len(out) >= count:
                    break
                if (v.get("duration") or 0) < min_seconds:
                    continue
                files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and (f.get("height") or 0) >= 720]
                if not files:
                    continue
                f = min(files, key=lambda f: abs((f.get("height") or 0) - 1080))   # the 1080p file, not 4K
                dst = P / "media" / f"{_slug(query)}_pexels{v['id']}.mp4"
                if not dst.exists():
                    _download(f["link"], dst)
                out.append(f"{dst}  video {f.get('width')}x{f.get('height')} {v.get('duration')}s  pexels.com/video/{v['id']} by {v.get('user', {}).get('name', '')}")
        else:
            data = _get("https://api.pexels.com/v1/search", headers=hdr,
                        params={"query": query, "per_page": 15, "orientation": "landscape"}).json()
            for ph in data.get("photos", [])[:count]:
                dst = P / "media" / f"{_slug(query)}_pexels{ph['id']}.jpg"
                if not dst.exists():
                    _download(ph["src"].get("large2x") or ph["src"]["original"], dst)
                out.append(f"{dst}  photo {ph.get('width')}x{ph.get('height')}  pexels.com/photo/{ph['id']} by {ph.get('photographer', '')}")
    elif kind == "wiki":
        api = "https://commons.wikimedia.org/w/api.php"
        data = _get(api, params={"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
                                 "gsrnamespace": 6, "gsrlimit": 12, "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime",
                                 "iiurlwidth": 1920}).json()
        pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        for pg in pages:
            if len(out) >= count:
                break
            ii = (pg.get("imageinfo") or [{}])[0]
            if ii.get("mime") not in ("image/jpeg", "image/png") or (ii.get("width") or 0) < 400:
                continue
            meta = ii.get("extmetadata") or {}
            lic = re.sub(r"<[^>]+>", "", (meta.get("LicenseShortName") or {}).get("value", ""))
            artist = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", ""))[:60]
            ext = ".png" if ii.get("mime") == "image/png" else ".jpg"
            dst = P / "media" / f"{_slug(query)}_wiki{pg['pageid']}{ext}"
            if not dst.exists():
                _download(ii.get("thumburl") or ii["url"], dst)
            out.append(f"{dst}  photo {ii.get('width')}x{ii.get('height')}  {lic}  {artist}  {ii.get('descriptionurl', '')}")
    else:
        raise ValueError("kind must be video, photo or wiki")
    if not out:
        return f"nothing found for '{query}' ({kind}); try other words"
    (P / "media" / "CREDITS.txt").open("a", encoding="utf-8").write("\n".join(out) + "\n")
    return "\n".join(out)


# ---- scene ------------------------------------------------------------------------------------------------------

GRADES = {
    "": "",
    "none": "",
    "doc_teal": "eq=contrast=1.05:saturation=0.82:brightness=-0.02,colorbalance=rs=-0.05:gs=0.01:bs=0.06:rm=-0.03:bm=0.04,vignette=PI/5",
    "warm": "eq=contrast=1.04:saturation=1.05,colorbalance=rs=0.05:bs=-0.04,vignette=PI/5",
    "bw": "hue=s=0,eq=contrast=1.12,vignette=PI/5",
}


def _encode_args(out: Path) -> list:
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an",
            "-movflags", "+faststart", str(out)]


def _scene_words(P: Path, name: str, at: float | None, dur: float) -> list:
    """The voice's words inside [at, at + dur], with times relative to the scene start: given to the page as window.WORDS."""
    wf = P / "voice" / "words.json"
    if at is None or not wf.exists():
        return []
    words = json.loads(wf.read_text(encoding="utf-8"))
    rel = [{"w": w["w"], "s": round(w["s"] - at, 3), "e": round(w["e"] - at, 3)} for w in words if at - 0.05 <= w["s"] < at + dur]
    f = P / "clips" / f".words_{_slug(name)}.json"
    f.write_text(json.dumps(rel, ensure_ascii=False), encoding="utf-8")
    return ["--words", str(f)]


# ---- short scene files ------------------------------------------------------------------------------------------
# A scene file may hold ONLY the scene's script (no <html>, <head>, layers or imports): the kit wraps it in the look pack's
# page. Fewer lines for the AI to write per scene = fewer credits. Layers: #cam (camera: svg #s + div #h inside), svg #tags
# (outside the camera: date tags, counters), #fl flash, vignette, grain.
_PACK_IMPORTS = {
    "doc_teal": "",
    "history_toon": ("import * as H from '/agent_kit/looks/history_toon/props.js';\n"
                     "import { P, shade } from '/agent_kit/looks/history_toon/palette.js';\n"
                     "import { person, personAt, OUTFITS } from '/agent_kit/looks/history_toon/person.js';\n"),
    "doodle_dark": ("import { hero, heroAt, SPEED } from '/agent_kit/looks/doodle_dark/hero.js';\n"
                    "import * as L from '/agent_kit/looks/doodle_dark/light.js';\n"
                    "import { P } from '/agent_kit/looks/doodle_dark/palette.js';\n"),
}
SHORT_FORM_NAMES = {"doc_teal": "K", "history_toon": "K, H, P, shade, person, personAt, OUTFITS",
                    "doodle_dark": "K, hero, heroAt, SPEED, L (light.js), P"}


def _pack_of(P: Path) -> str:
    try:
        lk = str(json.loads((P / "plan.json").read_text(encoding="utf-8")).get("look", "")).strip()
    except Exception:
        lk = ""
    return lk if lk in _PACK_IMPORTS else "doc_teal"


def _page(hp: Path, P: Path | None = None) -> Path:
    """The page to render: the file itself when it is a full HTML page, else a wrapped copy next to it (scenes/.<name>.full.html)."""
    src = hp.read_text(encoding="utf-8")
    head = src.lstrip()[:200].lower()
    if head.startswith("<") or "<html" in head:
        return hp
    pack = _pack_of(P if P is not None else hp.parent.parent)
    over = "over" if "// overlay" in src[:200].lower() else ""
    page = (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/agent_kit/looks/{pack}/look.css"></head>\n'
            f'<body class="{over}"><div id="cam" class="abs" style="inset:0;transform-origin:50% 50%"><svg id="s" width="{W}" height="{H}" '
            f'class="abs" style="inset:0"></svg><div id="h" class="abs" style="inset:0"></div></div>\n'
            f'<svg id="tags" width="{W}" height="{H}" class="abs" style="inset:0"></svg><div class="flash" id="fl"></div>'
            + ("" if over else '<div class="vignette"></div><div class="grain"></div>') + '\n'
            "<script type=\"module\">\nimport * as K from '/agent_kit/lib/kit.js';\n" + _PACK_IMPORTS[pack] +
            "window.sceneReady = document.fonts.ready;\n" + src + "\n</script></body></html>\n")
    out = hp.with_name(f".{hp.stem}.full.html")
    if not out.exists() or out.read_text(encoding="utf-8") != page:
        out.write_text(page, encoding="utf-8")
    return out


def scene(project: str, name: str, duration: float, html: str = "", media: str = "", start: float = 0.0,
          zoom: float = 1.08, pan: str = "center", grade: str = "doc_teal", overlay_html: str = "", workers: int = 3,
          at: float | None = None) -> str:
    """Make clips/<name>.mp4, exactly `duration` seconds.
    html: an HTML scene file (scenes/<name>.html) defining window.renderAt(t).
    media: a video (cut from `start`) or a photo (slow Ken Burns move to `zoom`, pan left|right|up|down|center).
    overlay_html: a transparent HTML page drawn over the media (labels, lower thirds).
    at: where this scene starts in the film (voice seconds): the page then gets window.WORDS, its spoken words with
    scene-relative times, so K.when('word') syncs a reveal to the narrator."""
    P = _project(project)
    out = P / "clips" / f"{_slug(name)}.mp4"
    dur = float(duration)
    if dur <= 0:
        raise ValueError("duration must be > 0")
    if html:
        hp = Path(html).expanduser()
        hp = hp if hp.is_absolute() else P / "scenes" / hp
        if not hp.exists():
            raise FileNotFoundError(f"no scene file: {hp}")
        hp = _page(hp, P)
        r = subprocess.run(["node", str(HERE / "scene.mjs"), "--html", str(hp), "--out", str(out), "--duration", f"{dur:.3f}",
                            "--fps", str(FPS), "--w", str(W), "--h", str(H), "--workers", str(workers), *_scene_words(P, name, at, dur)],
                           capture_output=True, text=True, timeout=3600)
        events = [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]
        last = events[-1] if events else {"event": "error", "message": r.stderr[-600:]}
        if last.get("event") != "done":
            raise RuntimeError(last.get("message", "scene failed"))
        note = f"  page errors: {last['errors']}" if last.get("errors") else ""
        return f"{out}  {_probe(out):.2f}s  drawn in {last.get('seconds')}s{note}"
    if not media:
        raise ValueError("give html or media")
    mp = Path(media).expanduser().resolve()
    if not mp.exists():
        raise FileNotFoundError(f"no media file: {mp}")
    g = GRADES.get(grade, grade or "")
    is_photo = mp.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    base = out if not overlay_html else P / "clips" / f".{_slug(name)}_base.mp4"
    fill = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if is_photo:
        n = max(1, round(dur * FPS))
        # Ken Burns on a 2x-sized frame so the move is smooth (zoompan works in whole pixels)
        px = {"left": f"(iw-iw/zoom)*(1-on/{n})", "right": f"(iw-iw/zoom)*on/{n}"}.get(pan, "iw/2-(iw/zoom/2)")
        py = {"up": f"(ih-ih/zoom)*(1-on/{n})", "down": f"(ih-ih/zoom)*on/{n}"}.get(pan, "ih/2-(ih/zoom/2)")
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='1+({zoom}-1)*on/{n}':x='{px}':y='{py}':d={n}:s={W}x{H}:fps={FPS}")
        vf += ("," + g) if g else ""
        _run(["ffmpeg", "-hide_banner", "-y", "-loop", "1", "-i", str(mp), "-vf", vf, "-frames:v", str(n), *_encode_args(base)])
    else:
        have = _probe(mp)
        if have - start < dur - 0.05:
            # too short: slow it down a little (up to 1.5x) rather than freeze
            slow = min(1.5, dur / max(0.1, have - start))
            vf = f"setpts={slow:.4f}*PTS,{fill},fps={FPS}"
        else:
            vf = f"{fill},fps={FPS}"
        vf += ("," + g) if g else ""
        _run(["ffmpeg", "-hide_banner", "-y", "-ss", f"{start:.3f}", "-i", str(mp), "-vf", vf, "-t", f"{dur:.3f}", *_encode_args(base)])
    if overlay_html:
        hp = Path(overlay_html).expanduser()
        hp = _page(hp if hp.is_absolute() else P / "scenes" / hp, P)
        r = subprocess.run(["node", str(HERE / "scene.mjs"), "--html", str(hp), "--over", str(base), "--out", str(out),
                            "--duration", f"{dur:.3f}", "--fps", str(FPS), "--w", str(W), "--h", str(H), "--workers", str(workers),
                            *_scene_words(P, name, at, dur)],
                           capture_output=True, text=True, timeout=3600)
        events = [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]
        if not events or events[-1].get("event") != "done":
            raise RuntimeError((events[-1] if events else {}).get("message") or r.stderr[-600:])
        base.unlink(missing_ok=True)
    return f"{out}  {_probe(out):.2f}s"


def render_all(project: str, workers: int = 3) -> str:
    """Render every drawn scene in plan.json (scenes/<name>.html, timed by its start/end) in ONE call. A clip newer than
    its scene file, scenes/common.js and the word times is kept, so call it again after fixing a few scenes."""
    P = _project(project)
    plan = json.loads((P / "plan.json").read_text(encoding="utf-8"))
    common = [f for f in (P / "scenes").glob("*.js")] + [P / "voice" / "words.json"]
    newest_dep = max((f.stat().st_mtime for f in common if f.exists()), default=0)
    lines, made, kept = [], 0, 0
    for sc in plan.get("scenes", []):
        name = sc.get("name", "")
        hp = P / "scenes" / (sc.get("html") or f"{name}.html")
        if sc.get("kind", "graphic") != "graphic" or not hp.exists():
            if sc.get("kind", "graphic") == "graphic":
                lines.append(f"MISSING {name}: no {hp.name}")
            continue
        dur = round(float(sc["end"]) - float(sc["start"]), 3)
        out = P / "clips" / f"{_slug(name)}.mp4"
        if out.exists() and out.stat().st_mtime > max(hp.stat().st_mtime, newest_dep) and abs(_probe(out) - dur) < 0.06:
            kept += 1
            continue
        try:
            lines.append(scene(project, name, dur, html=str(hp), at=float(sc["start"]), workers=workers))
            made += 1
        except Exception as exc:                          # one broken scene never stops the others
            lines.append(f"FAILED {name}: {exc}")
    return f"rendered {made}, kept {kept} unchanged\n" + "\n".join(lines)


# ---- map --------------------------------------------------------------------------------------------------------

def map_svg(project: str, name: str, west: float, south: float, east: float, north: float, width: int = W, height: int = H,
            countries: bool = True) -> str:
    """A sharp vector map of a region (Mercator, fitted to width x height): scenes/<name>.svg with land as <path id="land">
    and country borders as <path id="borders">, plus scenes/<name>.json with the projection. In a scene:
    const proj = await (await fetch('/@scene/<name>.json')).json();  const [x, y] = K.lonlat(proj, lon, lat);"""
    import gzip
    import math
    P = _project(project)
    data = REPO / "map_scene" / "data"
    mx = lambda lon: math.radians(lon)                                                   # noqa: E731
    my = lambda lat: math.log(math.tan(math.pi / 4 + math.radians(max(-85, min(85, lat))) / 2))   # noqa: E731
    x0, x1, y0, y1 = mx(west), mx(east), my(south), my(north)
    s = min(width / (x1 - x0), height / (y1 - y0))
    ox, oy = (width - s * (x1 - x0)) / 2, (height - s * (y1 - y0)) / 2
    proj = {"type": "mercator", "west": west, "south": south, "east": east, "north": north, "scale": s, "ox": ox, "oy": oy,
            "x0": x0, "y1": y1, "width": width, "height": height}

    def pt(lon, lat):
        return ((mx(lon) - x0) * s + ox, (y1 - my(lat)) * s + oy)

    pad = 3.0

    def rings(geom):
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            for ring in poly:
                lons = [c[0] for c in ring]
                lats = [c[1] for c in ring]
                if max(lons) < west - pad or min(lons) > east + pad or max(lats) < south - pad or min(lats) > north + pad:
                    continue
                yield ring

    def path_of(feats):
        out = []
        for g in feats:
            for ring in rings(g):
                pts, last = [], None
                for lon, lat in ring:
                    # points far outside the frame are pulled to its padded edge: same picture, a fraction of the size
                    x, y = pt(min(max(lon, west - pad), east + pad), min(max(lat, south - pad), north + pad))
                    q = (round(x, 1), round(y, 1))
                    if q != last:
                        pts.append(q)
                        last = q
                if len(pts) > 2:
                    out.append("M" + "L".join(f"{x:g},{y:g}" for x, y in pts) + "Z")
        return "".join(out)

    land = path_of(f["g"] for f in json.load(gzip.open(data / "land.json.gz"))["features"])
    borders = path_of(f["g"] for f in json.load(gzip.open(data / "countries.json.gz"))["features"]) if countries else ""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
           f'<path id="land" d="{land}"/>' + (f'<path id="borders" d="{borders}" fill="none"/>' if borders else "") + "</svg>")
    (P / "scenes" / f"{name}.svg").write_text(svg, encoding="utf-8")
    (P / "scenes" / f"{name}.json").write_text(json.dumps(proj), encoding="utf-8")
    kb = len(svg) // 1024
    return (f"{P / 'scenes' / (name + '.svg')} ({kb} KB) and {name}.json (projection). Inline the SVG with fetch('/@scene/{name}.svg') "
            f"or use it as <img>; style #land (fill) and #borders (stroke). Place things with K.lonlat(proj, lon, lat).")


# ---- terrain (real 3D relief, land and seafloor) ---------------------------------------------------------------

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TILE_CACHE = Path.home() / ".videogen" / "terrarium"


def terrain(project: str, name: str, west: float, south: float, east: float, north: float, zoom: int = 6) -> str:
    """Real elevation of a region, land AND seafloor (Terrarium tiles, cached in ~/.videogen/terrarium), into
    scenes/<name>_dem.png (Terrarium-encoded, Web-Mercator, cropped to the box) + scenes/<name>_dem.json.
    Draw it with /agent_kit/looks/doc_teal/terrain3d.js (makeTerrain): 3D relief with a water level you can move
    (drain or flood a sea), lighting, and screen positions for pins. zoom 5-8: 6 suits a sea or a country."""
    import math
    from PIL import Image
    P = _project(project)
    TILE_CACHE.mkdir(parents=True, exist_ok=True)

    def tx(lon, z):
        return (lon + 180) / 360 * 2 ** z

    def ty(lat, z):
        r = math.radians(lat)
        return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** z

    z = int(zoom)
    x0, x1 = tx(west, z), tx(east, z)
    y0, y1 = ty(north, z), ty(south, z)
    tiles = [(x, y) for x in range(int(x0), int(math.ceil(x1))) for y in range(int(y0), int(math.ceil(y1)))]
    if len(tiles) > 400:
        raise ValueError(f"{len(tiles)} tiles: use a lower zoom or a smaller box")
    canvas = Image.new("RGB", ((int(math.ceil(x1)) - int(x0)) * 256, (int(math.ceil(y1)) - int(y0)) * 256))
    for x, y in tiles:
        f = TILE_CACHE / f"{z}_{x}_{y}.png"
        if not f.exists():
            _download(TILE_URL.format(z=z, x=x, y=y), f, max_mb=5)
        canvas.paste(Image.open(f).convert("RGB"), ((x - int(x0)) * 256, (y - int(y0)) * 256))
    box = (round((x0 - int(x0)) * 256), round((y0 - int(y0)) * 256), round((x1 - int(x0)) * 256), round((y1 - int(y0)) * 256))
    img = canvas.crop(box)
    img.save(P / "scenes" / f"{name}_dem.png")
    px = img.load()
    lo, hi = 1e9, -1e9
    for j in range(0, img.height, 4):
        for i in range(0, img.width, 4):
            r, g, b = px[i, j]
            e = r * 256 + g + b / 256 - 32768
            lo, hi = min(lo, e), max(hi, e)
    meta = {"west": west, "south": south, "east": east, "north": north, "zoom": z, "width": img.width, "height": img.height,
            "min": round(lo), "max": round(hi), "mx0": x0, "my0": y0, "mx1": x1, "my1": y1}
    (P / "scenes" / f"{name}_dem.json").write_text(json.dumps(meta), encoding="utf-8")
    return (f"{P / 'scenes' / (name + '_dem.png')} {img.width}x{img.height}, {len(tiles)} tiles, elevation {meta['min']} to "
            f"{meta['max']} m. Use: const T = await makeTerrain(canvas, '/@scene/{name}_dem'); T.render({{water, cam}}); "
            f"T.screen(lon, lat) for pins.")


# ---- check_plan -------------------------------------------------------------------------------------------------

_NUM_WORDS = set("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
                 "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion "
                 "trillion half dozen percent".split())
_SMALL = set("a an the and or but so of to in on at by for from with as is are was were be been it its this that these those "
             "he she they we you i his her their our my your not no".split())


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def _named(words: list) -> list:
    """Words a viewer expects to see: proper names (capitalised, not starting a sentence), digits and number words.
    Neighbouring ones are joined ("Mikhail Budyko", "fifty seven million")."""
    out, cur, prev_end = [], [], True
    for w in words:
        raw = w["w"].strip()
        tok = _norm(raw)
        named = bool(tok) and (re.search(r"\d", tok) or tok in _NUM_WORDS or (raw[:1].isupper() and not prev_end and tok not in _SMALL))
        if not named and tok == "and" and cur and _norm(cur[-1]) in _NUM_WORDS:
            named = True                                     # "seven hundred and seventeen" stays one number
        if named:
            cur.append(raw.strip(",.;:!?\"'”“’"))
        elif cur:
            out.append(" ".join(cur)); cur = []
        prev_end = bool(re.search(r"[.!?…]['\"”’)]?$", raw))
    if cur:
        out.append(" ".join(cur))
    return [x for x in out if _norm(x) not in ("one", "i")]


_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                     "fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"thousand": 10 ** 3, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12}


def _as_numbers(item: str) -> set:
    """'seven hundred and seventeen million' -> {'717000000', '717'}: the digits a screen would show for it."""
    total = cur = 0
    seen = False
    for t in (_norm(x) for x in item.split()):
        if t in _UNITS:
            cur += _UNITS[t]; seen = True
        elif t in _TENS:
            cur += _TENS[t]; seen = True
        elif t == "hundred":
            cur = max(cur, 1) * 100; seen = True
        elif t in _SCALES:
            total += max(cur, 1) * _SCALES[t]; cur = 0; seen = True
        elif t.isdigit():
            cur += int(t); seen = True
    if not seen:
        return set()
    v = total + cur
    out = {str(v)}
    for sc in (10 ** 12, 10 ** 9, 10 ** 6, 10 ** 3):
        if v >= sc and v % sc == 0:
            out.add(str(v // sc))
    return out


def _shown(item: str, shows: list) -> bool:
    toks = [_norm(t) for t in item.split() if _norm(t)]
    blob = " ".join(_norm(s) for s in " ".join(shows).split())
    if any(n in blob.split() for n in _as_numbers(item)):
        return True
    return any(t in blob or (len(t) > 4 and t[:5] in blob) for t in toks)


def check_plan(project: str) -> str:
    """Check <project>/plan.json against the voice before any scene is made: timing (gaps, overlaps, coverage, scene
    lengths), graphics share, bare footage, hooks on spoken words, and names/places/numbers that are said but not shown.
    Also prints each scene's spoken words next to what it shows, to check animals and objects by eye."""
    P = _project(project)
    pf = P / "plan.json"
    if not pf.exists():
        raise FileNotFoundError(f"no plan: write {pf} first (format in the guide)")
    plan = json.loads(pf.read_text(encoding="utf-8"))
    words = json.loads((P / "voice" / "words.json").read_text(encoding="utf-8")) if (P / "voice" / "words.json").exists() else []
    meta = P / "voice" / "sentences.json"
    vlen = json.loads(meta.read_text())["duration"] if meta.exists() else (words[-1]["e"] if words else 0)
    scenes = sorted(plan.get("scenes", []), key=lambda s: float(s.get("start", 0)))
    probs, rows = [], []
    story = plan.get("story") or {}
    if not story.get("question") or len(story.get("beats") or []) < 3:
        probs.append("story: write the question the video answers and at least 3 beats (hook, turns, payoff)")
    if not scenes:
        return "no scenes in plan.json"
    if abs(float(scenes[0]["start"])) > 0.05:
        probs.append(f"timing: the first scene starts at {scenes[0]['start']}, not 0")
    total = graphics = 0.0
    for i, s in enumerate(scenes):
        name, a, b = s.get("name", f"#{i + 1}"), float(s["start"]), float(s["end"])
        d = b - a
        total += max(0, d)
        kind = s.get("kind", "graphic")
        if kind == "graphic" or (kind in ("footage", "photo") and s.get("overlay")):
            graphics += d if kind == "graphic" else d * 0.5
        if i + 1 < len(scenes) and abs(float(scenes[i + 1]["start"]) - b) > 0.05:
            gap = float(scenes[i + 1]["start"]) - b
            probs.append(f"{name}: {'gap' if gap > 0 else 'overlap'} of {abs(gap):.2f}s before {scenes[i + 1].get('name')}")
        if d < 1.5:
            probs.append(f"{name}: {d:.2f}s is too short to read; merge it with a neighbour")
        if d > (8.0 if kind == "graphic" else 6.0):
            probs.append(f"{name}: {d:.2f}s is too long for one {kind} scene; split it or add new events every 2-3 s")
        if kind in ("footage", "photo") and not s.get("overlay") and d > 2.5:
            probs.append(f"{name}: bare {kind} for {d:.2f}s; add an overlay (label, number, pin, caption)")
        shows = [str(x) for x in s.get("shows") or []]
        if not shows:
            probs.append(f"{name}: `shows` is empty; list what is on screen in the narration's words")
        said = [w for w in words if a - 0.05 <= w["s"] < b]
        spoken = {_norm(w["w"]) for w in said}
        hooks = s.get("hooks") or []
        if kind == "graphic" and len(hooks) < 2:
            probs.append(f"{name}: {len(hooks)} hook move(s); a graphic needs at least 2 on spoken words")
        for h in hooks:
            word = str(h).split(":", 1)[-1].strip()
            if word and not any(_norm(word) == x or (len(_norm(word)) > 3 and x.startswith(_norm(word))) for x in spoken):
                probs.append(f"{name}: hook '{h}' is on a word not spoken in this scene")
        nxt = scenes[i + 1].get("shows") or [] if i + 1 < len(scenes) else []
        for item in _named(said):
            if not _shown(item, shows) and not _shown(item, [str(x) for x in nxt]):
                probs.append(f"{name}: says '{item}' but does not show it")
        rows.append(f"{name:<18} {a:6.2f}-{b:6.2f} {kind:<8} says: {' '.join(w['w'] for w in said)[:110]}\n"
                    f"{'':<41}shows: {', '.join(shows)}")
    end = float(scenes[-1]["end"])
    if plan.get("end"):                                  # a part of the voice only (a test or one section): its own end
        if end < float(plan["end"]) - 0.05:
            probs.append(f"timing: the last scene ends at {end:.2f}s, before the plan's end {plan['end']}s")
    elif end < vlen + 0.3:
        probs.append(f"timing: the last scene ends at {end:.2f}s but the voice runs to {vlen:.2f}s (end at voice + 1 s)")
    share = graphics / total if total else 0
    if share < 0.7:
        probs.append(f"graphics: {share:.0%} of the runtime is graphics (half credit for footage with an overlay); aim for 70 %+")
    for i in range(1, len(scenes)):
        if scenes[i].get("type") and scenes[i].get("type") == scenes[i - 1].get("type"):
            probs.append(f"{scenes[i].get('name')}: the same graphic type '{scenes[i]['type']}' twice in a row")
    head = f"plan: {len(scenes)} scenes, {total:.1f}s, graphics {share:.0%}, voice {vlen:.2f}s"
    verdict = "OK: no problems found" if not probs else f"{len(probs)} problem(s) to fix:\n- " + "\n- ".join(probs)
    return (f"{head}\n{verdict}\n\nNow check by eye that every animal, person, object and action said below is in its "
            f"`shows`:\n" + "\n".join(rows))


# ---- look -------------------------------------------------------------------------------------------------------

def look(path: str, frames: int = 8, times: str = "", at: float | None = None, duration: float = 30.0, size: int = 960) -> str:
    """A contact sheet (one JPG) of a clip: `frames` frames spread over it, or the given times ("0.5,2,4").
    For an HTML scene file, JPG stills at `times`, `size` px wide (960 default; 1920 for full detail; no video is made).
    Returns the image path(s) to open."""
    p = Path(path).expanduser().resolve()
    if p.suffix.lower() == ".html":
        ts = times or "0.5,2,4"
        outdir = p.parent.parent / "look" if p.parent.name == "scenes" else p.parent
        extra = _scene_words(p.parent.parent, p.stem, at, duration) if p.parent.name == "scenes" else []
        page = _page(p)
        r = subprocess.run(["node", str(HERE / "scene.mjs"), "--html", str(page), "--stills", ts, "--outdir", str(outdir),
                            "--w", str(W), "--h", str(H), *extra], capture_output=True, text=True, timeout=600)
        ev = [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]
        if not ev or ev[-1].get("event") != "done":
            raise RuntimeError((ev[-1] if ev else {}).get("message") or r.stderr[-600:])
        note = f"\npage errors: {ev[-1]['errors']}" if ev[-1].get("errors") else ""
        # half-size JPGs: plenty to spot cut-off text, overlaps and wrong pictures, at about a quarter of the image cost
        small = []
        for f in ev[-1]["stills"]:
            fp = Path(f)
            jp = outdir / (p.stem + fp.stem[len(page.stem):] + ".jpg") if fp.stem.startswith(page.stem) else fp.with_suffix(".jpg")
            if size and size < W:
                _run(["ffmpeg", "-hide_banner", "-y", "-i", str(fp), "-vf", f"scale={int(size)}:-2", "-q:v", "3", str(jp)])
                fp.unlink(missing_ok=True)
                small.append(str(jp))
            else:
                small.append(str(fp))
        return "\n".join(small) + note
    d = _probe(p)
    ts = [float(x) for x in times.split(",")] if times else [d * (i + 0.5) / frames for i in range(frames)]
    outdir = p.parent.parent / "look" if p.parent.name == "clips" else p.parent
    outdir.mkdir(parents=True, exist_ok=True)
    sheet = outdir / f"{p.stem}_sheet.jpg"
    tmp = outdir / f".{p.stem}_f"
    tmp.mkdir(exist_ok=True)
    for i, t in enumerate(ts):
        _run(["ffmpeg", "-hide_banner", "-y", "-ss", f"{min(t, max(0, d - 0.05)):.3f}", "-i", str(p), "-frames:v", "1",
              "-vf", "scale=480:-2", str(tmp / f"{i:03d}.jpg")])      # no drawtext: many ffmpeg builds lack it
    cols = min(4, len(ts))
    rows = (len(ts) + cols - 1) // cols
    _run(["ffmpeg", "-hide_banner", "-y", "-i", str(tmp / "%03d.jpg"), "-vf", f"tile={cols}x{rows}:padding=4:color=black",
          "-frames:v", "1", "-q:v", "3", str(sheet)])
    shutil.rmtree(tmp, ignore_errors=True)
    return f"{sheet}  ({len(ts)} frames of {d:.2f}s, left to right, top to bottom, at {', '.join(f'{t:.1f}s' for t in ts)})"


# ---- join -------------------------------------------------------------------------------------------------------

def _sfx_file(name: str, i: int) -> Path:
    p = Path(name).expanduser()
    if p.suffix and p.exists():
        return p.resolve()
    d = SFX_ROOT / name
    files = sorted(d.glob("*.*")) if d.is_dir() else []
    if not files:
        cats = sorted(x.name for x in SFX_ROOT.iterdir() if x.is_dir()) if SFX_ROOT.exists() else []
        raise ValueError(f"no sound effect '{name}'; give a file path or one of: {', '.join(cats)}")
    # some library files are long beds (a 24 s 'ui', a 16 s 'impact'): pick only short one-shots unless the
    # category is a bed itself, so an effect never turns into background noise under the voice
    if name not in ("ambience", "cinematic"):
        short = [f for f in files if 0 < _sfx_len(f) <= 6.0]
        files = short or files
    return files[i % len(files)]


_SFX_LENS: dict = {}


def _sfx_len(f: Path) -> float:
    if f not in _SFX_LENS:
        try:
            _SFX_LENS[f] = duration(f)
        except Exception:
            _SFX_LENS[f] = 0.0
    return _SFX_LENS[f]


# longest an effect may ring (s); a short fade-out ends it. 0 = play the whole file. Override per effect with "len".
_SFX_MAX = {"riser": 5.0, "impact": 2.5, "transition": 2.0, "whoosh": 1.6, "ambience": 0, "cinematic": 0}


def join(project: str, clips: list, voice: str = "", music: str = "", music_db: float = -20.0, sfx: list | None = None,
         out: str = "", tail: float = 1.0, voice_end: float = 0.0) -> str:
    """Join clips (paths or names in clips/, in order) into final.mp4 with the voice, music under it (ducked while the voice
    speaks) and sound effects: sfx = [{"at": 12.4, "sound": "whoosh", "db": -8}, ...] (sound: a file or a category folder).
    The picture must cover the voice; `tail` seconds of picture after the voice ends are kept. voice_end: use the voice only up
    to this time (a test of the first minutes: end it at a sentence's end)."""
    P = _project(project)
    files = []
    for c in clips:
        f = Path(str(c)).expanduser()
        if not f.is_absolute():
            f = P / "clips" / (f.name if f.suffix else f.name + ".mp4")
        if not f.exists():
            raise FileNotFoundError(f"no clip: {f}")
        files.append(f.resolve())
    if not files:
        raise ValueError("no clips")
    lst = P / "clips" / ".join_list.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files), encoding="utf-8")
    pic = P / "clips" / ".joined_picture.mp4"
    _run(["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(pic)])
    vid_len = duration(pic)
    if not voice:
        meta = P / "voice" / "sentences.json"
        voice = json.loads(meta.read_text())["voice"] if meta.exists() else ""
    inputs, filters, mix = ["-i", str(pic)], [], []
    k = 1
    voice_len = 0.0
    if voice:
        voice_len = duration(voice)
        inputs += ["-i", str(Path(voice).expanduser())]
        cut = ""
        if voice_end and 0 < voice_end < voice_len:      # a part of the voice only (a test): end cleanly with a short fade
            voice_len = float(voice_end)
            cut = f"atrim=0:{voice_len:.3f},afade=t=out:st={max(0, voice_len - 0.3):.3f}:d=0.3,"
        filters.append(f"[{k}:a]{cut}aresample=48000,aformat=channel_layouts=stereo,asplit=2[vo][vkey]")
        mix.append("[vo]")
        k += 1
    end = min(vid_len, (voice_len + tail) if voice_len else vid_len)
    if music:
        mp = Path(music).expanduser()
        if not mp.exists() and (MUSIC_ROOT / music).exists():
            mp = MUSIC_ROOT / music
        inputs += ["-stream_loop", "-1", "-i", str(mp)]
        filters.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_db}dB,"
                       f"afade=t=in:d=1.5,afade=t=out:st={max(0, end - 2.5):.2f}:d=2.5[mu0]")
        if voice:
            filters.append("[mu0][vkey]sidechaincompress=threshold=0.03:ratio=6:attack=40:release=600[mu]")
        else:
            filters.append("[mu0]anull[mu]")
        mix.append("[mu]")
        k += 1
    elif voice:
        filters.append("[vkey]anullsink")
    for i, s in enumerate(sfx or []):
        f = _sfx_file(str(s.get("sound", "whoosh")), i)
        ms = int(float(s.get("at", 0)) * 1000)
        inputs += ["-i", str(f)]
        cap = float(s.get("len", _SFX_MAX.get(str(s.get("sound", "whoosh")), 1.2 if not Path(str(s.get("sound", ""))).suffix else 0)))
        trim = f"atrim=0:{cap:.2f},afade=t=out:st={max(0.0, cap - 0.25):.2f}:d=0.25," if cap > 0 else ""
        filters.append(f"[{k}:a]{trim}aresample=48000,aformat=channel_layouts=stereo,volume={float(s.get('db', -10))}dB,adelay={ms}|{ms}[s{i}]")
        mix.append(f"[s{i}]")
        k += 1
    final = Path(out).expanduser() if out else P / "final.mp4"
    cmd = ["ffmpeg", "-hide_banner", "-y", *inputs]
    if mix:
        filters.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=longest,"
                       f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
        cmd += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v"]
    vt = sys.platform == "darwin"
    venc = ["-c:v", "h264_videotoolbox", "-b:v", "14M", "-maxrate", "20M", "-bufsize", "28M"] if vt else \
           ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
    cmd += ["-t", f"{end:.3f}", *venc, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)]
    _run(cmd)
    pic.unlink(missing_ok=True)
    lst.unlink(missing_ok=True)
    warn = ""
    if voice_len and vid_len < voice_len - 0.05:
        warn = f"\nWARNING: the picture ({vid_len:.2f}s) is shorter than the voice ({voice_len:.2f}s); the end of the voice is cut"
    return f"{final}  {duration(final):.2f}s  ({len(files)} clips, picture {vid_len:.2f}s, voice {voice_len:.2f}s){warn}"


if __name__ == "__main__":       # quick manual use:  python3 agent_kit/kit.py look clip.mp4
    fn = {"align": align, "find": find, "scene": scene, "look": look, "join": join, "check_plan": check_plan}[sys.argv[1]]
    print(fn(*sys.argv[2:]))
