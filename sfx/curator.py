"""Scan Sonniss GDC source tree and shortlist production SFX candidates."""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from sfx.ambience_profiles import (
    AMBIENCE_PROFILE_TARGETS,
    AMBIENCE_SHORTLIST_CAP,
    ambience_tags_for_text,
    infer_ambience_profile,
)
from sfx.audio_probe import is_supported_audio, probe_audio
from sfx.sonniss_license import SONNISS_METADATA
from sfx.starter_catalog import CATEGORY_TAG_POOLS, SPECIAL_IDS
from smart_editing import SFX_CATEGORIES

DEFAULT_SOURCE_ROOT = Path.home() / "Downloads" / "videogen-sfx-source"
DEFAULT_CURATED_ROOT = Path.home() / "Downloads" / "videogen-sfx-curated"

# Narrow global rejects: keep "run/walk/beat" out so useful filenames are not dropped.
GLOBAL_EXCLUDE = (
    r"\bmusic\b",
    r"\bmelody\b",
    r"\bsong\b",
    r"\bsinging\b",
    r"\bsinger\b",
    r"\borchestr",
    r"\bpiano\b",
    r"\bguitar\b",
    r"\bdrum\s*loop\b",
    r"\bscore\b",
    r"\bbackground\s*music\b",
    r"\bdialogue\b",
    r"\bdialog\b",
    r"\bspeech\b",
    r"\bvocal",
    r"\bvoiceover\b",
    r"\bvoice[\s\-]?over\b",
    r"\btalk\b",
    r"\bconversation\b",
    r"\bannouncer\b",
    r"\bnarrat",
    r"\bfootstep",
    r"\bfoot\s*steps?\b",
    r"\banime\b",
    r"\bschoolgirl\b",
    r"\byell\b",
    r"\bscream\b",
    r"\bmoan\b",
    r"\bgrunt\b",
    r"\bchoking\b",
    r"\bdinosaur",
    r"\braptor\b",
    r"\bt[\s\-]?rex\b",
    r"\bbark",
    r"\bdog\b",
    r"\bcat\b",
    r"\bbird\s*call",
    r"\banimal\b",
    r"\bweapon",
    r"\bsword\b",
    r"\bspear\b",
    r"\bgun\b",
    r"\brifle\b",
    r"\bshotgun\b",
    r"\bbullet\b",
    r"\bexplosion\b",
    r"\bcasino\b",
    r"\bshuffl",
    r"\bdealing\b",
    r"\bchristmas\b",
    r"\bholiday\b",
    r"\bsanta\b",
    r"\bsleigh\b",
    r"\bhalloween\b",
    r"\bbarbershop\b",
    r"\bcarabiner\b",
    r"\bclimbing\s*gear\b",
    r"\bsuitcase\b",
    r"\bluggage\b",
    r"\bpage\s*turn",
    r"\bpolice\s*radio\b",
    r"\blooping\b",
    r"\blooped\b",
    r"\bvox",
    r"\banml",
    r"\bweap",
    r"\bgamecas\b",
)

# Pack / folder names that are rarely useful as general YouTube editorial SFX.
EXCLUDE_PACK = (
    r"anime fight voices",
    r"dinosaurs",
    r"dog vocal",
    r"casino cards",
    r"christmas",
    r"historical weapons",
    r"medieval weapons",
    r"british police",
    r"barbershop",
    r"car foley",
    r"climbing gear",
    r"antique luggage",
    r"antique books",
    r"antique small metals",
    r"cinema experience",
)

CATEGORY_RULES: Dict[str, dict] = {
    "whoosh": {
        "include": (
            r"\bwhoosh\b",
            r"\bswoosh\b",
            r"\bswish\b",
            r"\bsweep\b",
            r"\brush\b",
            r"\bfly[\s\-]?by\b",
            r"\bflyby\b",
            r"\bpass[\s\-]?by\b",
            r"\bpassby\b",
            r"\bair\s*designed\b",
            r"\baero",
            r"\bwinddsgn\b",
        ),
        "exclude": (r"\bfootstep", r"\bweapon", r"\btypewriter\b"),
        "duration": (0.3, 3.0),
        "hard_max": 8.0,
        "ideal": 0.7,
        "shortlist": 10,
        "min_target": 8,
        "report_shortlist": 18,
    },
    "impact": {
        "include": (
            r"\bimpact\b",
            r"\bhit\b",
            r"\bpunch\b",
            r"\bslam\b",
            r"\bboom\b",
            r"\bthump\b",
            r"\bthud\b",
            r"\bsmack\b",
            r"\bknock\b",
            r"\bbody\s*hit\b",
            r"\bheavy\s*hit\b",
            r"\bbang\b",
            r"\bcollision\b",
            r"\bsmash\b",
            r"\bimpt\b",
            r"\bfghtimpt\b",
        ),
        "exclude": (r"\bweapon", r"\bgun\b", r"\bsword\b", r"\bbass\s*drop\b", r"\bdowner\b"),
        "duration": (0.2, 3.0),
        "hard_max": 8.0,
        "ideal": 0.45,
        "shortlist": 10,
        "min_target": 8,
        "report_shortlist": 14,
    },
    "text": {
        "include": (
            r"\btext\b",
            r"\btyp(?:e|ing|ewriter)\b",
            r"\bkeyboard\b",
            r"\bkey\b",
            r"\bpop\b",
            r"\btap\b",
            r"\btick\b",
            r"\bclick\b",
            r"\breveal\b",
            r"\bappear\b",
            r"\bswipe\b",
            r"\btitle\b",
            r"\bmessage\b",
            r"\bcomtype\b",
        ),
        "exclude": (r"\bfootstep", r"\bweapon"),
        "duration": (0.05, 2.0),
        "hard_max": 5.0,
        "ideal": 0.32,
        "shortlist": 8,
        "min_target": 5,
        "report_shortlist": 12,
    },
    "ui": {
        "include": (
            r"\bclick\b",
            r"\btap\b",
            r"\bpop\b",
            r"\btick\b",
            r"\btype\b",
            r"\btyping\b",
            r"\bkeyboard\b",
            r"\bkey\b",
            r"\bnotification\b",
            r"\balert\b",
            r"\binterface\b",
            r"\bbutton\b",
            r"\bselect\b",
            r"\bconfirm\b",
            r"\berror\b",
            r"\bmessage\b",
            r"\bdigital\s*beep\b",
            r"\bbeep\b",
            r"\bping\b",
            r"\bui\b",
            r"\bclocktick\b",
            r"\bcomtelph\b",
            r"\btelephone\b",
            r"\bdial\b",
        ),
        "exclude": (r"\bfootstep", r"\bweapon"),
        "duration": (0.05, 2.0),
        "hard_max": 5.0,
        "ideal": 0.18,
        "shortlist": 8,
        "min_target": 5,
        "report_shortlist": 12,
    },
    "transition": {
        "include": (
            r"\btransition\b",
            r"\bsweep\b",
            r"\bswish\b",
            r"\bwhoosh\b",
            r"\bswoosh\b",
            r"\bpass[\s\-]?by\b",
            r"\bchange\b",
            r"\bstinger\b",
            r"\btransition\s*hit\b",
            r"\bswipe\b",
            r"\breverse\b",
        ),
        "exclude": (r"\bweapon", r"\btypewriter\b"),
        "duration": (0.3, 3.0),
        "hard_max": 8.0,
        "ideal": 0.7,
        "shortlist": 10,
        "min_target": 8,
        "report_shortlist": 14,
    },
    "riser": {
        "include": (
            r"\briser\b",
            r"\brising\b",
            r"\brise\b",
            r"\bbuild\b",
            r"\bbuild[\s\-]?up\b",
            r"\bbuildup\b",
            r"\bswell\b",
            r"\btension\b",
            r"\bcrescendo\b",
            r"\blift\b",
            r"\buplifter\b",
            r"\bbass\s*drop\b",
            r"\bdowner\b",
        ),
        "exclude": (r"\bweapon", r"\bloop\b"),
        "duration": (1.0, 8.0),
        "hard_max": 16.0,
        "ideal": 2.0,
        "shortlist": 8,
        "min_target": 5,
        "report_shortlist": 12,
    },
    "cinematic": {
        "include": (
            r"\bcinematic\b",
            r"\btrailer\b",
            r"\bboom\b",
            r"\bbraam\b",
            r"\bdramatic\b",
            r"\bepic\b",
            r"\btension\b",
            r"\bsuspense\b",
            r"\bdowner\b",
            r"\bbass\s*drop\b",
            r"\bdsgnbass\b",
            r"\bswell\b",
            r"\breveal\b",
            r"\bpulse\b",
            r"\bair\s*designed\b",
            r"\baerojet\b",
        ),
        "exclude": (r"\bui\b", r"\bclick\b", r"\bweapon", r"\btypewriter\b", r"\bpunch\b"),
        "duration": (0.5, 6.0),
        "hard_max": 14.0,
        "ideal": 1.4,
        "shortlist": 8,
        "min_target": 5,
        "report_shortlist": 12,
    },
    "technology": {
        "include": (
            r"\bdigital\b",
            r"\bcomputer\b",
            r"\belectronic",
            r"\bcyber\b",
            r"\bfuturistic\b",
            r"\bsci[\s\-]?fi\b",
            r"\binterface\b",
            r"\bdata\b",
            r"\bmachine\b",
            r"\brobot\b",
            r"\bhologram\b",
            r"\bglitch\b",
            r"\bsynth\b",
            r"\bmodem\b",
            r"\bmechanical\b",
            r"\btech\b",
            r"\bprocess\b",
            r"\bactivation\b",
            r"\belectric",
            r"\btelephone\b",
            r"\bcomtelph\b",
            r"\btypewriter\b",
            r"\bbeep\b",
        ),
        "exclude": (r"\bweapon", r"\bfootstep"),
        "duration": (0.05, 4.0),
        "hard_max": 10.0,
        "ideal": 0.4,
        "shortlist": 8,
        "min_target": 5,
        "report_shortlist": 12,
    },
    "ambience": {
        "include": (
            r"\bambien",
            r"\batmosphere\b",
            r"\broom\s*tone\b",
            r"\bcity\b",
            r"\burban\b",
            r"\bstreet\b",
            r"\boffice\b",
            r"\bforest\b",
            r"\brain\b",
            r"\bstorm\b",
            r"\bthunder\b",
            r"\bwind\b",
            r"\bnature\b",
            r"\benvironment\b",
            r"\bcrowd\b",
            r"\btraffic\b",
            r"\bhighway\b",
            r"\broom\b",
            r"\bocean\b",
            r"\bwave\b",
            r"\bshore\b",
            r"\briver\b",
            r"\btrain\b",
            r"\bsubway\b",
            r"\bmetro\b",
            r"\bairport\b",
            r"\bstation\b",
            r"\bfireplace\b",
            r"\bcampfire\b",
            r"\bfire\s*crackl",
            r"\bmeadow\b",
            r"\blibrary\b",
            r"\bhallway\b",
            r"\bserver\b",
            r"\blab\b",
            r"\bdata\s*center\b",
            r"\bdrone\b",
            r"\bambsubn\b",
            r"\bambdsgn\b",
            r"\bhaunting\s*ambience",
            r"\beast\s*coast\b",
            r"\bextreme\s*winds\b",
            r"\bghostly\b",
            r"\baerojet\b",
            r"\bdowntown\b",
            r"\bnight\b",
            r"\bindoor\b",
        ),
        "exclude": (
            r"\bweapon",
            r"\bdialogue\b",
            r"\bbanging\b",
            r"\brespirator\b",
            r"\bbreathing\b",
            r"\bfireworks\b",
            r"\bconstruction\b",
            r"\bjackhammer\b",
            r"\bmachinery\b",
        ),
        "duration": (1.0, 30.0),
        "hard_max": 200.0,
        "ideal": 4.0,
        "shortlist": AMBIENCE_SHORTLIST_CAP,
        "min_target": 45,
        "report_shortlist": 20,
    },
}


@dataclass
class Candidate:
    path: Path
    category: str
    score: float
    duration: float
    tags: List[str]
    intensity: str
    reasons: List[str] = field(default_factory=list)


@dataclass
class CurationReport:
    source_root: Path
    curated_root: Path
    candidates_by_category: Dict[str, List[Candidate]] = field(default_factory=dict)
    shortlisted_by_category: Dict[str, List[Candidate]] = field(default_factory=dict)
    staged_files: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    exclusion_counts: Dict[str, int] = field(default_factory=dict)
    scanned_files: int = 0

    def format_summary(self) -> str:
        lines = ["SFX CURATION", ""]
        unique_shortlisted = {
            str(c.path.resolve())
            for items in self.shortlisted_by_category.values()
            for c in items
        }
        for category in SFX_CATEGORIES:
            candidates = self.candidates_by_category.get(category, [])
            shortlisted = self.shortlisted_by_category.get(category, [])
            lines.append(category.upper())
            lines.append(f"  {len(candidates)} candidates")
            lines.append(f"  → {len(shortlisted)} shortlisted")
            if shortlisted:
                examples = ", ".join(c.path.name for c in shortlisted[:3])
                lines.append(f"  examples: {examples}")
            lines.append("")
        lines.append(f"Scanned {self.scanned_files} audio file(s)")
        lines.append(f"Unique shortlisted sounds: {len(unique_shortlisted)}")
        if self.staged_files:
            lines.append(f"Staged {len(self.staged_files)} file(s) under {self.curated_root}")
        if self.exclusion_counts:
            lines.append("")
            lines.append("Major exclusion reasons:")
            for reason, count in sorted(self.exclusion_counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"  - {reason}: {count}")
        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for err in self.errors[:15]:
                lines.append(f"  - {err}")
        return "\n".join(lines).rstrip()


def _compile_patterns(patterns: Sequence[str]) -> List[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


GLOBAL_EXCLUDE_RE = _compile_patterns(GLOBAL_EXCLUDE)
EXCLUDE_PACK_RE = _compile_patterns(EXCLUDE_PACK)
_INCLUDE_RE: Dict[str, List[re.Pattern[str]]] = {
    category: _compile_patterns(rules["include"]) for category, rules in CATEGORY_RULES.items()
}
_EXCLUDE_RE: Dict[str, List[re.Pattern[str]]] = {
    category: _compile_patterns(rules.get("exclude", ())) for category, rules in CATEGORY_RULES.items()
}


def _path_key(path: Path) -> str:
    """Normalize pack folders + filename for keyword matching."""
    parts = [part.lower() for part in path.parts[-4:] if part not in {".", ""}]
    text = " ".join(parts)
    text = text.replace("-", " ").replace("_", " ").replace(",", " ").replace("&", " ")
    text = text.replace(".", " ")
    return re.sub(r"\s+", " ", text).strip()


def _match_any(patterns: Sequence[re.Pattern[str]], text: str) -> List[str]:
    return [pat.pattern for pat in patterns if pat.search(text)]


def _duration_score(duration: float, ideal: float, bounds: Tuple[float, float], hard_max: float) -> float:
    lo, hi = bounds
    if duration <= 0:
        return -50.0
    if duration > hard_max:
        return -50.0
    if lo <= duration <= hi:
        spread = max(0.05, hi - lo)
        return 22.0 - abs(duration - ideal) / spread * 6.0
    if duration < lo:
        return max(0.0, 10.0 - (lo - duration) * 2.0)
    return max(0.0, 10.0 - (duration - hi) * 1.2)


def _guess_intensity(category: str, text: str, duration: float) -> str:
    if re.search(r"\b(soft|light|small|subtle|gentle|fast\s*short)\b", text, re.I):
        return "low"
    if re.search(r"\b(deep|heavy|hard|big|massive|cinematic|trailer|boom|epic)\b", text, re.I):
        return "high"
    rules = CATEGORY_RULES.get(category, {})
    ideal = float(rules.get("ideal", 0.5))
    if duration <= ideal * 0.7:
        return "low"
    if duration >= ideal * 1.4:
        return "high"
    return "medium"


def _tags_for_slot(category: str, index: int, text: str) -> List[str]:
    pool = CATEGORY_TAG_POOLS.get(category, [])
    base = list(pool[index % len(pool)]) if pool else [category]
    for token in ("short", "soft", "fast", "deep", "rising", "falling", "sweep", "click", "pop"):
        if re.search(rf"\b{token}\b", text, re.I) and token not in base:
            base.append(token)
    return base


def _catalog_ids(category: str, count: Optional[int] = None) -> List[str]:
    n = count if count is not None else int(CATEGORY_RULES[category]["shortlist"])
    special = SPECIAL_IDS.get(category) or []
    ids = list(special[:n])
    start = len(ids) + 1
    while len(ids) < n:
        candidate = f"{category}_{start:02d}"
        start += 1
        if candidate not in ids:
            ids.append(candidate)
    return ids


def scan_source_tree(source_root: Path) -> List[Path]:
    source_root = Path(source_root).expanduser()
    if not source_root.is_dir():
        return []
    return sorted(
        path for path in source_root.rglob("*") if path.is_file() and is_supported_audio(path)
    )


def _is_globally_excluded(text: str) -> Optional[str]:
    if _match_any(EXCLUDE_PACK_RE, text):
        return "excluded pack / specific Foley"
    if _match_any(GLOBAL_EXCLUDE_RE, text):
        return "dialogue, vocals, animals, weapons, holiday, casino, or similar"
    return None


def classify_candidate(
    path: Path,
    category: str,
    *,
    text: Optional[str] = None,
    duration: Optional[float] = None,
    sample_rate: int = 48000,
) -> Optional[Candidate]:
    rules = CATEGORY_RULES.get(category)
    if not rules:
        return None
    text = text if text is not None else _path_key(path)
    if _is_globally_excluded(text):
        return None
    include_hits = _match_any(_INCLUDE_RE[category], text)
    if not include_hits:
        return None
    if _match_any(_EXCLUDE_RE[category], text):
        return None
    if duration is None:
        try:
            info = probe_audio(path)
        except (ValueError, RuntimeError, FileNotFoundError):
            return None
        duration = info.duration_seconds
        sample_rate = info.sample_rate
    if category in {"whoosh", "impact", "ui", "text", "transition"} and duration > 12:
        return None
    if duration > 30 and re.search(r"\b(bang|banging|punch|sitting|broom|respirator|breathing)\b", text, re.I):
        if category != "ambience":
            return None
        if not re.search(
            r"\b(wind|rain|forest|city|ambience|atmosphere|room|traffic|ocean|train|fire|"
            r"crowd|street|urban|indoor|wave|storm|thunder|highway|subway|airport|drone|"
            r"water|shore|meadow|office|lab|server|environment|campfire|fireplace)\b",
            text,
            re.I,
        ):
            return None
    dur_score = _duration_score(
        duration,
        float(rules["ideal"]),
        tuple(rules["duration"]),
        float(rules.get("hard_max", 30.0)),
    )
    if dur_score <= -40.0:
        return None
    score = dur_score + len(include_hits) * 5.0
    if path.suffix.lower() in (".wav", ".flac", ".aif", ".aiff"):
        score += 8.0  # prefer lossless SOURCE material, not a specific extension
    if sample_rate >= 44100:
        score += 2.0
    if re.search(r"\b(loop|variation|var\d+|alt\d+)\b", text, re.I):
        score -= 6.0
    if re.search(r"\bdesigned\b", text, re.I):
        score += 3.0
    if category == "riser" and re.search(r"\b(slow|build|rising|swell|tension|lift)\b", text, re.I):
        score += 10.0
    if category == "cinematic" and re.search(r"\b(fast|boom|braam|trailer|epic|dramatic)\b", text, re.I):
        score += 10.0
    if category == "whoosh" and re.search(r"\b(whoosh|swoosh|swish|flyby|pass[\s\-]?by|rush)\b", text, re.I):
        score += 10.0
    if category == "text" and re.search(r"\b(typewriter|typing|text|keyboard)\b", text, re.I):
        score += 10.0
    if category == "ui" and re.search(r"\b(click|button|notification|beep|dial|tick)\b", text, re.I):
        score += 10.0
    if category == "impact" and re.search(r"\b(impact|punch|slam|thump|body hit|heavy hit)\b", text, re.I):
        score += 10.0
    if category == "technology" and re.search(r"\b(digital|sci[\s\-]?fi|electronic|glitch|computer|electric)\b", text, re.I):
        score += 8.0
    amb_tags: List[str] = []
    if category == "ambience":
        if re.search(r"\b(room\s*tone|ambience|atmosphere|environment)\b", text, re.I):
            score += 12.0
        if re.search(r"\b(loop|bed|background|subtle|distant|quiet|gentle|soft)\b", text, re.I):
            score += 6.0
        if re.search(r"\b(music|melody|score|orchestr|piano|guitar)\b", text, re.I):
            score -= 50.0
        amb_tags = ambience_tags_for_text(text, infer_ambience_profile(text))
    intensity = _guess_intensity(category, text, duration)
    return Candidate(
        path=path,
        category=category,
        score=score,
        duration=duration,
        tags=amb_tags,
        intensity=intensity,
        reasons=include_hits[:4],
    )


def find_candidates(source_root: Path) -> Dict[str, List[Candidate]]:
    by_category, _scanned, _exclusions = find_candidates_with_stats(source_root)
    return by_category


def find_candidates_with_stats(
    source_root: Path,
) -> Tuple[Dict[str, List[Candidate]], int, Dict[str, int]]:
    files = scan_source_tree(source_root)
    by_category: Dict[str, List[Candidate]] = {c: [] for c in SFX_CATEGORIES}
    exclusions: Counter[str] = Counter()
    for path in files:
        text = _path_key(path)
        blocked = _is_globally_excluded(text)
        if blocked:
            exclusions[blocked] += 1
            continue
        try:
            info = probe_audio(path)
        except (ValueError, RuntimeError, FileNotFoundError):
            exclusions["unreadable audio"] += 1
            continue
        matched: List[Candidate] = []
        for category in SFX_CATEGORIES:
            cand = classify_candidate(
                path,
                category,
                text=text,
                duration=info.duration_seconds,
                sample_rate=info.sample_rate,
            )
            if cand is not None:
                matched.append(cand)
                by_category[category].append(cand)
        if not matched:
            if info.duration_seconds > 20 and re.search(
                r"\b(bang|banging|sitting|broom|respirator|breathing|clock)\b", text, re.I
            ):
                exclusions["long Foley / looping bed"] += 1
            else:
                exclusions["no editorial category match"] += 1
    for items in by_category.values():
        items.sort(key=lambda c: c.score, reverse=True)
    return by_category, len(files), dict(exclusions)


def _dedupe_variations(candidates: Sequence[Candidate]) -> List[Candidate]:
    seen: Dict[str, Candidate] = {}
    for cand in candidates:
        stem = re.sub(r"\d+", "", cand.path.stem.lower())
        stem = re.sub(r"[_,\-]+", " ", stem)
        stem = re.sub(r"\s+", " ", stem).strip()
        prev = seen.get(stem)
        if prev is None or cand.score > prev.score:
            seen[stem] = cand
    return sorted(seen.values(), key=lambda c: c.score, reverse=True)


def shortlist_ambience_by_profile(candidates: Sequence[Candidate]) -> List[Candidate]:
    """Pick diverse documentary ambience beds across editorial profiles."""
    deduped = _dedupe_variations(candidates)
    by_profile: Dict[str, List[Candidate]] = {p: [] for p in AMBIENCE_PROFILE_TARGETS}
    for cand in deduped:
        key = _path_key(cand.path)
        profile = infer_ambience_profile(key)
        if not cand.tags:
            cand.tags = ambience_tags_for_text(key, profile)
        by_profile.setdefault(profile, []).append(cand)
    for pool in by_profile.values():
        pool.sort(key=lambda c: c.score, reverse=True)

    picks: List[Candidate] = []
    used: set[str] = set()
    for profile, target in AMBIENCE_PROFILE_TARGETS.items():
        count = 0
        for cand in by_profile.get(profile, []):
            if count >= target:
                break
            key = str(cand.path.resolve())
            if key in used:
                continue
            picks.append(cand)
            used.add(key)
            count += 1

    remaining = sorted(
        [c for c in deduped if str(c.path.resolve()) not in used],
        key=lambda c: c.score,
        reverse=True,
    )
    for cand in remaining:
        if len(picks) >= AMBIENCE_SHORTLIST_CAP:
            break
        picks.append(cand)
        used.add(str(cand.path.resolve()))
    return picks


def shortlist_candidates(by_category: Dict[str, List[Candidate]]) -> Dict[str, List[Candidate]]:
    """Assign each file to its highest-scoring category; never duplicate a physical file."""
    by_file: Dict[str, List[Candidate]] = {}
    for category in SFX_CATEGORIES:
        for cand in _dedupe_variations(by_category.get(category, [])):
            by_file.setdefault(str(cand.path.resolve()), []).append(cand)

    best_by_category: Dict[str, List[Candidate]] = {c: [] for c in SFX_CATEGORIES}
    leftovers: List[Candidate] = []
    for _key, options in by_file.items():
        ranked = sorted(options, key=lambda c: c.score, reverse=True)
        best_by_category[ranked[0].category].append(ranked[0])
        leftovers.extend(ranked[1:])

    shortlisted: Dict[str, List[Candidate]] = {}
    used_files: set[str] = set()
    for category in SFX_CATEGORIES:
        cap = int(CATEGORY_RULES[category]["shortlist"])
        picks: List[Candidate] = []
        for cand in _dedupe_variations(best_by_category[category]):
            if len(picks) >= cap:
                leftovers.append(cand)
                continue
            key = str(cand.path.resolve())
            picks.append(cand)
            used_files.add(key)
        shortlisted[category] = picks

    leftovers.sort(key=lambda c: c.score, reverse=True)
    for cand in leftovers:
        key = str(cand.path.resolve())
        if key in used_files:
            continue
        cap = int(CATEGORY_RULES[cand.category]["shortlist"])
        if len(shortlisted[cand.category]) >= cap:
            continue
        shortlisted[cand.category].append(cand)
        used_files.add(key)
    shortlisted["ambience"] = shortlist_ambience_by_profile(by_category.get("ambience", []))
    return shortlisted


def stage_curated_library(
    shortlisted: Dict[str, List[Candidate]],
    curated_root: Path,
    *,
    dry_run: bool = False,
) -> List[Path]:
    curated_root = Path(curated_root).expanduser()
    staged: List[Path] = []
    for category in SFX_CATEGORIES:
        picks = shortlisted.get(category, [])
        ids = _catalog_ids(category, len(picks))
        for index, cand in enumerate(picks):
            entry_id = ids[index]
            path_key = _path_key(cand.path)
            if category == "ambience":
                cand.tags = cand.tags or ambience_tags_for_text(path_key, infer_ambience_profile(path_key))
                tags = cand.tags
            else:
                tags = _tags_for_slot(category, index, path_key)
            cand.tags = tags
            dest = curated_root / category / f"{entry_id}{cand.path.suffix.lower()}"
            sidecar = curated_root / category / f"{entry_id}.json"
            meta = {
                "id": entry_id,
                "category": category,
                "tags": cand.tags,
                "intensity": cand.intensity,
                "duration": round(cand.duration, 3),
                **SONNISS_METADATA,
                "original_path": str(cand.path),
                "curation_score": round(cand.score, 2),
            }
            if dry_run:
                staged.append(dest)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cand.path, dest)
            sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            staged.append(dest)
    return staged


def curate_sonniss_library(
    source_root: Path,
    curated_root: Path,
    *,
    dry_run: bool = False,
) -> CurationReport:
    source_root = Path(source_root).expanduser()
    curated_root = Path(curated_root).expanduser()
    report = CurationReport(source_root=source_root, curated_root=curated_root)
    if not source_root.is_dir():
        report.errors.append(f"Source directory not found: {source_root}")
        return report
    files = scan_source_tree(source_root)
    report.scanned_files = len(files)
    if not files:
        report.errors.append(
            f"No supported audio files under {source_root}. "
            "Extract the official Sonniss GDC bundle here first."
        )
        return report
    by_category, scanned, exclusions = find_candidates_with_stats(source_root)
    report.scanned_files = scanned
    report.exclusion_counts = exclusions
    report.candidates_by_category = by_category
    report.shortlisted_by_category = shortlist_candidates(by_category)
    report.staged_files = stage_curated_library(
        report.shortlisted_by_category,
        curated_root,
        dry_run=dry_run,
    )
    return report


def write_curation_report(report: CurationReport, output_path: Path) -> Path:
    unique = {
        str(c.path.resolve())
        for items in report.shortlisted_by_category.values()
        for c in items
    }
    payload = {
        "source_root": str(report.source_root),
        "curated_root": str(report.curated_root),
        "scanned_files": report.scanned_files,
        "unique_shortlisted": len(unique),
        "summary": report.format_summary(),
        "exclusion_counts": report.exclusion_counts,
        "categories": {},
        "errors": report.errors,
    }
    for category in SFX_CATEGORIES:
        picks = report.shortlisted_by_category.get(category, [])
        ids = _catalog_ids(category, len(picks))
        payload["categories"][category] = {
            "candidates": len(report.candidates_by_category.get(category, [])),
            "shortlisted": len(picks),
            "files": [
                {
                    "id": ids[i],
                    "source": str(c.path),
                    "filename": c.path.name,
                    "score": round(c.score, 2),
                    "duration": round(c.duration, 3),
                    "intensity": c.intensity,
                    "reasons": c.reasons,
                }
                for i, c in enumerate(picks)
            ],
        }
    output_path = Path(output_path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path
