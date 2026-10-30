"""Rep Theory engine: narration sentences -> scenes -> one 16:9 video with the voiceover. One ffmpeg process takes raw frames from the compositor and the voiceover as its audio input:
nothing is left behind on cancel, memory stays bounded (a frame at a time), exact frame counts. Same entry shape as health_cinema.engine.run_health_cinema."""
from __future__ import annotations
import json, os, subprocess, threading, time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import cadence as C, draw as D, library as L, planner as P, scenes as S, theme as T

class Cancelled(Exception): pass
TRANSITION_S = 0.45
NOT_IMPLEMENTED = ["tier list with more than one ranked item per video", "before/after comparison scene", "word-level timing from the transcript when the scenes file has none (words are spread by length inside each sentence)"]

def _ff() -> str:
    try:
        from health_cinema import assets
        return assets.ffmpeg_path() or "ffmpeg"
    except Exception: return "ffmpeg"
def _probe(path: str) -> float:
    try: r = subprocess.run([_ff().replace("ffmpeg", "ffprobe") if "ffmpeg" in _ff() else "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60); return float(r.stdout.strip())
    except Exception: return 0.0

def end_card_config(cfg: Optional[dict], title: str, log: Callable[[str], None] = lambda m: None) -> Optional[dict]:
    """The optional product end card: {enabled, title, url, image}. None (no card) unless enabled; a missing title falls back to the section label; an unreadable or missing picture gives a text-only
    card; with nothing at all to show (no title, URL or picture) there is no card, and the log says why. Never raises."""
    if not cfg or not cfg.get("enabled"): return None
    ttl = (cfg.get("title") or "").strip() or (title or "").split("\u00b7")[0].strip(); url = (cfg.get("url") or "").strip(); img = None; ipath = (cfg.get("image") or "").strip()
    if ipath:
        img = D.Ctx(1920, 1080).file_art(str(Path(ipath).expanduser())) if Path(ipath).expanduser().is_file() else None
        if img is None: log(f"end card: the picture '{ipath}' could not be read: the card is text only")
    if not (ttl or url or img): log("end card: enabled but no title, URL or picture was given: no end card"); return None
    return {"title": ttl, "url": url, "image": img}

def timeline(sentences: List[dict], total_s: float) -> List[dict]:
    ss = sorted((dict(s) for s in sentences), key=lambda s: float(s["start"]))
    for i, s in enumerate(ss):
        s["start"] = 0.0 if i == 0 else float(ss[i - 1]["end"]); s["end"] = float(ss[i + 1]["start"]) if i + 1 < len(ss) else max(float(s["end"]), total_s or float(s["end"])); s["scene_no"] = i + 1
    return ss

def run_rep_theory(project_dir, sentences: List[dict], voiceover_path: str, out_path: str, *, quality: str = "final", title: str = "", cancel_check: Optional[Callable[[], bool]] = None,
                   progress_cb: Optional[Callable[[float, str], None]] = None, log: Callable[[str], None] = lambda m: None, write_report: bool = True, max_seconds: float = 0.0,
                   end_card: Optional[dict] = None, planner: str = "legacy", per_beat: bool = False, illustrate: bool = False, flow_mode: str = "agent") -> Dict:
    t0 = time.time(); cancelled = cancel_check or (lambda: False); prog = progress_cb or (lambda k, m: None)
    if quality not in T.SIZES: raise ValueError(f"quality must be one of {list(T.SIZES)} (16:9 landscape only)")
    W, H = T.SIZES[quality]; total = _probe(voiceover_path) if voiceover_path else 0.0; sents = timeline(sentences, total)
    need = ["rep_stand_v1"]; miss = L.missing(need)
    if miss: raise RuntimeError(f"Rep Theory art missing: {', '.join(miss)} (looked in: {L.where()}). It ships with the app in assets/reptheory, so this install is incomplete; to add your own pictures use reptheory.library.register (nothing is generated automatically)")
    scenes, plan_info = None, {"planner": "legacy"}
    if planner == "beats":      # the narrative beat planner; any failure falls back to the legacy sentence planner and says so (never a silent switch)
        try:
            from . import beats as B
            res = B.plan(sents, title=title, per_beat=per_beat); scenes = res["scenes"]; plan_info = {"planner": "beats", "summary": res["summary"]}
            if write_report: C.write_report(Path(str(out_path) + ".plan"), res)
        except Exception as ex:
            log(f"beat planner failed ({type(ex).__name__}: {ex}); using the legacy planner"); plan_info = {"planner": "legacy", "fallback_from": "beats", "fallback_reason": f"{type(ex).__name__}: {ex}"}
    if scenes is None: scenes = P.plan(sents, title=title)
    if not scenes: raise ValueError("no scenes to render")
    if illustrate:      # a picture per beat from the narration, generated once through Flow and cached (reptheory/beat_art.py)
        from . import beat_art as BA
        try: log(f"[REP THEORY ART] beat pictures: {BA.prepare(scenes, mode=flow_mode, log=log)}")
        except Exception as ex: log(f"[REP THEORY ART] beat pictures unavailable ({type(ex).__name__}: {ex}); scenes keep their previous treatment")
    for sc in scenes: log(f"scene {sc['no']} {sc['start']:.1f}-{sc['end']:.1f}s {sc['kind']} ({sc['art'] or 'no art'}): {'; '.join(sc['decisions'][:2])}")
    end_s = scenes[-1]["end"] if not max_seconds else min(scenes[-1]["end"], max_seconds); n_narr = round(end_s * T.FPS); ctx = D.Ctx(W, H)
    card = None if max_seconds else end_card_config(end_card, title, log)      # optional: off (None / not enabled) keeps the ending exactly as it was
    n_frames = n_narr + (round(D.END_CARD_S * T.FPS) if card else 0)
    out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True); tmp = out_path.with_name(out_path.name + ".rendering.mp4")
    cmd = [_ff(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(T.FPS), "-i", "-"]
    if voiceover_path: cmd += ["-i", voiceover_path, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-af", "apad", "-t", f"{n_frames / T.FPS:.3f}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE); err: List[bytes] = []
    th = threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True); th.start()
    starts = [round(sc["start"] * T.FPS) for sc in scenes] + [n_frames]; cur = 0; counts = {}
    try:
        for f in range(n_frames):
            if cancelled(): raise Cancelled("cancelled")
            while cur + 1 < len(scenes) and f >= starts[cur + 1]: cur += 1
            sc = scenes[cur]; t = f / T.FPS - sc["start"]; changed = bool(cur) and scenes[cur - 1]["section"] != sc["section"]
            if f >= n_narr:      # the optional end card: the last scene's final state pushes out into it
                tc = (f - n_narr) / T.FPS; cv = ctx.backdrop(); D.ghost_word(cv, ctx, sc.get("topic", ""), t); D.end_card(cv, ctx, card["title"], card["url"], card["image"], tc)
                if tc < TRANSITION_S: cv = S.transition(S.frame(ctx, sc, t, tag=False), cv, tc / TRANSITION_S, ctx)
                proc.stdin.write(cv.tobytes()); continue
            img = S.frame(ctx, sc, t, tag=False)
            if cur and t < TRANSITION_S:      # push transition into the next scene; the section tag is drawn once, over both
                outgoing = S.frame(ctx, scenes[cur - 1], scenes[cur - 1]["end"] - scenes[cur - 1]["start"] + t, tag=False); img = S.transition(outgoing, img, t / TRANSITION_S, ctx)
            D.section_tag(img, ctx, sc["section"], t if (changed or not cur) else 9.0, scenes[cur - 1]["section"] if changed else None, 0.0)
            proc.stdin.write(img.tobytes())
            if f % 24 == 0: prog(f / n_frames, f"scene {sc['no']}/{len(scenes)}: {sc['kind']}")
        proc.stdin.close(); rc = proc.wait(timeout=7200); th.join(5); proc.stderr.close()
        if rc != 0: raise RuntimeError("ffmpeg failed: " + (err[0].decode(errors="replace")[-400:] if err else str(rc)))
        os.replace(tmp, out_path)
    except BaseException:
        try: proc.kill(); proc.wait(5); th.join(5); proc.stderr.close()
        except Exception: pass
        try: tmp.unlink(missing_ok=True)
        except OSError: pass
        raise
    for sc in scenes: counts[sc["kind"]] = counts.get(sc["kind"], 0) + 1
    rep = {"ok": True, "out": str(out_path), "quality": quality, "size": [W, H], "fps": T.FPS, "frames": n_frames, "end_card": bool(card), "plan": plan_info, "cadence": C.metrics(scenes, n_narr / T.FPS), "seconds": round(time.time() - t0, 2), "video_seconds": round(n_frames / T.FPS, 2),
           "scenes": [{k: v for k, v in sc.items() if k not in ("words",)} for sc in scenes], "kind_counts": counts, "art_used": sorted({sc["art"] for sc in scenes if sc["art"]}), "art_source": {a: (L.find(a) or {}).get("source") for a in {sc["art"] for sc in scenes if sc["art"]}},
           "not_implemented": NOT_IMPLEMENTED}
    if write_report: Path(str(out_path) + ".rep_theory.json").write_text(json.dumps(rep, indent=1, default=str))
    prog(1.0, "done"); return rep
