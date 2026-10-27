"""Cues for a board clip and their resolution against the narration's word times.

A cue says WHAT appears and on WHICH spoken word. Resolution turns the word into absolute seconds and then clip seconds:

    onset_abs  = word time (+ the cue's offset)             type, pop, title
    clear      = start of the next sentence after the word   (or the word itself)
    clip time  = abs time - clip origin                      origin = beat start, or beat start - dissolve_s / 2 when the join is a dissolve

Default offsets come from the one reference passage measured in Phase 0 (a paired icon about 0.2 s after its word, a display title about
0.0 to 0.2 s after its word, a typed phrase starting on its word, a board cleared exactly at the next sentence start). They are
PROVISIONAL (three fine measurements) and are plain numbers here so the scorecard can change them.

Nothing here guesses: a cue whose word is not found in the beat is reported in `problems` and is not drawn."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]            # (text as transcribed, start s, end s), the same shape the rest of the repository uses
SCHEMA_VERSION = 1                                 # docs/explainer/explainer_cue_schema.md
LEGACY_KINDS = ("type", "pop", "title", "clear")   # behaviour frozen: Milestone 1 must not change them
NEW_KINDS = ("header", "card", "icon", "chip", "arrow", "caption", "visual")      # visual: schema v1.3 (reference-style elements)   # caption: schema v1.2 (Milestone 3)
NARRATOR_KINDS = ("narrator",)                     # schema v1.1 (Milestone 2): timed by explainer.narrator.timeline, not a layout slot
KINDS = LEGACY_KINDS + NEW_KINDS + NARRATOR_KINDS
RESERVED_KINDS = ("map", "footage")                 # named in the schema, not board cues (map and archive beats are plan data, explainer.beats)
DEFAULT_OFFSET_S = {"type": 0.0, "pop": 0.2, "title": 0.1, "clear": 0.0,   # provisional, from the Phase 0 reference passage
                    "header": 0.0, "card": 0.1, "icon": 0.2, "chip": 0.1, "arrow": 0.0, "narrator": 0.0, "caption": 0.0, "visual": 0.1}   # new kinds: provisional, same rule as pop / title
TEXT_KINDS = ("type", "title", "header", "chip", "caption")   # these need text; card needs text or asset; icon needs asset; arrow needs src and dst
SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*$")


class BoardCueError(ValueError):
    def __init__(self, problems: Sequence[str]):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


@dataclass
class Cue:
    id: str
    kind: str                                   # type | pop | title | clear
    anchor: Dict[str, Any]                      # {"word": "river", "occurrence": 1} | {"index": 3} (inside the beat) | {"time": 12.3} (absolute)
    text: str = ""                              # type, title: the words drawn; pop: the label under the object
    role: str = "blue"                          # colour role of a pop: blue | green | gold | red
    offset_s: Optional[float] = None            # seconds after the anchor; None = the default for the kind
    cps: float = 30.0                           # type-on speed (reference: about 30 characters per second, n = 1)
    finish_with: Optional[str] = None           # type only: "sentence_end" = the phrase finishes as its sentence ends (it starts no earlier than its word)
    at: str = "word"                            # clear only: "word" | "next_sentence"
    pos: Optional[Tuple[int, int]] = None       # centre (pop, title) or top-left (type) in pixels; None = the builder's slot for this cue
    asset: str = ""                             # icon (required), card (optional): "icon:<name>" from explainer.board.icons
    src: str = ""                               # arrow: id of the cue it starts at
    dst: str = ""                               # arrow: id of the cue it points to
    grow_s: float = 0.4                         # arrow: seconds the shaft takes to grow
    slot: Optional[str] = None                  # header / card / icon / chip: a named layout slot; None = the first free one
    params: Dict[str, Any] = field(default_factory=dict)   # reserved for later kinds (narrator pose, caption style, map options)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Cue":
        keep = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if "pos" in keep and keep["pos"] is not None:
            keep["pos"] = tuple(keep["pos"])
        return cls(**keep)


@dataclass
class ResolvedCue:
    cue: Cue
    word: str = ""
    word_start_abs: Optional[float] = None
    sentence_start_abs: Optional[float] = None
    sentence_end_abs: Optional[float] = None
    onset_abs: Optional[float] = None           # when it appears (clear: when the board empties)
    onset_clip: Optional[float] = None
    type_duration_s: Optional[float] = None     # type: time to finish typing
    first_frame: Optional[int] = None           # first clip frame on which it is visible
    problems: List[str] = field(default_factory=list)
    sentence_source: str = ""
    slot: str = ""                              # layout: the slot a new-kind cue was given (filled by render.layout)
    lines: List[str] = field(default_factory=list)   # layout: the wrapped text lines (card, header, chip)
    font_px: int = 0                            # layout: the font size the text was fitted at
    caption: Dict[str, Any] = field(default_factory=dict)   # caption cues: the timing record (rung, matches, reveal times and frames, word boxes)

    def to_dict(self) -> Dict[str, Any]:
        d = {k: getattr(self, k) for k in ("word", "word_start_abs", "sentence_start_abs", "sentence_end_abs", "onset_abs", "onset_clip", "type_duration_s", "first_frame", "problems", "sentence_source")}
        d.update({"id": self.cue.id, "kind": self.cue.kind, "text": self.cue.text, "role": self.cue.role, "anchor": self.cue.anchor, "offset_s": self.cue.offset_s,
                  "finish_with": self.cue.finish_with, "at": self.cue.at, "slot": self.slot, "asset": self.cue.asset, "src": self.cue.src,
                  "dst": self.cue.dst, "grow_s": self.cue.grow_s, "lines": list(self.lines), "font_px": self.font_px, "caption": self.caption})
        return d


def norm(token: str) -> str:
    return re.sub(r"[^\w']+", "", token.lower())


PAUSE_GAP_S, PAUSE_MIN_WORDS, PAUSE_MAX_WORDS = 0.55, 5, 32     # the same rule hybrid.narration._from_pauses applies when no script text is given


def sentence_spans(words: Sequence[Word], sentences: Optional[Sequence[Tuple[float, float]]] = None) -> Tuple[List[Tuple[int, int]], str]:
    """((first word index, last word index) of each sentence, where the boundaries came from).

    The application's own transcription step returns normalised tokens WITHOUT punctuation (video_generator._transcribe_locked), so punctuation
    cannot be relied on. Sources, in order:
      "given"        the caller passes sentence (start, end) times, for example from hybrid.narration.build_sentences (script-aligned);
      "punctuation"  some word ends in . ! or ? (Whisper's raw text, a typed script);
      "pauses"       the Hybrid pause rule: a gap of at least 0.55 s after at least 5 words, or 32 words."""
    n = len(words)
    if n == 0:
        return [], "none"
    if sentences:
        bounds = sorted(float(s[0]) for s in sentences)
        first_of = []
        for i, (_w, st, _e) in enumerate(words):
            k = max([j for j, b in enumerate(bounds) if b <= st + 0.05] or [0])
            first_of.append(k)
        spans, a = [], 0
        for i in range(1, n + 1):
            if i == n or first_of[i] != first_of[a]:
                spans.append((a, i - 1))
                a = i
        return spans, "given"
    if any(SENTENCE_END.search(w.strip()) for w, _s, _e in words[:-1]):
        spans, first = [], 0
        for i, (w, _s, _e) in enumerate(words):
            if SENTENCE_END.search(w.strip()) or i == n - 1:
                spans.append((first, i))
                first = i + 1
        return spans, "punctuation"
    spans, first = [], 0
    for i in range(n):
        nxt = words[i + 1] if i + 1 < n else None
        gap = (nxt[1] - words[i][2]) if nxt else 99.0
        count = i - first + 1
        if nxt is None or (gap >= PAUSE_GAP_S and count >= PAUSE_MIN_WORDS) or count >= PAUSE_MAX_WORDS:
            spans.append((first, i))
            first = i + 1
    return spans, "pauses"


def _frame_of(t: float, fps: int) -> int:
    return int(math.ceil(t * fps - 1e-9))


def resolve_cues(cues: Sequence[Cue], words: Sequence[Word], beat_start: float, beat_end: float, clip_origin: float, fps: int = 30,
                 clip_length: Optional[float] = None, sentences: Optional[Sequence[Tuple[float, float]]] = None) -> List[ResolvedCue]:
    """Resolve every cue (in the order given). A problem is recorded on the cue, never raised; the builder decides what to do with it."""
    spans, source = sentence_spans(words, sentences)
    starts_of = {i: spans[k] for k, (a, b) in enumerate(spans) for i in range(a, b + 1)}
    in_beat = [i for i, (_w, s, _e) in enumerate(words) if beat_start - 1e-6 <= s < beat_end]
    out: List[ResolvedCue] = []
    for cue in cues:
        rc = ResolvedCue(cue)
        rc.sentence_source = source
        out.append(rc)
        if cue.kind in RESERVED_KINDS:
            rc.problems.append(f"cue {cue.id}: kind {cue.kind!r} is reserved for a later milestone and is not implemented")
            continue
        if cue.kind not in KINDS:
            rc.problems.append(f"cue {cue.id}: unknown kind {cue.kind!r} (use {', '.join(KINDS)})")
            continue
        if cue.kind in TEXT_KINDS and not str(cue.text).strip():
            rc.problems.append(f"cue {cue.id}: a {cue.kind} cue needs text")
            continue
        if cue.kind == "card" and not (str(cue.text).strip() or cue.asset):
            rc.problems.append(f"cue {cue.id}: a card needs text or an icon asset")
            continue
        if cue.kind == "visual":
            from .styles import STYLES
            st = (cue.params or {}).get("style", "")
            if st not in STYLES:
                rc.problems.append(f"cue {cue.id}: a visual cue needs params.style, one of {', '.join(STYLES)}")
                continue
            if st in ("set", "figure", "crowd", "prop"):         # cartoon kit (schema v1.4): the params name what to draw
                from ..cartoon import kit
                why = kit.problem(st, cue.params or {})
                if why:
                    rc.problems.append(f"cue {cue.id}: {why}")
                    continue
                if cue.pos is None and st != "set":
                    rc.problems.append(f"cue {cue.id}: a {st} cue needs pos (the top-left corner of the figure's visible pixels)")
                    continue
            else:
                if st != "cross" and not (str(cue.text).strip() or cue.asset):             # a cross-out (schema v1.6) is two strokes over another cue: no text
                    rc.problems.append(f"cue {cue.id}: a visual cue needs text or an icon asset")
                    continue
                if cue.pos is None:
                    rc.problems.append(f"cue {cue.id}: a visual cue needs pos (its top-left corner)")
                    continue
        if cue.kind == "icon" and not cue.asset:
            rc.problems.append(f"cue {cue.id}: an icon cue needs an asset (icon:<name>)")
            continue
        if cue.asset:
            from .icons import ICONS, icon_ids       # local import: icons depends on theme only
            if cue.asset not in ICONS:
                rc.problems.append(f"cue {cue.id}: unknown asset {cue.asset!r} (available: {', '.join(icon_ids())})")
                continue
        if cue.kind == "arrow" and not (cue.src and cue.dst):
            rc.problems.append(f"cue {cue.id}: an arrow needs src and dst (ids of the cues it joins)")
            continue
        a = cue.anchor or {}
        idx: Optional[int] = None
        if "word" in a:
            want, occ, seen = norm(str(a["word"])), int(a.get("occurrence", 1)), 0
            for i in in_beat:
                if norm(words[i][0]) == want:
                    seen += 1
                    if seen == occ:
                        idx = i
                        break
            if idx is None:
                rc.problems.append(f"cue {cue.id}: the word {a['word']!r} (occurrence {occ}) is not spoken inside this beat ({beat_start:.2f} to {beat_end:.2f} s)")
                continue
        elif "index" in a:
            k = int(a["index"])
            if not 0 <= k < len(in_beat):
                rc.problems.append(f"cue {cue.id}: word index {k} is outside this beat, which has {len(in_beat)} words")
                continue
            idx = in_beat[k]
        elif "time" in a:
            rc.word_start_abs = float(a["time"])
        else:
            rc.problems.append(f"cue {cue.id}: the anchor must hold word, index or time")
            continue
        if idx is not None:
            rc.word, rc.word_start_abs = words[idx][0], float(words[idx][1])
            sa, sb = starts_of[idx]
            rc.sentence_start_abs, rc.sentence_end_abs = float(words[sa][1]), float(words[sb][2])
        off = DEFAULT_OFFSET_S[cue.kind] if cue.offset_s is None else float(cue.offset_s)
        t = rc.word_start_abs + off
        if cue.kind == "caption" or (cue.kind == "visual" and (cue.params or {}).get("style") == "line" and (cue.params or {}).get("sync")):
            from ..captions.timing import resolve_caption
            mode = str((cue.params or {}).get("mode", "words"))
            if mode not in ("words", "typed"):
                rc.problems.append(f"cue {cue.id}: params.mode must be words or typed")
                continue
            if idx is not None:
                sa, sb = starts_of[idx]
                window = [i for i in range(idx, sb + 1) if i in set(in_beat)]
                send = rc.sentence_end_abs
            else:
                window = [i for i in in_beat if words[i][1] >= rc.word_start_abs - 1e-6]
                send = None
            ct = resolve_caption(cue.id, cue.text, mode, rc.word_start_abs, words, window, 0 if idx is not None else None, send, beat_end,
                                 clip_origin + (clip_length if clip_length is not None else beat_end - clip_origin), fps)
            if ct.problems:
                rc.problems += ct.problems
                rc.caption = ct.to_dict()
                continue
            rc.caption = ct.to_dict()
            rc.caption["offset_s"] = off
            rc.caption["cps"] = cue.cps
            rc.caption["reveal_frames"] = [_frame_of(rt + off - clip_origin, fps) for rt in ct.reveal_times]
            t = ct.reveal_times[0] + off
        if cue.kind in ("type", "header"):
            rc.type_duration_s = len(cue.text) / max(1.0, cue.cps)
            if cue.finish_with == "sentence_end":
                if rc.sentence_end_abs is None:
                    rc.problems.append(f"cue {cue.id}: finish_with needs a word anchor (a time anchor has no sentence)")
                    continue
                t = max(t, rc.sentence_end_abs + off - rc.type_duration_s)
            elif cue.finish_with:
                rc.problems.append(f"cue {cue.id}: finish_with {cue.finish_with!r} is not supported (use sentence_end)")
                continue
        elif cue.kind == "clear":
            if cue.at == "next_sentence":
                if idx is None:
                    rc.problems.append(f"cue {cue.id}: next_sentence needs a word anchor")
                    continue
                sb = starts_of[idx][1]
                if sb + 1 >= len(words):
                    rc.problems.append(f"cue {cue.id}: no sentence follows the word {rc.word!r}; the board is not cleared")
                    continue
                t = float(words[sb + 1][1])
            elif cue.at != "word":
                rc.problems.append(f"cue {cue.id}: clear.at must be word or next_sentence")
                continue
        rc.onset_abs = t
        rc.onset_clip = t - clip_origin
        if rc.onset_clip < -1e-6 or (clip_length is not None and rc.onset_clip >= clip_length - 1.0 / fps):
            rc.problems.append(f"cue {cue.id}: it would appear at clip second {rc.onset_clip:.2f}, outside the clip (0 to {clip_length if clip_length is not None else 'end'})")
            continue
        rc.first_frame = _frame_of(max(0.0, rc.onset_clip), fps)
        if cue.kind == "caption" or (cue.kind == "visual" and rc.caption):
            fr = rc.caption["reveal_frames"]
            if min(fr) < 0 or (clip_length is not None and max(fr) >= int(round(clip_length * fps))):
                rc.problems.append(f"cue {cue.id}: a caption word would be revealed outside the clip (frames {min(fr)} to {max(fr)})")
                rc.first_frame = None
                continue
            rc.first_frame = min(fr)
    _check_arrows(out)
    return out


def _check_arrows(out: List[ResolvedCue]) -> None:
    """An arrow joins two drawable cues of this beat that are both visible when it starts (a left-out or later endpoint is a problem, not a guess)."""
    by_id = {r.cue.id: r for r in out}
    for r in out:
        if r.cue.kind != "arrow" or r.problems:
            continue
        for role, cid in (("src", r.cue.src), ("dst", r.cue.dst)):
            e = by_id.get(cid)
            if e is None or e is r or e.cue.kind in ("clear", "arrow"):
                r.problems.append(f"cue {r.cue.id}: {role} {cid!r} is not a drawable cue of this beat")
                break
            if e.problems or e.first_frame is None:
                r.problems.append(f"cue {r.cue.id}: {role} {cid!r} could not be drawn, so the arrow cannot be drawn")
                break
            if e.first_frame > r.first_frame:
                r.problems.append(f"cue {r.cue.id}: {role} {cid!r} appears at frame {e.first_frame}, after the arrow starts (frame {r.first_frame})")
                break
