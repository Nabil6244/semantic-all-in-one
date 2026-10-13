"""A News or Post-Event video always shows the storm's data: when the plan has none (the AI was not told the event's date, so it
could not write a single data_source), Weather reads the date and the states from the script itself and adds the graphics a
storm story needs, in the beats that talk about them:

  radar + warnings_archive   the same UTC window (each warning appears on the radar frame of its issue time), on the first map
                             beat about the storm or its warnings
  storm_reports + counter    the SPC reports of that day (tornadoes), on the map beat about what was confirmed or surveyed
  source_line                with each of them
  satellite                  the picture of the storm day instead of today's ("latest")

Rows go into the project's weather_layers.csv (the plan.csv you loaded is not touched) with ids auto_*, so this happens once.
Footage beats never get them (weather graphics hide under footage). A script with no date adds nothing and says why."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from .news.timeline import STATE_NAMES

MONTHS = {m: i for i, m in enumerate(("january february march april may june july august september october november december").split(), 1)}
DATE_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I)
ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DATA_TYPES = {"radar", "warnings_archive", "storm_reports", "counter", "spc_outlook", "wpc_ero", "storm_cone", "storm_track",
              "satellite_loop", "rain_map", "rain_total", "record", "river_crest", "temp_extreme", "event_timeline"}
STORM_WORDS = {"storm", "storms", "tornado", "tornadoes", "radar", "warning", "warnings", "rotation", "thunderstorm", "thunderstorms",
               "supercell", "squall", "line", "touched", "struck", "hit", "swept", "moved", "crossed"}
REPORT_WORDS = {"reports", "reported", "confirmed", "survey", "surveys", "surveyed", "tornadoes", "ef", "ef0", "ef1", "ef2", "ef3", "ef4",
                "path", "damage", "track", "count", "touchdowns"}
# a storm day in the US runs through the local afternoon and evening: 10:00Z to 04:00Z the next day covers 6 AM to midnight Eastern
WINDOW_START_H, WINDOW_HOURS = 10, 18


@dataclass
class Event:
    day: str                          # YYYY-MM-DD (the SPC convective day)
    states: List[str] = field(default_factory=list)

    @property
    def window(self) -> str:
        a = datetime.strptime(self.day, "%Y-%m-%d") + timedelta(hours=WINDOW_START_H)
        b = a + timedelta(hours=WINDOW_HOURS)
        return f"{a:%Y-%m-%dT%H:%MZ}..{b:%Y-%m-%dT%H:%MZ}"

    @property
    def satellite_time(self) -> str:
        mid = datetime.strptime(self.day, "%Y-%m-%d") + timedelta(hours=WINDOW_START_H + WINDOW_HOURS / 2)
        return f"{mid:%Y-%m-%dT%H}:{mid.minute // 10 * 10:02d}Z"


def detect_event(text: str) -> Optional[Event]:
    """The first full date the script says ("October 11, 2026", or 2026-10-11) and the states it names, in order."""
    m = DATE_RE.search(text)
    if m:
        day = f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    else:
        m = ISO_RE.search(text)
        if not m:
            return None
        day = m.group(0)
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return None
    low = " " + re.sub(r"[^a-z ]+", " ", text.lower()) + " "
    found = []
    for name in sorted(STATE_NAMES, key=len, reverse=True):   # "west virginia" before "virginia"
        for hit in re.finditer(rf" {name} ", low):
            found.append((hit.start(), STATE_NAMES[name]))
        low = low.replace(f" {name} ", " " + "#" * len(name) + " ")
    states = []
    for _pos, code in sorted(found):
        if code not in states:
            states.append(code)
    return Event(day, states)


def _beats(beats_text: str):
    rows = list(csv.DictReader(io.StringIO(beats_text.lstrip("﻿"))))
    return [r for r in rows if (r.get("row") or "").strip().lower() == "beat"]


def _words(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def ensure_storm_data(project, fmt: str, notes: List[str]) -> bool:
    """Adds the storm's data graphics to a News / Post-Event plan that has none. True when rows were added."""
    if fmt not in ("news", "post") or not project.beats_csv.is_file() or not project.layers_csv.is_file():
        return False
    from .sidecar import COLUMNS

    beats_text = project.beats_csv.read_text(encoding="utf-8")
    layers_text = project.layers_csv.read_text(encoding="utf-8")
    rows = [r for r in csv.DictReader(io.StringIO(layers_text.lstrip("﻿"))) if any((v or "").strip() for v in r.values())]
    if any((r.get("type") or "").strip().lower() in DATA_TYPES for r in rows):
        return False
    beats = _beats(beats_text)
    event = detect_event(" ".join(b.get("text", "") for b in beats))
    if event is None:
        notes.append("This video has no radar or storm data: the script never says the event's date (like October 11, 2026), so "
                     "Weather cannot fetch it. Add the date to the script or to THE EVENT line of the prompt.")
        return False
    maps = [b for b in beats if (b.get("mode") or "").strip().lower() in ("map", "map_footage")]
    if not maps:
        return False
    first = maps[0]["beat"]
    storm = next((b for b in maps[1:] if _words(b.get("text")) & STORM_WORDS), maps[1] if len(maps) > 1 else maps[0])
    later = [b for b in maps if maps.index(b) > maps.index(storm)]
    report = next((b for b in later if _words(b.get("text")) & REPORT_WORDS), later[0] if later else storm)
    st = {"states": event.states[:3]} if event.states else {}
    add = [
        dict(beat=storm["beat"], vo_anchor=storm["vo_anchor"], id="auto_radar", type="radar", data_source=f"iem:radar@{event.window}#n0q"),
        dict(beat=storm["beat"], vo_anchor=storm["vo_anchor"], id="auto_warnings", type="warnings_archive",
             data_source=f"iem:warnings@{event.window}#TO,SV", extra=json.dumps(st) if st else ""),
        dict(beat=storm["beat"], vo_anchor=storm["vo_anchor"], id="auto_src_storm", type="source_line"),
        dict(beat=report["beat"], vo_anchor=report["vo_anchor"], id="auto_reports", type="storm_reports",
             data_source=f"spc:reports@{event.day}#tornado"),
        dict(beat=report["beat"], vo_anchor=report["vo_anchor"], id="auto_count", type="counter", data_source=f"spc:reports@{event.day}#tornado",
             extra=json.dumps({"anchor": "tr"})),
    ]
    if report["beat"] != storm["beat"]:
        add.append(dict(beat=report["beat"], vo_anchor=report["vo_anchor"], id="auto_src_reports", type="source_line"))

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    lines = list(csv.reader(io.StringIO(layers_text.lstrip("﻿"))))
    head = [c.strip().lower() for c in lines[0]] if lines else list(COLUMNS)
    w.writerow(head)
    for cells in lines[1:]:
        r = {h: (cells[i] if i < len(cells) else "") for i, h in enumerate(head)}
        typ = r.get("type", "").strip().lower()
        if typ == "satellite" and r.get("data_source", "").strip() == "gibs:geocolor@latest":
            r["data_source"] = f"gibs:geocolor@{event.satellite_time}"
        if typ == "headline" and fmt == "news":
            try:
                ex = json.loads(r.get("extra") or "{}")
                if isinstance(ex, dict) and ex.get("tone") != "news":
                    ex["tone"] = "news"
                    r["extra"] = json.dumps(ex)
            except ValueError:
                pass
        w.writerow([r.get(h, "") for h in head] if any(c.strip() for c in cells) else [])
    for r in add:
        w.writerow([r.get(h, "") for h in head])
    project.layers_csv.write_text(out.getvalue(), encoding="utf-8")
    try:
        project.resolved_json.unlink()   # fetched again, with the new graphics
    except OSError:
        pass
    where = storm["beat"] if storm["beat"] == report["beat"] else f"{storm['beat']} and {report['beat']}"
    notes.append(f"The plan had no storm data, so Weather added it from the script's date ({event.day}"
                 + (f", {', '.join(event.states)}" if event.states else "") + f"): radar and warnings, tornado reports and a "
                 f"tornado counter (beats {where}), and the satellite picture of that day.")
    return True
