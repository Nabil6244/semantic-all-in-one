"""A Reddit Short's story: one of the built-in stories (hand-made picture beats) or the user's own pasted story
(picture beats made here from its sentences). No Gemini, no network."""
from __future__ import annotations

import re

from reddit_shorts.beats import BEATS
from reddit_shorts.stories import STORIES

VOICES = {"Andrew (US man)": "en-US-AndrewNeural", "Ava (US woman)": "en-US-AvaNeural",
          "Brian (US man)": "en-US-BrianNeural", "Emma (US woman)": "en-US-EmmaNeural",
          "Christopher (US man)": "en-US-ChristopherNeural", "Jenny (US woman)": "en-US-JennyNeural"}
WORDS_PER_BEAT = 18          # one picture every ~5-6 s of voice
MIN_BEATS, MAX_BEATS = 5, 11


def builtin_ids():
    return [s["id"] for s in STORIES]


def builtin(sid):
    st = dict(next(s for s in STORIES if s["id"] == sid))
    b = BEATS[sid]
    st["cast"] = b["cast"]
    st["beats"] = [list(x) for x in b["beats"]]
    st["builtin"] = True
    return st


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (s[:40].rstrip("_") or "story")


def _third_person(text):
    """'I' lines become 'the narrator' so the picture shows the storyteller, not a random person."""
    t = re.sub(r"\bI'm\b", "the narrator is", text)
    t = re.sub(r"\bI\b", "the narrator", t)
    t = re.sub(r"\b(me|myself)\b", "the narrator", t, flags=re.I)
    t = re.sub(r"\b(my|mine)\b", "the narrator's", t, flags=re.I)
    return t


def sentences(body):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", body.strip()) if s.strip()]


def auto_beats(title, body):
    """Group the sentences into 5-11 picture moments; each picture shows what its sentences say."""
    sents = sentences(body)
    total = sum(len(s.split()) for s in sents)
    n = max(MIN_BEATS, min(MAX_BEATS, round(total / WORDS_PER_BEAT)))
    target = total / n if n else total
    groups, cur, count = [], [], 0
    for s in sents:
        cur.append(s)
        count += len(s.split())
        if count >= target * (len(groups) + 1) and len(groups) < n - 1:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    beats = [["", "a cartoon scene that shows the start of this story: " + _third_person(title)]]
    for g in groups:
        first = re.sub(r"[^\w\s']", " ", g[0]).split()[:4]
        beats.append([" ".join(first), "a cartoon scene that shows this moment of the story: " + _third_person(" ".join(g))])
    return beats


def custom(title, body, sub="AmITheJerk", voice="en-US-AndrewNeural", cast=""):
    title, body = " ".join(title.split()), " ".join(body.split())
    if not title or not body:
        raise ValueError("A story needs a title and the story text.")
    if len(body.split()) < 40:
        raise ValueError("The story is too short: write at least 40 words (about 150 make a 55 s Short).")
    sub = re.sub(r"^r/", "", sub.strip()) or "AmITheJerk"
    n = len(body.split())
    return {"id": slug(title), "sub": sub, "user": "throwaway_" + str(sum(map(ord, title)) % 9000 + 1000),
            "voice": voice, "ups": f"{10 + n % 40}.{n % 10}k", "com": f"{1 + n % 6}.{n % 9}k",
            "title": title, "body": body, "cast": cast.strip(), "beats": auto_beats(title, body), "builtin": False}
