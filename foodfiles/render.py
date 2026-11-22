"""Food Files render: every shot drawn by FoodDrawer and encoded in parallel (spawn pool, like Prepper Host), joined, mixed.

Sound: Prepper Host's mixer (voice levelled, effects on the card cues, quiet music bed under speech) with the Food Files
cues (stamp thump, sting, number hit) lent to it for this mix only.
"""
import os
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed

from PIL import Image, ImageDraw

from prepper_host import render as R
from . import cards, look as L

Stopped = R.Stopped


def _encode_shot(args):
    spec, assets, i, f0, f1, out, crf = args
    shot = dict(spec["shots"][i], i=i)
    dr = cards.FoodDrawer(spec, assets)
    W, H = spec["size"]
    fps = spec["fps"]
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
                          "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
                          "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", out], stdin=subprocess.PIPE)
    try:
        for fr in range(f0, f1):
            p.stdin.write(dr.frame(shot, fr / fps).tobytes())
    finally:
        p.stdin.close()
        p.wait()
        dr.close()
    if p.returncode:
        raise RuntimeError(f"ffmpeg failed on shot {i}")
    return i


def render_picture(spec, assets, out, workers=None, progress=None, cancel=None, crf=19):
    fps = spec["fps"]
    if spec.get("voice_path") and "env" not in assets:
        assets = dict(assets, env=R.voice_envelope(spec["voice_path"], fps, spec["duration"]))
    shots = spec["shots"]
    total = int(round(spec["duration"] * fps))
    starts = [int(round(s["t0"] * fps)) for s in shots] + [total]
    starts[0] = 0
    with tempfile.TemporaryDirectory() as wd:
        jobs = [(spec, assets, i, starts[i], max(starts[i] + 1, starts[i + 1]), os.path.join(wd, f"s{i:04d}.mp4"), crf)
                for i in range(len(shots))]
        workers = workers or max(1, min(6, (os.cpu_count() or 4) - 2))
        made = set()

        def tick():
            if progress:
                progress(len(made) / len(jobs), f"drawing shot {len(made)}/{len(jobs)}")
            if cancel and cancel():
                raise Stopped("Stopped.")

        if workers > 1:
            try:
                import multiprocessing as mp
                with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
                    futs = {ex.submit(_encode_shot, j): j[2] for j in jobs}
                    try:
                        for fu in as_completed(futs):
                            made.add(fu.result())
                            tick()
                    except Stopped:
                        for g in futs:
                            g.cancel()
                        raise
            except Stopped:
                raise
            except Exception as e:  # noqa: BLE001 - finish on this core
                if progress:
                    progress(len(made) / len(jobs), f"workers failed ({type(e).__name__}); drawing on one core")
        for j in jobs:
            if j[2] not in made:
                made.add(_encode_shot(j))
                tick()
        lst = os.path.join(wd, "list.txt")
        with open(lst, "w") as fh:
            for j in jobs:
                fh.write(f"file '{j[5]}'\n")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", str(out)], check=True)
    return out


def mix(spec, out_wav, sound="music"):
    saved_sfx, saved_bed = dict(R.SFX), R.MUSIC_BED
    try:
        R.SFX.update(L.SFX)
        from . import wall_moments as WM
        R.SFX.update(WM.sound_table(spec))
        R.MUSIC_BED = L.MUSIC_BED
        return R.mix(spec, out_wav, sound=sound)
    finally:
        R.SFX.clear()
        R.SFX.update(saved_sfx)
        R.MUSIC_BED = saved_bed


def thumbnail(picture, lines, out, size=(1280, 720)):
    """Picture on the right, big condensed words on the left, a red stamp, hazard tape along the bottom."""
    W, H = size
    u = H / 720
    base = cards.background(size, "dark").copy()
    if picture and os.path.isfile(picture):
        ph = R.cover(Image.open(picture).convert("RGB"), (int(W * 0.58), H)).convert("RGBA")
        mask = Image.linear_gradient("L").rotate(90).resize(ph.size)          # fades in from the left
        base.paste(ph, (int(W * 0.42), 0), mask)
    d = ImageDraw.Draw(base)
    lines = [l for l in (lines or []) if l][:3] or ["FOOD FILES"]
    y = H * 0.20
    for i, l in enumerate(lines):
        ft = cards.fit_font(d, l.upper(), L.TITLE_FONT, (150 if i == 0 else 120) * u, W * 0.52)
        col = L.RED if i == 0 else L.WHITE
        for dx, dy in ((5, 5), (-3, 3), (3, -3)):
            d.text((50 * u + dx * u, y + dy * u), l.upper(), font=ft, fill=(0, 0, 0, 255), anchor="lt")
        d.text((50 * u, y), l.upper(), font=ft, fill=col + (255,), anchor="lt")
        y += ft.size * 1.05
    th = int(46 * u)
    base.alpha_composite(cards.tape(W, th), (0, H - th))
    base.convert("RGB").save(out, quality=92)
    return out
