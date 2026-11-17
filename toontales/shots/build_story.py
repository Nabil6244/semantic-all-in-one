"""Toon Tales: whole story plan -> one rendered clip per shot (cached), plus a manifest for the edit step.

Run: python3 -m toontales.shots.build_story <plan.json> [--only s01,s05] [--draft] [--rough]
  --draft   540x960, fewer samples (quick look; cached separately)
  --rough   also join the clips with the voice into out/toontales_<id>_rough.mp4 (no music/SFX/captions yet)

Steps: plan check (errors stop it) -> voice per shot (cached) -> compile shot.json -> render only the
shots whose content or engine code changed (one Blender run for all of them) -> clips.json manifest.
"""
import hashlib
import os
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from toontales.plan import check as C
from toontales.plan import schema as S
from toontales.shots import compile as K

TT = S.TT
ROOT = TT.parent
sys.path[:0] = [str(TT / "audio"), str(TT / "props"), str(TT / "edit")]
import chart  # noqa: E402
import text_art  # noqa: E402
import voice  # noqa: E402

BUILD = TT / "build"
CACHE = BUILD / "cache"
WORKERS = 2
ENGINE_FILES = ["cast/puppet.py", "cast/faces.py", "cast/cast.json", "library/actions.py", "library/poses.json",
                "sets/mine.py", "sets/backdrop.py", "sets/kits.json", "props/props.py", "shots/shot.py", "cast/fx.py", "cast/fx_art.py",
                "sets/ambient.py", "sets/world.py", "sets/parts.py", "sets/diorama.py", "sets/actor.py", "sets/objects.py",
                "diorama/actor_acts.py"]


def engine_hash():
    h = hashlib.sha1()
    for f in ENGINE_FILES:
        h.update((TT / f).read_bytes())
    for f in sorted((TT.parent / "assets" / "diorama" / "cast").glob("*.blend")):  # realistic actors (Channel 3)
        h.update(f.read_bytes())
    return h.hexdigest()[:10]


def ensure_faces(cast_file=None):
    cast_file = Path(cast_file or TT / "cast" / "cast.json")
    out = BUILD / "faces"
    src = [TT / "cast" / "faces.py", cast_file]
    stamp = out / f".stamp_{cast_file.stem}_{hashlib.sha1(str(cast_file).encode()).hexdigest()[:6]}"
    key = hashlib.sha1(b"".join(p.read_bytes() for p in src)).hexdigest()
    if not stamp.exists() or stamp.read_text() != key:
        subprocess.run([sys.executable, str(TT / "cast" / "faces.py"), str(cast_file), str(out)],
                       check=True, capture_output=True)
        stamp.write_text(key)


def ensure_fx():
    out = BUILD / "fx"
    src = TT / "cast" / "fx_art.py"
    stamp = out / ".stamp"
    key = hashlib.sha1(src.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text() != key:
        subprocess.run([sys.executable, str(src), str(out)], check=True, capture_output=True)
        stamp.write_text(key)


def art(kind, text):
    return text_art.make(kind if kind in text_art.STYLE else "label", text, BUILD / "props_art")


def build(plan_path, only=None, draft=False, rough=False):
    plan = S.load_plan(plan_path)
    r = C.check(plan, fix=False)
    if not r["ok"]:
        print(C.format_report(r))
        raise SystemExit("plan has errors: run the checker with --fix and fix the rest first")
    plan = r["plan"]  # normalized: ids and defaults filled in
    cast_file = S.cast_file_for(plan)
    os.environ["TT_CAST"] = str(cast_file)  # voices use the channel's cast
    ensure_faces(cast_file)
    ensure_fx()
    cast_cfg, _ = S.load_cast(cast_file)
    cast_sha = hashlib.sha1(Path(cast_file).read_bytes()).hexdigest()[:12]
    kits = S.load_kits()
    sid = plan["id"]
    work = BUILD / "stories" / sid
    (work / "shots").mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    eng = engine_hash()
    clips, jobs = [], []
    voice.prefetch([(s["speaker"], s["text"]) for s in plan["shots"]], BUILD / "voice")
    for i, shot in enumerate(plan["shots"]):
        line = voice.speak(shot["speaker"], shot["text"], BUILD / "voice")
        if shot.get("screen"):  # trading-screen shot: drawn in Python (edit/chart.py), no Blender
            dur = round(max(1.0, line["dur"] + K.BREATH), 3)
            spec = dict(shot["screen"], seed=shot["screen"].get("seed", i + 1))
            key = hashlib.sha1(json.dumps([spec, dur, chart.VERSION, draft], sort_keys=True).encode()).hexdigest()[:16]
            clip = CACHE / f"screen_{key}.mp4"
            if not clip.exists() and not (only and shot["id"] not in only):
                chart.make(spec, dur, clip, size=(540, 960) if draft else (1080, 1920))
                print("SCREEN", shot["id"], flush=True)
            (work / "shots" / f"{shot['id']}.json").write_text(json.dumps({"id": shot["id"], "dur": dur, "actions": [],
                                                                          "camera": {}, "screen": True}))
            clips.append({"id": shot["id"], "clip": str(clip), "dur": dur, "wav": line["wav"],
                          "voice_dur": line["dur"], "speaker": shot["speaker"], "text": shot["text"],
                          "transition": shot.get("transition", "cut"), "sfx": shot.get("sfx", []),
                          "overlay": shot.get("overlay"), "beat": shot.get("beat"), "set": shot.get("set"),
                          "freeze": shot.get("freeze"), "punch": shot.get("punch"), "mood": shot.get("mood"),
                          "hud": shot.get("hud"), "callout": shot.get("callout")})
            continue
        kit = S.kit_for(plan, shot["set"], kits)
        sj = K.compile_shot(shot, i, line, cast_cfg, kit, art=art)
        sj["cast_file"], sj["cast_sha"] = str(cast_file), cast_sha
        if kit.get("world"):  # 3D toon world built from the model packs: no picture to paint
            sj["world"] = S.world_layout(plan, kit["place"])
            sj["moves"] = shot.get("moves", [])
            sj["ambient"] = (plan["places"][kit["place"]].get("ambient")) or "none"
        elif kit.get("place"):
            img = S.place_image(plan, kit["place"])
            if not img.exists():
                raise SystemExit(f"place '{kit['place']}' has no picture yet ({img}); paint the places first:\n"
                                 f"  cd flow-engine && node ../toontales/sets/paint_places.mjs {plan_path}")
            sj["backdrop"] = str(img)
            pl = (plan.get("places") or {}).get(kit["place"])
            sj["ambient"] = (pl.get("ambient") if isinstance(pl, dict) else None) or "dust"
            sj["backdrop_sha"] = hashlib.sha1(img.read_bytes()).hexdigest()[:12]
        if draft:
            sj["size"], sj["samples"] = [540, 960], 12
        else:  # 720p/8 samples upscaled at encode: same look as 1080p/24, ~5x faster
            sj["size"], sj["samples"] = [720, 1280], 8
        text = json.dumps(sj, sort_keys=True)
        key = hashlib.sha1((text + eng).encode()).hexdigest()[:16]
        clip = CACHE / f"{key}.mp4"
        (work / "shots" / f"{shot['id']}.json").write_text(json.dumps(sj, indent=1))
        clips.append({"id": shot["id"], "clip": str(clip), "dur": sj["dur"], "wav": line["wav"],
                      "voice_dur": line["dur"], "speaker": shot["speaker"], "text": shot["text"],
                      "transition": shot.get("transition", "cut"), "sfx": shot.get("sfx", []),
                      "overlay": shot.get("overlay"), "beat": shot.get("beat"), "set": shot.get("set"),
                      "freeze": shot.get("freeze"), "punch": shot.get("punch"), "mood": shot.get("mood"),
                          "hud": shot.get("hud"), "callout": shot.get("callout")})
        if clip.exists() or (only and shot["id"] not in only):
            continue
        frames = BUILD / "frames" / key
        shutil.rmtree(frames, ignore_errors=True)
        jobs.append({"shot": str(work / "shots" / f"{shot['id']}.json"), "out": str(frames), "clip": str(clip),
                     "id": shot["id"], "fps": sj["fps"]})
    print(f"{len(plan['shots'])} shots, {len(jobs)} to render, {len(plan['shots']) - len(jobs)} cached or skipped",
          flush=True)
    if jobs:
        # WORKERS Blender runs side by side (2 measured 1.55x on a 16 GB M-series Mac; 3 only 1.6x)
        n = min(WORKERS, len(jobs))
        procs = []
        for w in range(n):
            batch = work / f"batch{w}.json"
            batch.write_text(json.dumps(jobs[w::n], indent=1))
            procs.append(subprocess.Popen(["blender", "-b", "--factory-startup", "--python",
                                           str(TT / "shots" / "shot.py"), "--", "--batch", str(batch)],
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))

        def _pump(w, pr):
            for ln in pr.stdout:
                if ln.startswith(("BATCH", "SHOT DONE", "Traceback", "Error:")) and "Shadow buffer" not in ln:
                    print(f"[w{w}] {ln.rstrip()}", flush=True)
            pr.wait()
        threads = [threading.Thread(target=_pump, args=(w, pr)) for w, pr in enumerate(procs)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        for j in jobs:  # encode every finished shot, even if a later one failed
            fr = Path(j["out"])
            if not (fr / "DONE").exists():
                print("NOT RENDERED", j["id"])
                continue
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(j["fps"]), "-i", str(fr / "f%04d.png"),
                            "-vf", "scale=1080:1920:flags=lanczos", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium",
                            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                            j["clip"]], check=True)
            shutil.rmtree(fr, ignore_errors=True)
        bad = [pr.returncode for pr in procs if pr.returncode]
        if bad:
            raise SystemExit(f"Blender stopped with code {bad[0]}")
    manifest = {"id": sid, "title": plan.get("title"), "hook_title": plan.get("hook_title"),
                "keywords": plan.get("keywords", []), "draft": draft, "clips": clips,
                "total": round(sum(c["dur"] for c in clips), 2)}
    (work / ("clips_draft.json" if draft else "clips.json")).write_text(json.dumps(manifest, indent=1))
    print("CLIPS ->", work / ("clips_draft.json" if draft else "clips.json"), f"({manifest['total']:.1f}s)")
    if rough:
        return rough_cut(manifest, work)
    return manifest


def rough_cut(manifest, work):
    """Clips back to back with the voice on top (the edit step adds captions, SFX, music, overlays)."""
    have = [c for c in manifest["clips"] if Path(c["clip"]).exists()]
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{c['clip']}'\n" for c in have))
    inputs, filt, t = [], [], 0.0
    for i, c in enumerate(have):
        inputs += ["-i", c["wav"]]
        filt.append(f"[{i + 1}]adelay={int(t * 1000)}:all=1[a{i}]")
        t += c["dur"]
    filt.append("".join(f"[a{i}]" for i in range(len(have))) + f"amix=inputs={len(have)}:normalize=0[a]")
    out = ROOT / "out" / f"toontales_{manifest['id']}_{'draft' if manifest['draft'] else 'rough'}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), *inputs,
                    "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
    print("ROUGH ->", out)
    return out


def main(argv):
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    build(Path(argv[0]), only=only, draft="--draft" in argv, rough="--rough" in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
