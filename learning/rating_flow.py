"""Rating logic shared by the UI: which renders can be rated, their current rating, prompt eligibility. No Tk here."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import events as ev
from . import ledger as _ledger

PROMPT_MAX_AGE_S = 900


def render_key(e: Dict[str, Any]) -> str:
    """The id a rating is attached to: the tracker's generation_id, else this ledger's own operation id."""
    return e.get("generation_id") or "op-" + str((e.get("payload") or {}).get("operation_id") or e["event_id"])


def render_history(project_id: str, ledger: Optional[_ledger.Ledger] = None, limit: int = 50) -> List[Dict[str, Any]]:
    led = ledger or _ledger.default_ledger()
    out = []
    for r in led.events(event_type="render_outcome", project_id=project_id, newest_first=True, limit=500):
        if (r.get("payload") or {}).get("outcome") != "success":
            continue
        key = render_key(r)
        rating = None
        for x in led.events(event_type="video_rating", project_id=project_id, style_scope=r["style_scope"], newest_first=True, limit=200):
            if (x.get("generation_id") or None) == key:
                rating = x
                break
        gid = r.get("generation_id")
        bad = bool(gid) and any(not (v.get("payload") or {}).get("validated", True)
                                for v in led.events(event_type="render_validation", generation_id=gid, limit=5))
        out.append({"render_key": key, "style_scope": r["style_scope"], "occurred_at": r["occurred_at"], "rendered": r,
                    "validation_failed": bad, "rating": rating})
        if len(out) >= limit:
            break
    return out


def pending_prompt_target(project_id: str, ledger: Optional[_ledger.Ledger] = None, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """The finished render to offer a rating for: newest, successful, not output-invalid, unrated, not skipped, and recent."""
    led = ledger or _ledger.default_ledger()
    hist = render_history(project_id, led, limit=1)
    if not hist:
        return None
    h = hist[0]
    try:
        age = (now or time.time()) - datetime.fromisoformat(h["occurred_at"]).timestamp()
    except Exception:
        return None
    if h["rating"] is not None or h["validation_failed"] or age > PROMPT_MAX_AGE_S or age < -5:
        return None
    if led.get_meta("rating_skipped:" + h["render_key"]):
        return None
    return h


def skip(render_key_: str, ledger: Optional[_ledger.Ledger] = None) -> None:
    """Skipping records no rating (so it is never a negative one); it only stops re-prompting."""
    try:
        (ledger or _ledger.default_ledger()).set_meta("rating_skipped:" + render_key_, "1")
    except Exception:
        pass


def submit(h: Dict[str, Any], rating: int, *, categories=None, tags=None, comment=None, ledger: Optional[_ledger.Ledger] = None) -> ev.RatingResult:
    r = h["rendered"]
    return ev.record_video_rating(r["project_id"], h["style_scope"], rating, generation_id=h["render_key"], categories=categories,
                                  tags=tags, comment=comment, ledger=ledger)
