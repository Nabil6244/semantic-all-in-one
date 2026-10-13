"""Clip approval for a Weather News project, and the hand-off of approved clips to Hybrid's footage beats.

<project>/weather/clips.json holds the event and its clips (weather.news.footage_pool.Clip), each proposed, approved or
rejected. Only an approved clip whose licence is allowed can reach a video:

    store = ClipStore(project_root)
    store.save_pool(event, clips)                 # after footage_pool.search (keeps earlier decisions)
    store.decide("nasa:jsc2022m000251_...", "approved", start_s=95, dur_s=8)
    download(store.get(id), store.media_dir)      # NASA / Commons: the file part we use, fetched with ffmpeg (no full download)
    store.clip_rows("b6")                         # beats.csv rows:  b6,clip,...,asset=<local file>,dur=8
    store.credit_rows("b6", "on the space station")  # weather_layers.csv rows: footage_credit with the clip's credit text

YouTube clips are fetched by the app's own YouTube code at render time (providers.youtube YtDlpBackend.download_segment);
that hand-off is an integrator request (docs/weather/agent_phase3.md R4). Until then a YouTube clip cannot become a clip row."""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .footage_pool import STATUSES, Clip, Event, assess

CLIPS_FILE = "clips.json"


class ApprovalError(ValueError):
    pass


class ClipStore:
    def __init__(self, project_root: "str | Path"):
        self.root = Path(project_root)
        self.dir = self.root / "weather"
        self.path = self.dir / CLIPS_FILE
        self.media_dir = self.dir / "clips"

    # ---- storage ----
    def load(self) -> "tuple[Optional[Event], List[Clip]]":
        if not self.path.is_file():
            return None, []
        d = json.loads(self.path.read_text(encoding="utf-8"))
        ev = Event(**d["event"]) if d.get("event") else None
        return ev, [Clip.from_dict(c) for c in d.get("clips", [])]

    def _write(self, ev: Optional[Event], clips: List[Clip]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        body = {"version": 1, "event": ev.__dict__ if ev else None, "clips": [c.to_dict() for c in clips]}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def save_pool(self, ev: Event, clips: List[Clip]) -> List[Clip]:
        """Merge a fresh search into the store: a clip the user already decided keeps its decision, times and file."""
        _old_ev, old = self.load()
        by_id = {c.id: c for c in old}
        merged = []
        for c in clips:
            prev = by_id.pop(c.id, None)
            if prev is not None and prev.decided:
                c.status, c.decided, c.local_path, c.start_s, c.dur_s = prev.status, True, prev.local_path, prev.start_s, prev.dur_s
            if prev is not None:
                c.use, c.beat = prev.use, prev.beat   # the user's labels survive a new search
            merged.append(assess(c, ev))
        merged += list(by_id.values())   # clips no longer found keep their record
        self._write(ev, merged)
        return merged

    def get(self, clip_id: str) -> Clip:
        for c in self.load()[1]:
            if c.id == clip_id:
                return c
        raise ApprovalError(f"no clip {clip_id!r} in {self.path}")

    def decide(self, clip_id: str, status: str, *, start_s: Optional[float] = None, dur_s: Optional[float] = None) -> Clip:
        if status not in STATUSES:
            raise ApprovalError(f"a clip is {', '.join(STATUSES)} (got {status!r})")
        ev, clips = self.load()
        for c in clips:
            if c.id != clip_id:
                continue
            if status == "approved":
                c.status, c.decided = "proposed", False
                assess(c, ev) if ev else None
                if c.reasons and c.status == "rejected" and any("licence" in r.lower() for r in c.reasons):
                    raise ApprovalError(f"{clip_id}: cannot be approved: {'; '.join(c.reasons)}")
            c.status, c.decided = status, True
            if start_s is not None:
                c.start_s = float(start_s)
            if dur_s is not None:
                if dur_s <= 0:
                    raise ApprovalError("dur_s must be more than 0 seconds")
                c.dur_s = float(dur_s)
            self._write(ev, clips)
            return c
        raise ApprovalError(f"no clip {clip_id!r} in {self.path}")

    def set_local(self, clip_id: str, path: "str | Path") -> None:
        ev, clips = self.load()
        for c in clips:
            if c.id == clip_id:
                c.local_path = str(path)
        self._write(ev, clips)

    def approved(self) -> List[Clip]:
        return [c for c in self.load()[1] if c.status == "approved" and c.decided]

    # ---- hand-off ----
    def clip_rows(self, beat: str, clip_ids: Optional[List[str]] = None) -> List[List[str]]:
        """beats.csv rows (row=clip) for the approved, downloaded clips (all of them, or these ids, in this order)."""
        clips = self.approved()
        if clip_ids is not None:
            by = {c.id: c for c in clips}
            missing = [i for i in clip_ids if i not in by]
            if missing:
                raise ApprovalError(f"not approved: {', '.join(missing)}")
            clips = [by[i] for i in clip_ids]
        rows = []
        for c in clips:
            if not c.local_path or not Path(c.local_path).is_file():
                raise ApprovalError(f"{c.id} is approved but not downloaded yet ({'YouTube clips are fetched by the app' if c.source == 'youtube' else 'run download'})")
            rows.append([beat, "clip", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", c.local_path,
                         f"{c.dur_s:g}" if c.dur_s else "", f"{c.credit} ({c.source} {c.source_id})"])
        return rows

    def credit_rows(self, beat: str, vo_anchor: str, clip_ids: Optional[List[str]] = None, tz: str = "America/New_York") -> List[List[str]]:
        """weather_layers.csv rows (type footage_credit) naming each clip's credit, date and place."""
        out = []
        for i, c in enumerate([c for c in self.approved() if clip_ids is None or c.id in clip_ids]):
            out.append([beat, vo_anchor, "", f"{beat}_credit{i + 1}", "footage_credit", "", "", "", "", json.dumps({"text": credit_text(c, tz)}, ensure_ascii=False)])
        return out


def credit_text(c: Clip, tz: str = "America/New_York") -> str:
    """'VIDEO: NASA · SEP 28, 2022' (+ ' · PLACE' when the clip names one)."""
    from .sources import parse_date

    parts = [c.credit.upper()]
    d = parse_date(c.date)
    if d is not None:
        parts.append(f"{d.strftime('%b').upper()} {d.day}, {d.year}")
    if c.place:
        parts.append(c.place.upper())
    if c.use in ("historical", "illustrative"):
        parts.append("ARCHIVE" if c.use == "historical" else "ILLUSTRATIVE")
    return " · ".join(parts)


def rows_csv(rows: List[List[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


# ---- download (direct-file sources) ----------------------------------------------------------------------------------

def media_url(c: Clip, get_text: Callable[[str], str]) -> str:
    """The video file of a NASA or Commons clip."""
    if c.media_url:
        return c.media_url
    if c.source == "nasa" and c.assets_url:
        from .sources import nasa_pick_rendition

        url = nasa_pick_rendition(json.loads(get_text(c.assets_url.replace("http://", "https://", 1))))
        if url:
            return url
    raise ApprovalError(f"{c.id}: no video file to download ({c.source} clips are fetched by the app)")


def download(c: Clip, dest_dir: "str | Path", get_text: Callable[[str], str], *, ffmpeg: str = "ffmpeg",
             run: Callable[..., Any] = subprocess.run) -> Path:
    """Fetch the used part of an APPROVED NASA/Commons clip (start_s, dur_s) with ffmpeg's ranged reads, into dest_dir."""
    if c.status != "approved" or not c.decided:
        raise ApprovalError(f"{c.id} is not approved: only approved clips are downloaded")
    if c.source not in ("nasa", "commons"):
        raise ApprovalError(f"{c.id}: {c.source} clips are fetched by the app's own code (integrator request R4)")
    url = media_url(c, get_text)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", c.source_id)[:80]
    out = dest_dir / f"{c.source}_{safe}_{int(c.start_s)}_{int(c.dur_s or 0)}.mp4"
    cmd = [ffmpeg, "-v", "error", "-y", "-ss", f"{c.start_s:g}", "-i", url]
    if c.dur_s:
        cmd += ["-t", f"{c.dur_s:g}"]
    cmd += ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
    r = run(cmd, capture_output=True, text=True)
    if getattr(r, "returncode", 1) != 0 or not out.is_file():
        raise ApprovalError(f"{c.id}: the download failed ({(getattr(r, 'stderr', '') or '').strip()[-300:]})")
    return out
