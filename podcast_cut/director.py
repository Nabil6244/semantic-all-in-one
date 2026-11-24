"""Footage director: the clip plan -> the film's timeline (audio pieces, shots, captions).

Timeline (output seconds):  hook clip | "<channel> presents" card (3 s, music only) | body clips in order.
Every clip is cut into 3-6 s windows on word boundaries (a sentence end or a pause is preferred). Each window is either
  camera  the podcast's own camera at that moment (when the source has video)
  b-roll  a literal stock search when a filmable thing is said (shark, ice bath, marathon ...), listed in the Visuals tab
          so it can be checked / retried / changed, else a clip from the mood library chosen by the window's feeling
Rules: camera on the first window after every jump and on host questions; camera runs of 6-12 s and b-roll runs of
10-18 s (never more than 20 s camera / 25 s b-roll in a row); about 45-50 % camera overall; a literal subject at most
once a minute and a half; no library clip again within 8 minutes; never the same mood three times running.
Captions: the words of each window in lines of 3-6 words (broken on punctuation and pauses).
"""
from __future__ import annotations

import random
import re
from typing import Dict, List, Optional, Sequence

from .picker import Clip, PRESENTS_CARD, Word, _ends_sentence
from . import library as LIB

WIN_MIN, WIN_TARGET, WIN_MAX = 3.0, 4.5, 6.0
CAM_MAX, BROLL_MAX = 20.0, 25.0
LIBRARY_GAP = 8 * 60.0
LITERAL_GAP = 90.0

# a filmable thing said in the window -> the stock search for it (word-boundary match, longest first)
LITERAL: Dict[str, str] = {
    "shark": "great white shark underwater", "sharks": "great white shark underwater", "ice bath": "ice bath cold plunge",
    "cold shower": "cold shower water", "cold water": "cold water plunge", "marathon": "marathon runners",
    "car crash": "car crash traffic night", "accident": "car accident night road", "hospital": "hospital corridor",
    "surgeon": "surgeon operating room", "doctor": "doctor hospital", "phone": "scrolling smartphone dark",
    "social media": "scrolling social media phone", "instagram": "scrolling social media phone", "gym": "gym workout dark",
    "lift weights": "weightlifting gym dark", "boxing": "boxing training", "fight": "boxing fight", "fighting": "boxing fight",
    "fire": "fire flames dark", "fires": "forest fire", "plane": "airplane flying clouds", "airport": "airport terminal",
    "ocean": "ocean waves", "diving": "scuba diver underwater", "cage": "shark cage diving", "brain": "brain neurons animation",
    "neurons": "brain neurons animation", "heart": "heartbeat monitor", "children": "children playing", "kids": "children playing",
    "baby": "baby sleeping", "money": "money cash counting", "wealth": "luxury city night", "school": "school classroom",
    "university": "university campus", "lab": "science laboratory", "laboratory": "science laboratory",
    "military": "soldiers training", "seal": "navy seals training", "soldier": "soldier silhouette", "war": "soldiers silhouette",
    "mountain": "mountain climbing", "climb": "mountain climbing", "running": "man running", "run": "man running",
    "sleep": "man sleeping dark bedroom", "bed": "man lying in bed dark", "alarm": "alarm clock morning",
    "sunlight": "morning sunlight window", "sun": "sunrise", "coffee": "coffee pouring dark", "alcohol": "whiskey glass dark",
    "drugs": "pills dark", "cocaine": "pills dark", "ice": "ice melting", "snow": "snow falling night", "rain": "rain window",
    "wedding": "wedding couple", "relationship": "couple holding hands", "girlfriend": "couple silhouette",
    "funeral": "funeral flowers", "cemetery": "cemetery fog", "prison": "prison bars", "jail": "prison bars",
    "office": "office night", "computer": "typing laptop dark", "car": "driving car night", "driving": "driving car night",
    "dog": "dog running", "bulldog": "bulldog", "stage": "stage spotlight", "public speaking": "speaker on stage audience",
    "audience": "audience applause", "lecture": "lecture hall", "book": "reading book dark", "books": "library books",
    "chess": "chess game", "army": "soldiers marching", "firefighter": "firefighter fire", "parachute": "skydiving",
    "jump": "cliff jumping", "food": "food cooking dark", "hungry": "empty plate", "elbows and knees": "man crawling",
}
_LIT = sorted(LITERAL, key=len, reverse=True)
_LIT_RE = [(k, re.compile(r"\b" + re.escape(k) + r"\b", re.I)) for k in _LIT]


def literal_for(text: str) -> Optional[str]:
    for k, rx in _LIT_RE:
        if rx.search(text):
            return k
    return None


def _words_in(words: Sequence[Word], a: float, b: float) -> List[Word]:
    return [w for w in words if w[1] >= a - 0.01 and w[2] <= b + 0.2]


def windows(clip_words: List[Word], start: float, end: float) -> List[Dict]:
    """Contiguous [a, b) source-time windows covering the clip, cut on word boundaries."""
    if not clip_words:
        return [{"a": start, "b": end, "words": []}]
    out, cur = [], []
    w0 = start
    for k, w in enumerate(clip_words):
        cur.append(w)
        nxt = clip_words[k + 1] if k + 1 < len(clip_words) else None
        dur = w[2] - w0
        gap = (nxt[1] - w[2]) if nxt else 0.0
        if nxt is None:
            break
        if dur >= WIN_MAX or (dur >= WIN_MIN and (_ends_sentence(w[0]) or gap >= 0.3 or dur >= WIN_TARGET)):
            cut = round((w[2] + nxt[1]) / 2, 3)
            out.append({"a": w0, "b": cut, "words": cur})
            cur, w0 = [], cut
    out.append({"a": w0, "b": end, "words": cur})
    if len(out) > 1 and out[-1]["b"] - out[-1]["a"] < 1.5:      # a sliver at the end joins the window before it
        last = out.pop()
        out[-1]["b"] = last["b"]
        out[-1]["words"] += last["words"]
    return out


def caption_lines(ws: List[Word], to_out) -> List[Dict]:
    lines, cur = [], []
    for k, w in enumerate(ws):
        cur.append(w)
        nxt = ws[k + 1] if k + 1 < len(ws) else None
        if (nxt is None or len(cur) >= 6 or (len(cur) >= 3 and (w[0][-1:] in ",.?!;:" or nxt[1] - w[2] > 0.4))):
            lines.append({"text": " ".join(x[0] for x in cur).strip(" ,"), "out_start": round(to_out(cur[0][1]), 3),
                          "out_end": round(to_out(cur[-1][2]) + 0.12, 3)})
            cur = []
    for a, b in zip(lines, lines[1:]):      # a line stays up until the next one (no flicker in short gaps)
        if b["out_start"] - a["out_end"] < 0.6:
            a["out_end"] = b["out_start"]
    return lines


class _Picker:
    def __init__(self, index: List[dict], seed: int):
        self.by_tag: Dict[str, List[dict]] = {}
        for it in index:
            self.by_tag.setdefault(it["tag"], []).append(it)
        self.rng = random.Random(seed)
        for v in self.by_tag.values():
            self.rng.shuffle(v)
        self.used: Dict[str, float] = {}
        self.recent_tags: List[str] = []
        self.general = 0

    def pick(self, text: str, t: float, prefer: Sequence[str] = ()) -> Optional[dict]:
        tags = list(prefer) or LIB.moods_for(text)
        if not tags:
            tags = LIB.GENERAL[self.general:] + LIB.GENERAL[:self.general]
            self.general = (self.general + 1) % len(LIB.GENERAL)
        tags = [x for x in tags if self.recent_tags[-2:] != [x, x]] or tags
        tags = tags + [x for x in LIB.GENERAL if x not in tags] + [x for x in self.by_tag if x not in tags and x not in LIB.GENERAL]
        for gap in (LIBRARY_GAP, LIBRARY_GAP / 4, 0.0):
            for tag in tags:
                for it in self.by_tag.get(tag, []):
                    if t - self.used.get(it["file"], -1e9) >= gap:
                        self.used[it["file"]] = t
                        self.recent_tags.append(tag)
                        return it
        return None


def build(clips: Sequence[Clip], words: Sequence[Word], has_video: bool = True, index: Optional[List[dict]] = None,
          seed: int = 7, channel: str = "") -> Dict:
    words = [tuple(w) for w in words]
    index = LIB.load_index() if index is None else index
    lib = _Picker(index, seed)
    rng = random.Random(seed)
    segments, shots, captions, rows = [], [], [], []
    t = 0.0
    card = None
    cam_run = broll_run = 0.0
    cam_len, broll_len = rng.uniform(6, 12), rng.uniform(10, 18)
    lit_used: Dict[str, float] = {}

    def add_broll(text: str, a_out: float, dur: float, prefer=()) -> None:
        nonlocal broll_run
        key = literal_for(text)
        if key and a_out - lit_used.get(key, -1e9) >= LITERAL_GAP:
            lit_used[key] = a_out
            n = len(rows) + 1
            rows.append({"scene_no": n, "text": text.strip()[:300], "asset_type": "stock_video", "prompt": LITERAL[key],
                         "stock": LITERAL[key], "start": round(a_out, 3), "end": round(a_out + dur, 3)})
            it = lib.pick(text, a_out, prefer)      # the stand-in if the search finds nothing
            shots.append({"kind": "broll", "out_start": round(a_out, 3), "dur": round(dur, 3), "row": n, "query": LITERAL[key],
                          "file": it["file"] if it else "", "tag": it["tag"] if it else ""})
        else:
            it = lib.pick(text, a_out, prefer)
            if it is None:                           # an empty library: a search per mood instead, listed in the Visuals tab
                tags = list(prefer) or LIB.moods_for(text) or LIB.GENERAL
                q = LIB.MOODS[tags[len(rows) % len(tags)]][0]
                n = len(rows) + 1
                rows.append({"scene_no": n, "text": text.strip()[:300], "asset_type": "stock_video", "prompt": q, "stock": q,
                             "start": round(a_out, 3), "end": round(a_out + dur, 3)})
                shots.append({"kind": "broll", "out_start": round(a_out, 3), "dur": round(dur, 3), "row": n, "query": q,
                              "file": "", "tag": ""})
            else:
                shots.append({"kind": "broll", "out_start": round(a_out, 3), "dur": round(dur, 3), "file": it["file"],
                              "tag": it["tag"]})
        broll_run += dur

    for ci, c in enumerate(clips):
        seg = {"clip": ci, "role": c.role, "src_start": c.start, "src_end": c.end, "out_start": round(t, 3),
               "out_end": round(t + c.length, 3)}
        segments.append(seg)

        def to_out(s, _c=c, _t=t):
            return _t + (s - _c.start)

        cw = _words_in(words, c.start, c.end)
        wins = windows(cw, c.start, c.end)
        captions += caption_lines(cw, to_out)
        for k, w in enumerate(wins):
            a_out, dur = to_out(w["a"]), w["b"] - w["a"]
            text = " ".join(x[0] for x in w["words"])
            want_cam = has_video and (k == 0 or c.role == "question" or (broll_run >= broll_len)
                                      or (cam_run > 0 and cam_run + dur <= cam_len))
            if has_video and broll_run + dur > BROLL_MAX:
                want_cam = True
            if cam_run + dur > CAM_MAX or (cam_run >= cam_len and k > 0 and c.role != "question"):
                want_cam = False
            if want_cam:
                shots.append({"kind": "camera", "out_start": round(a_out, 3), "dur": round(dur, 3), "src_t": round(w["a"], 3)})
                cam_run += dur
                if broll_run:
                    broll_run, broll_len = 0.0, rng.uniform(10, 18)
            else:
                add_broll(text, a_out, dur)
                if cam_run:
                    cam_run, cam_len = 0.0, rng.uniform(6, 12)
        t += c.length
        if c.role == "hook" and ci == 0:
            card = {"out_start": round(t, 3), "out_end": round(t + PRESENTS_CARD, 3), "channel": channel}
            it = lib.pick("", t, LIB.PRESENTS_TAGS)
            shots.append({"kind": "card", "out_start": round(t, 3), "dur": PRESENTS_CARD, "file": it["file"] if it else "",
                          "tag": it["tag"] if it else ""})
            t += PRESENTS_CARD
            cam_run = broll_run = 0.0
    cam = sum(s["dur"] for s in shots if s["kind"] == "camera")
    return {"segments": segments, "card": card, "shots": shots, "captions": captions, "rows": rows, "length": round(t, 3),
            "camera_share": round(cam / t, 3) if t else 0.0, "has_video": has_video}
