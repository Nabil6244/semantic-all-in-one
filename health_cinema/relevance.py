"""Does a downloaded clip show what the narration is about? Stock search ranks by loose metadata, so an anatomy scene can come back with a plastic sheet.

Two cheap checks, applied only where a wrong subject is unmistakable (a scene about a named body part):
  1. title check: the clip's own page title (the slug in the Pexels URL) must mention the body part or a close synonym; a title that names something else
     (a snowy mountain, a kitchen) is a mismatch. No network, no model.
  2. frame check (optional): when the title says nothing, two frames are shown to the app's vision QA (`visual_qa.semantic.vision_semantic_score`).
     Without a Gemini key this step is skipped, never guessed.
The verdict is written into the clip record's `qa` (semantic_match, vision_used) so `acquire.is_weak` and the retry chain treat it like the app's own QA."""
from __future__ import annotations
import re, subprocess, tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional, Set

SYNONYMS: Dict[str, Set[str]] = {
    "knee": {"knee", "joint", "leg", "cartilage", "orthopedic", "orthopaedic", "skeleton", "skeletal", "bone", "bones", "anatomy", "anatomical", "medical"},
    "joints": {"joint", "joints", "knee", "hip", "shoulder", "arthritis", "cartilage", "bone", "bones", "skeleton", "skeletal", "orthopedic", "anatomy", "anatomical", "medical"},
    "spine": {"spine", "spinal", "back", "vertebra", "vertebrae", "skeleton", "skeletal", "bone", "anatomy", "anatomical", "medical"},
    "brain": {"brain", "neuro", "neuron", "neurons", "head", "skull", "mri", "cerebral", "mind", "anatomy", "anatomical", "medical"},
    "eye": {"eye", "eyes", "vision", "retina", "iris", "pupil", "optic", "sight", "eyeball", "anatomy", "anatomical", "medical"},
    "heart": {"heart", "cardiac", "cardio", "cardiovascular", "pulse", "artery", "arteries", "ecg", "blood", "anatomy", "anatomical", "medical"},
    "lungs": {"lung", "lungs", "breathing", "respiratory", "chest", "breath", "oxygen", "anatomy", "anatomical", "medical"},
    "liver": {"liver", "hepatic", "abdomen", "abdominal", "digestive", "organ", "organs", "anatomy", "anatomical", "medical"},
    "pancreas": {"pancreas", "pancreatic", "insulin", "diabetes", "glucose", "digestive", "organ", "anatomy", "anatomical", "medical"},
    "kidney": {"kidney", "kidneys", "renal", "urinary", "organ", "anatomy", "anatomical", "medical"},
    "stomach": {"stomach", "gastric", "digestive", "abdomen", "gut", "anatomy", "anatomical", "medical"},
    "intestines": {"intestine", "intestines", "intestinal", "gut", "bowel", "digestive", "colon", "microbiome", "anatomy", "anatomical", "medical"},
}
WEAK_SCORE = 0.1
_TOK = re.compile(r"[a-z0-9]+")

GENERIC = {"anatomy", "anatomical", "medical", "organ", "organs", "medicine", "health", "body", "human"}   # on every medical clip: they prove nothing about WHICH part is shown

def subject_terms(organ: Optional[str]) -> Set[str]:
    return (set(SYNONYMS.get(organ or "", set())) - GENERIC) if organ else set()

def slug_tokens(rec: dict) -> Set[str]:
    """Words of the clip's own title: the readable slug at the end of a Pexels (or similar) page URL. Empty when the source gives no title."""
    url = str(rec.get("source_url") or "")
    m = re.search(r"/video/([a-z0-9\-]+?)-\d+/?$", url, re.I)
    return set(_TOK.findall(m.group(1).lower())) if m else set()

_TAG_CACHE: Dict[str, Set[str]] = {}

def pixabay_tags(rec: dict, settings: Optional[dict]) -> Set[str]:
    """Pixabay pages carry no readable title, but its API gives every video's own tags (the app's manifest does not keep them). One small request per clip,
    with the user's own Pixabay key; any failure means 'no tags' (the caller then treats the clip as unjudged by title)."""
    import os
    url = str(rec.get("source_url") or ""); m = re.search(r"pixabay\.com/videos/.*?(\d+)/?$", url) or re.search(r"(\d+)$", str(rec.get("asset_id") or rec.get("provider_asset_id") or ""))
    key = (settings or {}).get("pixabay_api_key") or os.environ.get("PIXABAY_API_KEY", "")
    if "pixabay" not in url or not m or not key: return set()
    vid = m.group(1)
    if vid in _TAG_CACHE: return _TAG_CACHE[vid]
    try:
        import requests
        hits = requests.get("https://pixabay.com/api/videos/", params={"key": key, "id": vid}, timeout=15).json().get("hits") or []
        _TAG_CACHE[vid] = set(_TOK.findall(str(hits[0].get("tags", "")).lower())) if hits else set()
    except Exception: _TAG_CACHE[vid] = set()
    return _TAG_CACHE[vid]

def title_verdict(rec: dict, organ: Optional[str], settings: Optional[dict] = None) -> str:
    """'match' | 'mismatch' | 'unknown' (no organ in the scene, or the source gave no title or tags)."""
    terms = subject_terms(organ); slug = slug_tokens(rec) or pixabay_tags(rec, settings)
    if not terms or not slug: return "unknown"
    return "match" if slug & terms else "mismatch"

_BRIDGES = [{"senior", "seniors", "elderly", "older", "old", "aged", "mature", "retired", "grandparents", "grandmother", "grandfather", "couple", "adults"},
            {"woman", "women", "lady", "female", "girl"}, {"man", "men", "male", "gentleman", "guy"}, {"stairs", "staircase", "steps", "stairway", "handrail", "banister"},
            {"walking", "walk", "stroll", "strolling", "hiking", "walks", "walker"}, {"swimming", "swim", "swimmer", "pool", "laps"}, {"doctor", "physician", "nurse", "clinic", "hospital", "patient"},
            {"jogging", "running", "runner", "jog", "run"}, {"desk", "office", "laptop", "computer", "work", "working"}, {"park", "garden", "trail", "outdoors", "outdoor", "path"}]
_FILLER = {"a", "an", "the", "of", "in", "on", "at", "with", "and", "to", "for", "slow", "slowly", "morning", "evening", "close", "up", "shot", "view", "side", "low", "high", "real", "natural"}

def _norm(t: str) -> str: return t[:-1] if len(t) > 3 and t.endswith("s") else t

def _expand(words: Set[str]) -> Set[str]:
    out = {_norm(w) for w in words}
    for g in _BRIDGES:
        if out & {_norm(x) for x in g}: out |= {_norm(x) for x in g}
    return out

def query_overlap(rec: dict, query: str, settings: Optional[dict] = None) -> str:
    """'match' | 'mismatch' | 'unknown' for a scene that is not about a named body part: does the clip's own title or tags share ANY content word (or a plain synonym such
    as senior/elderly, stairs/staircase) with the search? Zero overlap means the stock search returned something else entirely (a sunset cello for 'woman climbing stairs')."""
    title = slug_tokens(rec) or pixabay_tags(rec, settings)
    q = {w for w in _TOK.findall((query or "").lower()) if w not in _FILLER and not w.isdigit()}
    if not title or not q: return "unknown"
    return "match" if _expand(q) & _expand(title) else "mismatch"

def _frames(path: str, ffmpeg: str, n: int = 2) -> List[str]:
    out: List[str] = []; d = tempfile.mkdtemp(prefix="hc_rel_")
    try:
        r = subprocess.run([ffmpeg.replace("ffmpeg", "ffprobe") if ffmpeg.endswith("ffmpeg") else "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
        dur = float(r.stdout.strip() or 0)
    except Exception: dur = 0.0
    for i in range(n):
        t = max(0.0, dur * (i + 1) / (n + 1)); p = str(Path(d) / f"f{i}.jpg")
        try:
            subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "5", p], check=True, timeout=60)
            out.append(p)
        except Exception: pass
    return out

def check(rec: dict, narration: str, query: str, organ: Optional[str], settings: Optional[dict], ffmpeg: str = "ffmpeg", log: Callable[[str], None] = lambda m: None) -> dict:
    """Judge one acquired clip and record the verdict in rec['qa']. Returns rec. Only scenes about a named body part are judged; others keep the app's own QA."""
    if not rec.get("ok"): return rec
    qa = dict(rec.get("qa") or {})
    if not organ:
        if query_overlap(rec, query, settings) == "mismatch":
            qa.update(semantic_match=WEAK_SCORE, vision_used=True, status="TITLE_MISMATCH"); rec["qa"] = qa
            log(f"relevance: clip title/tags '{'-'.join(sorted(slug_tokens(rec) or pixabay_tags(rec, settings)))[:60]}' share nothing with the search '{query[:40]}'")
        return rec
    v = title_verdict(rec, organ, settings)
    if v == "mismatch":
        qa.update(semantic_match=WEAK_SCORE, vision_used=True, status="TITLE_MISMATCH"); rec["qa"] = qa
        log(f"relevance: clip title/tags '{'-'.join(sorted(slug_tokens(rec) or pixabay_tags(rec, settings)))[:60]}' names nothing about the {organ}: rejected"); return rec
    if v == "match": return rec
    if qa.get("vision_used"): return rec                      # the app's QA already looked at its frames
    try:
        from visual_qa.semantic import vision_semantic_score
        frames = _frames(str(rec["path"]), ffmpeg)
        score, _ = vision_semantic_score(SimpleNamespace(script_segment=narration, prompt=query, stock=query), frames, settings=settings or {})
    except Exception as exc:
        log(f"relevance: frame check unavailable ({str(exc)[:60]})"); return rec
    if score is not None:
        qa.update(semantic_match=float(score), vision_used=True, status="VISION"); rec["qa"] = qa
        if score < 0.30: log(f"relevance: frames do not show the {organ} (vision {score:.2f}): rejected")
    return rec
