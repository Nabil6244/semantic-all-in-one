"""Synthetic long-form material for the Hybrid tests: narration with Whisper-style word times of any length, and a deterministic stand-in
for Gemini that answers the Director, critic and repair requests the way the real one is asked to. No network, no credits."""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple

PLACES = ["Kenya", "Ethiopia", "Egypt", "Sudan", "Chad", "Niger", "Mali", "Nigeria", "Libya", "Algeria", "Morocco", "Tanzania", "Uganda", "Ghana", "Senegal", "Angola"]
WORDS_PER_SECOND = 2.6


def make_narration(minutes: float, *, seed: int = 7) -> Tuple[List[Tuple[str, float, float]], str]:
    """(words with times, script text) for a narration of about `minutes`. Sentences of 12-24 words, a short pause between them, a longer one
    at every paragraph end (a paragraph is 8 sentences), like a read documentary."""
    import random

    rnd = random.Random(seed)
    words: List[Tuple[str, float, float]] = []
    paras: List[str] = []
    t, sent_no, total = 0.0, 0, minutes * 60.0
    para: List[str] = []
    while t < total - 4.0:
        n = rnd.randint(12, 24)
        toks = [f"w{sent_no}x{k}" for k in range(n)]
        toks[0] = toks[0].capitalize()
        for k, tok in enumerate(toks):
            d = 1.0 / WORDS_PER_SECOND * rnd.uniform(0.8, 1.2)
            words.append((tok, round(t, 3), round(t + d * 0.9, 3)))
            t += d
        para.append(" ".join(toks) + ".")
        sent_no += 1
        t += rnd.uniform(0.3, 0.7)
        if len(para) == 8:
            paras.append(" ".join(para))
            para = []
            t += rnd.uniform(0.8, 1.4)
    if para:
        paras.append(" ".join(para))
    return words, "\n\n".join(paras)


_LINE = re.compile(r"^\[(\d+)\]\s+([\d.]+)s-\s*([\d.]+)s\s+(.*)$")


def parse_sentence_lines(text: str) -> List[Tuple[int, float, float, str]]:
    out = []
    for line in text.splitlines():
        m = _LINE.match(line.strip())
        if m:
            out.append((int(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4)))
    return out


class FakeGemini:
    """Answers like the Director: groups the sentences it is shown into beats, cycling map / map+card / footage; the critic: marks the first
    beat of each chapter weak (when asked to); repair: redoes the beats it is sent as plain map beats. Counts every request."""

    def __init__(self, *, beat_sentences: int = 6, weak_first: bool = False, fail_on_chapter: Optional[int] = None, fail_times: int = 0):
        self.beat_sentences, self.weak_first = beat_sentences, weak_first
        self.fail_on_chapter, self.fail_times = fail_on_chapter, fail_times
        self.calls: List[dict] = []
        self.api_key = "fake"
        self.credentials = None
        self._k = 0

    # the interface hybrid.director._complete uses
    def complete(self, system: str, user: str, **kw: Any) -> str:
        kind = "repair" if user.startswith("Redo ONLY") else ("critic" if "Return the JSON findings" in user else "director")
        m = re.search(r"planning chapter (\d+) of (\d+)", user)
        chapter = int(m.group(1)) if m else 1
        self.calls.append({"kind": kind, "chars": len(user), "chapter": chapter, "context": "CHAPTER CONTEXT" in user, "user": user if kind == "director" else ""})
        if kind == "director" and self.fail_on_chapter == chapter and self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("Gemini API error: You exceeded your current quota")
        if kind == "critic":
            return self._critic(user)
        if kind == "repair":
            return self._repair(user)
        return self._director(user, chapter)

    def _director(self, user: str, chapter: int) -> str:
        sents = parse_sentence_lines(user.split("Narration of this chapter")[-1] if "Narration of this chapter" in user else user)
        beats = []
        for k in range(0, len(sents), self.beat_sentences):
            grp = sents[k:k + self.beat_sentences]
            a, b = grp[0][0], grp[-1][0]
            self._k = int(grp[0][1] // 7) + 1          # from the narration itself, so a resumed run answers exactly as an uninterrupted one
            kind = self._k % 4
            place = PLACES[self._k % len(PLACES)]
            first_words = grp[0][3].split()[:3]
            if kind == 3:
                beats.append({"sentences": [a, b], "mode": "footage", "purpose": f"footage {self._k}",
                              "footage": {"footage_intent": "see it", "clips": [{"source": "stock_video", "query": f"scene {self._k} of {place}", "reason": "shows it"}]}})
                continue
            m = {"geo_intent": f"show {place}", "camera": {"place": place, "frame": "region", "move": "fly_to"}, "overlay_intent": "mark it",
                 "layers": ([{"type": "fill", "anchor": " ".join(first_words), "place": place, "role": "subject"}] if kind in (0, 1) else []) + [{"type": "marker", "anchor": " ".join(first_words), "place": place, "label": place.upper(), "role": "featured", "until": "after_footage" if kind == 2 and self._k % 8 == 2 else "beat_end"}]}
            beat = {"sentences": [a, b], "mode": "map_footage" if kind == 2 else "map", "purpose": f"map {self._k}", "map": m}
            if kind == 2:
                beat["support"] = {"source": "stock_image", "query": f"photo {self._k} {place}", "place": place, "label": place.upper(), "anchor": " ".join(first_words), "reason": "what it looks like"}
            beats.append(beat)
        return json.dumps({"chapter_title": f"Chapter {chapter}", "beats": beats})

    def _critic(self, user: str) -> str:
        ids = re.findall(r"^(b\d+) \|", user, re.M)          # the critic receives one compact line per beat
        findings = []
        if self.weak_first:
            for bid in ids[::10]:
                findings.append({"beat": bid, "severity": "weak", "category": "pacing", "issue": "too static", "suggestion": "change it"})
        return json.dumps({"overall": {"balance": "balanced", "coherence": 4, "summary": "fine"}, "findings": findings})

    def _repair(self, user: str) -> str:
        out = []
        for m in re.finditer(r"--- BEAT (b\d+): sentences \[(\d+), (\d+)\]", user):
            out.append({"beat": m.group(1), "sentences": [int(m.group(2)), int(m.group(3))], "mode": "map", "purpose": "repaired",
                        "map": {"geo_intent": "repaired", "camera": {"place": "Kenya", "frame": "region", "move": "fly_to"}, "overlay_intent": "", "layers": []}})
        return json.dumps({"beats": out})
