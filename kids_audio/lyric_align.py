"""Find when each lyric section starts in a sung song (e.g. one made with ACE-Step), so scenes can cut on the verses.

python3 -m kids_audio.lyric_align song.mp3 lyrics.txt
lyrics.txt uses [verse] / [chorus] tags; each tag opens a section. Prints
{"sections": [{"tag", "first_line", "t": seconds | null, "score"}], "words": n, "duration": s}.

Method: faster-whisper word timestamps (local, CPU), then for each section's first line the best matching run of sung
words after the previous section (word overlap, in order). A section that is not found gets t = null and is spread
evenly between its neighbours by the caller.
"""
import json
import re
import subprocess
import sys


def _whisper_backend():
    """The repo's whisper_backend.py (Apple-GPU Whisper with a CPU fallback), or None where it can't be imported."""
    try:
        import sys as _sys
        from pathlib import Path as _P
        root = str(_P(__file__).resolve().parents[1])
        if root not in _sys.path:
            _sys.path.append(root)
        import whisper_backend
        return whisper_backend
    except Exception:  # noqa: BLE001
        return None


def sections(lyrics):
    out, tag = [], None
    for raw in lyrics.splitlines():
        ln = raw.strip()
        m = re.match(r"^\[(\w[\w\s-]*)\]$", ln)
        if m:
            tag = m.group(1).lower()
            out.append({"tag": tag, "lines": []})
        elif ln and out:
            out[-1]["lines"].append(ln)
    return [s for s in out if s["lines"]]


def _norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


def transcribe(path, model="small"):
    wb = _whisper_backend()
    if wb is not None:   # Apple GPU when it can (whisper_backend.py), else the same CPU model
        segs, _ = wb.transcribe(path, model, language="en", word_timestamps=True, vad_filter=False, beam_size=5)
    else:
        from faster_whisper import WhisperModel
        m = WhisperModel(model, device="cpu", compute_type="int8")
        segs, _ = m.transcribe(path, language="en", word_timestamps=True, vad_filter=False, beam_size=5)
    words = []
    for s in segs:
        for w in s.words or []:
            if _norm(w.word):
                words.append({"w": _norm(w.word), "t0": round(w.start, 2), "t1": round(w.end, 2)})
    return words


def align(path, lyrics, words=None):
    secs = sections(lyrics)
    words = words if words is not None else transcribe(path)
    pos, res = 0, []
    for s in secs:
        target = [_norm(w) for w in s["lines"][0].split() if _norm(w)]
        best, best_i = 0.0, None
        for i in range(pos, len(words)):
            win = [x["w"] for x in words[i:i + len(target) + 2]]
            hit = sum(1 for t in target if t in win)
            score = hit / max(1, len(target)) - 0.002 * (i - pos)     # earliest good match wins
            if words[i]["w"] in target[:2]:
                score += 0.15                                        # the line starts here
            if score > best:
                best, best_i = score, i
        if best_i is not None and best >= 0.5:
            res.append({"tag": s["tag"], "first_line": s["lines"][0], "t": words[best_i]["t0"], "score": round(best, 2)})
            pos = best_i + max(1, len(target) // 2)
        else:
            res.append({"tag": s["tag"], "first_line": s["lines"][0], "t": None, "score": round(best, 2)})
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                               capture_output=True, text=True).stdout.strip() or 0)
    return {"sections": res, "words": len(words), "duration": dur, "transcript": " ".join(w["w"] for w in words)}


if __name__ == "__main__":
    print(json.dumps(align(sys.argv[1], open(sys.argv[2], encoding="utf-8").read()), indent=1))
