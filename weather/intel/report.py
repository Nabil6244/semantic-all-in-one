"""The production report of an engine run: what was understood, what was found, what was added, what was not and why.

It never claims that every possible graphic was added: it lists the graphics the engine considered and, for each one left out,
the specific reason (no narration for it, no evidence, a source that failed, no room on the beat)."""

from __future__ import annotations

from typing import List

from .sources import SOURCES


def _beat_time(res, beat: str) -> str:
    seg = next((s for s in res.beats if s.id == beat), None)
    if seg is None or seg.start is None:
        return beat
    return f"{beat} ({seg.start:.1f}s)"


def report_text(res, project=None, *, recorded_how: str = "") -> str:
    e = res.event
    out: List[str] = ["# Weather Intelligence report", ""]
    out.append(f"Mode: {'A — no weather layers file: every data graphic was found by the engine' if res.mode == 'A' else 'B — your weather layers were kept; the engine filled the gaps'}"
               + (" (dry run: nothing was written)" if res.dry_run else ""))
    out += ["", "## The event", ""]
    cat = e.get("category", "").replace("_", " ")
    out.append(f"- Category: {cat}" + (f" (also: {', '.join(h.replace('_', ' ') for h in e.get('hazards', [])[1:])})" if len(e.get("hazards", [])) > 1 else ""))
    if e.get("storm"):
        s = e["storm"]
        out.append(f"- Storm: {s['name'].title()} — {s['id']} ({s['year']}), {e.get('storm_note', '')}")
    for name, note in e.get("context_storms") or []:
        out.append(f"- Also named: {note}")
    if e.get("main_day"):
        days = e.get("days") or []
        out.append(f"- Date: {e['main_day']}" + (f" (the story names {', '.join(days)})" if len(days) > 1 else ""))
    if e.get("moment"):
        out.append(f"- Key moment: {e['moment']} — {e.get('moment_note', '')}")
    if e.get("convective_day") and e.get("category") in ("tornado", "severe"):
        out.append(f"- SPC convective day: {e['convective_day']} (12 UTC to 12 UTC)")
    if e.get("states"):
        out.append(f"- Where: {', '.join(e['states'])}" + (f"; map focus {e.get('focus_name')}" if e.get("focus_name") else ""))
    if e.get("recorded"):
        out.append(f"- Recorded: {e['recorded']}" + (f" ({recorded_how})" if recorded_how else ""))
    for lf in e.get("landfalls") or []:
        out.append(f"- Landfall (NHC best track): {lf['time']} at {lf['lat']}, {lf['lon']}")
    if res.assumptions or res.ambiguities:
        out += ["", "## Assumptions and open questions", ""]
        out += [f"- Assumed: {a}" for a in res.assumptions]
        out += [f"- **Needs you:** {a}" for a in res.ambiguities]

    out += ["", "## Added for you", ""]
    data_added = [d for d in res.added if d.type != "source_line"]
    if not data_added:
        out.append("- Nothing: see below for why each graphic was left out.")
    for d in data_added:
        out.append(f"- **{d.id}** ({d.type}) on beat {_beat_time(res, d.beat)}, at the words \"{d.vo_anchor}\""
                   + (f" — {d.data_source}" if d.data_source else "") + f"\n  - why: {d.why}")
    lines = [d for d in res.added if d.type == "source_line"]
    if lines:
        out.append(f"- Source lines on beats {', '.join(d.beat for d in lines)} (they name the data on screen)")

    if res.preserved:
        out += ["", "## Your graphics, kept as they are", ""]
        out += [f"- {spec}: your row {rid}" for spec, rid in res.preserved]
    if res.conflicts:
        out += ["", "## Conflicts with the evidence (your rows were NOT changed)", ""]
        for c in res.conflicts:
            out.append(f"- **{c.row}** ({c.kind}): {c.problem}." + (f" Proposal: {c.proposal}." if c.proposal else "")
                       + (" Applied, as your overrides accept it." if c.applied else
                          (f" To apply it, add \"{c.kind}:{c.row}\" to \"accept\" in intel/overrides.json." if c.replacement else "")))

    out += ["", "## Left out, and why", ""]
    if not res.skipped and not res.dropped:
        out.append("- Nothing the engine considered was left out.")
    for s in res.skipped:
        out.append(f"- {s.title}: {s.reason}" + (f" (beat {s.beat})" if s.beat else ""))
    for d, why in res.dropped:
        if d.type == "source_line":
            continue
        out.append(f"- {d.id} ({d.type}) on beat {d.beat}: {why}")

    if res.claims:
        ok = [c for c in res.claims if c["verified"]]
        out += ["", "## The narration's numbers", "",
                f"{len(ok)} of {len(res.claims)} numbers the narrator says match a number the graphics show. The others are not "
                "wrong — no source the engine read shows them (a damage survey or an article it cannot read), so check them yourself.", ""]
        for c in res.claims:
            out.append(f"- \"{c['said']}\" (beat {c['beat']}): " + (f"matches {c['by']}" if c["verified"] else "not verified by a fetched source"))
    out += ["", "## Sources", ""]
    seen = {}
    for a in res.evidence.attempts:
        k = (a.source, a.status)
        seen.setdefault(k, []).append(a)
    for (sid, status), items in sorted(seen.items()):
        name = SOURCES[sid].name if sid in SOURCES else sid
        detail = f" — {items[0].detail}" if status not in ("ok", "cached") and items[0].detail else ""
        out.append(f"- {name}: {len(items)} request(s) {status}{detail}")
    used = sorted({a.source for a in res.evidence.attempts if a.source in SOURCES})
    if used:
        out += ["", "What each source is:", ""]
        for sid in used:
            s = SOURCES[sid]
            out.append(f"- {s.name} ({s.kind}): {s.measures}. Times: {s.times}. Caveats: {s.caveats}. Credit: {s.attribution}.")

    facts = [f for f in res.evidence.facts]
    if facts:
        out += ["", "## Evidence", ""]
        for f in facts[:60]:
            q = "" if f.quality == "final" else f" [{f.quality.upper()}]"
            out.append(f"- {f.kind}: {f.subject} — {f.what} = {f.value}{(' ' + f.unit) if f.unit else ''}{q}"
                       + (f" (issued {f.issued})" if f.issued else "") + (f" · {', '.join(f.caveats)}" if f.caveats else ""))
        if len(facts) > 60:
            out.append(f"- … {len(facts) - 60} more in intel/evidence.json")
    if res.notes:
        out += ["", "## Notes", ""]
        out += [f"- {n}" for n in dict.fromkeys(res.notes)]
    degraded = [a for a in res.evidence.attempts if a.status == "temporary"]
    if degraded:
        out += ["", f"**Degraded:** {len(degraded)} request(s) failed for network or server reasons; run again later to try them."]
    return "\n".join(out) + "\n"


def summary_lines(res) -> List[str]:
    """A few lines for the app's log and the Check plan box."""
    e = res.event
    head = f"Weather Intelligence: {e.get('category', '').replace('_', ' ')}"
    if e.get("storm"):
        head += f", {e['storm']['name'].title()} ({e['storm']['id']})"
    if e.get("main_day"):
        head += f", {e['main_day']}"
    out = [head]
    data_added = [d for d in res.added if d.type != "source_line"]
    if data_added:
        out.append("Added for you: " + "; ".join(f"{d.type} on {d.beat}" for d in data_added))
    for c in res.conflicts:
        out.append(f"Check your row {c.row}: {c.problem}")
    for a in res.ambiguities:
        out.append(f"Needs you: {a}")
    left = [s for s in res.skipped if "never discusses" not in s.reason and "not a " not in s.reason]
    for s in left[:6]:
        out.append(f"Not added — {s.title}: {s.reason}")
    for d, why in res.dropped:
        if d.type != "source_line":
            out.append(f"Not added — {d.id}: {why}")
    return out
