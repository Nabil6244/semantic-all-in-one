"""Clip picker: a long podcast's words -> the stretches worth keeping, in the order they were said, plus one hook.

No Gemini. Steps:
  1. thoughts()  group words into thoughts: sentences that run on, ending on a pause (>= 0.7 s) once the thought is
                 6 s+ long; a question gets its own thought (so an answer can bring its question along)
  2. junk        sponsor reads, "subscribe / link below", show intros and thanks, SponsorBlock ranges
  3. score()     you-talk, advice words, stories, numbers, short punchy sentences, the episode's main words;
                 minus filler (um, you know, sort of) and rushed crosstalk
  4. select()    best thoughts (score smoothed with their neighbours, so the cut keeps runs instead of fragments)
                 until the target length, a question kept only when its answer is kept, back in time order
  5. hook()      the best 12-28 s run of whole sentences that doesn't start mid-thought ("and", "but", "so" ...)
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]

PAUSE = 0.7          # a pause this long can end a thought
HARD_PAUSE = 1.6     # always ends a thought
MIN_THOUGHT = 6.0
MAX_THOUGHT = 45.0
HOOK_MIN, HOOK_MAX = 12.0, 28.0
LEAD, TAIL = 0.08, 0.15     # cut a little before the first word and after the last one
PRESENTS_CARD = 3.0         # the "<channel> presents" card between the hook and the body (phase 3)
MIN_CLIP = 12.0             # a body clip shorter than this is a scrap, not a moment
LOCAL_SPAN = 120            # words each side: no sentence end this close = Whisper dropped punctuation here

STOP = set("""a an the and or but so to of in on at by for with from as is are was were be been being it its it's this that
these those there here i me my we our us you your he she they them their his her him what which who whom when where why how
not no yes do does did done have has had having can could would should will just like really very also then than too
about into out up down over more most some any all one two get got going go know think mean thing things kind sort
yeah okay right well um uh actually because people something lot much even way back say said see make made""".split())

ADVICE = ("you need to", "you have to", "you've got to", "you must", "you should", "the key", "the secret", "the truth",
          "most people", "the problem", "the reason", "if you want", "stop ", "start ", "never ", "always ", "remember",
          "the only", "the most important", "here's the thing", "what matters", "the point is", "nobody", "everyone",
          "discipline", "habit", "purpose", "meaning", "fear", "pain", "success", "failure", "change your")
STORY = ("i remember", "when i was", "years ago", "i was ", "i decided", "i realized", "i learned", "my father", "my mother",
         "my dad", "my mom", "the first time", "one day")
# A "Motivation" cut keeps mindset talk and drops protocol detail (doses, routines, products), as the reference does
MINDSET = {"mind", "mindset", "fear", "pain", "suffering", "grief", "loss", "trauma", "discipline", "purpose", "meaning",
           "growth", "grow", "grows", "change", "courage", "failure", "fail", "success", "confidence", "identity",
           "future", "past", "life", "lives", "choose", "choice", "control", "struggle", "resilience", "stress",
           "anxiety", "love", "heartbreak", "regret", "potential", "mentor", "believe", "belief", "power", "strength",
           "weak", "hard", "harder", "quit", "persist", "endure", "mistake", "lonely", "happiness", "peace", "habits"}
PROTOCOL = {"milligrams", "mg", "dose", "doses", "dosage", "supplement", "supplements", "caffeine", "sauna", "degrees",
            "fahrenheit", "celsius", "testosterone", "estrogen", "receipts", "bpa", "creatine", "protocol", "protocols",
            "electrolytes", "electrolyte", "melatonin", "magnesium", "milliliters", "grams", "nap", "naps", "breakfast",
            "coffee", "fasting", "glucose", "insulin", "sponsor", "clinic", "clinics", "prescription", "nicotine"}
FILLER_WORDS = {"um", "uh", "er", "ah", "erm", "hmm", "mm"}
FILLER_PHRASES = ("you know", "sort of", "kind of", "i mean", "like i said", "excuse me", "sorry")
DANGLING = {"and", "but", "so", "because", "which", "that", "or", "yeah", "right", "well", "also", "then", "anyway",
            "plus", "cause", "'cause", "like", "um", "uh", "it", "they", "he", "she", "this", "those", "these"}

JUNK_PATTERNS = [
    (r"\b(sponsor(ed)?|brought to you by|promo code|use (the )?code|discount code|free trial|% off|percent off)\b", "ad read"),
    (r"\b(link (is )?in the description|links? below|show notes|smash (that|the) like|hit (the )?subscribe|subscribe to|"
     r"turn on (the )?notifications?|patreon|newsletter)\b", "channel plug"),
    (r"\b(athletic greens|ag1|ag one|betterhelp|better help|squarespace|helix sleep|eight sleep|manscaped|nordvpn|"
     r"expressvpn|audible|skillshare|blinkist|hims|function health|whoop|momentous|lmnt|element electrolytes)\b", "ad read"),
    (r"\b(this video|this episode|the next \d+ (minutes|hours)|(stay|staying) on this|click(ing)? off|"
     r"in a minute,? i'?m going to|i'?m (now )?going to list|today,? (i'?m|we'?re) going to (cover|go through|give you)|"
     r"(later|now|earlier|further) (on )?in (this|the) (video|episode)|pause (the|this) video|in this video)\b", "source framing"),
    (r"\b(see you (soon|later|guys|next)|see you\W*$|bye( bye)?\W*$|goodbye\W*$)", "show housekeeping"),
    (r"\b(welcome (back )?to (the|my) (show|podcast|channel)|thanks? (you )?for (having me|coming on|joining)|"
     r"thank you for (having me|coming on|being here)|where can people find you|before we (start|begin|get into)|"
     r"that's (all|it) for today|see you (next|in the next))\b", "show housekeeping"),
]


def _tok(w: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", w.lower())


def _ends_sentence(w: str) -> bool:
    return w.rstrip("\"')]”’").endswith((".", "?", "!", "…"))


def has_punctuation(words: Sequence[Word]) -> bool:
    return bool(words) and sum(1 for w in words if _ends_sentence(w[0])) >= max(3, len(words) // 200)


def sparse_punctuation(words: Sequence[Word]) -> bool:
    """Whisper on a long file often drops most full stops but keeps the capital letter that starts a sentence (one real
    episode: 576 sentence ends in 31,856 words). Then a capital after a short pause marks a sentence start as well."""
    ends = sum(1 for w in words if _ends_sentence(w[0]))
    return bool(words) and ends > 0 and len(words) / ends > 25


_I_WORDS = {"I", "I'm", "I've", "I'd", "I'll", "I'm,"}

# a clip never ends on these: the sentence is still going
END_BAD = {"and", "but", "so", "or", "nor", "the", "a", "an", "of", "to", "in", "on", "at", "for", "with", "about", "from",
           "into", "is", "are", "was", "were", "be", "that", "which", "who", "because", "if", "than", "as", "i", "my",
           "your", "our", "their", "his", "her", "its", "very", "really", "just", "like", "um", "uh", "not", "you're",
           "we're", "they're", "it's", "i'm", "can", "will", "would", "should", "could", "do", "does", "have", "has"}


def local_punct(words: Sequence[Word], span: int = LOCAL_SPAN) -> List[bool]:
    """Per word: is there a sentence end within span words? Whisper on a long file can switch punctuation off for the
    rest of the episode (one real episode: none after minute 33); there, sentences are found from pauses instead."""
    pre = [0]
    for w in words:
        pre.append(pre[-1] + (1 if _ends_sentence(w[0]) else 0))
    n = len(words)
    return [pre[min(n, k + span + 1)] - pre[max(0, k - span)] > 0 for k in range(n)]


def clean_end(words: Sequence[Word], k: int, punct: bool, sparse: bool, lp: Sequence[bool]) -> bool:
    """Can a clip end right after words[k] (and so the next clip start at k+1)?"""
    if k + 1 >= len(words):
        return True
    if _tok(words[k][0]) in END_BAD:
        return False
    if punct and lp[k]:
        return boundary_after(words, k, punct, sparse)
    return words[k + 1][1] - words[k][2] >= 0.5


def boundary_after(ws: Sequence[Word], k: int, punct: bool, sparse: bool) -> bool:
    """Does a sentence end after ws[k]?"""
    w = ws[k][0]
    if not punct or _ends_sentence(w):
        return True
    if not sparse or k + 1 >= len(ws):
        return False
    nxt = ws[k + 1]
    cap = nxt[0][:1].isupper() and nxt[0].strip(",.") not in _I_WORDS
    in_name = w[:1].isupper() and w.strip(",.") not in _I_WORDS      # "Mary Frances", "David Goggins": one name, not two sentences
    return cap and not in_name      # no pause needed: Whisper's VAD output often has none between words


# a sentence that opens like a question ("What about emotional fears", "Do they work") even when Whisper dropped the "?"
QUESTION_START = re.compile(
    r"^(what about|how about|(do|does|did|is|are|was|were|can|could|would|should|have|has|will)\s+(you|we|they|people|it|that|"
    r"there|i|he|she|those|these|some|men|women)\b|(what|how|why|where|when|who)\s+(do|does|did|is|are|was|were|would|can|"
    r"should|about|have|has)\b)", re.I)


def question_like(text: str) -> bool:
    return bool(QUESTION_START.match(text.strip().lstrip("\"'").strip()))


@dataclass
class Thought:
    i: int
    words: List[Word]
    question: bool = False
    junk: str = ""
    score: float = 0.0
    smooth: float = 0.0

    @property
    def start(self) -> float:
        return self.words[0][1]

    @property
    def end(self) -> float:
        return self.words[-1][2]

    @property
    def dur(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def text(self) -> str:
        return " ".join(w[0] for w in self.words)


@dataclass
class Clip:
    role: str            # hook / body / question
    start: float
    end: float
    text: str
    score: float = 0.0
    thoughts: List[int] = field(default_factory=list)

    @property
    def length(self) -> float:
        return max(0.0, self.end - self.start)


# ---------- 1. thoughts ----------

def thoughts(words: Sequence[Word]) -> List[Thought]:
    punct = has_punctuation(words)
    sparse = punct and sparse_punctuation(words)
    lp = local_punct(words)
    out: List[Thought] = []
    cur: List[Word] = []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        gap = (nxt[1] - w[2]) if nxt else 99.0
        dur = w[2] - cur[0][1]
        end_s = boundary_after(words, k, punct, sparse) if lp[k] else True
        question_end = punct and lp[k] and (w[0].rstrip("\"')]”’").endswith("?")
                                  or (sparse and end_s and dur <= 20 and question_like(" ".join(x[0] for x in cur))))
        brk = (gap >= HARD_PAUSE
               or (question_end and gap >= 0.3)
               or (end_s and gap >= PAUSE and dur >= MIN_THOUGHT)
               or (end_s and dur >= MAX_THOUGHT and gap >= 0.15)
               or (dur >= MAX_THOUGHT * 1.4 and gap >= 0.25)
               or dur >= MAX_THOUGHT * 2)
        if brk:
            out.append(Thought(i=len(out), words=cur, question=question_end))
            cur = []
    if cur:
        out.append(Thought(i=len(out), words=cur))
    return out


# ---------- 2. junk ----------

# a sentence that only leads in to what comes next: a clip doesn't end on one ("Next up, how to PR your business.")
SETUP_END = re.compile(r"^(next up|next,|so let's|let's|let me|now let's|now i'm going to|i'm going to (show|tell|talk)|"
                       r"here's (how|what)|the (first|second|third|next) (step|thing|part)|step (one|two|three|\d))", re.I)


def junk_reason(text: str) -> str:
    low = " " + text.lower() + " "
    if len(re.findall(r"(?:^|[.?!]\s+)how to ", low.strip())) >= 3:
        return "topic list"     # the talk's own table of contents: "How to sell. How to hire. How to grow."
    for pat, why in JUNK_PATTERNS:
        if re.search(pat, low):
            return why
    return ""


def mark_junk(ts: List[Thought], sponsor: Sequence[Dict] = ()) -> None:
    for t in ts:
        t.junk = junk_reason(t.text)
        if not t.junk and t.dur > 0:
            for r in sponsor or ():
                ov = min(t.end, float(r["end"])) - max(t.start, float(r["start"]))
                if ov > 0.5 * t.dur:
                    t.junk = f"SponsorBlock {r.get('category') or 'ad'}"
                    break


# ---------- 3. score ----------

def topic_weights(ts: Sequence[Thought], top: int = 60) -> Dict[str, float]:
    c = Counter(tok for t in ts if not t.junk for tok in (_tok(w[0]) for w in t.words) if len(tok) > 3 and tok not in STOP)
    common = c.most_common(top)
    if not common:
        return {}
    hi = common[0][1]
    return {k: v / hi for k, v in common}


def score_words(ws: Sequence[Word], topics: Dict[str, float]) -> float:
    toks = [_tok(w[0]) for w in ws]
    toks = [t for t in toks if t]
    n = len(toks)
    if not n:
        return -5.0
    dur = max(0.5, ws[-1][2] - ws[0][1])
    low = " " + " ".join(toks) + " "
    you = sum(1 for t in toks if t in ("you", "your", "yourself", "you're", "youre", "you've", "youve")) / n
    advice = sum(low.count(p) for p in ADVICE)
    story = sum(low.count(p) for p in STORY)
    nums = sum(1 for t in toks if t.isdigit())
    filler = sum(1 for t in toks if t in FILLER_WORDS) + sum(low.count(" " + p + " ") for p in FILLER_PHRASES)
    sents = sum(1 for w in ws if _ends_sentence(w[0]))
    avg_sent = n / sents if sents else 12.0     # no punctuation here: don't punish it for "one long sentence"
    topic = sum(topics.get(t, 0.0) for t in toks) / n
    mindset = sum(1 for t in toks if t in MINDSET) / n
    protocol = sum(1 for t in toks if t in PROTOCOL) / n
    s = min(you * 8.0, 1.5) + min(advice * 0.45, 2.0) + min(story * 0.5, 1.0) + min(nums * 0.1, 0.3) + topic * 6.0
    s += min(mindset * 25.0, 1.5) - min(protocol * 40.0, 2.0)
    s -= min(filler / n * 12.0, 2.0)
    if 7 <= avg_sent <= 20:
        s += 0.5
    elif avg_sent > 35:
        s -= 0.4
    if n / dur > 4.3:        # rushed: usually two people talking over each other
        s -= 0.5
    if dur < 4.0:
        s -= 1.0
    return round(s, 3)


def score_all(ts: List[Thought]) -> Dict[str, float]:
    topics = topic_weights(ts)
    for t in ts:
        t.score = score_words(t.words, topics) if not t.junk else -9.0
    for k, t in enumerate(ts):
        near = [x.score for x in (ts[k - 1] if k else None, ts[k + 1] if k + 1 < len(ts) else None)
                if x is not None and not x.junk and not x.question]
        t.smooth = t.score + (0.35 * sum(near) / len(near) if near else 0.0)
    return topics


# ---------- 4. select ----------

def select(ts: List[Thought], target_s: float, tol: float = 30.0, skip: Sequence[int] = ()) -> List[Thought]:
    """Best thoughts until target_s (± tol), a question only when its answer is kept, in time order. Half the time is
    shared out across the whole episode first (its best parts per stretch), so the cut follows the talk start to end
    instead of taking an hour from one end. skip = thoughts already used (the hook's)."""
    skip = set(skip)
    eligible = [t for t in ts if not t.junk and not t.question and t.i not in skip]
    picked: Dict[int, Thought] = {}
    total = 0.0
    if eligible:
        t0, t1 = eligible[0].start, eligible[-1].end
        n_b = max(3, min(12, round((t1 - t0) / 720.0)))
        quota = 0.5 * target_s / n_b
        floor = sorted(x.smooth for x in eligible)[len(eligible) // 2]     # never force a below-median thought in
        for b in range(n_b):
            lo, hi = t0 + (t1 - t0) * b / n_b, t0 + (t1 - t0) * (b + 1) / n_b
            got = 0.0
            for t in sorted((x for x in eligible if lo <= x.start < hi), key=lambda x: -x.smooth):
                if got >= quota or t.smooth < floor or total >= target_s:
                    break
                picked[t.i] = t
                got += t.dur
                total += t.dur
    for t in sorted(eligible, key=lambda x: -x.smooth):
        if t.i in picked:
            continue
        if total >= target_s:
            break
        picked[t.i] = t
        total += t.dur

    def context_q(t: Thought) -> Optional[Thought]:
        if t.i == 0:
            return None
        q = ts[t.i - 1]
        return q if q.question and not q.junk and q.dur <= 25 else None

    for t in list(picked.values()):
        q = context_q(t)
        if q and q.i not in picked:
            picked[q.i] = q
            total += q.dur
    # too long: drop the weakest answers (and the question that came with them) while staying above target - tol
    for t in sorted([p for p in picked.values() if not p.question], key=lambda x: x.smooth):
        if total <= target_s + tol:
            break
        q = context_q(t)
        cut = t.dur + (q.dur if q and q.i in picked else 0.0)
        if total - cut < target_s - tol:
            continue
        picked.pop(t.i, None)
        total -= t.dur
        if q and q.i in picked and not (q.i + 1 in picked):
            picked.pop(q.i)
            total -= q.dur
    return [picked[i] for i in sorted(picked)]


def _cut(words_all: Sequence[Word], idx_first: int, idx_last: int) -> Tuple[float, float]:
    s = words_all[idx_first][1] - LEAD
    if idx_first > 0:
        s = max(s, words_all[idx_first - 1][2] + 0.02)
    e = words_all[idx_last][2] + TAIL
    if idx_last + 1 < len(words_all):
        e = min(e, words_all[idx_last + 1][1] - 0.02)
    return round(max(0.0, s), 2), round(max(e, s + 0.1), 2)


def _lower_start(words: Sequence[Word], k: int, lp: Sequence[bool]) -> bool:
    """In punctuated talk a sentence starts on a capital: a lower-case first word is the middle of one."""
    w = words[k][0].lstrip("\"'(“‘")
    return bool(lp[k]) and w[:1].islower()


def _trim(words: Sequence[Word], a: int, b: int, ok, lp: Optional[Sequence[bool]] = None) -> Tuple[int, int]:
    """Move a clip's edges in to the nearest sentence ends (never more than 30% / 8 s+ of it from either side), and drop
    a last sentence that only leads in to what comes next."""
    lp = lp if lp is not None else [False] * len(words)
    cap = max(8.0, 0.3 * (words[b][2] - words[a][1]))
    if a > 0 and (not ok(a - 1) or _lower_start(words, a, lp)):
        for k in range(a, b):
            if words[k][2] - words[a][1] > cap:
                break
            if ok(k) and not _lower_start(words, k + 1, lp):
                a = k + 1
                break
    if not ok(b):
        for k in range(b - 1, a, -1):
            if words[b][2] - words[k][2] > cap:
                break
            if ok(k):
                b = k
                break
    # the last sentence: find where it starts (the word after the previous sentence end)
    k = b - 1
    while k > a and not ok(k):
        k -= 1
    if k > a and SETUP_END.match(" ".join(w[0] for w in words[k + 1:b + 1]).strip("\"' ")) \
            and words[b][2] - words[k][2] <= cap:
        b = k
    return a, b


def to_clips(chosen: List[Thought], words_all: Sequence[Word]) -> List[Clip]:
    """Thoughts that sit next to each other in the episode become one clip (no cut where none is needed), its edges
    moved to whole sentences."""
    index = {(w[1], w[2], w[0]): k for k, w in enumerate(words_all)}
    punct = has_punctuation(words_all)
    sparse = punct and sparse_punctuation(words_all)
    lp = local_punct(words_all)

    def ok(k: int) -> bool:
        return clean_end(words_all, k, punct, sparse, lp)

    runs: List[List[Thought]] = []
    for t in chosen:
        if runs and runs[-1][-1].i + 1 == t.i:
            runs[-1].append(t)
        else:
            runs.append([t])
    clips = []
    for run in runs:
        a = index[(run[0].words[0][1], run[0].words[0][2], run[0].words[0][0])]
        b = index[(run[-1].words[-1][1], run[-1].words[-1][2], run[-1].words[-1][0])]
        role = "question" if all(t.question for t in run) else "body"
        if role == "body":
            a, b = _trim(words_all, a, b, ok, lp)
        s, e = _cut(words_all, a, b)
        body = [t for t in run if not t.question] or run
        clips.append(Clip(role=role, start=s, end=e, text=" ".join(w[0] for w in words_all[a:b + 1]),
                          score=round(sum(t.score for t in body) / len(body), 2), thoughts=[t.i for t in run]))
    return clips


# ---------- 5. hook ----------

def sentences(ts: Sequence[Thought], punct: bool) -> List[Tuple[int, List[Word]]]:
    """(thought index, words) per sentence; without punctuation, pieces split on 0.35 s pauses."""
    return [(i, ws) for i, ws, _clean in sentences_marked(ts, punct)]


def sentences_marked(ts: Sequence[Thought], punct: bool) -> List[Tuple[int, List[Word], bool]]:
    """(thought index, words, clean end). clean = the sentence really ends there (a full stop, or the next word starts a
    new sentence), not just where a thought was cut for length."""
    flat = [(t.i, w) for t in ts for w in t.words]
    allw = [w for _i, w in flat]
    sparse = punct and sparse_punctuation(allw)
    lp = local_punct(allw)
    out = []
    cur: List[Word] = []
    for k, (ti, w) in enumerate(flat):
        cur.append(w)
        last_of_thought = k + 1 >= len(flat) or flat[k + 1][0] != ti
        nxt = allw[k + 1] if k + 1 < len(allw) else None
        if punct and lp[k]:
            end = boundary_after(allw, k, punct, sparse)
        else:
            end = nxt is None or nxt[1] - w[2] >= 0.35
        if end or last_of_thought:
            out.append((ti, cur, bool(end) or nxt is None or (nxt[1] - w[2] >= 0.6)))
            cur = []
    return out


def ranked_windows(ts: List[Thought], topics: Dict[str, float], punct: bool, lo: float, hi: float,
                   n: int = 1, max_sents: int = 8) -> List[Tuple[float, List[Word]]]:
    """The best runs of whole sentences lasting lo..hi s that don't start mid-thought or end on a question, best first,
    never overlapping each other. The hook is the top 12-28 s one; Shorts take the top 25-55 s ones."""
    good = {t.i for t in ts if not t.junk and not t.question}
    marked = [s for s in sentences_marked(ts, punct) if s[0] in good]
    sents = [(i, ws) for i, ws, _c in marked]
    clean = [c for _i, _ws, c in marked]
    cands: List[Tuple[float, List[Word]]] = []
    for a in range(len(sents)):
        if _tok(sents[a][1][0][0]) in DANGLING or question_like(" ".join(x[0] for x in sents[a][1])):
            continue
        ws: List[Word] = []
        best_here = None
        for b in range(a, min(len(sents), a + max_sents)):
            if b > a and (sents[b][0] - sents[b - 1][0] > 1 or sents[b][1][0][1] - ws[-1][2] > 1.2):
                break
            ws = ws + sents[b][1]
            dur = ws[-1][2] - ws[0][1]
            if dur > hi:
                break
            if dur < lo or not clean[b] or (punct and ws[-1][0].rstrip("\"')]”’").endswith("?")):
                continue
            s = score_words(ws, topics) + (0.3 if dur <= (lo + hi) / 2 else 0.0)
            if best_here is None or s > best_here[0]:
                best_here = (s, list(ws))
        if best_here:
            cands.append(best_here)
    cands.sort(key=lambda x: -x[0])
    out: List[Tuple[float, List[Word]]] = []
    for s, ws in cands:
        if all(ws[-1][2] <= o[1][0][1] or ws[0][1] >= o[1][-1][2] for o in out):
            out.append((s, ws))
            if len(out) >= n:
                break
    return out


def hook(ts: List[Thought], topics: Dict[str, float], punct: bool) -> Optional[List[Word]]:
    best = ranked_windows(ts, topics, punct, HOOK_MIN, HOOK_MAX, n=1)
    return best[0][1] if best else None


def shorts(words: Sequence[Word], n: int = 3, sponsor: Sequence[Dict] = (), lo: float = 25.0, hi: float = 55.0) -> List[Clip]:
    """The n best stand-alone 25-55 s quotes, for 9:16 Shorts."""
    words = [tuple(w) for w in words]
    ts = thoughts(words)
    mark_junk(ts, sponsor)
    topics = score_all(ts)
    punct = has_punctuation(words)
    out = []
    for s, ws in ranked_windows(ts, topics, punct, lo, hi, n=n, max_sents=14):
        a, b = _cut(words, words.index(ws[0]), words.index(ws[-1]))
        out.append(Clip(role="body", start=a, end=b, text=" ".join(w[0] for w in ws), score=round(s, 2)))
    return out


# ---------- all together ----------

def pick(words: Sequence[Word], target_min: float = 35.0, sponsor: Sequence[Dict] = ()) -> Dict:
    """Everything the plan needs: {'clips': [hook, body...], 'thoughts': [...], 'notes': [...]}."""
    words = [tuple(w) for w in words]
    notes: List[str] = []
    ts = thoughts(words)
    mark_junk(ts, sponsor)
    topics = score_all(ts)
    punct = has_punctuation(words)
    if not punct:
        notes.append("The transcript has no punctuation (YouTube captions): thoughts were split on pauses only.")
    hk = hook(ts, topics, punct)
    clips: List[Clip] = []
    hook_len = 0.0
    if hk:
        k0 = words.index(hk[0])
        k1 = words.index(hk[-1])
        s, e = _cut(words, k0, k1)
        hook_len = e - s
        clips.append(Clip(role="hook", start=s, end=e, text=" ".join(w[0] for w in hk), score=score_words(hk, topics)))
    else:
        notes.append("No clean 12-28 s hook line was found; the video starts straight on the talk.")
    target_s = target_min * 60.0
    body_target = max(60.0, target_s - hook_len - (PRESENTS_CARD if hk else 0.0))
    usable = sum(t.dur for t in ts if not t.junk and not t.question)
    if usable < body_target:
        notes.append(f"The episode only has {usable / 60:.1f} min of usable talk; the video will be shorter than "
                     f"{target_min:g} min.")
    hook_ts = [t.i for t in ts if hk and t.start < clips[0].end and t.end > clips[0].start]   # never heard twice
    goal = body_target
    for _ in range(4):
        chosen = select(ts, goal, skip=hook_ts)
        body = [c for c in to_clips(chosen, words) if c.role != "body" or c.length >= MIN_CLIP]
        short = body_target - sum(c.length for c in body)
        if short <= 30.0 or sum(t.dur for t in chosen) >= usable:
            break
        goal += short    # trimmed edges and dropped scraps: ask for that much more
    if hk and body and body[0].start <= clips[0].start + 1.0 < body[0].end:
        # the first body clip opens on the hook's own line: start it after the hook, so the line isn't heard twice in a row
        if body[0].end - clips[0].end >= 5.0:
            body[0].start = clips[0].end
        else:
            body.pop(0)
    clips += body
    junk = [t for t in ts if t.junk]
    if junk:
        notes.append(f"Left out {len(junk)} piece(s) of ads / plugs / housekeeping "
                     f"({sum(t.dur for t in junk) / 60:.1f} min).")
    return {"clips": clips, "thoughts": ts, "notes": notes, "topics": topics}
