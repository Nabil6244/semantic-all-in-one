"""War Footage Director, Stage 5: is this real footage of THIS event? Scored apart from relevance (a clip can be on topic and still not be
evidence of the event the narrator describes).

docs/war/FOOTAGE_DIRECTOR_PLAN.md. Public signals only, so the class is an estimate, never proof (the report and labels say so):

  verified_event  an agency / broadcaster / regional war-news upload that names the scene's place or subject, uploaded within VERIFY_DAYS after the event's
                  earliest possible day (or, for an undated event, within RECENT_DAYS before the film)
  corroborated    the same picture (tile hashes) appears in uploads from at least two independent channels; the earliest is the likely origin
  unverified      everything else

Red flags cap a clip at 'unverified': AI / simulation / game / reconstruction / 'archive' wording, an upload before the event, a channel
whose tier is commentary. EVENT and MOVEMENT scenes take only verified_event or corroborated clips; LOCATION and SUBJECT scenes may use an
unverified clip, labelled ILLUSTRATIVE FOOTAGE; with a CSV prompt the prompt match decides (see allowed()).
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .director_rules import _has, _upload, channel_tier, event_date, hamming
from .narration_read import Reading, fold

VERIFY_DAYS = 14
RECENT_DAYS = 60
RECENT_AGENCY_DAYS = 180
STRICT_TYPES = ("EVENT", "MOVEMENT")
_RED = re.compile(r"\b(ai|ai[- ]generated|simulation|simulated|game|gameplay|reconstruction|recreated|re-enactment|cgi|archive|archival|"
                  r"file footage|old footage|years ago|rare footage)\b", re.I)


def classify(c: Any, r: Reading, film_date: Optional[_dt.date], hashes: Sequence[str] = (),
             others: Sequence[Tuple[str, str, Sequence[str]]] = (), story: Optional[Tuple[_dt.date, _dt.date]] = None,
             level: str = "exact") -> Tuple[str, List[str]]:
    """(class, reasons). `others` = (video_id, channel, tile hashes) of other candidates' windows, for corroboration. A contextual clip
    (the story's place, filmed earlier in the story) is timely when it was uploaded inside the story's period."""
    why: List[str] = []
    if getattr(c, "blocked", False):
        return "unverified", [f"metadata and previews need a sign-in on YouTube (age-restricted{': ' + c.content_warning if c.content_warning else ''}):"
                              " upload date and pictures could not be checked before capture"]
    tier = channel_tier(c.channel)
    up = _upload(c)
    red = _RED.search(f"{c.title} {(getattr(c, 'details', None) or {}).get('description', '')[:300]}")
    if red:
        why.append(f"red flag: '{red.group(0)}'")
    if tier == "commentary":
        why.append("red flag: commentary channel")
    stated = getattr(r, "date_source", "stated") in ("stated", "")
    win = event_date(r, film_date) if film_date and stated else None
    parts_ = [p_ for p_ in (getattr(r, "prompt_parts", None) or []) if p_.get("names") or p_.get("words")]
    generic = bool(parts_) and not any(p_.get("names") for p_ in parts_)
    if up and win and up < win[0] and level != "contextual" and not generic:     # a generic picture (jets, troops) has no date
        why.append(f"red flag: uploaded {up}, before the event")
    if why:
        return "unverified", why
    hay = fold(f"{c.title} {c.description}").lower()
    named = any(_has(hay, k) for k in r.key_terms[:5]) if r.key_terms else False
    timely = False
    if up and story and level == "contextual":
        timely = story[0] - _dt.timedelta(days=30) <= up <= story[1] + _dt.timedelta(days=365 * 3)
    elif up and win:
        timely = 0 <= (up - win[0]).days <= VERIFY_DAYS + (win[1] - win[0]).days
    elif up and story and not win:
        # a historical film: the story's months. 2026-11-10 owner (accuracy): one year after the story at most, not three (Moskva 044:
        # 2024 Neptune strikes on Oryol / Borisoglebsk passed for the 2022 Moskva strike)
        timely = story[0] - _dt.timedelta(days=30) <= up <= story[1] + _dt.timedelta(days=365)
    elif up and film_date and not win:
        # an undated sentence describes a running situation (queues, outages): an agency / broadcaster report of it within months still
        # shows it; a regional re-post must be recent
        timely = 0 <= (film_date - up).days <= (RECENT_AGENCY_DAYS if tier in ("agency", "broadcaster") else RECENT_DAYS)
    if tier in ("agency", "broadcaster", "regional") and named and timely:
        return "verified_event", [f"{tier} upload ({c.channel}) naming the subject, uploaded {up}"]
    # corroboration: the same picture from another, independent channel
    if hashes:
        same = [(vid, ch) for vid, ch, hs in others if vid != c.video_id and ch and ch.lower() != (c.channel or "").lower()
                and sum(1 for h in hashes if any(hamming(h, x) <= 10 for x in hs)) >= 2]
        if same:
            return "corroborated", [f"same footage also uploaded by {', '.join(sorted({ch for _, ch in same}))[:80]}"]
    reasons = [f"{tier} channel"]
    if not named:
        reasons.append("subject not named")
    if not timely:
        reasons.append(f"upload date {up or 'unknown'} not close to the event")
    return "unverified", reasons


def allowed(cls: str, r: Reading, level: str = "exact", tier: str = "", blocked: bool = False, reasons: Sequence[str] = ()) -> bool:
    """Which classes a scene may use.
    - Red flags (AI / game / simulation / commentary channel / uploaded before the event) never.
    - With a CSV prompt the writer said what the picture is; the rules already made the clip show it (its subject + one more prompt word),
      so an unverified clip is allowed, labelled ILLUSTRATIVE FOOTAGE. Both reference channels show the sentence's KIND of thing (a
      warship, jets, troops, a refinery fire, the named politician), not footage proven to be from that day (2026-11-10 owner: the
      footage we need is mostly generic; verified-only left the Moskva film with 0 clips).
    - Without a prompt: EVENT / MOVEMENT scenes take verified or corroborated footage (an age-restricted agency / broadcaster upload that
      names the subject as UNVERIFIED); other scenes anything that passed the rules."""
    if cls in ("verified_event", "corroborated"):
        return level != "atmospheric" or bool(getattr(r, "prompt_parts", None))
    if any(str(x).startswith("red flag") for x in reasons):
        return False
    if getattr(r, "prompt_parts", None):
        return True
    if level == "atmospheric":
        return False
    if any(t in r.types for t in STRICT_TYPES):
        return blocked and tier in ("agency", "broadcaster")
    return True

def label(cls: str) -> str:
    return {"verified_event": "", "corroborated": "", "unverified": "ILLUSTRATIVE FOOTAGE"}.get(cls, "ILLUSTRATIVE FOOTAGE")
