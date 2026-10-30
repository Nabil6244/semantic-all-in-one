"""Story Fast compositor: every treatment moves, never goes black, right frame count/size; envs, cache, cancel, job_key."""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from story_fast import compose as C

fails = []
def ok(c, m):
    print(("ok  " if c else "FAIL"), m)
    if not c: fails.append(m)

OUT = ROOT / "out" / "story_fast_test"; OUT.mkdir(parents=True, exist_ok=True)
SMALL = (640, 360)
USING_FAKE_DEPTH = False
if not C._depth_available():          # depth model not installed: synthetic depth so the layered path is still exercised
    USING_FAKE_DEPTH = True
    def _fake(path):
        im = Image.open(path); w, h = im.size; y, x = np.mgrid[0:h, 0:w]
        d = np.exp(-(((x / w - .5) * 2.2) ** 2 + ((y / h - .55) * 2.2) ** 2)); g = np.asarray(im.convert("L"), np.float32) / 255
        return (.7 * d + .3 * g).astype(np.float32)
    C._depth = _fake; C._depth_available = lambda: True

def frames(path, idx, w, h):
    """uint8 luma frames n=idx via ffmpeg rawvideo (gray)."""
    ff = C._ffmpeg(); res = []
    for n in idx:
        r = subprocess.run([ff, "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
        res.append(np.frombuffer(r.stdout, np.uint8).reshape(h, w).astype(np.float32) if len(r.stdout) == w * h else None)
    return res

def probe(path):
    ff = C._ffmpeg().replace("ffmpeg", "ffprobe")
    r = subprocess.run([ff, "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries", "stream=nb_read_frames,width,height,pix_fmt", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    a = r.stdout.strip().split(","); return int(a[0]), int(a[1]), int(a[3]), a[2]

def pics():
    d = OUT / "pics"; d.mkdir(exist_ok=True)
    rng = np.random.default_rng(3)
    # portrait 1000x1600 with structure, tiny 320x200
    def mk(w, h, name):
        y, x = np.mgrid[0:h, 0:w]; a = np.stack([120 + 100 * np.sin(x / 37.0), 100 + 90 * np.cos(y / 41.0), 140 + 80 * np.sin((x + y) / 53.0)], -1)
        a += rng.normal(0, 6, a.shape); Image.fromarray(a.clip(0, 255).astype(np.uint8)).save(d / name); return str(d / name)
    return mk(1000, 1600, "portrait.png"), mk(320, 200, "tiny.png")

portrait, tiny = pics()
REAL = [str(ROOT / "Images" / n) for n in ("011.png", "016.png", "033.png") if (ROOT / "Images" / n).is_file()]
base = REAL[0] if REAL else portrait

def job(tr, still=None, **kw):
    j = {"shot_id": "t", "still": still or base, "duration": 1.5, "fps": 30, "size": SMALL, "seed": 7, "treatment": tr}; j.update(kw); return j

W, H = SMALL
MOVE_MIN = {"hold_alive": .15, "handheld": .25}
t0 = time.time()
ok(set(("push_in pull_out pan_left pan_right tilt_up tilt_down parallax_left parallax_right dolly_through arc reveal_up track_lateral handheld hold_alive").split()) <= set(C.TREATMENTS), "all treatments listed")
ok(set("dust fog embers rain snow light_sweep shimmer none".split()) <= set(C.ENVIRONMENTS), "all environments listed")
ok(C.available_encoder() in ("h264_videotoolbox", "libx264"), f"encoder {C.available_encoder()}" + (" (synthetic depth: model missing)" if USING_FAKE_DEPTH else ""))

for tr in C.TREATMENTS:
    out = OUT / f"{tr}.mp4"
    try:
        C.render_shot(job(tr), str(out))
        w, h, n, pf = probe(out)
        fr = frames(out, [0, 22, 44], W, H)
        luma = [float(f.mean()) for f in fr if f is not None]
        mv = float(np.abs(fr[0] - fr[2]).mean())
        good = (w, h, n, pf) == (W, H, 45, "yuv420p") and len(luma) == 3 and min(luma) > 8 and mv > MOVE_MIN.get(tr, .6)
        ok(good, f"{tr}: {w}x{h} {n}f {pf} luma>{min(luma):.0f} move={mv:.2f}")
    except Exception as e:
        ok(False, f"{tr}: {e!r}")

# other aspects / sizes: portrait, tiny, and the other real pictures, for a flat and a layered treatment
for name, p in [("portrait", portrait), ("tiny", tiny)] + [(Path(x).stem, x) for x in REAL[1:]]:
    for tr in ("push_in", "parallax_right", "track_lateral"):
        try:
            out = OUT / f"{name}_{tr}.mp4"; C.render_shot(job(tr, p), str(out)); w, h, n, pf = probe(out); fr = frames(out, [0, 44], W, H)
            ok((w, h, n) == (W, H, 45) and float(fr[0].mean()) > 8 and float(np.abs(fr[0] - fr[1]).mean()) > .5, f"{name}/{tr}: cover-fit {w}x{h} {n}f moves")
        except Exception as e:
            ok(False, f"{name}/{tr}: {e!r}")

# environments change pixels (same shot with and without), still moving
plain = OUT / "env_plain.mp4"; C.render_shot(job("hold_alive", env=["shimmer"], seed=9, tparams={"amount": .2}), str(plain)); pf0 = frames(plain, [20], W, H)[0]
C.render_shot(job("push_in", seed=9), str(OUT / "env_none.mp4")); f_none = frames(OUT / "env_none.mp4", [20], W, H)[0]
for e in ("dust", "fog", "embers", "rain", "snow", "light_sweep", "shimmer"):
    try:
        out = OUT / f"env_{e}.mp4"; C.render_shot(job("push_in", seed=9, env=[e]), str(out)); fe = frames(out, [20], W, H)[0]
        d = float(np.abs(fe - f_none).mean()); ok(d > .02 and probe(out)[2] == 45 and float(fe.mean()) > 8, f"env {e}: changes pixels (diff {d:.2f})")
    except Exception as ex:
        ok(False, f"env {e}: {ex!r}")

# cache hit is faster; output exact copy
j = job("pan_left", seed=int(time.time() * 1000) % 10**9, duration=2.0); a = OUT / "c1.mp4"; b = OUT / "c2.mp4"
t = time.time(); C.render_shot(j, str(a)); t1 = time.time() - t
t = time.time(); C.render_shot(j, str(b)); t2 = time.time() - t
ok(t2 < t1 * .5 and a.read_bytes() == b.read_bytes(), f"cache hit {t2*1000:.0f} ms vs {t1*1000:.0f} ms")

# cancel
calls = {"n": 0}
def cancel():
    calls["n"] += 1; return calls["n"] > 2
cj = job("handheld", seed=123, duration=4.0, size=(1280, 720)); cp = OUT / "cancelled.mp4"
try:
    C.render_shot(cj, str(cp), cancel=cancel); ok(False, "cancel raises")
except C.Cancelled:
    ok(not cp.exists(), "cancel raises Cancelled and leaves no output")
except Exception as e:
    ok(False, f"cancel: {e!r}")
ok(not list((C.CACHE / "shots").glob("*.part.mp4")), "no partial files left")

# job_key stable and sensitive
k = C.job_key(job("push_in"))
ok(len(k) == 32 and k == C.job_key(job("push_in")) and k == C.job_key(job("push_in", shot_id="other")), "job_key stable, ignores shot_id")
ok(len({k, C.job_key(job("push_in", seed=8)), C.job_key(job("pull_out")), C.job_key(job("push_in", duration=1.6)), C.job_key(job("push_in", env=["dust"])),
        C.job_key(job("push_in", tparams={"amount": .9})), C.job_key(job("push_in", intensity="high")), C.job_key(job("push_in", size=(320, 180))),
        C.job_key(job("push_in", fps=24)), C.job_key(job("push_in", still=portrait))}) == 10, "job_key sensitive to each input")
ok(C.job_key(job("no_such_move")) == k, "unknown treatment behaves as push_in")

# missing picture
try:
    C.render_shot(job("push_in", still=str(OUT / "nope.png")), str(OUT / "x.mp4")); ok(False, "missing picture raises")
except C.ComposeError:
    ok(True, "missing picture raises ComposeError")

def benchmark(size=(1920, 1080), secs=4.0):
    """Seconds of render per 1 s of video (cache bypassed by a fresh seed), with the encoder in use."""
    res = {}
    for tr, env in (("push_in", []), ("parallax_right", []), ("track_lateral", []), ("handheld", ["dust"]), ("dolly_through", ["rain"])):
        C.prepare(base, size, None, need_depth=tr in C._DEPTH_TREATMENTS)           # layers are a once-per-picture cost, reported separately
        t = time.time(); C.render_shot(job(tr, size=size, duration=secs, seed=int(time.time()) % 100000, env=env), str(OUT / f"bench_{tr}.mp4")); res[tr] = (time.time() - t) / secs
    return res

if "--bench" in sys.argv:
    for k_, v_ in benchmark().items(): print(f"bench {k_}: {v_:.2f} s per 1 s of 1080p30")

KEEP = "--keep" in sys.argv
for f in ([] if KEEP else OUT.glob("*.mp4")):
    try: f.unlink()
    except OSError: pass
shutil.rmtree(OUT / "pics", ignore_errors=True)
print(f"({time.time()-t0:.0f}s)")
print("ALL OK" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
