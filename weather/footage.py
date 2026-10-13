"""Full-screen footage in a Weather video: Hybrid's footage beats (beats.csv rows `clip`, and photo cards), fetched by the app's
existing providers and listed in the existing Visual Plan table.

Which sources a Weather video may use (docs/weather/weather_style_plan.md §6):
  - stock video and stock pictures (Pexels, Pixabay) and the user's own files: generic weather b-roll ("rain on a city street");
  - NEVER generated footage (Flow): a weather video must not show made-up weather as if it were real;
  - YouTube and other event footage arrive with Weather News (phase 3), with per-clip licence checks and approval.
Stock b-roll is generic, so it is never presented as footage of a particular event."""

from __future__ import annotations

from typing import List

ALLOWED = ("stock_video", "stock_image")
REFUSED = {
    "flow_video": "generated (Flow) video is never used in a weather video: it would show weather that did not happen",
    "flow_image": "generated (Flow) pictures are never used in a weather video: they would show weather that did not happen",
}


def _kind(asset: str) -> str:
    """'stock_video:rain on a street' -> 'stock_video'; a file path -> 'file'."""
    head, sep, _rest = str(asset).partition(":")
    if sep and head.replace("_", "").isalpha() and len(head) > 2:   # "C:\\clips\\a.mp4" has a one-letter head: a file
        return head.lower()
    return "file"


def footage_problems(plan, project_root=None) -> List[str]:
    """Every clip or card source the plan names that a Weather video may not use, naming the beat. With the project folder, an
    event clip (weather/clips/, Weather News) must also be approved in weather/clips.json."""
    out = []
    clips_dir, approved = None, set()
    if project_root is not None:
        from .news.approval import ClipStore

        store = ClipStore(project_root)
        clips_dir = str(store.media_dir)
        try:
            approved = {c.local_path for c in store.approved() if c.local_path}
        except (OSError, ValueError, KeyError, TypeError):
            approved = set()
    for b in plan.beats:
        assets = [("clip", c.asset) for c in b.clips]
        assets += [("card", s.asset) for s in ([b.support] if b.support is not None else []) + list(b.more_cards)]
        for what, asset in assets:
            kind = _kind(asset)
            if kind == "file" and clips_dir and str(asset).startswith(clips_dir) and str(asset) not in approved:
                out.append(f"beats.csv beat {b.id}: {what} {asset!r}: this event clip is not approved (weather/clips.json)")
                continue
            if kind == "file" or kind in ALLOWED:
                continue
            why = REFUSED.get(kind) or (f"{kind} is not available in Weather yet (stock_video:, stock_image: or your own file)"
                                        if kind != "youtube" else "YouTube footage is used only as an approved, downloaded event clip "
                                                                  "(weather/clips.json); use stock_video: or your own file")
            out.append(f"beats.csv beat {b.id}: {what} {asset!r}: {why}")
    return out


def footage_beats(plan) -> int:
    return sum(1 for b in plan.beats if b.mode == "footage")
