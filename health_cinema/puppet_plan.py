"""Paper-cutout puppet for Health Cinema: which shots get a character move, and how the engine renders them (pipeline side only).

The puppet engine itself lives in health_cinema/puppet/ and is imported lazily, so nothing here costs anything (and nothing can break) when the
feature is off. Contract used from it:
  puppet.render_shot(still_path, character, action, out_path, duration, fps, direction, size, params) -> out_path
  puppet.render_transition(still_a, still_b, character, transition, out_path, duration, fps, size, direction) -> out_path
  puppet.list_characters() / puppet.list_actions()

Three jobs:
  * parse_action / parse_character: the optional CSV cells (character_action, character) -> a known action, a direction, a cast name, or a warning;
  * plan_puppet: scenes (+ the CSV rows) -> {scene_no: {character, action, direction, params, source, transition?}}; deterministic for a seed;
  * Runner: renders a planned scene (cached by still hash + character + action + params + version) and conforms it to the pipeline's clip format.
    Any failure returns None so the engine renders the scene as it always did: a puppet problem never stops a video.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import random
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

PLAN_VERSION = "1"
FALLBACK_ACTIONS = ("walk", "run", "stand_idle", "look_around", "point", "turn", "pick_up", "put_down", "wave", "stop")
FALLBACK_TRANSITIONS = ("tear_seam", "door_walk", "page_flip", "behind_object")
INTENSITY = {"low": (0.20, 0.6), "medium": (0.35, 1.0), "high": (0.50, 1.4)}      # share of shots, motion amount
ELIGIBLE_KINDS = ("footage", "text_card", "still")      # data graphics, 3D, cards with numbers/evidence and chapter titles stay as they are
MIN_SCENE_S = 2.5
TRANSITION_S = 1.0
NONE_WORDS = ("none", "off", "no", "plain", "skip", "false", "n/a", "na", "-")

# words in a CSV phrase -> an action name (first meaning wins; "stand" gives way to a later verb: stand_and_look = look_around)
_WORD_ACTION = {"walk": "walk", "walks": "walk", "walking": "walk", "enter": "walk", "enters": "walk", "exit": "walk", "stroll": "walk", "cross": "walk",
                "run": "run", "runs": "run", "running": "run", "sprint": "run", "jog": "run", "hurry": "run", "stand": "stand_idle", "idle": "stand_idle",
                "look": "look_around", "glance": "look_around", "search": "look_around", "scan": "look_around", "point": "point", "gesture": "point",
                "pick": "pick_up", "grab": "pick_up", "lift": "pick_up", "carry": "pick_up", "put": "put_down", "place": "put_down", "drop": "put_down",
                "wave": "wave", "greet": "wave", "stop": "stop", "halt": "stop", "freeze": "stop", "turn": "turn", "spin": "turn"}


# ---- the puppet engine, lazily ------------------------------------------------------------------------------------------------------------

def _module():
    return importlib.import_module((__package__ or "health_cinema") + ".puppet")


def _names(seq: Any) -> List[str]:
    out: List[str] = []
    for x in seq or []:
        n = x if isinstance(x, str) else (x.get("name") or x.get("id") if isinstance(x, dict) else getattr(x, "name", None) or getattr(x, "id", None))
        if n:
            out.append(str(n))
    return out


def vocab(module: Any = None) -> Dict[str, List[str]]:
    """{'actions', 'characters', 'transitions'} from the engine; the contract's own action list when it cannot be read (characters then stay empty)."""
    try:
        m = module or _module()
    except Exception:       # noqa: BLE001 - the engine is optional here
        return {"actions": list(FALLBACK_ACTIONS), "characters": [], "transitions": list(FALLBACK_TRANSITIONS), "available": False}
    def _try(fn: str) -> List[str]:
        try:
            return _names(getattr(m, fn)())
        except Exception:       # noqa: BLE001
            return []
    return {"actions": _try("list_actions") or list(FALLBACK_ACTIONS), "characters": _try("list_characters"),
            "transitions": [t for t in getattr(m, "TRANSITIONS", ()) or FALLBACK_TRANSITIONS], "available": True}


def _norm(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (raw or "").strip().lower()).strip("_")


def parse_action(raw: str, actions: Optional[Sequence[str]] = None) -> Tuple[Optional[str], Optional[str], str]:
    """A CSV cell -> (action, direction, warning). action is a known action name, 'none' (keep the scene plain) or None (blank/unknown; warning says why).
    'walk_in_from_left' -> ('walk', 'right', ''), 'stand_and_look' -> ('look_around', None, ''), 'pick_up_box' -> ('pick_up', None, '')."""
    key = _norm(raw)
    if not key:
        return None, None, ""
    if key in NONE_WORDS:
        return "none", None, ""
    known = list(actions) if actions else vocab()["actions"]
    direction = None
    m = re.search(r"(?:^|_)(?:(from|to|toward|towards|into|onto)_)?(left|right)(?:_|$)", key)
    if m:       # entering "from the left" means moving right; "to the right" or a bare "right" means moving right too
        side = m.group(2)
        direction = ("right" if side == "left" else "left") if m.group(1) == "from" else side
    if key in known:
        return key, direction, ""
    hits: List[str] = []
    for tok in key.split("_"):
        a = _WORD_ACTION.get(tok)
        if a and a not in hits:
            hits.append(a)
    if len(hits) > 1 and "stand_idle" in hits:
        hits.remove("stand_idle")
    for a in hits:
        if a in known:
            return a, direction, ""
    return None, None, f"character_action '{raw}' is not a known action ({', '.join(known)}, or none): the planner chooses for this scene"


def parse_character(raw: str, characters: Optional[Sequence[str]] = None) -> Tuple[Optional[str], str]:
    """A CSV cell -> (cast name, warning). Blank and 'auto' mean the planner picks; an unknown name is ignored with a warning."""
    key = _norm(raw)
    if not key or key == "auto":
        return None, ""
    known = list(characters) if characters is not None else vocab()["characters"]
    if not known:
        return key, ""      # the cast cannot be read here (engine not installed): keep the name, the render step reports it
    for n in known:
        if _norm(n) == key:
            return n, ""
    return None, f"character '{raw}' is not in the cast ({', '.join(known)}): Auto is used for this scene"


# ---- planning ------------------------------------------------------------------------------------------------------------------------------

PERSON_RE = re.compile(r"\b(man|men|woman|women|person|patient|doctor|nurse|child|children|kid|boy|girl|runner|worker|athlete|grandparents?|grandmother|grandfather|"
                       r"someone|he|she|his|her|you|your|jogger|walker|neighbou?r|friend|teenager|adult|adults|elderly|farmer)\b", re.I)
MOVE_RE = re.compile(r"\b(walk\w*|run\w*|jog\w*|step\w*|climb\w*|stand\w*|sit\w*|reach\w*|carry\w*|carries|lift\w*|pick\w*|hold\w*|exercis\w*|stretch\w*|stairs|enter\w*|"
                     r"leav\w*|head\w*|travel\w*|look\w*|point\w*|wave\w*|turn\w*|move\w*|open\w*|cross\w*|arriv\w*|wak\w*|get up|gets up|rise|rises)\b", re.I)
PLAIN_RE = re.compile(r"\b(crowds?|millions?|billions?|population|worldwide|global|globally|countries|nations?|map|maps|chart|graph|diagram|statistics?|percent|per cent|"
                      r"rates?|cases|survey|studies|trial|trials|army|armies|ranks|soldiers|thousands|hundreds|endless|swarm|workforce|towers?|stacks?|piles?|skyline|skyscrapers?|aerial|sky|clouds?|ocean|sea|underwater)\b|%", re.I)
ACTION_CUES = (("run", re.compile(r"\b(run\w*|jog\w*|sprint\w*|rush\w*|hurr\w*)\b", re.I)), ("walk", re.compile(r"\b(walk\w*|stroll\w*|stairs|climb\w*|head\w*|enter\w*|cross\w*|travel\w*|arriv\w*)\b", re.I)),
               ("pick_up", re.compile(r"\b(pick\w*|lift\w*|carr\w*|grab\w*|hold\w*|take[sn]?|took)\b", re.I)), ("put_down", re.compile(r"\b(put\w*|plac\w*|drop\w*|set down|sets down)\b", re.I)),
               ("point", re.compile(r"\b(point\w*|show\w*|notice\w*|reveal\w*|shows)\b", re.I)), ("look_around", re.compile(r"\b(look\w*|search\w*|wonder\w*|see|sees|watch\w*|wait\w*)\b", re.I)),
               ("wave", re.compile(r"\b(wave\w*|greet\w*|hello|goodbye)\b", re.I)), ("turn", re.compile(r"\b(turn\w*|spin\w*|rotat\w*)\b", re.I)),
               ("stop", re.compile(r"\b(stop\w*|halt\w*|pause\w*|freez\w*|rest\w*)\b", re.I)), ("stand_idle", re.compile(r"\b(stand\w*|sit\w*|quiet\w*|still)\b", re.I)))
TRANSITION_CUES = (("door_walk", re.compile(r"\b(door|home|room|inside|house|kitchen|office|leave\w*|exit\w*|enter\w*|outside)\b", re.I)), ("page_flip", re.compile(r"\b(page|chapter|story|book|next|then|later|meanwhile)\b", re.I)),
                   ("behind_object", re.compile(r"\b(behind|hid\w*|hide|cover\w*|shadow\w*|tree|wall)\b", re.I)), ("tear_seam", re.compile(r"\b(tear\w*|break\w*|split|divid\w*|crack\w*|suddenly|but)\b", re.I)))


def _get(sc: Any, name: str, default: Any = None) -> Any:
    return sc.get(name, default) if isinstance(sc, dict) else getattr(sc, name, default)


def _rand(seed: int, *parts: Any) -> float:
    h = hashlib.sha256(("%s|" % seed + "|".join(str(p) for p in parts)).encode()).digest()
    return int.from_bytes(h[:6], "big") / float(1 << 48)


def default_seed(scenes: Sequence[Any]) -> int:
    """Same script, same plan: the seed comes from the narration unless the caller gives one."""
    return int(hashlib.sha256("\n".join(str(_get(s, "text", "")) for s in scenes).encode()).hexdigest()[:8], 16)


def settings_from(raw: Optional[dict]) -> dict:
    """The app's puppet options -> a clean dict {enabled, intensity, share, motion, character, seed}."""
    raw = dict(raw or {})
    level = str(raw.get("intensity") or "medium").strip().lower()
    level = level if level in INTENSITY else "medium"
    share, motion = INTENSITY[level]
    ch = str(raw.get("character") or "auto").strip()
    return {"enabled": bool(raw.get("enabled")), "intensity": level, "share": share, "motion": motion,
            "character": None if ch.lower() in ("", "auto") else ch, "seed": raw.get("seed")}


def csv_overrides(scenes: Sequence[Any], rows: Optional[Sequence[dict]]) -> Dict[int, dict]:
    """{scene_no: {action?, direction?, character?}} from the CSV rows each scene covers (first row that fills a puppet cell wins)."""
    out: Dict[int, dict] = {}
    for sc in scenes or []:
        a, b = float(_get(sc, "start", 0.0)), float(_get(sc, "end", 0.0))
        for r in rows or []:
            if not (r.get("character_action") or r.get("character") or r.get("character_ground")):
                continue
            t = r.get("start")
            if t is None or not (a - 0.01 <= float(t) < b - 0.01 or (a == b == float(t))):
                continue
            ov = {k: r[k] for k in ("character_action", "character_direction", "character", "character_ground") if r.get(k)}
            out[_get(sc, "scene_no")] = {"action": ov.get("character_action"), "direction": ov.get("character_direction"), "character": ov.get("character"), "ground": ov.get("character_ground")}
            break
    return out


def _score(text: str) -> float:
    if PLAIN_RE.search(text or ""):
        return 0.0
    s = (2.0 if PERSON_RE.search(text) else 0.0) + (1.5 if MOVE_RE.search(text) else 0.0)
    return s if s >= 1.5 else 0.0


def _pick_action(text: str, actions: Sequence[str], avoid: set, seed: int, no: int) -> str:
    cands = [a for a, rx in ACTION_CUES if a in actions and rx.search(text)]
    pool = [a for a in actions if a in ("walk", "stand_idle", "look_around", "point", "run", "wave", "turn")] or list(actions)
    order = cands + sorted(pool, key=lambda a: _rand(seed, "act", no, a))
    for a in order:
        if a not in avoid:
            return a
    return next((a for a in actions if a not in avoid), actions[0])


def plan_puppet(scenes: Sequence[Any], settings: Optional[dict] = None, rows: Optional[Sequence[dict]] = None, has_still: Optional[Callable[[Any], bool]] = None,
                log: Optional[Callable[[str], None]] = None, module: Any = None) -> Dict[int, dict]:
    """Which scenes get a character move. -> {scene_no: {character, action, direction, params, source: 'csv'|'auto', transition?, transition_s?, transition_from?}}.
    Empty when the feature is off. CSV cells win; the rest is chosen about `share` of all scenes (30-40% at Medium), only among scenes that look like a person or
    a movement and are not crowds/maps/diagrams/figures; never the same action twice in a row; adjacent shots keep their character and direction and join with a
    transition; shots further apart vary character and direction. Deterministic for a seed."""
    say = log or (lambda m: None)
    st = settings if settings and "share" in settings else settings_from(settings)
    if not st["enabled"]:
        return {}
    v = vocab(module)
    actions, chars, trans = v["actions"], v["characters"], v["transitions"] or list(FALLBACK_TRANSITIONS)
    seed = st["seed"] if st.get("seed") is not None else default_seed(scenes)
    if not isinstance(seed, int):
        seed = int(hashlib.sha256(str(seed).encode()).hexdigest()[:8], 16)
    ov = csv_overrides(scenes, rows)
    usable = lambda sc: _get(sc, "kind") in ELIGIBLE_KINDS and float(_get(sc, "end", 0)) - float(_get(sc, "start", 0)) >= MIN_SCENE_S and (has_still is None or has_still(sc))
    chosen: Dict[int, str] = {}
    for sc in scenes:
        no = _get(sc, "scene_no")
        o = ov.get(no)
        if o and o.get("action") == "none":
            say(f"scene {no}: CSV says no character move")
            continue
        if o and (o.get("action") or o.get("character")):
            if usable(sc):
                chosen[no] = "csv"
            else:
                say(f"scene {no}: the CSV asked for a character move but this scene has no still picture, is a graphic or is too short: left plain")
    forced = len(chosen)
    target = int(round(st["share"] * len(scenes)))
    cand = []
    for sc in scenes:
        no = _get(sc, "scene_no")
        if no in chosen or (ov.get(no) or {}).get("action") == "none" or not usable(sc):
            continue
        sc_score = _score(_get(sc, "text", ""))
        if sc_score > 0:
            cand.append((-(sc_score + _rand(seed, "pick", no)), no))
    for _, no in sorted(cand)[:max(0, target - forced)]:
        chosen[no] = "auto"
    order = [_get(sc, "scene_no") for sc in scenes if _get(sc, "scene_no") in chosen]
    by_no = {_get(sc, "scene_no"): sc for sc in scenes}
    plan: Dict[int, dict] = {}
    prev_no = None
    prev: dict = {}
    last_trans = None
    for i, no in enumerate(order):
        sc = by_no[no]; o = ov.get(no) or {}; text = _get(sc, "text", "")
        nxt_act = (ov.get(order[i + 1]) or {}).get("action") if i + 1 < len(order) else None
        avoid = {x for x in (prev.get("action"), nxt_act if nxt_act != "none" else None) if x}
        if o.get("action") and o["action"] != "none":
            action = o["action"]
        else:
            action = _pick_action(text, actions, avoid, seed, no)
        adjacent = prev_no is not None and _is_next(scenes, prev_no, no)
        if o.get("character"):
            character = o["character"]
        elif st["character"]:
            character = st["character"]
        elif not chars:
            character = None
        elif adjacent and prev.get("character"):
            character = prev["character"]
        else:
            ranked = sorted(chars, key=lambda c: _rand(seed, "chr", no, c))
            character = next((c for c in ranked if c != prev.get("character")), ranked[0])
        if o.get("direction"):
            direction = o["direction"]
        elif adjacent and prev.get("direction"):
            direction = prev["direction"]
        elif prev.get("direction"):
            direction = prev["direction"] if _rand(seed, "dir", no) < 0.25 else ("left" if prev["direction"] == "right" else "right")
        else:
            direction = "right" if _rand(seed, "dir0", no) < 0.5 else "left"
        entry = {"character": character, "action": action, "direction": direction, "source": "csv" if chosen[no] == "csv" else "auto",
                 "params": {"motion": st["motion"], "intensity": st["intensity"]}}
        if o and o.get("ground"):
            entry["params"].update(y=o["ground"], y_b=o["ground"])
        if adjacent:
            ttype = next((t for t, rx in TRANSITION_CUES if t in trans and rx.search(text) and t != last_trans), None)
            if ttype is None:
                ranked_t = sorted(trans, key=lambda t: _rand(seed, "trn", no, t))
                ttype = next((t for t in ranked_t if t != last_trans), ranked_t[0])
            dur = float(_get(sc, "end", 0)) - float(_get(sc, "start", 0))
            entry.update({"transition": ttype, "transition_s": round(max(0.4, min(TRANSITION_S, 0.4 * dur)), 3), "transition_from": prev_no})
            last_trans = ttype
        plan[no] = entry
        prev_no, prev = no, entry
    say(f"puppet: {len(plan)} of {len(scenes)} scenes get a character move ({st['intensity']}, seed {seed}); {forced} set by the CSV")
    return plan


def _is_next(scenes: Sequence[Any], a_no: Any, b_no: Any) -> bool:
    nos = [_get(s, "scene_no") for s in scenes]
    try:
        return nos.index(b_no) == nos.index(a_no) + 1
    except ValueError:
        return False


# ---- rendering -----------------------------------------------------------------------------------------------------------------------------

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def still_for(sc: Any) -> Optional[str]:
    """The still picture a scene shows, if it has one: visual['still'|'image'|'path'] or the acquired asset's file when it is an image."""
    vis = _get(sc, "visual", None) or {}
    asset = _get(sc, "asset", None) or {}
    for p in (vis.get("still"), vis.get("image"), vis.get("path"), asset.get("path")):
        if p and str(p).lower().endswith(IMAGE_EXT) and Path(str(p)).is_file():
            return str(p)
    return None


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:20]


def cache_key(kind: str, hashes: Sequence[str], character: Any, what: str, direction: str, params: Optional[dict], frames: int, fps: int, size: Tuple[int, int], version: str = "") -> str:
    """Key of one raw puppet render: still hash(es), character, action/transition, direction, params, length, size and engine version. Nothing else, so editing one
    scene's text re-renders only that scene (and a caption change re-renders nothing here)."""
    payload = json.dumps({"k": kind, "h": list(hashes), "c": character, "w": what, "d": direction, "p": params or {}, "n": int(frames), "fps": int(fps), "s": list(size),
                          "v": PLAN_VERSION + ":" + str(version)}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


class PuppetCancelled(Exception):
    """Raised by Runner when the cancel flag is set and the engine passes no cancellation type of its own."""


class Runner:
    """Renders planned scenes for one run. render() -> {"path", "pre", "cache_hit", "used_kind", "fallback", "puppet"} or None (the engine then renders the scene normally)."""

    def __init__(self, cache_dir: Path, W: int, H: int, fps: int, cancel: Optional[threading.Event] = None, log: Callable[[str], None] = lambda m: None,
                 module: Any = None, conform: Optional[Callable[..., None]] = None, cancel_exc: Optional[type] = None):
        self.dir = Path(cache_dir) / "puppet"
        self.W, self.H, self.fps, self.cancel, self.log = W, H, fps, cancel, log
        self._module_arg, self._mod, self._conform = module, None, conform or self._ffmpeg_conform
        self.cancel_exc = cancel_exc or PuppetCancelled
        self.disabled = ""
        self.stats = {"planned": 0, "rendered": 0, "cache_hits": 0, "fallbacks": 0, "transitions": 0}

    # -- helpers
    def _engine(self):
        if self._mod is None:
            self._mod = self._module_arg or _module()
        return self._mod

    def _check_cancel(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise self.cancel_exc("cancelled")

    def _call(self, fn: Callable, *args, **kw) -> Any:
        """Run an engine call in a worker thread so Stop is honoured within a fraction of a second (the abandoned thread ends on its own)."""
        box: Dict[str, Any] = {}
        def work() -> None:
            try:
                box["r"] = fn(*args, **kw)
            except BaseException as exc:      # noqa: BLE001 - handed to the caller
                box["e"] = exc
        th = threading.Thread(target=work, name="hc-puppet", daemon=True)
        th.start()
        while th.is_alive():
            th.join(0.1)
            self._check_cancel()
        if "e" in box:
            raise box["e"]
        return box.get("r")

    def _raw(self, kind: str, key: str, make: Callable[[str], Any]) -> Tuple[str, bool]:
        self.dir.mkdir(parents=True, exist_ok=True)
        out = self.dir / f"{kind}_{key}.mp4"
        if out.is_file() and out.stat().st_size > 0:
            return str(out), True
        part = self.dir / f"{kind}_{key}.part.mp4"
        try:
            part.unlink(missing_ok=True)
            res = self._call(make, str(part))
            src = Path(str(res or part))
            if not src.is_file() or src.stat().st_size <= 0:
                raise RuntimeError("the puppet engine wrote no video")
            os.replace(src, out)
        finally:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
        return str(out), False

    def _ffmpeg_conform(self, src: str, dst: str, frames: int, captions: Sequence[Tuple[float, float, str]], skip_frames: int) -> None:
        """Puppet video -> the pipeline's clip format: W x H, fps, yuv420p, no audio, exactly `frames` frames, the scene's caption phrases over it."""
        from . import assets, graphics, render_journey as RJ
        ff = assets.ffmpeg_path() or "ffmpeg"
        work = Path(dst).with_suffix(".cap"); work.mkdir(parents=True, exist_ok=True)
        try:
            cmd = [ff, "-y", "-v", "error", "-i", src]
            chain = (f"[0:v]scale={self.W}:{self.H}:force_original_aspect_ratio=increase,crop={self.W}:{self.H},setsar=1,fps={self.fps},"
                     f"tpad=stop_mode=clone:stop_duration=4,format=yuv420p[v0]")
            last = "v0"; n = 0
            off = skip_frames / float(self.fps)
            for a, b, text in captions or []:
                a, b = a - off, b - off
                if b <= 0 or a >= frames / float(self.fps):
                    continue
                n += 1; png = work / f"c{n}.png"; graphics.caption_overlay_png(text, self.W, self.H).save(png); cmd += ["-i", str(png)]
                chain += f";[{last}][{n}:v]overlay=0:0:enable='between(t,{max(a, 0):.3f},{b:.3f})'[v{n}]"; last = f"v{n}"
            cmd += ["-filter_complex", chain, "-map", f"[{last}]", "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", dst]
            RJ.run_cancellable(cmd, self.cancel, 1800)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _final(self, raw: str, raw_key: str, frames: int, captions: Sequence, skip_frames: int, tag: str) -> str:
        ck = hashlib.sha256(json.dumps([raw_key, frames, self.W, self.H, self.fps, [list(c) for c in captions], skip_frames, PLAN_VERSION], default=str).encode()).hexdigest()[:24]
        out = self.dir / f"clip_{tag}_{ck}.mp4"
        if out.is_file() and out.stat().st_size > 0:
            return str(out)
        part = out.with_suffix(".part.mp4")
        try:
            self._conform(raw, str(part), frames, captions, skip_frames)
            os.replace(part, out)
        finally:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
        return str(out)

    # -- one planned scene
    def render(self, sc: Any, entry: dict, prev_sc: Any = None, captions: Sequence = (), frames: Optional[int] = None) -> Optional[dict]:
        self._check_cancel()
        no = _get(sc, "scene_no")
        if self.disabled:
            return None
        self.stats["planned"] += 1
        try:
            if frames is None:
                frames = round(float(_get(sc, "end")) * self.fps) - round(float(_get(sc, "start")) * self.fps)
            if frames <= 0:
                raise ValueError("scene has no frames")
            still = still_for(sc)
            if not still:
                raise RuntimeError("the scene has no still picture to put a character on")
            if not entry.get("character"):
                raise RuntimeError("no character available (the puppet cast is empty)")
            m = self._engine()
            ver = str(getattr(m, "VERSION", "") or getattr(m, "__version__", ""))
            h = file_hash(still)
            pre: List[str] = []
            skip = 0
            tf = 0
            if entry.get("transition") and prev_sc is not None:
                still_a = still_for(prev_sc)
                if still_a:
                    try:
                        tf = min(round(float(entry.get("transition_s") or TRANSITION_S) * self.fps), max(0, frames - round(1.0 * self.fps)))
                        if tf >= round(0.3 * self.fps):
                            k = cache_key("transition", [file_hash(still_a), h], entry["character"], entry["transition"], entry["direction"], entry.get("params"), tf, self.fps, (self.W, self.H), ver)
                            raw, hit = self._raw("transition", k, lambda p: m.render_transition(still_a, still, entry["character"], entry["transition"], p, tf / float(self.fps), fps=self.fps,
                                                                                                 size=(self.W, self.H), direction=entry["direction"]))
                            pre = [self._final(raw, k, tf, captions, 0, "t")]
                            self.stats["transitions"] += 1; self.stats["cache_hits"] += int(hit)
                        else:
                            tf = 0
                    except self.cancel_exc:
                        raise
                    except Exception as exc:      # noqa: BLE001 - the shot still plays without its transition
                        tf = 0; pre = []
                        self.log(f"scene {no}: puppet transition failed ({type(exc).__name__}: {str(exc)[:120]}): no transition, the shot plays alone")
            skip = tf
            n_shot = frames - tf
            k = cache_key("shot", [h], entry["character"], entry["action"], entry["direction"], entry.get("params"), n_shot, self.fps, (self.W, self.H), ver)
            raw, hit = self._raw("shot", k, lambda p: m.render_shot(still, entry["character"], entry["action"], p, duration=n_shot / float(self.fps), fps=self.fps,
                                                                     direction=entry["direction"], size=(self.W, self.H), params=entry.get("params")))
            path = self._final(raw, k, n_shot, captions, skip, "s")
            self.stats["rendered"] += 1; self.stats["cache_hits"] += int(hit)
            return {"path": path, "pre": pre, "cache_hit": bool(hit), "used_kind": "puppet", "fallback": "",
                    "puppet": {"character": entry["character"], "action": entry["action"], "direction": entry["direction"], "transition": entry.get("transition") if pre else None,
                               "source": entry.get("source")}}
        except self.cancel_exc:
            raise
        except ImportError as exc:
            self.disabled = f"puppet engine not available ({exc})"
            self.log(f"puppet: {self.disabled}; scenes are rendered normally")
        except Exception as exc:      # noqa: BLE001 - never stop the video
            self.log(f"scene {no}: puppet render failed ({type(exc).__name__}: {str(exc)[:160]}): normal render used")
        self.stats["fallbacks"] += 1
        return None
