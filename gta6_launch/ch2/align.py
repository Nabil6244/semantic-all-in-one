"""Step 2 of the brief: faster-whisper word timestamps on manual_vo_mastered.mp3, then each beat's start/end anchor phrase is
fuzzy-matched against the word timeline. Beats are made seamless (cut_out[i] == cut_in[i+1], last == VO length) and the
seconds are written back into manifest.json. Run: python3 align.py [voice.mp3]"""
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VO = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "manual_vo_mastered.mp3"


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def words_of(vo):
    from faster_whisper import WhisperModel

    model = WhisperModel("small", compute_type="int8")
    segs, _ = model.transcribe(str(vo), word_timestamps=True, language="en", vad_filter=False)
    out = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in s.words]
    (HERE / "words.json").write_text(json.dumps(out))
    return out


NUM = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fifteen twenty thirty forty fifty "
          "sixty seventy eighty ninety hundred thousand".split())


def find(words, phrase, after=0):
    """Index of the first word of the best fuzzy match of the phrase, searching from word 'after'. Number words and
    digit tokens are left out on both sides (Whisper writes 'thirteen hundred' as '$1,300')."""
    target = [k for k in (norm(x) for x in phrase.split()) if k and k not in NUM]
    keys = [(i, norm(w["w"])) for i, w in enumerate(words) if i >= after and norm(w["w"]) and not any(c.isdigit() for c in w["w"])
            and norm(w["w"]) not in NUM]
    n, best, at = len(target), -1.0, after
    for k in range(0, max(1, len(keys) - n + 1)):
        r = difflib.SequenceMatcher(None, " ".join(x for _i, x in keys[k:k + n]), " ".join(target)).ratio()
        if r > best:
            best, at = r, keys[k][0]
    return at, best


def duration(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout)


if __name__ == "__main__":
    m = json.loads((HERE / "manifest.json").read_text())
    cache = HERE / "words.json"
    words = json.loads(cache.read_text()) if cache.is_file() and len(sys.argv) < 2 else words_of(VO)
    total, pos = duration(VO), 0
    for b in m["beats"]:
        i, r = find(words, b["sync_anchors"]["start_phrase"], pos)
        b["cut_in_sec"], b["_match"] = words[i]["s"], round(r, 2)
        pos = i + 1
    beats = m["beats"]
    beats[0]["cut_in_sec"] = 0.0
    for a, b in zip(beats, beats[1:]):
        a["cut_out_sec"] = b["cut_in_sec"]                 # pauses go to the beat before: no gaps
    beats[-1]["cut_out_sec"] = round(total, 3)
    m["vo_duration_sec"] = round(total, 3)
    (HERE / "manifest.json").write_text(json.dumps(m, indent=2))
    for b in beats:
        print(f"{b['beat_id']:28s} {b['cut_in_sec']:7.2f} -> {b['cut_out_sec']:7.2f}  match {b['_match']}")
