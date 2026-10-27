"""War Documentary demonstration: narration -> planner -> segmented render, end to end.

    python3 -m cinematic_explainer.war.demo [out.mp4]

The narration is spoken by the system voice (macOS `say`), so the audio is real but the WORD TIMINGS are estimated from text length, not
measured from the audio: they are illustrative. Footage is the repo's generic fixture clips (Images/), which do not show the war; they are
declared as mismatched stock so the plan labels them ILLUSTRATIVE FOOTAGE. Figures marked fixture are not real data.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from . import planner, segments

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = [
    ("Ukraine lies on the northern shore of the Black Sea. It borders Russia to the east and north, and Poland, Slovakia, Hungary, Romania and Moldova to the west and south.", "013.mp4"),
    ("The Black Sea ports of Odesa and Mykolaiv have long been central to the country's grain exports.", None),
    ("Western air defense systems such as the Patriot, a long-range surface-to-air missile system developed in the United States, have been supplied to Ukraine.", "009.mp4"),
    ("The United Nations Security Council has met repeatedly to discuss the war, and its statements are attributed to its members.", None),
    ("In this demonstration, an example ministry reports that monthly output rose from 40 to 200 units. This is a fixture figure, not real data.", "025.mp4"),
    ("The key dates are well documented: Crimea was annexed by Russia in 2014, and the full-scale invasion began in February 2022.", None),
]


def _say(text: str, out: Path) -> float:
    voice = ["-v", "Daniel"] if shutil.which("say") else []
    subprocess.run(["say", *voice, "-r", "165", "-o", str(out), text], check=True)
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)], capture_output=True, text=True)
    return float(r.stdout.strip())


def build_scenes(tmp: Path) -> tuple[List[Dict[str, Any]], str]:
    scenes: List[Dict[str, Any]] = []
    parts: List[Path] = []
    t = 0.6
    gap = 0.35
    for i, (text, clip) in enumerate(SCRIPT, 1):
        wav = tmp / f"s{i}.aiff"
        d = _say(text, wav)
        parts.append(wav)
        words = re.findall(r"\S+", text)
        total = sum(len(w) + 2 for w in words)
        acc = 0.0
        wl = []
        for w in words:
            share = (len(w) + 2) / total * d
            wl.append({"w": w, "t0": round(t + acc, 3), "t1": round(t + acc + share, 3)})
            acc += share
        scene: Dict[str, Any] = {"scene_no": i, "text": text, "start": round(t - 0.2, 3), "end": round(t + d + gap, 3), "words": wl}
        if clip:
            scene["footage"] = str(ROOT / "Images" / clip)
            scene["footage_meta"] = {"mismatch": True, "publisher": "fixture clip", "verification": "unverified"}
        scenes.append(scene)
        t += d + gap
    # one audio file: silence lead-in, then each part with a gap, in the same order as the scene times
    lst = tmp / "audio.txt"
    sil = tmp / "sil.wav"
    gapf = tmp / "gap.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.6", str(sil)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", str(gap), str(gapf)], check=True)
    # make every part the same format
    fixed: List[Path] = []
    for i, p in enumerate(parts):
        q = tmp / f"p{i}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-ar", "22050", "-ac", "1", str(q)], check=True)
        fixed.append(q)
    seq = [sil]
    for q in fixed:
        seq += [q, gapf]
    lst.write_text("".join(f"file '{p}'\n" for p in seq), encoding="utf-8")
    audio = tmp / "voice.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(audio)], check=True)
    scenes[-1]["end"] = round(scenes[-1]["end"] + 0.6, 3)
    return scenes, str(audio)


def main(argv: List[str]) -> int:
    out = argv[1] if len(argv) > 1 else str(ROOT / "out" / "war_documentary_demo.mp4")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="war_demo_"))
    try:
        scenes, audio = build_scenes(tmp)
        plan = planner.plan(scenes)
        print(planner.explain(plan))
        res = segments.render_with_fallback(plan.shots, plan.layers, out, audio_path=audio, state_dir=str(tmp / "state"))
        print(json.dumps({k: v for k, v in res.items() if k != "pieces"}, default=str)[:600])
        print("credits:", plan.credits)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
