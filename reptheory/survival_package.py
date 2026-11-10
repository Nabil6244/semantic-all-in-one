"""Survival packaging, written next to the finished video (no AI calls, all from the video's own plan):
- <video>.chapters.txt: YouTube chapters (0:00 first, one per countdown item or chapter, at least 10 s apart, three or more or none);
- <video>.titles.txt: title ideas in the niche's formulas (docs/survival/NICHE_STUDY.md), filled from the video's own count, subject and disaster word: suggestions to edit;
- <video>.thumbnail.png: 1280x720, the hook picture on the right, the big number in an ink circle and two or three words on the left."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageChops, ImageDraw

from . import theme as T

DISASTERS = ((r"\bgrid (?:is |goes |went |has gone )?(?:down|fails?|failed|dies|died|collaps\w*)|\bpower grid\b", "When the Grid Goes Down"), (r"\bblackouts?\b|\bpower(?:'s| is)? out\b", "in a Blackout"),
             (r"\bshtf\b", "After SHTF"), (r"\bcollaps\w*\b", "After Collapse"), (r"\bwinter\b|\bfreez\w*\b|\bblizzards?\b", "This Winter"),
             (r"\bwar\b|\bdrones?\b", "If War Comes Home"), (r"\bfloods?\b|\bhurricanes?\b|\bstorms?\b", "When the Storm Hits"))
CHAPTER_MIN_S = 10.0

def _mmss(t: float) -> str:
    t = int(max(0.0, t)); return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"

def chapters(scenes: List[dict]) -> List[tuple]:
    """[(seconds, name)]: the countdown items (their chapter names), else the chapters as the narration moves through them."""
    out: List[tuple] = [(0.0, "Intro")]
    numbered = []
    for k, sc in enumerate(scenes):
        for c in (sc.get("sv") or {}).get("numbers", []):      # the chapter starts on the item's hook: the sentence just before "That's number 3", when it leads in
            prev = scenes[k - 1] if k else None
            t0 = float(prev["start"]) if prev is not None and float(c["at"]) - float(prev["start"]) <= 8.0 and not (prev.get("sv") or {}).get("numbers") else float(sc["start"])
            numbered.append((t0, sc.get("section") or f"Number {c['n']}"))
    if numbered: marks = numbered
    else:
        marks, prev = [], None
        for sc in scenes:
            if sc.get("section") and sc["section"] != prev: marks.append((float(sc["start"]), sc["section"])); prev = sc["section"]
    for t, name in sorted(marks):
        name = re.sub(r"\s+", " ", str(name)).strip()
        if name.isupper(): name = " ".join(w if w in ("·", "#") else (w.lower() if w.lower() in ("a", "an", "the", "of", "to", "in", "on", "and", "or", "for") and i and name.split()[i - 1] != "·" else w.capitalize()) for i, w in enumerate(name.split()))
        if t - out[-1][0] >= CHAPTER_MIN_S and name and name.lower() != out[-1][1].lower(): out.append((t, name))
    return out if len(out) >= 3 else []

def _subject(title: str) -> str:
    s = re.sub(r"^\s*\d+\s*", "", title or "").strip(" ·-")
    return s.title() if s else "Survival Tricks"

def titles(scenes: List[dict], title: str = "") -> List[str]:
    text = " ".join(sc.get("script_text") or sc.get("text", "") for sc in scenes).lower()
    nums = [c["n"] for sc in scenes for c in (sc.get("sv") or {}).get("numbers", [])]; n = max(nums) if nums else None
    when = next((w for rx, w in DISASTERS if re.search(rx, text)), "When Help Isn't Coming")
    subj = _subject(title); count = f"{n} " if n else ""; k = min(4, n) if n else None
    out = [f"{count}Forgotten {subj} That Could SAVE Your Life {when}",
           f"They Lied About Survival Gear — {count}{subj} That Actually WORK {when}".replace("  ", " "),
           f"{count}{subj} Old-Timers Still Use" + (f" (Most People Get #{k} WRONG)" if k else " (Most People Get It WRONG)"),
           f"{count}{subj} You Can Learn in ONE DAY {when}",
           f"Why {count}Cheap {subj} BEAT Expensive Prepper Gear {when}"]
    return [re.sub(r"\s+", " ", x).strip() for x in out]

def thumbnail(scenes: List[dict], path: Path, title: str = "") -> Optional[Path]:
    from . import picture as PIC, survival as SV, draw as D
    pic = next((PIC._path(sc["art"]) for sc in scenes if sc.get("art") and (sc.get("kind") == "illus" or sc.get("look") == "flow") and PIC._path(sc["art"])), None)
    W, H = 1280, 720; ctx = D.Ctx(W, H); cv = Image.new("RGB", (W, H), T.BG_TOP)
    if pic:
        im = Image.open(pic).convert("RGB"); s = max(W * 0.64 / im.width, H / im.height); im = im.resize((int(im.width * s), int(im.height * s)))
        x0 = W - im.width + int(im.width * 0.04); box = (x0, (H - im.height) // 2)
        part = cv.crop((box[0], box[1], box[0] + im.width, box[1] + im.height)); cv.paste(ImageChops.multiply(part, im), box)
    d = ImageDraw.Draw(cv, "RGBA"); nums = [c["n"] for sc in scenes for c in (sc.get("sv") or {}).get("numbers", [])]
    words = _subject(title).upper().split()[:3]; y = 80
    if nums:
        f = ctx.font(T.HEAD_FONT, 230); txt = str(max(nums)); bb = d.textbbox((0, 0), txt, font=f); cx, cy = 250, 220
        d.text((cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2), txt, font=f, fill=T.WHITE)
        SV._hand_circle(d, cx, cy, max((bb[2] - bb[0]) / 2 + 50, 140), 1.0, T.ORANGE + (255,), 12, max(nums)); y = 400
    f = ctx.font(T.HEAD_FONT, 96 if len(words) <= 2 else 80)
    for i, w in enumerate(words):
        d.text((70, y), w, font=f, fill=T.ORANGE if i == len(words) - 1 else T.WHITE); y += int(f.size * 1.02)
    path = Path(path); cv.save(path); return path

def write(scenes: List[dict], out_path: str, title: str = "", log=print) -> Dict[str, str]:
    """The three files next to the video; each that fails is skipped and said."""
    base = Path(str(out_path)); got: Dict[str, str] = {}
    try:
        ch = chapters(scenes)
        if ch: p = Path(str(base) + ".chapters.txt"); p.write_text("\n".join(f"{_mmss(t)} {n}" for t, n in ch) + "\n", encoding="utf-8"); got["chapters"] = str(p)
    except Exception as ex: log(f"[SURVIVAL PACKAGE] chapters skipped ({type(ex).__name__}: {ex})")
    try:
        p = Path(str(base) + ".titles.txt"); p.write_text("Title ideas (edit before use: they only use words and numbers from this video)\n\n" + "\n".join(titles(scenes, title)) + "\n", encoding="utf-8"); got["titles"] = str(p)
    except Exception as ex: log(f"[SURVIVAL PACKAGE] titles skipped ({type(ex).__name__}: {ex})")
    try:
        p = thumbnail(scenes, Path(str(base) + ".thumbnail.png"), title)
        if p: got["thumbnail"] = str(p)
    except Exception as ex: log(f"[SURVIVAL PACKAGE] thumbnail skipped ({type(ex).__name__}: {ex})")
    log(f"[SURVIVAL PACKAGE] {', '.join(sorted(got)) or 'nothing written'}"); return got
