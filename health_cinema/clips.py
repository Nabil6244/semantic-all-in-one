"""Per-scene clip renderers for Health Cinema. Every clip is 1920x1080 (or the 1280x720 preview), 24 fps, yuv420p, no audio, an exact frame count.
A 3D scene that cannot render (no asset, no Node/Chromium, worker failure) falls back to a text card and records why; it never stops the video."""
from __future__ import annotations
import copy, hashlib, json, os, shutil, subprocess, threading
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from . import assets, cards, graphics, profiles as P, render_journey as RJ
from .planner import Scene

LIGHTING = "tissue"      # soft studio light, wet tissue, matte bone (page.js); Rep Theory, which renders through the same page, keeps the classic look

FPS = 24
SIZES = {"final": (1920, 1080), "preview": (1280, 720)}
TEMPLATES = Path(__file__).resolve().parent / "templates"
CLIP_VERSION = "1"

def template_spec(name: str, variant: int = 0) -> dict:
    from . import library
    return library.apply_variant(_template_spec(name), int(variant or 0))

def _template_spec(name: str) -> dict:
    if name.startswith(("auto:", "micro:", "cond:")):      # generated from the library (condition scenes too): needs the model's anchors
        from . import library
        return library.build_spec(name, assets.anatomy_assets(library.model_of(name))["anchors"])
    if name in ("brain_journey", "eye_journey"): return json.loads((TEMPLATES / f"{name}.json").read_text())
    spec = json.loads((TEMPLATES / "heart_journey.json").read_text())
    if name == "heart_journey": return spec
    if name == "chest_journey":   # body -> chest -> lungs: the same path cut at the lungs
        cut = 8.2
        spec["duration"] = cut; spec["camera"] = [k for k in spec["camera"] if k["t"] <= 6.0] + [{"t": cut, "target": "lungs", "dist": 1.05, "az": 8, "el": 3, "fov": 30}]
        for k in ("Layer_Vessels", "Layer_Heart", "Layer_HeartCut", "Layer_HeartInner"): spec["layers"].pop(k, None)
        spec["layers"]["Layer_Lungs"] = [[0, 0.0], [5.2, 0.0], [6.1, 0.85], [cut, 0.85]]
        spec["glow"] = [g for g in spec["glow"] if g["id"] in ("chest", "skin")]
        spec["labels"] = [l for l in spec["labels"] if l["id"] == "chest"] + [{"id": "lungs", "text": "Lungs", "anchor": "lungs", "offset": [0.07, -0.05, 0.05], "t0": 6.6, "t1": cut - 0.4, "side": "right", "layer": "Layer_Lungs"}]
        spec["layer_order"] = [n for n in spec["layer_order"] if n not in ("Layer_Vessels", "Layer_Heart", "Layer_HeartCut", "Layer_HeartInner")]
        return spec
    raise KeyError(name)

def scale_spec(spec: dict, seconds: float) -> dict:
    """Stretch the journey's timeline to `seconds` (every time value scales; geometry, order and look are unchanged)."""
    k = seconds / spec["duration"]; s = copy.deepcopy(spec); s["duration"] = seconds
    for c in s["camera"]: c["t"] *= k
    for ch in ("layers",):
        for name, keys in s[ch].items(): s[ch][name] = [[t * k, v] for t, v in keys]
    for g in s.get("glow", []): g["strength"] = [[t * k, v] for t, v in g["strength"]]
    for fl in s.get("flow", []): fl["strength"] = [[t * k, v] for t, v in fl["strength"]]
    for pu in s.get("pulse", []):
        if pu.get("strength"): pu["strength"] = [[t * k, v] for t, v in pu["strength"]]      # pulse and flow rates are real-world (per minute): only their envelopes stretch
    for h in s.get("highlights", []): h["strength"] = [[t * k, v] for t, v in h["strength"]]
    for l in s.get("labels", []): l["t0"] *= k; l["t1"] *= k
    for name, keys in s.get("tracks", {}).items(): s["tracks"][name] = [[t * k, v] for t, v in keys]      # procedural-scene tracks and pathology tints follow the stretched timeline too
    for name, keys in s.get("tints", {}).items(): s["tints"][name] = [[t * k, v] for t, v in keys]
    return s

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def organ_cards(wanted: list, spec: dict, anchors: dict, log: Callable[[str], None] = lambda m: None) -> list:
    """Illustration cards on an organ 3D scene (CSV card_type / card_ref on a 3d row), pinned where the camera is looking when the card appears, like a
    body-map card. A card whose picture is not in the illustration library yet is left out and said (Generate scenes makes it in the Visuals tab)."""
    from . import illustrations as ILL
    D = float(spec["duration"]); out = []
    for i, c in enumerate(wanted):
        e = ILL.find(c.get("ref") or "")
        if not e: log(f"illustration card '{c.get('ref') or c.get('prompt', '')[:40]}' is not in the library yet: this 3D scene is drawn without it"); continue
        if Path(e["path"]).suffix.lower() not in IMAGE_EXT: log(f"illustration card '{c.get('ref')}' is not a picture ({Path(e['path']).name}): this 3D scene is drawn without it"); continue      # a video put in a card row must not break the scene
        t0 = float(c["at"]) if c.get("at") not in (None, "") else min(1.6, D * 0.25); t1 = max(t0 + 1.5, D - 0.3)
        if c.get("auto"): t0, t1 = 0.5, max(2.3, min(D * 0.36, 4.2))      # an automatic card plays during the opening move and leaves before the labels
        keys = [k for k in spec.get("camera", []) if k.get("target") in anchors] or [{"t": 0, "target": next((l["anchor"] for l in spec.get("labels", []) if l["anchor"] in anchors), None)}]
        target = ([k for k in keys if k.get("t", 0) <= (t0 + t1) / 2] or keys)[-1].get("target")
        if not target: continue
        out.append({"id": f"oc{i}", "image": e["path"], "sha256": e["sha256"], "title": e.get("title") or (e.get("topic") or "").capitalize(), "tag": "ILLUSTRATION",
                    "foot": "AI-generated medical illustration, not a clinical photograph" if e["source"] == "flow" else "Illustration",
                    "anchor": target, "t0": round(t0, 2), "t1": round(min(D - 0.05, t1), 2), "side": "left" if c.get("auto") else "right"})
    for cd in out:      # a label on the card's side waits until the card has gone
        for l in spec.get("labels", []):
            if l.get("side") == cd["side"] and l["t0"] < cd["t1"] + 0.2 < l["t1"] - 1.0: l["t0"] = round(cd["t1"] + 0.2, 2)
    return out


def captions_for(sc: Scene):
    return [(round(a, 3), round(b, 3), t) for a, b, t in graphics.caption_chunks(sc.sentences, sc.start)] if sc.sentences else []

def clip_key(sc: Scene, W: int, H: int, extra: str = "") -> str:
    payload = json.dumps({"k": sc.kind, "v": sc.visual, "cap": captions_for(sc), "asset": (sc.asset or {}).get("path", ""), "p": sc.profile, "ill": sc.illustrative, "W": W, "H": H, "fps": FPS, "frames": round(sc.end * FPS) - round(sc.start * FPS), "ver": CLIP_VERSION, "x": extra, "code": RJ.code_version((Path(__file__), Path(cards.__file__)))}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]

def _overlay_inputs(ovs, W: int, H: int, dur: float, work: Path, accent, first_input: int, last: str) -> Tuple[list, str, str]:
    """ffmpeg inputs and filter steps that put the scene's overlays (graphics.overlay_layer) over the stream `last`, one after another: each fades in at
    its t0 and out at its t1 (default: before the scene ends); a pulse also scrolls its heart-rate line. -> (input args, filter text starting with ';', last label)."""
    args, chain, n = [], "", first_input
    for j, ov in enumerate([o for o in (ovs if isinstance(ovs, list) else [ovs]) if o]):
        a_, c_, last, used = _one_overlay(ov, j, W, H, dur, work, accent, n, last); args += a_; chain += c_; n += used
    return args, chain, last


def _one_overlay(ov: dict, j: int, W: int, H: int, dur: float, work: Path, accent, n: int, last: str):
    t0 = max(0.0, min(float(ov.get("t0", 0.6)), dur - 1.6)); t_out = max(t0 + 0.8, min(float(ov.get("t1", dur - 0.7)), dur - 0.7))
    png = work / f"ov{j}.png"; graphics.overlay_layer(ov, W, H, accent).save(png)
    args = ["-loop", "1", "-framerate", str(FPS), "-i", str(png)]
    chain = (f";[{n}:v]format=rgba,fade=t=in:st={t0:.2f}:d=0.45:alpha=1,fade=t=out:st={t_out:.2f}:d=0.4:alpha=1[ova{j}]"
             f";[{last}][ova{j}]overlay=0:0[ovv{j}]"); last = f"ovv{j}"
    if ov.get("type") == "pulse":
        bw, bh = graphics.pulse_box(W, H); strip = work / f"pulse{j}.png"; graphics.pulse_strip(W, H, accent).save(strip)
        try: bpm = float(str(ov.get("bpm") or 70).split("-")[0])
        except ValueError: bpm = 70.0
        speed = (bw / 2) / (60.0 / max(30.0, min(180.0, bpm))); x = W - round(W * 0.05) - bw; y = round(H * 0.07) + round(56 * H / 1080)
        args += ["-loop", "1", "-framerate", str(FPS), "-i", str(strip)]
        chain += (f";[{n + 1}:v]format=rgba,crop=w={bw}:h={bh}:x='mod(t*{speed:.2f}\\,{bw})':y=0,fade=t=in:st={t0:.2f}:d=0.45:alpha=1,fade=t=out:st={t_out:.2f}:d=0.4:alpha=1[pls{j}]"
                  f";[{last}][pls{j}]overlay={x}:{y}[plv{j}]"); last = f"plv{j}"
        return args, chain, last, 2
    return args, chain, last, 1


def _with_overlay(src: str, ov, W: int, H: int, frames: int, out: Path, ffmpeg: str, accent, cancel: Optional[threading.Event] = None) -> None:
    """A finished clip (a 3D journey) with an overlay laid over it; the clip itself is not changed."""
    import tempfile
    tmp = out.with_suffix(".part.mp4"); work = Path(tempfile.mkdtemp(prefix="hco_"))
    try:
        args, chain, last = _overlay_inputs(ov, W, H, frames / FPS, work, accent, 1, "0:v")
        cmd = [ffmpeg, "-y", "-v", "error", "-i", src] + args + ["-filter_complex", chain.lstrip(";") + f";[{last}]format=yuv420p[vout]", "-map", "[vout]", "-frames:v", str(frames), "-an",
                                                                   "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
        RJ.run_cancellable(cmd, cancel, 1800); tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True); shutil.rmtree(work, ignore_errors=True)


def _footage_clip(path: str, W: int, H: int, frames: int, out: Path, ffmpeg: str, cancel: Optional[threading.Event] = None, captions=None,
                  overlay=None, accent=(255, 112, 90)) -> None:
    """Cover-crop to 16:9, hold the last frame if the clip is short (or loop it when it is much shorter), a slow push-in, dip-to-dark fades at both ends so
    footage and graphics join without a hard cut, and caption PNGs overlaid only during their phrase."""
    import tempfile
    tmp = out.with_suffix(".part.mp4"); dur = frames / FPS; fade = 0.35
    base = (f"[0:v]scale={int(W * 1.12)}:{int(H * 1.12)}:force_original_aspect_ratio=increase,crop={int(W * 1.12)}:{int(H * 1.12)},setsar=1,fps={FPS},"
            f"zoompan=z='1+0.07*on/{max(1, frames)}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={FPS},format=yuv420p[v0]")
    cmd = [ffmpeg, "-y", "-v", "error", "-stream_loop", "-1", "-i", path]; work = Path(tempfile.mkdtemp(prefix="hcc_")); chain = base; last = "v0"
    try:
        for i, (a, b, text) in enumerate(captions or []):
            png = work / f"c{i}.png"; graphics.caption_overlay_png(text, W, H).save(png); cmd += ["-i", str(png)]
            chain += f";[{last}][{i + 1}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[v{i + 1}]"; last = f"v{i + 1}"
        args, ochain, last = _overlay_inputs(overlay, W, H, dur, work, accent, len(captions or []) + 1, last); cmd += args; chain += ochain
        chain += f";[{last}]fade=t=in:st=0:d={fade}:color=black,fade=t=out:st={max(0.0, dur - fade):.3f}:d={fade}:color=black[vout]"
        cmd += ["-filter_complex", chain, "-map", "[vout]", "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
        RJ.run_cancellable(cmd, cancel, 1800)
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True); shutil.rmtree(work, ignore_errors=True)

def render_scene(sc: Scene, prof: P.Profile, cache_dir: Path, *, quality: str = "final", cancel: Optional[threading.Event] = None, log: Callable[[str], None] = lambda m: None,
                 frame_renderer: Optional[Callable] = None) -> Dict:
    """-> {"path", "cache_hit", "used_kind", "fallback": "" | reason}. Cached by content key under cache_dir."""
    W, H = SIZES[quality]; frames = round(sc.end * FPS) - round(sc.start * FPS)
    if frames <= 0: raise ValueError("scene has no frames")
    cache_dir = Path(cache_dir); cache_dir.mkdir(parents=True, exist_ok=True); ff = assets.ffmpeg_path() or "ffmpeg"
    is_cancelled = (lambda: bool(cancel and cancel.is_set()))
    kind, visual, fallback = sc.kind, dict(sc.visual), ""
    if kind == "anatomy_3d":
        a = assets.anatomy_assets(assets.model_for_template(sc.visual.get("template", "heart_journey")) or "chest")
        if not a or (frame_renderer is None and not assets.threejs_ready()):
            fallback = "3D assets or Node/three.js not available"; kind = "text_card"; visual = {"text": sc.text, "illustrative": ""}
        else:
            try:
                if sc.visual.get("body_rows"):      # one continuous body-map shot built from the CSV beats (bodymap.py); invalid beats never reach a frame
                    from . import bodymap
                    beats = bodymap.beats_from_rows(sc.visual["body_rows"], sc.start); chk = bodymap.validate(beats, bodymap.load_anchors(a["anchors"]))
                    if chk["errors"]: raise ValueError("body-map beats are not valid: " + "; ".join(chk["errors"])[:200])
                    spec = bodymap.build_spec(beats, bodymap.load_anchors(a["anchors"]), frames / FPS)
                else: spec = scale_spec(template_spec(sc.visual["template"], sc.visual.get("variant", 0)), frames / FPS)
                from . import parts, variety
                if not sc.visual.get("body_rows") and not str(sc.visual.get("template", "")).startswith(("cond:", "micro:")):
                    spec = parts.focus(spec, " ".join(x for x in (sc.visual.get("subject"), sc.text) if x), a["anchors"])      # the CSV's visual subject first, then the sentence      # the part the sentence names (a valve, the retina, a disc ...) is where the shot ends
                spec = variety.apply(spec, sc.visual.get("direction"))      # this video's own camera move and mood for the scene
                spec["footer"] = sc.illustrative; spec["captions"] = captions_for(sc); spec["lighting"] = LIGHTING      # Health Cinema's own look (threejs/page.js)
                if sc.visual.get("cards") and not sc.visual.get("body_rows"): spec["cards"] = organ_cards(sc.visual["cards"], spec, {**json.loads(Path(a["anchors"]).read_text())["anchors"], **spec.get("anchor_overrides", {})}, log)      # drawn scenes keep their points in the spec
                sp = cache_dir / f"spec_{clip_key(sc, W, H, 'spec')}.json"; sp.write_text(json.dumps(spec))
                r = RJ.render_journey(sp, a["anchors"], a["model"], W, H, FPS, cache_dir / "journeys", cancel=cancel, frame_renderer=frame_renderer or RJ.pooled_frames,
                                      on_line=None)
                if sc.visual.get("overlays"):      # the figures / labels / pulse over the 3D picture: a separate clip, so the journey cache stays as it is
                    ov_out = cache_dir / f"anatomy_ov_{clip_key(sc, W, H, 'ov')}.mp4"
                    if not (ov_out.exists() and ov_out.stat().st_size > 0): _with_overlay(r["path"], sc.visual["overlays"], W, H, frames, ov_out, ff, prof.accent, cancel)
                    return {"path": str(ov_out), "cache_hit": r["cache_hit"], "used_kind": "anatomy_3d", "fallback": ""}
                return {"path": r["path"], "cache_hit": r["cache_hit"], "used_kind": "anatomy_3d", "fallback": ""}
            except RJ.Cancelled: raise
            except Exception as exc:
                fallback = f"3D render failed: {str(exc)[:160]}"; log(fallback); kind = "text_card"; visual = {"text": sc.text}
    key = clip_key(sc, W, H, kind if fallback else ""); out = cache_dir / f"{kind}_{key}.mp4"
    if out.exists() and out.stat().st_size > 0 and not fallback: return {"path": str(out), "cache_hit": True, "used_kind": kind, "fallback": ""}
    if kind == "footage":
        _footage_clip(visual["path"], W, H, frames, out, ff, cancel, captions_for(sc), visual.get("overlays"), prof.accent)
    else:
        prm = dict(visual); prm["illustrative"] = sc.illustrative if kind != "anatomy_3d" else ""
        if kind in ("counter_card", "bar_card", "timeline_card"): prm["captions"] = captions_for(sc); prm["source_line"] = _source_line(sc)
        if kind == "stat_card": prm.update(_stat_params(sc))
        if kind == "evidence_card": prm.update({"level": sc.evidence_level, "source_line": _source_line(sc)})
        if kind == "chapter_card": prm = {"title": visual.get("title") or sc.chapter or sc.text[:80], "kicker": visual.get("kicker") or "Chapter"}
        cards.render_card_clip(kind, prm, prof, W, H, FPS, frames, out, ff, cancel=is_cancelled)
    return {"path": str(out), "cache_hit": False, "used_kind": kind, "fallback": fallback}

def _source_line(sc: Scene) -> str:
    if not sc.sources: return ""
    s = sc.sources[0]; bits = [s.get("title") or s.get("citation") or "", str(s.get("year") or ""), s.get("population") or s.get("context") or ""]
    return " · ".join(b for b in bits if b)

def _stat_params(sc: Scene) -> dict:
    num = (sc.visual.get("number") or "").replace(",", ""); unit = sc.visual.get("unit") or ("%" if "%" in sc.text or "percent" in sc.text.lower() else "")
    return {"number": num, "unit": unit, "source_line": _source_line(sc), "context": sc.text}
