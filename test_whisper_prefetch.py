"""Whisper prefetch (app.py): words transcribed in the background while assets are made are handed to the render; mismatches and failures fall back."""
import tempfile, time
from pathlib import Path
from types import SimpleNamespace as NS
import app as A

calls = []
A.vg = NS(transcribe_audio=lambda p, m: (calls.append((p, m)), time.sleep(0.2), [("hi", 0.0, 0.5)])[2])
A.get_cached_whisper_words = lambda sd, a: None
fails = []
def ok(c, m):
    print("ok  " if c else "FAIL", m)
    if not c: fails.append(m)

me = NS(_pakmap_get_words=lambda p, m, sd, log: A.vg.transcribe_audio(str(p), m))
me._whisper_warm = lambda *a: A.VideoGeneratorApp._whisper_warm(me, *a)
start = A.VideoGeneratorApp._whisper_prefetch_start; take = A.VideoGeneratorApp._whisper_prefetch_take
f = Path(tempfile.mkdtemp()) / "a.mp3"; f.write_bytes(b"x" * 100)
cfg = {"audio_path": f, "model": "base"}
start(me, cfg, "render", Path("."))
ok(me._whisper_prefetch is not None, "started")
ok(take(me, cfg) == [("hi", 0.0, 0.5)] and len(calls) == 1, "take waits and returns the words")
ok(take(me, cfg) is None, "taken once")
start(me, cfg, "assets", Path(".")); ok(me._whisper_prefetch is None, "no render: skipped")
start(me, cfg, "render", Path(".")); ok(take(me, {**cfg, "model": "small"}) is None, "other model: ignored")
A.vg = NS(transcribe_audio=lambda p, m: (_ for _ in ()).throw(SystemExit("no words")))
me._whisper_job = None; start(me, cfg, "render", Path(".")); ok(take(me, cfg) is None, "failure: falls back")
# early start (voiceover picked): shares the job with Generate, skips when busy / no project / setting off
calls.clear(); A.vg = NS(transcribe_audio=lambda p, m: (calls.append((p, m)), time.sleep(0.2), [("hi", 0.0, 0.5)])[2])
logs = []
e = NS(_settings={}, audio_var=NS(get=lambda: str(f)), model_var=NS(get=lambda: "base"), _workspace=NS(state_dir=Path(tempfile.mkdtemp())),
       _worker=None, _append_log=logs.append, _whisper_job=None, _pakmap_get_words=lambda p, m, sd, log: A.vg.transcribe_audio(str(p), m))
e._whisper_warm = lambda *a: A.VideoGeneratorApp._whisper_warm(e, *a)
e._whisper_early_busy = lambda: A.VideoGeneratorApp._whisper_early_busy(e)
A.VideoGeneratorApp._whisper_early_run(e)
ok(e._whisper_job is not None and logs, "early start runs and logs once")
e._whisper_prefetch = None
A.VideoGeneratorApp._whisper_prefetch_start(e, {"audio_path": f, "model": "base"}, "render", e._workspace.state_dir)
ok(e._whisper_prefetch is e._whisper_job, "Generate joins the early job")
ok(A.VideoGeneratorApp._whisper_prefetch_take(e, {"audio_path": f, "model": "base"}) == [("hi", 0.0, 0.5)] and len(calls) == 1, "one transcription for both")
e._whisper_job = None; e._hybrid_running = True; A.VideoGeneratorApp._whisper_early_run(e)
ok(e._whisper_job is None, "busy: no early start")
e._hybrid_running = False; e._workspace = None; A.VideoGeneratorApp._whisper_early_run(e)
ok(e._whisper_job is None, "no project: no early start")
e._settings = {"early_transcribe": False}; e.after = lambda *a: (_ for _ in ()).throw(AssertionError("scheduled"))
A.VideoGeneratorApp._whisper_early_schedule(e); ok(True, "setting off: nothing scheduled")
print("FAILED" if fails else "ALL OK"); raise SystemExit(bool(fails))
