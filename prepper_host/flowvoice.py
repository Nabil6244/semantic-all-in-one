"""Flow voice (owner, 2026-11-21): the host's own lines are spoken by his Flow talking clips, so his lips match the words.

Only the lines that land on a host / split / round-cam shot get a clip (one Flow video each, made once and kept in the library);
every other line keeps the Edge voice (or stays as it is). A host line longer than MAX_WORDS is cut into pieces, one clip each.
The speech is cut out of each clip, levelled to the Edge pieces and laid into one voice track; a clip Flow could not make
leaves that line on the Edge voice.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from prepper_host import director, voice as pv

SAY_KINDS = ("host", "split", "pip")
MAX_WORDS = 18
SR = 24000
TARGET_RMS_DB = -20.0
CACHE = pv.CACHE


# ------------------------------------------------------------------ which lines
def chunks(line, max_words=MAX_WORDS):
    """A host line in pieces of at most max_words, cut at sentence ends, then commas, then hard."""
    out = []
    for s in pv.sentences(line) or [line]:
        words = s.split()
        if len(words) <= max_words:
            out.append(s)
            continue
        n = -(-len(words) // max_words)            # even pieces, each cut at a comma near its mark when there is one
        cuts, prev = [], 0
        for j in range(1, n):
            mark = round(len(words) * j / n)
            near = [i for i in range(max(prev + 2, mark - 3), min(len(words) - 2, mark + 3) + 1) if words[i - 1][-1:] in ",;:"]
            c = min(near, key=lambda i: abs(i - mark)) if near else mark
            if c - prev > max_words:
                c = prev + max_words
            cuts.append(c)
            prev = c
        bounds = [0] + cuts + [len(words)]
        parts = [words[x:y] for x, y in zip(bounds, bounds[1:]) if y > x]
        out += [" ".join(p) for p in parts]
    merged = []                              # a lone short tail joins the piece before it when it still fits
    for c in out:
        if merged and len(c.split()) < 4 and len(merged[-1].split()) + len(c.split()) <= max_words:
            merged[-1] += " " + c
        else:
            merged.append(c)
    return merged


def split_rows(rows, spec):
    """Rows for the second pass: every row keeps the shot pass 1 gave it, host lines are cut into clip-sized pieces
    (r["say"] = True). Cards, products and chapters stay on the first piece."""
    first = {}
    for s in spec["shots"]:
        first.setdefault(s.get("row"), s["kind"])
    out = []
    for k, r in enumerate(rows):
        kind = first.get(k, r.get("shot") or "broll")
        if kind not in SAY_KINDS:
            out.append(dict(r, shot=r.get("shot") or kind))
            continue
        for i, c in enumerate(chunks(r["line"])):
            nr = dict(r, line=c, shot=kind if i == 0 or kind != "host" else "split", say=True)
            if i:
                nr.update(chapter="", title="", rows="", product="")
            out.append(nr)
    return out


def clip_key(meta, line):
    v = meta.get("voice") or ""
    return "say_" + director.key_of(f"{meta['name']}|{v}|{line}" if v else f"{meta['name']}|{line}")


def flow_voice(meta):
    return {"name": meta["voice"], "performance": meta.get("voice_performance", "")} if meta.get("voice") else None


def clip_prompt(meta, line):
    return (f"Photorealistic video, 8 seconds long, static medium shot on a tripod. The man from the reference pictures "
            f"{meta.get('set') or ''}. He looks straight into the camera and says, clearly, at a calm natural pace: \"{line}\" "
            "Then he stops talking and stays quiet. "
            + (f"He speaks in the attached voice, {meta['voice']}. " if meta.get("voice")
               else "Deep, warm, slightly gravelly American male voice, the same voice every time. ")
            + "Small natural hand gestures. No music, quiet room tone. No text, no subtitles, no logos.")


# ------------------------------------------------------------------ audio
def _read(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True, timeout=300).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float32)


def speech_span(y, frame=0.02):
    """(start, end) seconds of the speech in a clip's sound: first/last 20 ms frame within 30 dB of the loudest."""
    n = int(SR * frame)
    if len(y) < n:
        return 0.0, len(y) / SR
    fr = y[: len(y) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    on = np.where(db > max(-45.0, db.max() - 30.0))[0]
    if not len(on):
        return 0.0, len(y) / SR
    a = max(0.0, on[0] * frame - 0.06)
    b = min(len(y) / SR, (on[-1] + 1) * frame + 0.12)
    return a, b


def _level(y):
    rms = float(np.sqrt((y ** 2).mean())) if len(y) else 0.0
    return y * (10 ** (TARGET_RMS_DB / 20) / rms) if rms > 1e-5 else y


def _spread(text, t0, t1):
    """Word times spread over a clip's speech by word length (a clip has no word times of its own)."""
    words = text.split()
    w8 = np.array([len(re.sub(r"\W", "", w)) + 1 for w in words], dtype=float)
    edges = t0 + (t1 - t0) * np.concatenate([[0], np.cumsum(w8)]) / max(1.0, w8.sum())
    return [{"word": w, "start": round(float(a), 4), "end": round(float(b) - 0.02, 4)} for w, a, b in zip(words, edges, edges[1:])]


# ------------------------------------------------------------------ the same voice for the other lines
def voice_sample(meta, clip_paths, seconds=20.0):
    """Dale's own Flow voice as a clone sample: the speech of his clips, joined until ~20 s (kept in his host folder)."""
    dest = Path(meta["dir"]) / (f"flow_voice_sample_{meta['voice']}.wav" if meta.get("voice") else "flow_voice_sample.wav")
    if dest.is_file():
        return dest
    parts, total = [], 0.0
    for c in clip_paths:
        try:
            y = _read(c)
            a, b = speech_span(y)
            seg = _level(y[int(a * SR): int(b * SR)])
        except Exception:  # noqa: BLE001
            continue
        parts += [seg, np.zeros(int(SR * 0.3), dtype=np.float32)]
        total += len(seg) / SR
        if total >= seconds:
            break
    if total < 6.0:                      # too little of him to copy yet
        return None
    _write(np.concatenate(parts), dest)
    return dest


def clone_lines(texts, sample, log=print, cancel=None):
    """{text: wav} spoken in the sample's voice by Chatterbox (one model load for all of them), cached per line."""
    import os
    import sys
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from voice_clone import chatterbox_engine as cb
    if not cb.is_ready():
        raise RuntimeError("the Chatterbox voice clone is not set up (Voiceover tab → Clone engine)")
    tag = hashlib.sha1(Path(sample).read_bytes()).hexdigest()[:10]
    out = {t: CACHE / f"clone_{tag}_{hashlib.sha1(t.encode()).hexdigest()[:12]}.wav" for t in texts}
    todo = [{"text": t, "out": str(w)} for t, w in out.items() if not (w.is_file() and w.stat().st_size > 1000)]
    if todo:
        log(f"prepper host: speaking {len(todo)} line(s) in his Flow voice (voice clone)")
        job = CACHE / f"clone_job_{tag}.json"
        job.write_text(json.dumps({"ref": str(sample), "device": "", "pieces": todo}))
        proc = subprocess.Popen([str(cb.env_python()), str(cb.worker_path()), str(job)], stdout=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                errors="replace", env=cb._child_env())
        err = ""
        try:
            for line in proc.stdout:
                if cancel and cancel():
                    raise RuntimeError("stopped")
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                err = ev.get("error", err)
            proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        bad = [t for t, w in out.items() if not (w.is_file() and w.stat().st_size > 1000)]
        if bad:
            log(f"prepper host: the voice clone missed {len(bad)} line(s){': ' + err if err else ''}; those use the Edge voice")
        _ = os
    return {t: w for t, w in out.items() if w.is_file() and w.stat().st_size > 1000}


def _write(y, path):
    import wave
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def build(rows, clips, edge_voice, log=print, cloned=None):
    """rows from split_rows, clips {row index: mp4} -> {"path","duration","words","said": {row: (clip, clip_at)}}."""
    sig = hashlib.sha1(json.dumps([[r["line"], clips.get(k, ""), str((cloned or {}).get(r["line"], ""))] for k, r in enumerate(rows)] + [edge_voice]).encode()).hexdigest()[:16]
    out = CACHE / f"flowvoice_{sig}.wav"
    CACHE.mkdir(parents=True, exist_ok=True)
    gap = np.zeros(int(SR * pv.GAP), dtype=np.float32)
    parts, words, said, t = [], [], {}, 0.0
    for k, r in enumerate(rows):
        clip = clips.get(k)
        seg = None
        if clip:
            try:
                y = _read(clip)
                a, b = speech_span(y)
                seg = _level(y[int(a * SR): int(b * SR)])
                words += _spread(r["line"], t, t + len(seg) / SR)
                said[k] = (str(clip), round(a, 3), round(t, 3))
            except Exception as e:  # noqa: BLE001 - that line keeps the Edge voice
                log(f"prepper host: clip sound not usable ({e}); Edge voice for: {r['line'][:60]}")
                seg = None
        if seg is None and (cloned or {}).get(r["line"]):
            try:
                y = _read(cloned[r["line"]])
                a, b = speech_span(y)
                seg = _level(y[int(a * SR): int(b * SR)])
                words += _spread(r["line"], t, t + len(seg) / SR)
            except Exception as e:  # noqa: BLE001
                log(f"prepper host: cloned line not usable ({e}); Edge voice for: {r['line'][:60]}")
                seg = None
        if seg is None:
            ev = pv.edge(r["line"], edge_voice, log=lambda m: None)
            seg = _level(_read(ev["path"]))
            words += [{"word": w["word"], "start": round(w["start"] + t, 4), "end": round(w["end"] + t, 4)} for w in ev["words"]]
        parts += [seg, gap]
        t += (len(seg) + len(gap)) / SR
    y = np.concatenate(parts) if parts else np.zeros(SR, dtype=np.float32)
    _write(y, out)
    return {"path": str(out), "duration": len(y) / SR, "words": words, "said": said}


def attach(spec, rows, said):
    """Host shots of a spoken row play its own clip from the moment its speech starts."""
    for s in spec["shots"]:
        k = s.get("row")
        if k in said and s["kind"] in SAY_KINDS:
            clip, at, row_t0 = said[k]
            s["talk"] = clip
            s["talk_at"] = round(max(0.0, at + (s["t0"] - row_t0)), 3)
            s["talk_loop"] = False
    return spec
