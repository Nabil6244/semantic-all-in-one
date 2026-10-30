"""Phase 1 spike driver: builds a representative one-minute voiceover (macOS `say`, one file per sentence so every sentence time is exact), then renders it through the same
engine entry the app's Render button uses (reptheory.engine.run_rep_theory).

    python3 -m reptheory.spike [--preview] [--out DIR]
"""
from __future__ import annotations
import argparse, subprocess, sys, tempfile
from pathlib import Path

SCRIPT = [
    "You do not need a gym to train your grip.",
    "All you need is a full two litre bottle of water, and you probably have one at home.",
    "Screw the cap on tight, so nothing leaks while you squeeze.",
    "One litre of water weighs about one kilogram, so two litres is about two kilograms.",
    "That is the weight you will be holding with just your fingers and thumb.",
    "Hold the bottle by the neck and pinch it for as long as you can.",
    "Stand tall, keep your arm by your side, and keep squeezing.",
    "Your forearm muscles do the squeezing, so that is where you will feel it.",
    "When the bottle starts to slip, rest, then switch to the other hand.",
    "Now let us rank it, from S tier at the top down to F tier at the bottom.",
    "Pinching a bottle is a simple beginner test, so it lands in B tier.",
    "Next, a harder one. Hang from a bar with both hands and hold on for as long as you can.",
    "Same idea, bigger test, and no gym needed.",
]
TITLE = "Grip · No Gym"

def align_words(text: str, wav: Path, offset: float, model) -> tuple:
    """([{w, t0, t1}] for the script's own words with Whisper's times, matched share). Words Whisper heard differently are interpolated between matched neighbours; the script text is always what is kept."""
    import difflib, re
    segs, _ = model.transcribe(str(wav), word_timestamps=True, language="en", beam_size=1, vad_filter=False); hw = [w for sg in segs for w in sg.words]
    from . import lexicon as LX
    inv = {str(v): k for k, v in LX.NUMBER_WORDS.items()}; toks = text.split(); norm = lambda x: inv.get(re.sub(r"[^a-z0-9]", "", x.lower()), re.sub(r"[^a-z0-9]", "", x.lower())); a, b = [norm(t) for t in toks], [norm(w.word) for w in hw]
    t0s: list = [None] * len(toks); t1s: list = [None] * len(toks); hit = 0
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size): t0s[blk.a + k], t1s[blk.a + k] = hw[blk.b + k].start + offset, hw[blk.b + k].end + offset; hit += 1
    if not hw: return [], 0.0
    lo, hi = hw[0].start + offset, hw[-1].end + offset
    for i in range(len(toks)):
        if t0s[i] is None:
            j = i - 1
            while j >= 0 and t1s[j] is None: j -= 1
            k = i + 1
            while k < len(toks) and t0s[k] is None: k += 1
            left = t1s[j] if j >= 0 else lo; right = t0s[k] if k < len(toks) else hi; n = k - j - 1; idx = i - j - 1
            t0s[i] = left + (right - left) * idx / n; t1s[i] = left + (right - left) * (idx + 1) / n
    return [{"w": t, "t0": round(x, 3), "t1": round(y, 3)} for t, x, y in zip(toks, t0s, t1s)], hit / max(1, len(toks))

def build_voiceover(workdir: Path, rate: int = 145, voice: str = "Daniel", script=None, align: bool = False):
    """(wav path, sentences [{text, start, end}]) from `say`, 0.45 s of air between sentences. With align=True each sentence also gets Whisper word times ("words"), kept only when most words matched."""
    import wave
    script = script or SCRIPT; model = None
    if align:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8", local_files_only=True)
    parts, sents, t = [], [], 0.0; gap = 0.45
    sil = workdir / "gap.wav"; subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(gap), str(sil)], check=True, timeout=900)
    for i, text in enumerate(script):
        aif, wav = workdir / f"s{i}.aiff", workdir / f"s{i}.wav"
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aif), text], check=True, timeout=900)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(aif), "-ar", "24000", "-ac", "1", str(wav)], check=True, timeout=900)
        with wave.open(str(wav)) as w: d = w.getnframes() / w.getframerate()
        sent = {"text": text, "start": t, "end": t + d}
        if model:
            ws, share = align_words(text, wav, t, model); sent["align_match"] = round(share, 2)
            if ws and share >= 0.7: sent["words"] = ws
        sents.append(sent); t += d + gap; parts += [wav, sil]
    lst = workdir / "list.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts)); out = workdir / "voiceover.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True, timeout=900)
    return out, sents

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--preview", action="store_true"); ap.add_argument("--out", default="out/rep_theory_spike"); ap.add_argument("--rate", type=int, default=145)
    ap.add_argument("--script", default=""); ap.add_argument("--title", default=""); ap.add_argument("--planner", default="legacy", choices=["legacy", "beats"]); ap.add_argument("--align", action="store_true"); ap.add_argument("--plan-only", action="store_true"); ap.add_argument("--per-beat", action="store_true"); ap.add_argument("--illustrate", action="store_true"); ap.add_argument("--flow-mode", default="agent"); ap.add_argument("--name", default="rep_theory_spike")
    ap.add_argument("--end-card", action="store_true"); ap.add_argument("--end-title", default=""); ap.add_argument("--end-url", default=""); ap.add_argument("--end-image", default=""); a = ap.parse_args(argv)
    from . import engine
    out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True); work = Path(tempfile.mkdtemp(prefix="rt_spike_"))
    script = [ln.strip() for ln in Path(a.script).read_text().splitlines() if ln.strip() and not ln.startswith("#")] if a.script else None
    vo, sents = build_voiceover(work, a.rate, script=script, align=a.align); (out_dir / "voiceover.wav").write_bytes(vo.read_bytes()); (out_dir / "sentences.json").write_text(__import__("json").dumps(sents, indent=1))
    if a.plan_only:      # plan report only (no render): the beat plan, or the legacy plan measured the same way
        from . import beats as B, cadence as C, planner as P
        if a.planner == "beats": res = B.plan(sents, title=a.title or TITLE, per_beat=a.per_beat)
        else: sc = P.plan(sents, title=a.title or TITLE); res = {"title": a.title or TITLE, "planner": "legacy", "timing": "word" if all(x.get("words") for x in sents) else "estimated", "scenes": sc, "beats": [], "metrics": C.metrics(sc), "narrative": None, "summary": {"scenes": len(sc)}}
        C.write_report(out_dir / f"{a.name}.plan", res); print(res["summary"]); return 0
    rep = engine.run_rep_theory(out_dir, sents, str(out_dir / "voiceover.wav"), str(out_dir / f"{a.name}.mp4"), quality="preview" if a.preview else "final", title=a.title or TITLE, log=print, planner=a.planner, per_beat=a.per_beat, illustrate=a.illustrate, flow_mode=a.flow_mode, end_card={"enabled": a.end_card, "title": a.end_title, "url": a.end_url, "image": a.end_image},
                                progress_cb=lambda k, m: print(f"{int(k * 100):3d}% {m}", flush=True) if m == "done" or int(k * 100) % 10 == 0 else None)
    print({k: rep[k] for k in ("out", "size", "video_seconds", "seconds", "kind_counts", "art_source")}); return 0

if __name__ == "__main__":
    sys.exit(main())
