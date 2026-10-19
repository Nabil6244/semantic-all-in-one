"""What If: ShotPlan (+ fetched files) -> the renderer's spec (whatif-engine/lib/shots.mjs). A shot whose picture could not be had
is never swapped for an unrelated one: a world with a texture becomes its globe, anything else a dark plate carrying the
sentence's key phrase (a meaningful typographic shot, like the references' title lines)."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import narration as nr
from .planner import PHOTO_WORLDS, Shot, ShotPlan, _world

WIDTH, HEIGHT, FPS = 1920, 1080, 30
LOOK = {"saturate": 0.82, "contrast": 1.04, "lift": "#080B10", "vignette": 0.34, "grain": 0.035}
DRIFT_FOCUS = ((0.5, 0.5), (0.45, 0.5), (0.55, 0.48), (0.5, 0.45), (0.5, 0.55))


def _fallback(s: Shot, notes: List[str]) -> None:
    """This shot has no picture: a meaningful alternative, in place."""
    w = _world(s.text)
    why = s.asset.split(":", 1)[0] if s.asset else "picture"
    if w and w[0] and not PHOTO_WORLDS.search(s.text):
        s.kind, s.texture, s.atmosphere, s.model, s.cite = "globe", w[0], w[2], "", ("ILLUSTRATION", "")
        notes.append(f"shot {s.id}: no {why} could be had, so it shows {w[1].title()} as a globe")
        return
    s.kind, s.tint, s.cite = "plate", "dark", ("ILLUSTRATION", "")
    s.extra["lockup"] = True
    notes.append(f"shot {s.id}: no {why} could be had, so it carries the sentence as a title shot")


def _lockup(s: Shot) -> Optional[Dict[str, Any]]:
    phrase = [re.sub(r"[^\w'°%.\-]", "", t).strip(".-") for t in s.text.split()]
    phrase = [p for p in phrase if p]
    while phrase and phrase[0].lower() in nr.FILLER:
        phrase.pop(0)
    cut = phrase[:7]
    while len(cut) > 2 and (cut[-1].lower() in nr.FILLER or cut[-1].lower() in nr.TAIL_WORDS):
        cut.pop()
    if len(cut) < 2:
        return None
    return {"type": "tm_caption", "text": " ".join(cut).upper(), "size": "large", "anchor": "ml", "start": round(s.start + 0.2, 3),
            "end": round(s.end - 0.2, 3), "fade_in": 0.1, "fade_out": 0.3, "z": 5}


# instruments and credits sit in the corners; they never make a diagram plate "drawn on"
_CORNER_TYPES = ("tm_mission", "tm_clock", "tm_cite", "tm_fade", "tm_survival", "tm_gauge")
EMPTY_PLATE_S = 2.0
HOLD_GAP_S = 4.0       # a plate gap up to this long after a graphic: the graphic holds (a caption would only flash)
REUSE_GAP_S = 90.0            # the same picture again only this long after it was last on screen (the Pale Blue Dot 3 times in 30 s, #016)


def _said_block(words: List[Any], a: float, b: float) -> Optional[Dict[str, Any]]:
    """The reference's information block for an empty stretch, from what is said in it: a number, else a named thing or term, with the
    words around it (whatif/typeset.py). None when the stretch says nothing of the kind."""
    if not words:
        return None
    from . import typeset as ty

    ws = list(words)
    cl = nr.clauses(ws)
    metrics = {m.i0: m for m in nr.extract_metrics(ws)}
    names = ty._names()
    for k, (x, y) in enumerate(cl):
        if not (a - 0.1 <= ws[x].start <= b - 1.6):
            continue
        blk = ty._block(ws, cl, k, metrics, names)
        if blk is None:
            continue
        t0, t1 = round(max(a + 0.1, ws[x].start - 0.25), 3), round(b - 0.2, 3)
        if t1 - t0 < 1.6:
            continue
        timing = {"start": t0, "end": t1, "fade_in": 0.05, "fade_out": 0.3, "z": 5, "typeset": True}
        if blk["metric"] is not None:
            m = blk["metric"]
            return {"type": "tm_metric", "value": ("≈ " if m.approx else "") + m.shown + ("×" if m.kind == "ratio" else ""),
                    "unit": "" if m.kind == "ratio" else m.unit, "kicker": blk["kicker"], "sub": blk["sub"], "sub_color": "amber",
                    "anchor": "left", "size": "large" if len(m.shown + m.unit) <= 12 else "medium", **timing}
        return {"type": "tm_caption", "text": blk["head"], "kicker": blk["kicker"], "sub": blk["sub"], "sub_color": "amber",
                "size": "large", "anchor": "ml", **timing}
    return None


FRAME_X = 0.13          # how far a craft / globe slides right when the information block is at the left (fraction of the width)
YOU_PER_MIN = 1.0       # "you" / "your" this often: the narration makes the viewer the traveller (the reference's "YOU / ON BOARD")


def _left_text(L: Dict[str, Any]) -> bool:
    t = L.get("type")
    if t == "tm_metric":
        return L.get("anchor") in ("left", "upper_left")
    if t == "tm_caption":
        return L.get("size") != "photo" and L.get("anchor", "bl") in ("ml", "bl", "tl")
    return False


def _identity(out_shots: List[Dict[str, Any]], layers: List[Dict[str, Any]], words: List[Any], notes: List[str]) -> None:
    """The journey's own craft gets a ring marker (V3: "YOU / ON BOARD" on Voyager), and a craft or world slides right while an information
    block is at the left, so the type never sits on the subject. The marker says YOU only when the narration speaks to the viewer as the
    traveller; otherwise it carries the craft's name. Only the craft with the most shots (3 or more) is the journey's."""
    from collections import Counter

    from .planner import CRAFT

    crafts = Counter(d.get("model") for d in out_shots if d["kind"] == "craft" and d.get("model"))
    model, n = crafts.most_common(1)[0] if crafts else (None, 0)
    if model and n >= 3:
        # one model can be several craft (voyager.glb is Voyager 1 and 2): the name the narration says most (the marker read
        # "VOYAGER 2" on Voyager 1 when the first table entry was taken)
        said = " ".join(getattr(w, "norm", "") for w in words)
        cands = [(len(re.findall(p_, said, re.I)), nm) for p_, m, nm in CRAFT if m == model]
        name = max(cands)[1] if cands and max(cands)[0] > 0 else next((nm for _p, m, nm in CRAFT if m == model), "")
        mins = max(1.0, (words[-1].end - words[0].start) / 60.0) if words else 1.0
        second_person = sum(1 for w in words if getattr(w, "norm", "") in ("you", "your")) / mins >= YOU_PER_MIN
        label = "YOU\nON BOARD" if second_person else name
        for d in out_shots:
            if d["kind"] != "craft" or d.get("model") != model or not label:
                continue
            named = any(L.get("type") == "tm_caption" and str(L.get("text", "")).upper() == label and float(L["start"]) < d["end"]
                        and d["start"] < float(L["end"]) for L in layers)
            if not named:
                d["marker"] = label
        notes.append(f"plan: the journey's craft ({name or model}) carries its marker: {label.replace(chr(10), ' / ')}")
    for d in out_shots:
        if d["kind"] in ("craft", "globe") and any(_left_text(L) and float(L["start"]) < d["end"] - 1.0 and d["start"] + 1.0 < float(L["end"])
                                                    for L in layers):
            d["frame_x"] = FRAME_X


_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)")


def _one_number_at_a_time(layers: List[Dict[str, Any]], notes: List[str]) -> List[Dict[str, Any]]:
    """The same number in two text layers at once ("124,000 KM ABOVE" in the middle and "124,000 KM / ABOVE SATURN'S CLOUDS" at the
    lower left, #016 at 5:01): the later one is left out."""
    def number(L: Dict[str, Any]) -> str:
        if L.get("type") not in ("tm_metric", "tm_caption"):
            return ""
        m = _NUM.search(f"{L.get('value') or ''} {L.get('text') or ''}")
        return m.group(1).replace(",", "") if m else ""

    kept: List[Dict[str, Any]] = []
    drop = set()
    for L in sorted(layers, key=lambda x: float(x.get("start") or 0)):
        n = number(L)
        if n and any(number(K) == n and float(K["start"]) < float(L["end"]) and float(L["start"]) < float(K["end"]) for K in kept):
            notes.append(f"the number {n} was already on screen at {float(L['start']):.1f}s; its second copy is left out")
            drop.add(id(L))
            continue
        kept.append(L)
    return [L for L in layers if id(L) not in drop]          # the drawing order stays as it was


_BROWSER_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP"}
_STILL_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".avif"}


def _browser_safe(src: Path, dest: Path, notes: List[str]) -> bool:
    """A still whose real format the renderer's browser cannot open (NASA's Oort Cloud illustration was a TIFF named .jpg: it never
    loaded, and render #016 hung on it) is written to dest as a JPEG. Returns True when it wrote dest; False leaves the copy to the
    caller (a clip, or a picture already in a format the page reads)."""
    if src.suffix.lower() not in _STILL_EXT:
        return False
    try:
        from PIL import Image

        with Image.open(src) as im:
            if (im.format or "").upper() in _BROWSER_FORMATS:
                return False
            im.convert("RGB").save(dest, "JPEG", quality=92)
        notes.append(f"{src.name} is a {im.format} picture, which the renderer cannot open: converted to JPEG")
        return True
    except Exception:
        return False


EMPTY_EDGE = 0.05            # edge density (0-255 scale, edgedetect mean) no sampled frame of an empty clip reaches; dark space footage sits at 0.3+
_empty_cache: Dict[tuple, bool] = {}


def _empty_clip(path: str) -> bool:
    """A clip with nothing in it: none of its keyframes shows any edge. Render 024's NASA clip (1:51-2:00) was the black middle of
    a launch video, so the shot showed 8.8 s of black under its text. Star fields, night skies and dark footage all have edges and pass;
    a clip that cannot be read is left to the renderer (False)."""
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return False
    key = (str(p.resolve()), st.st_size, st.st_mtime)
    if key in _empty_cache:
        return _empty_cache[key]
    empty = False
    try:
        from map_scene.render import _ffmpeg

        try:
            from providers.hidden_subprocess import run as _run
        except Exception:                    # noqa: BLE001
            import subprocess

            _run = subprocess.run
        r = _run([_ffmpeg(), "-hide_banner", "-nostats", "-skip_frame", "nokey", "-i", str(p), "-an", "-vf",     # keyframes only: fast
                  "scale=320:-2,format=gray,edgedetect=low=0.08:high=0.2,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                  "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        vals = [float(m) for m in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.]+)", (r.stderr or "") + (r.stdout or ""))]
        empty = bool(vals) and max(vals) < EMPTY_EDGE
    except Exception:                        # noqa: BLE001 -- unknown: the clip is used as before
        empty = False
    _empty_cache[key] = empty
    return empty


def _openable(path: str) -> bool:
    """A still the renderer can be given at all (a broken or unknown file: its shot takes its fallback, never a stall)."""
    p = Path(path)
    if p.suffix.lower() not in _STILL_EXT:
        return True
    try:
        from PIL import Image

        with Image.open(p) as im:
            im.verify()
        return True
    except Exception:
        return False


def _plate_content(L: Dict[str, Any]) -> bool:
    from .planner import DIAGRAMS

    return L.get("type") in DIAGRAMS or (L.get("type") == "tm_template" and bool(L.get("plate", True)))


def _hold_to_next(s: Shot, layers: List[Dict[str, Any]], notes: List[str]) -> None:
    """A graphic that ends a moment before its plate does (a 5 s template on a 7 s shot) holds its last frame to the next graphic or the
    cut: #017 had five blank plates of 1-2 s ("IT MOVES" at 35.4 s, "ONE ORBIT" at 240.6 s), each too short for a caption of its own."""
    def drawn(L: Dict[str, Any]) -> bool:
        return L.get("type") not in _CORNER_TYPES and L.get("start") is not None and L.get("end") is not None \
            and float(L["start"]) < s.end and float(L["end"]) > s.start

    for L in sorted((L for L in layers if drawn(L)), key=lambda L: float(L["end"])):
        end = float(L["end"])
        if end >= s.end - 0.05 or float(L["start"]) < s.start - 0.05:
            continue                                   # already to the cut, or it came from the shot before
        nxt = min([float(M["start"]) for M in layers if drawn(M) and M is not L and float(M["start"]) >= end - 0.05] + [s.end])
        covered = any(drawn(M) and M is not L and float(M["start"]) < end and float(M["end"]) > end + 0.3 for M in layers)
        if not covered and 0.3 <= nxt - end <= HOLD_GAP_S:
            L["end"] = round(nxt if nxt < s.end else s.end, 3)
            notes.append(f"shot {s.id}: its graphic holds {nxt - end:.1f}s longer, to {'the next one' if nxt < s.end else 'the cut'}, instead of a blank plate")


def _fill_empty_plates(shots: List[Shot], layers: List[Dict[str, Any]], notes: List[str], words: List[Any] = ()) -> List[Dict[str, Any]]:
    """A plate whose diagram was left out (or never written) showed only its small heading on a dark background, up to 15 s at a time
    (project #016: 28 such screens, 31 % of its frames near-empty). Every stretch of a plate with nothing drawn on it for EMPTY_PLATE_S
    or more carries the words spoken over it as a large title, timed to that stretch alone so it never covers a graphic that is there."""
    out: List[Dict[str, Any]] = []
    for s in shots:
        if s.kind != "plate":
            continue
        _hold_to_next(s, layers, notes)
        busy = sorted((max(s.start, float(L["start"])), min(s.end, float(L["end"]))) for L in layers + out
                      if L.get("type") not in _CORNER_TYPES and L.get("start") is not None and L.get("end") is not None
                      and float(L["start"]) < s.end and float(L["end"]) > s.start)
        gaps, t = [], s.start
        for a, b in busy:
            if a - t >= EMPTY_PLATE_S:
                gaps.append((t, a))
            t = max(t, b)
        if s.end - t >= EMPTY_PLATE_S:
            gaps.append((t, s.end))
        for a, b in gaps:
            L = _said_block(words, a, b)
            if L is None:
                # what is said in that stretch, from the first clause that starts in it (never from the middle of one), weak ends trimmed
                ws = list(words)
                starts = [x for x, y in (nr.clauses(ws) if ws else []) if a - 0.05 <= ws[x].start < b - 1.0]
                from .typeset import _clean
                text = " ".join(_clean([w.text for w in ws[starts[0]:] if w.start < b - 0.3])) if starts else ""
                text = text or " ".join(w.text for w in words if a - 0.05 <= w.start < b - 0.3) or s.text
                part = Shot(id=s.id, start=a, end=b, kind="plate", text=text)
                lock = _lockup(part)
                if lock and len([w for w in lock["text"].split() if w.lower() not in nr.FILLER]) < 3:
                    lock = None                   # "SOMEWHERE OUT": a fragment says nothing; calm sky for a moment is better (V3 6:46)
                L = lock or ({"type": "tm_caption", "text": s.title.upper(), "size": "large", "anchor": "ml", "start": round(a + 0.2, 3),
                                       "end": round(b - 0.2, 3), "fade_in": 0.1, "fade_out": 0.3, "z": 5} if s.title else None)
            if L:
                out.append(L)
                notes.append(f"shot {s.id}: nothing was drawn on its diagram from {a:.1f}s to {b:.1f}s; the narration's words are shown there instead")
    return out


def _finite(v: Any) -> bool:
    if isinstance(v, float):
        return v == v and abs(v) != float("inf")
    if isinstance(v, dict):
        return all(_finite(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return all(_finite(x) for x in v)
    return True


def _finite_layers(layers: List[Dict[str, Any]], notes: List[str]) -> List[Dict[str, Any]]:
    """A layer carrying NaN / infinity (a broken number from a CSV) cannot be written as JSON for the renderer: it is left out."""
    out = []
    for L in layers:
        if _finite(L):
            out.append(L)
        else:
            notes.append(f"a {L.get('type', 'layer')} graphic had a broken number and was left out")
    return out


def citation(shots: List[Shot]) -> Dict[str, Any]:
    segs = []
    for s in shots:
        kind, text = s.cite if s.cite[0] else (("ILLUSTRATION", ""))
        if s.kind in ("image", "video") and s.file and not s.asset.lower().startswith(("flow_",)):
            real = bool(s.credit and "nasa" in s.credit.lower() or s.asset.startswith(("nasa_", "commons_", "archive_")))
            # "REAL PHOTO · VENERA 14 · NASA/NSSDCA/COURTESY OF THE USSR": what it shows, then who made it
            kind = ("REAL PHOTO" if s.name else "REAL IMAGE") if real else "IMAGE"
            text = " · ".join(x for x in (s.name.upper() if s.name else "", _credit_text(s.credit) or text) if x)
        elif s.kind in ("image", "video") and s.asset.lower().startswith("flow_"):
            kind, text = "AI ILLUSTRATION", ""
        elif s.kind == "craft":
            kind, text = "ILLUSTRATION", "NASA 3D MODEL · NASA/JPL-CALTECH"
        elif s.kind == "globe":
            kind, text = "ILLUSTRATION", "NASA / SOLAR SYSTEM SCOPE TEXTURE"
        segs.append({"t0": round(s.start, 3), "t1": round(s.end, 3), "kind": kind, "text": text})
    return {"type": "tm_cite", "segments": segs, "z": 12}


def _credit_text(credit: str) -> str:
    return re.sub(r"^(photo|image|credit|footage)\s*:\s*", "", (credit or "").strip(), flags=re.I)[:90]


def _join_same_file(out: List[Dict[str, Any]], names: Dict[str, str], notes: List[str]) -> List[Dict[str, Any]]:
    """Two shots back to back that show the same file are one shot. A split shot (the opening's pace, the 6 s Flow clip rule, a split
    half given its twin's picture) whose halves got the same clip restarted it at frame 0 at the cut -- the probe jumped back and played
    its move again (project #013, 5:51) -- and a picture's slow push restarted, faster, on the shorter half. Joined, the clip plays on
    and the push runs once over the whole length."""
    import hashlib

    by_name = {v: k for k, v in names.items()}
    digest: Dict[str, str] = {}

    def same(name: str) -> str:
        if name not in digest:
            src = Path(by_name.get(name, name))
            try:
                h = hashlib.md5()
                with open(src, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                digest[name] = h.hexdigest()
            except OSError:
                digest[name] = name
        return digest[name]

    joined: List[Dict[str, Any]] = []
    merged = 0
    for d in out:
        p = joined[-1] if joined else None
        if (p is not None and d["kind"] == p["kind"] and d["kind"] in ("image", "video") and p.get("file") and d.get("file")
                and abs(p["end"] - d["start"]) < 0.05 and same(p["file"]) == same(d["file"])):
            p["end"] = d["end"]
            p["exit"] = d.get("exit", p.get("exit"))
            merged += 1
            continue
        joined.append(d)
    if merged:
        notes.append(f"{merged} cut(s) between two shots of the same picture or clip removed: it plays on instead of restarting")
    return joined


UPSCALE_BELOW = 0.6         # a clip shorter than this share of the video's height is enlarged a lot (a 360p Flow clip in 1080p: 0.33)


def _low_res(path: str, height: int) -> bool:
    try:
        from media_size import probe_size

        size = probe_size(path)
    except Exception:                        # noqa: BLE001 -- unknown size: scaled as before
        return False
    return bool(size) and size[1] < UPSCALE_BELOW * height


OPENING_EMPTY_S = 0.8       # the first frames always carry a graphic: render 024 opened on 1.2 s of a dark star-trail clip and nothing else
OPENING_PULL_S = 3.0         # the first graphic due within this many seconds comes in early to fill them
OPENING_START_S = 0.3
_INSTRUMENT_TYPES = {"tm_clock", "tm_mission", "tm_cite"}


def _opening_never_empty(layers: List[Dict[str, Any]], notes: List[str]) -> None:
    content = [L for L in layers if L.get("type") not in _INSTRUMENT_TYPES and L.get("start") is not None]
    if not content or any(float(L["start"]) < OPENING_EMPTY_S for L in content):
        return
    first = min(content, key=lambda L: float(L["start"]))
    if float(first["start"]) <= OPENING_PULL_S:
        notes.append(f"the opening: the first graphic comes in at {OPENING_START_S:.1f}s instead of {float(first['start']):.1f}s, so the video "
                     f"never opens on an empty screen")
        first["start"] = OPENING_START_S


def compile_spec(plan: ShotPlan, *, width: int = WIDTH, height: int = HEIGHT, fps: int = FPS, media_dir: Optional[Path] = None,
                 title: str = "") -> Dict[str, Any]:
    """The spec for whatif-engine. Files are hard-linked into media_dir (one folder the renderer serves)."""
    notes: List[str] = list(plan.notes)
    shots = plan.shots
    layers: List[Dict[str, Any]] = [dict(L) for L in plan.layers]
    names: Dict[str, str] = {}

    def place(src: str) -> str:
        p = Path(src).resolve()
        if str(p) not in names:
            if media_dir is None:
                return str(p)
            Path(media_dir).mkdir(parents=True, exist_ok=True)
            name = f"{len(names) + 1:03d}_{p.name}"
            if _browser_safe(p, Path(media_dir) / name, notes):
                pass                                   # converted (a TIFF saved as .jpg, #016) or already a format the page reads
            else:
                try:
                    os.link(p, Path(media_dir) / name)
                except OSError:
                    shutil.copy2(p, Path(media_dir) / name)
            names[str(p)] = name
        return names[str(p)]

    out_shots: List[Dict[str, Any]] = []
    shown_until: Dict[str, float] = {}           # a file -> when it was last on screen
    for n, s in enumerate(shots):
        if s.kind in ("image", "video") and s.file and not Path(s.file).is_file():
            notes.append(f"shot {s.id}: its picture {Path(s.file).name} is no longer on disk (cache cleared or file moved)")
            s.file = ""
        elif s.kind in ("image", "video") and s.file and not _openable(s.file):
            notes.append(f"shot {s.id}: its picture {Path(s.file).name} cannot be opened (broken or unknown format); its fallback is shown")
            s.file = ""
        elif s.kind == "video" and s.file and Path(s.file).suffix.lower() not in _STILL_EXT and _empty_clip(s.file):
            notes.append(f"shot {s.id}: its clip {Path(s.file).name} is black from start to end (nothing to see); its fallback is shown instead")
            s.file = ""
        if s.kind in ("image", "video") and s.file:
            key = str(Path(s.file).resolve())
            prev = shots[n - 1] if n else None
            joined = prev is not None and prev.file and str(Path(prev.file).resolve()) == key   # back to back: _join_same_file holds it
            if key in shown_until and not joined and s.start - shown_until[key] < REUSE_GAP_S:
                notes.append(f"shot {s.id}: {Path(s.file).name} was on screen {s.start - shown_until[key]:.0f} s ago; not shown again so soon")
                s.file, s.asset = "", ""
            else:
                shown_until[key] = s.end
        if s.kind in ("image", "video") and not s.file:
            if s.asset.lower().startswith("file:") and Path(s.asset.split(":", 1)[1].strip()).is_file():
                s.file = s.asset.split(":", 1)[1].strip()
            else:
                _fallback(s, notes)               # a title shot: its words come in the free stretches only (_fill_empty_plates)
        d: Dict[str, Any] = {"id": s.id, "start": round(s.start, 3), "end": round(s.end, 3), "kind": s.kind, "exit": s.exit}
        if s.kind in ("image", "video"):
            d["file"] = place(s.file)
            if s.cite[0] == "REAL IMAGE" and s.kind == "image" and not s.extra.get("full_bleed"):
                d["compose"] = "letterbox"            # a real photograph: the whole picture over a blurred copy of itself (V1 6:40)
                if any(L.get("typeset") and _left_text(L) and float(L["start"]) < s.end - 0.5 and s.start + 0.5 < float(L["end"]) for L in layers):
                    d["compose"] = "card_right"       # with the information block at the left: the photo as a card on the right (V3 1:46)
            fx, fy = DRIFT_FOCUS[n % len(DRIFT_FOCUS)]
            d["drift"] = {"from": 1.0, "to": 1.04, "fx": fx, "fy": fy}
            if s.kind == "video" and Path(s.file).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"):
                d["kind"] = "image"                  # a clip row that got a still picture is drawn as a picture (never looped as a clip)
                notes.append(f"shot {s.id}: its clip is a still picture ({Path(s.file).name}); shown as a picture")
            elif s.kind == "video":
                d["in_s"], d["loop"] = float(s.extra.get("in_s", 0)), True
                if _low_res(s.file, height):
                    d["upscale"] = True              # the cutter scales it with Lanczos and a light unsharp mask (whatif-engine/cutter.mjs)
        elif s.kind == "plate":
            # the heading belongs over a graphic (the reference's "VOYAGER 1 · COMPUTER MEMORY"), never alone on an empty plate
            drawn = any(_plate_content(L) and float(L.get("start", 0)) < s.end - 0.3 and s.start + 0.3 < float(L.get("end", 0)) for L in layers)
            d["tint"], d["title"], d["sub"] = s.tint, (s.title if drawn else ""), (s.sub if drawn else "")
            d["lockup"] = bool(s.extra.get("lockup"))            # a typographic stand-in: the act's instruments stay on over it
        elif s.kind == "hero":
            d["scene"], d["cam"] = s.scene, s.cam
        elif s.kind == "craft":
            d["model"], d["cam"] = s.model, s.cam
            d["spin_deg_s"] = float(s.extra.get("spin_deg_s", 0))
        elif s.kind == "globe":
            d["texture"], d["cam"], d["atmosphere"] = s.texture, s.cam, s.atmosphere
        out_shots.append(d)
    _identity(out_shots, layers, getattr(plan, "words", None) or [], notes)
    for d in out_shots:                       # a photo card's caption sits under the card, on the right
        if d.get("compose") == "card_right":
            for L in layers:
                if L.get("type") == "tm_caption" and L.get("size") == "photo" and float(L["start"]) < d["end"] and d["start"] < float(L["end"]):
                    L["cx"], L["cy"] = 0.73, 0.92
    out_shots = _join_same_file(out_shots, names, notes)
    # the photograph of a disc-map plate (V2 0:22): the plate shot's fetched file goes into its tm_discmap layer
    for s in shots:
        if s.kind == "plate" and s.file and Path(s.file).is_file():
            for L in layers:
                if L.get("type") == "tm_discmap" and s.start - 0.1 <= float(L["start"]) < s.end:
                    L["image"] = place(s.file)
                if L.get("type") == "tm_template" and L.get("image_slot") and s.start - 0.1 <= float(L["start"]) < s.end:
                    L.setdefault("slots", {})[L["image_slot"]] = place(s.file)     # the template's photo (eht_pair, map_overlay ...)
    for L in layers:                     # a template photo given as a local file: placed in the media folder like any other
        if L.get("type") == "tm_template" and L.get("image_slot"):
            v = str(L.get("slots", {}).get(L["image_slot"], ""))
            if v.lower().startswith("file:") and Path(v.split(":", 1)[1].strip()).is_file():
                L["slots"][L["image_slot"]] = place(v.split(":", 1)[1].strip())
    layers[:] = _one_number_at_a_time(layers, notes)
    layers.extend(_fill_empty_plates(shots, layers, notes, getattr(plan, "words", None) or []))
    layers.append(citation(shots))
    _opening_never_empty(layers, notes)
    layers = _finite_layers(layers, notes)
    spec = {"width": width, "height": height, "fps": fps, "duration": round(plan.duration, 3), "look": dict(LOOK), "shots": out_shots,
            "layers": layers, "whatif": {"title": title or plan.title, "notes": notes}}
    if media_dir is not None:
        spec["media_dir"] = str(media_dir)
    return spec
