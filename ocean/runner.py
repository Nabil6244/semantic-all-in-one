"""Ocean Predators runner: voice-over words -> planned film (plan.json) -> rendered video. Used by ui/ocean_section.py.

    scenes_from_words(words, total_s)            -> timed sentence scenes (each keeps its words for caption timing)
    auto_chapters(scenes)                        -> chapter start times (list ordinals, "what would you do", long stretches)
    plan_film(scenes, work, channel, log)        -> summary dict; writes work/plan.json
    load_plan(work)                              -> the saved plan dict or None
    sound_events(plan) / music_plan(plan)        -> stage pops / whooshes, one music bed per chapter (deep chapters darker)
    clip_scenes(plan)                            -> the real-clip slots as Visuals-tab scenes (ocean/clips.py)
    render_film(work, voice, out, found=...)     -> {"seconds", "chunks", "clips", ...}; found = {scene_no: {"path", "meta"}} from the
                                                    Visuals tab; a slot without a clip keeps the drawn stage; sound never stops a film

The picture is drawn entirely in code (ocean/stage.py over a black base clip), so a film needs no downloads, no Flow and
no Gemini: only the voice-over. Rendering is split into chunks rendered in parallel, joined, then the mixed voice is laid on
at -14 LUFS (aviation.sound.mix, the same mixer Aviation uses).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import clips as CL
from . import planner as P
from . import reader as R

PLAN_FILE = "plan.json"
CHAPTER_MAX_S = 90.0
CHAPTER_MIN_S = 25.0
DEEP_SETS = ("abyss", "depth_column")
BEDS_CALM = ("long_note_four", "echoes_of_time_v2")
BEDS_DEEP = ("dark_fog",)
BED_LUFS = -33.0
STAGE_SOUND = {"pop": "pop", "rise": "whoosh_soft", "slide_left": "whoosh_soft", "slide_right": "whoosh_soft", "drop": "thud_soft"}


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------- scenes

def scenes_from_words(words: Sequence[Any], total_s: float = 0.0) -> List[Dict[str, Any]]:
    from cinematic_explainer.war.app_section import sentences_from_words

    scenes = sentences_from_words(list(words or []), total_s)
    for sc in scenes:
        sc["words"] = [(w["w"], float(w["t0"]), float(w["t1"])) for w in sc.get("words") or []]
    return scenes


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(w).lower())


def align_script(script: str, words: Sequence[Any]) -> List[tuple]:
    """The script's own words (spelling, numbers, punctuation) on the voice-over's word times: matched by their letters
    (difflib), so a word the speech engine merged, split or dropped still gets a time between its neighbours. Without
    punctuation in the timed words (Edge voices, some transcripts) sentences could not be found; with this they can."""
    import difflib

    toks = str(script or "").split()
    ws = [(str(w[0]), float(w[1]), float(w[2])) if not isinstance(w, dict) else
          (str(w.get("word") or w.get("text") or ""), float(w.get("start", 0)), float(w.get("end", 0))) for w in words or []]
    if not toks or not ws:
        return list(ws)
    times: List[Optional[tuple]] = [None] * len(toks)
    sm = difflib.SequenceMatcher(a=[_norm(t) for t in toks], b=[_norm(w[0]) for w in ws], autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = (ws[blk.b + k][1], ws[blk.b + k][2])
    for op, a0, a1, b0, b1 in sm.get_opcodes():      # replaced runs: spread the script words over the spoken ones
        if op == "replace" and b1 > b0:
            t0, t1 = ws[b0][1], ws[b1 - 1][2]
            n = a1 - a0
            for k in range(n):
                times[a0 + k] = (t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n)
    out: List[tuple] = []
    for i, tok in enumerate(toks):                   # words still without a time sit between their neighbours
        if times[i] is None:
            prev = out[-1][2] if out else 0.0
            nxt = next((times[j][0] for j in range(i + 1, len(toks)) if times[j] is not None), prev + 0.2)
            times[i] = (prev, max(prev, min(nxt, prev + 0.25)))
        out.append((tok, times[i][0], times[i][1]))
    return out


_CHAPTER_START = re.compile(r"^\s*(so |now |but )?(the (first|second|third|fourth|fifth|next|last)|number (one|two|three)|"
                            r"what would you|what if you|imagine you|if you were|so why|why does|here's the thing|which brings)",
                            re.I)


def auto_chapters(scenes: Sequence[Dict[str, Any]]) -> List[float]:
    """Chapter starts from the narration's own turns (list ordinals, the second-person 'what would you do', 'so why');
    a stretch longer than CHAPTER_MAX_S gets a break at its longest pause."""
    starts: List[float] = []
    last = 0.0
    for i, sc in enumerate(scenes):
        t = float(sc["start"])
        text = str(sc.get("text", ""))
        if t - last >= CHAPTER_MIN_S and (_CHAPTER_START.search(text) or R.read(text).ordinal is not None):
            starts.append(t)
            last = t
        elif t - last >= CHAPTER_MAX_S and i > 0:
            gap_i = max(range(max(1, i - 6), i + 1), key=lambda k: float(scenes[k]["start"]) - float(scenes[k - 1]["end"]))
            tt = float(scenes[gap_i]["start"])
            if tt - last >= CHAPTER_MIN_S:
                starts.append(tt)
                last = tt
    return starts


# ---------------------------------------------------------------------------------------------------------------- plan

def plan_film(scenes: Sequence[Dict[str, Any]], work: str, channel: str = "Ocean",
              log: Callable[[str], None] = lambda m: None, real_clips: bool = True) -> Dict[str, Any]:
    if not scenes:
        raise RuntimeError("the voice-over has no sentences to plan from")
    chapters = auto_chapters(scenes)
    pl = P.plan(scenes, chapters, channel=channel or "Ocean")
    wd = Path(work)
    wd.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "channel": channel, "chapters": chapters, "scenes": [dict(s) for s in scenes],
            "layers": pl.layers, "shots": pl.shots, "report": pl.report,
            "total": max(float(s["end"]) for s in scenes)}
    data["clips"] = CL.choose(data["scenes"], pl.layers, data["total"], pl.shots) if real_clips else []
    tmp = wd / (PLAN_FILE + ".tmp")
    tmp.write_text(json.dumps(data, default=list), encoding="utf-8")
    tmp.replace(wd / PLAN_FILE)
    r = pl.report
    log(f"planned {r['shots']} shots (avg {r['shot_avg_s']} s), {sum(r['cards'].values())} cards, {r['captions']} captions, "
        f"{len(chapters)} chapters, {r['species']} animals, {len(data['clips'])} real-clip slots; longest still {r['longest_still_s']} s")
    return {"shots": r["shots"], "cards": sum(r["cards"].values()), "captions": r["captions"], "chapters": len(chapters),
            "duration": data["total"], "species": r["species"], "clips": len(data["clips"]), "report": r}


def clip_scenes(plan: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return CL.visual_scenes((plan or {}).get("clips") or [])


def load_plan(work: str) -> Optional[Dict[str, Any]]:
    f = Path(work) / PLAN_FILE
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------------------------------------------- sound

def sound_events(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A soft pop when a card or animal pops in, a short whoosh when something slides, a thud on a drop; two sounds are
    never closer than the mixer's MIN_GAP_S (the earlier one wins); silhouette passers-by make no sound."""
    from aviation import sound as AS

    raw: List[Dict[str, Any]] = []
    for ly in plan.get("layers") or []:
        if ly.get("name") != "ocean.lay_ocean":
            continue
        s0 = float(ly["start"])
        for e in (ly.get("params") or {}).get("elements") or []:
            if (e.get("args") or {}).get("silhouette") and e.get("kind") == "animal" and float((e.get("args") or {}).get("width", 0)) < 200:
                continue
            name = STAGE_SOUND.get(e.get("enter", ""))
            if name and name in AS.SFX_MAP:
                raw.append(AS._ev(s0 + float(e["t0"]), name))
            if e.get("t1") is not None and str(e.get("exit", "")).startswith("slide"):
                raw.append(AS._ev(s0 + float(e["t1"]), "whoosh_soft"))
    raw.sort(key=lambda e: e["t"])
    kept: List[Dict[str, Any]] = []
    for e in raw:
        if not kept or e["t"] - kept[-1]["t"] >= AS.MIN_GAP_S:
            kept.append(e)
    return kept


def music_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One bed per chapter: a darker bed when most of the chapter is in the deep sets; neighbours cross-fade."""
    from aviation import sound as AS

    total = float(plan.get("total") or 0.0)
    if total <= 0:
        return []
    cuts = [0.0] + [float(c) for c in plan.get("chapters") or [] if 0 < float(c) < total] + [total]
    shots = plan.get("shots") or []
    beds: List[Dict[str, Any]] = []
    calm_i = 0
    for a, b in zip(cuts, cuts[1:]):
        deep = sum(min(b, s["end"]) - max(a, s["start"]) for s in shots if s.get("set") in DEEP_SETS and s["end"] > a and s["start"] < b)
        if deep > 0.5 * (b - a):
            name = BEDS_DEEP[0]
        else:
            name = BEDS_CALM[calm_i % len(BEDS_CALM)]
            calm_i += 1
        beds.append({"start": a, "end": b, "bed": str(AS.MUSIC_DIR / f"{name}.opus"), "gain_db": BED_LUFS, "mood": "ocean",
                     "xfade": AS.XFADE_S, "dips": []})
    h = AS.XFADE_S / 2
    for i, bd in enumerate(beds):
        if i > 0:
            bd["start"] = max(0.0, bd["start"] - h)
        if i < len(beds) - 1:
            bd["end"] = bd["end"] + h
    return beds


# ---------------------------------------------------------------------------------------------------------------- render

def card_table() -> Dict[str, Any]:
    from . import captions as CAP
    from . import stage as OS
    return {**OS.CARDS, **CAP.CARDS}


def timeline(plan: Dict[str, Any], black: str):
    from cinematic_explainer.render import Layer, Shot

    total = float(plan["total"])
    shots = [Shot(black, 0.0, total, 0.0)]
    layers = [Layer(ly["name"], float(ly["start"]), float(ly["end"]), ly.get("params") or {}) for ly in plan.get("layers") or []]
    return shots, layers


def render_film(work: str, voice: str, out: str, *, found: Optional[Dict[str, Dict[str, Any]]] = None, chunk_s: float = 45.0,
                workers: int = 3,
                progress: Callable[[float, str], None] = lambda k, m: None, cancel: Callable[[], bool] = lambda: False,
                log: Callable[[str], None] = lambda m: None, sound: bool = True) -> Dict[str, Any]:
    from aviation import bridge as BR
    from aviation.runner import split_timeline
    from cinematic_explainer import render as RD

    plan = load_plan(work)
    if not plan:
        raise RuntimeError("no planned film: click Generate first")
    if cancel():
        raise Cancelled()
    wd = Path(work)
    total = float(plan["total"])
    black = BR.ensure_black(str(wd / "black.mp4"), total)
    used: List[Dict[str, Any]] = []
    if found:
        shots, layers, used = CL.apply(plan, found, black, str(wd), log)
        if used:
            log(f"{len(used)} real clips cut in (graded into the blue world, credited)")
    else:
        shots, layers = timeline(plan, black)
    chunks = split_timeline(shots, layers, chunk_s)
    table = card_table()
    parts = [wd / f"part_{i:03d}.mp4" for i in range(len(chunks))]
    done = [0]
    mixed: Dict[str, Any] = {}

    def sound_mix() -> None:
        try:
            from aviation import sound as AS
            ev, mu = sound_events(plan), music_plan(plan)
            dst = wd / "voice_mix.m4a"
            AS.mix(str(voice), ev, mu, str(dst), total)
            if dst.is_file() and dst.stat().st_size > 0:
                mixed.update(path=str(dst), events=len(ev), beds=len(mu))
        except Exception as ex:  # noqa: BLE001
            log(f"sound design skipped ({ex}); the plain voice-over is used")

    def one(i: int) -> None:
        if cancel():
            raise Cancelled()
        _c0, cs, cl = chunks[i]
        RD.render(cs, cl, str(parts[i]), card_table=table)
        done[0] += 1
        progress(0.92 * done[0] / len(chunks), f"rendered {done[0]} of {len(chunks)} parts")

    progress(0.01, f"rendering {len(chunks)} parts")
    with ThreadPoolExecutor(max_workers=1) as sx:
        sfut = sx.submit(sound_mix) if sound and total > 0 else None
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for f in [ex.submit(one, i) for i in range(len(chunks))]:
                f.result()
        if sfut is not None:
            sfut.result()
    if mixed.get("path"):
        log(f"sound: {mixed['events']} effects + {mixed['beds']} music beds mixed under the voice")
        voice = mixed["path"]
    if cancel():
        raise Cancelled()
    lst = wd / "parts.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = wd / "joined.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)],
                   check=True, timeout=3600)
    progress(0.95, "laying the voice-over")
    tmp = Path(out).with_name(Path(out).stem + ".part.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", str(tmp)], check=True, timeout=3600)
    if cancel():
        tmp.unlink(missing_ok=True)
        raise Cancelled()
    shutil.move(str(tmp), out)
    for p in parts + [silent, lst]:
        Path(p).unlink(missing_ok=True)
    for u in used:
        Path(u["path"]).unlink(missing_ok=True)
    _write_description(plan, Path(out), used)
    progress(1.0, "done")
    return {"seconds": total, "chunks": len(chunks), "sound": bool(mixed.get("path")), "clips": len(used)}


def _write_description(plan: Dict[str, Any], out: Path, used: Sequence[Dict[str, Any]] = ()) -> None:
    """Chapters with timestamps (+ the real clips' credits) next to the video, ready for the description."""
    try:
        lines = ["0:00 Intro"]
        scenes = plan.get("scenes") or []
        for c in plan.get("chapters") or []:
            sc = next((s for s in scenes if abs(float(s["start"]) - float(c)) < 0.05), None)
            title = " ".join(re.findall(r"[A-Za-z0-9']+", str(sc.get("text", "")) if sc else "")[:6]) or "Chapter"
            m, s = divmod(int(float(c)), 60)
            lines.append(f"{m}:{s:02d} {title}")
        credits = sorted({u["credit"].replace("Footage: ", "") for u in used if u.get("credit")})
        if credits:
            lines += ["", "Credits: Footage: " + "; ".join(credits) + "."]
        out.with_name(out.stem + "_chapters.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
