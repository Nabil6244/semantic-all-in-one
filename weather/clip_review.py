"""The event-footage screen (phase 5): find clips for a News or Post-Event project, see each clip's source, rights evidence and why it
was (or was not) picked, approve or reject it, label it historical or illustrative, pick the beat it is for, download it, and put
the approved clips into their beats.

The logic is plain functions (tested in test_weather_clip_review.py); `open_window(app)` is the thin CustomTkinter screen over them.
Approving records the user's decision; it is not a licence. The screen shows the rights evidence the source gave and nothing more."""

from __future__ import annotations

import csv
import io
import json
import threading
import webbrowser
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .news.approval import ApprovalError, ClipStore, credit_text, download
from .news.footage_pool import Clip, Event, search

USES = ("", "historical", "illustrative")


# ---- what the screen shows -------------------------------------------------------------------------------------------------

def why_text(c: Clip) -> str:
    """Why the clip was picked, or why it cannot be used, in one line."""
    if c.status == "rejected" and c.reasons:
        return "Not usable: " + "; ".join(c.reasons)
    if c.reasons:
        return "Check: " + "; ".join(c.reasons)
    return "Picked: dated inside the event window and names the event or its places"


def rights_text(c: Clip) -> str:
    lic = c.licence or ("U.S. government work (public domain)" if c.source == "nasa" else "no licence given")
    url = f" ({c.licence_url})" if c.licence_url else ""
    return f"Rights evidence from the source: {lic}{url}. Approving records your decision; it is not a licence."


def beats_of(beats_csv: Path) -> List[Dict[str, str]]:
    """[{id, mode, words}] of the plan's beats (words: the first words of the narration)."""
    if not beats_csv.is_file():
        return []
    out = []
    for r in csv.DictReader(io.StringIO(beats_csv.read_text(encoding="utf-8"))):
        if (r.get("row") or "") == "beat":
            out.append({"id": r.get("beat", ""), "mode": r.get("mode", ""), "words": " ".join((r.get("text") or "").split()[:10])})
    return out


def set_labels(store: ClipStore, clip_id: str, *, use: Optional[str] = None, beat: Optional[str] = None) -> Clip:
    if use is not None and use not in USES:
        raise ApprovalError(f"a clip is historical, illustrative or unlabelled (got {use!r})")
    ev, clips = store.load()
    for c in clips:
        if c.id == clip_id:
            if use is not None:
                c.use = use
            if beat is not None:
                c.beat = beat
            store._write(ev, clips)
            return c
    raise ApprovalError(f"no clip {clip_id!r} in {store.path}")


# ---- the hand-off: approved clips into their beats ------------------------------------------------------------------------

def _write_csv(header: List[str], rows: List[Dict[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def use_in_beats(store: ClipStore, beats_csv: Path, layers_csv: Path) -> List[str]:
    """Put every approved, downloaded clip that names a beat into that beat (beats.csv clip rows, under the beat) and its credit
    chip into weather_layers.csv. Event clips placed earlier are replaced; other clips (stock, your own files) are kept.
    Returns what was done; raises ApprovalError naming the problem (and writes nothing) when a clip cannot be placed."""
    clips = [c for c in store.approved() if c.beat]
    if not clips:
        raise ApprovalError("no approved clip has a beat yet: pick the beat each clip is for")
    text = beats_csv.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    header, rows = list(reader.fieldnames or []), list(reader)
    for col in ("asset", "dur", "why"):
        if col not in header:
            header.append(col)
    beats = {r.get("beat"): r for r in rows if r.get("row") == "beat"}
    by_beat: Dict[str, List[Clip]] = {}
    for c in clips:
        b = beats.get(c.beat)
        if b is None:
            raise ApprovalError(f"{c.id} is for beat {c.beat!r}, which the plan does not have")
        if (b.get("mode") or "") != "footage":
            raise ApprovalError(f"beat {c.beat} is a map beat: make it a footage beat (mode footage) in beats.csv first")
        if not c.local_path or not Path(c.local_path).is_file():
            raise ApprovalError(f"{c.id} is approved but not downloaded yet")
        by_beat.setdefault(c.beat, []).append(c)
    media = str(store.media_dir)
    kept = [r for r in rows if not (r.get("row") == "clip" and r.get("beat") in by_beat and str(r.get("asset", "")).startswith(media))]
    out_rows: List[Dict[str, str]] = []
    for i, r in enumerate(kept):   # event clips placed before are replaced: the new ones go at the end of their beat's rows
        out_rows.append(r)
        last_of_beat = i + 1 == len(kept) or kept[i + 1].get("beat") != r.get("beat")
        if r.get("beat") in by_beat and last_of_beat:
            for c in by_beat[r["beat"]]:
                out_rows.append({"beat": c.beat, "row": "clip", "asset": c.local_path, "dur": f"{c.dur_s:g}" if c.dur_s else "",
                                 "why": f"{c.credit} ({c.source} {c.source_id})"})
    lt = layers_csv.read_text(encoding="utf-8") if layers_csv.is_file() else "beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"
    lr = csv.DictReader(io.StringIO(lt))
    lheader, lrows = list(lr.fieldnames or []), [r for r in lr if not (r.get("type") == "footage_credit" and r.get("beat") in by_beat)]
    for beat, cs in by_beat.items():
        for i, c in enumerate(cs):
            lrows.append({"beat": beat, "vo_anchor": beats[beat].get("vo_anchor", ""), "id": f"{beat}_credit{i + 1}", "type": "footage_credit",
                          "extra": json.dumps({"text": credit_text(c)}, ensure_ascii=False)})
    beats_csv.write_text(_write_csv(header, out_rows), encoding="utf-8")
    layers_csv.write_text(_write_csv(lheader, lrows), encoding="utf-8")
    return [f"beat {b}: {len(cs)} clip(s) with credit" for b, cs in by_beat.items()]


# ---- the screen ---------------------------------------------------------------------------------------------------------------

def open_window(app) -> None:
    """The Event footage window for the current project (Weather card > Event footage…)."""
    from . import app_section as A
    from .layers import http_text

    M = A._m(app)
    ctk = M.ctk
    p = A.project(app)
    if p is None:
        return
    store = ClipStore(p.root)
    win = ctk.CTkToplevel(app)
    win.title("Weather · Event footage")
    win.geometry("980x720")
    win.grid_columnconfigure(0, weight=1)
    win.grid_rowconfigure(2, weight=1)
    ev, _clips = store.load()
    top = ctk.CTkFrame(win, fg_color="transparent")
    top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
    fields = {}
    for col, (key, label, width, val) in enumerate((("name", "Event", 200, ev.name if ev else ""), ("start", "From (YYYY-MM-DD)", 120, ev.start if ev else ""),
                                                     ("end", "To", 120, ev.end if ev else ""), ("places", "Places (comma separated)", 260, ", ".join(ev.places) if ev else ""))):
        ctk.CTkLabel(top, text=label, font=ctk.CTkFont(size=11, weight="bold"), text_color=M._MUTED).grid(row=0, column=col, sticky="w", padx=(0, 8))
        var = ctk.StringVar(value=val)
        ctk.CTkEntry(top, textvariable=var, width=width, height=30).grid(row=1, column=col, sticky="w", padx=(0, 8))
        fields[key] = var
    status = ctk.StringVar(value="Search finds NASA (and Wikimedia Commons) clips of the event and checks each one's date, subject and licence.")
    ctk.CTkLabel(win, textvariable=status, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=940, justify="left").grid(
        row=1, column=0, sticky="ew", padx=16)
    body = ctk.CTkScrollableFrame(win, fg_color="transparent")
    body.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)
    body.grid_columnconfigure(0, weight=1)
    beat_list = beats_of(p.beats_csv)
    beat_names = ["(no beat)"] + [f"{b['id']} · {b['mode'] or 'map'} · {b['words']}" for b in beat_list]

    def run_bg(work: Callable[[], str]) -> None:
        def worker():
            try:
                msg = work()
            except Exception as exc:  # noqa: BLE001 - shown to the user
                msg = f"Problem: {exc}"
            win.after(0, lambda: (status.set(msg), refresh()))
        threading.Thread(target=worker, daemon=True).start()

    def act(fn: Callable[[], object], msg: str) -> None:
        try:
            fn()
            status.set(msg)
        except ApprovalError as exc:
            status.set(f"Problem: {exc}")
        refresh()

    def card(c: Clip, row: int) -> None:
        f = ctk.CTkFrame(body, fg_color=M._CARD, corner_radius=8, border_width=1, border_color=M._BORDER)
        f.grid(row=row, column=0, sticky="ew", pady=4)
        f.grid_columnconfigure(0, weight=1)
        colour = {"approved": "#2E8B57", "rejected": "#C8102E"}.get(c.status, M._MUTED)
        ctk.CTkLabel(f, text=f"{c.status.upper()} · {c.title}", font=ctk.CTkFont(size=12, weight="bold"), text_color=colour, anchor="w").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(f, text=f"{c.source.upper()} · {c.date or 'no date'} · {c.place or 'no place'} · credit: {c.credit or '—'}",
                     font=ctk.CTkFont(size=11), text_color=M._TEXT, anchor="w").grid(row=1, column=0, columnspan=4, sticky="w", padx=12)
        for i, line in enumerate((why_text(c), rights_text(c))):
            ctk.CTkLabel(f, text=line, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=900, justify="left").grid(
                row=2 + i, column=0, columnspan=4, sticky="w", padx=12)
        ctl = ctk.CTkFrame(f, fg_color="transparent")
        ctl.grid(row=4, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8))
        beat_var = ctk.StringVar(value=next((n for n in beat_names if n.split(" · ")[0] == c.beat), beat_names[0]))
        ctk.CTkOptionMenu(ctl, values=beat_names, variable=beat_var, width=300, dynamic_resizing=False,
                          command=lambda v, cid=c.id: act(lambda: set_labels(store, cid, beat="" if v == beat_names[0] else v.split(" · ")[0]),
                                                          "Beat saved.")).pack(side="left", padx=(0, 6))
        use_var = ctk.StringVar(value=c.use or "unlabelled")
        ctk.CTkSegmentedButton(ctl, values=["unlabelled", "historical", "illustrative"], variable=use_var,
                               command=lambda v, cid=c.id: act(lambda: set_labels(store, cid, use="" if v == "unlabelled" else v), "Label saved.")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(ctl, text="Preview", width=70, command=lambda u=c.page_url: u and webbrowser.open(u)).pack(side="left", padx=(0, 6))
        if not (c.status == "rejected" and any("licence" in r.lower() for r in c.reasons)):
            ctk.CTkButton(ctl, text="Approve", width=70, fg_color="#2E8B57",
                          command=lambda cid=c.id: act(lambda: store.decide(cid, "approved", dur_s=8.0 if not c.dur_s else None),
                                                       "Approved (your decision, not a licence).")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(ctl, text="Reject", width=60, fg_color="#7A1F2B",
                      command=lambda cid=c.id: act(lambda: store.decide(cid, "rejected"), "Rejected.")).pack(side="left", padx=(0, 6))
        if c.status == "approved" and c.source in ("nasa", "commons") and not c.local_path:
            ctk.CTkButton(ctl, text="Download", width=80,
                          command=lambda cid=c.id: run_bg(lambda: (store.set_local(cid, download(store.get(cid), store.media_dir, http_text)),
                                                                   "Downloaded.")[1])).pack(side="left")

    def refresh() -> None:
        for w in body.winfo_children():
            w.destroy()
        _ev, clips = store.load()
        order = {"approved": 0, "proposed": 1, "rejected": 2}
        for i, c in enumerate(sorted(clips, key=lambda c: order.get(c.status, 3))):
            card(c, i)
        if not clips:
            ctk.CTkLabel(body, text="No clips yet: fill in the event and click Search. Without suitable footage, keep the beats on the map.",
                         text_color=M._MUTED).grid(row=0, column=0, pady=20)

    def do_search() -> None:
        e = Event(name=fields["name"].get().strip(), start=fields["start"].get().strip(), end=fields["end"].get().strip(),
                  places=[x.strip() for x in fields["places"].get().split(",") if x.strip()])
        if not (e.name and e.start and e.end):
            status.set("Fill in the event, its first and last day.")
            return
        status.set("Searching…")

        def work() -> str:
            clips, problems = search(e, http_text)
            store.save_pool(e, clips)
            return f"{len(clips)} clip(s) found." + (f" {'; '.join(problems)}" if problems else "")
        run_bg(work)

    def do_use() -> None:
        try:
            done = use_in_beats(store, p.beats_csv, p.layers_csv)
            status.set("In the plan: " + "; ".join(done) + ". Check plan again before you render.")
            app._weather_ok = None
        except (ApprovalError, OSError) as exc:
            status.set(f"Problem: {exc}")

    bar = ctk.CTkFrame(win, fg_color="transparent")
    bar.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
    ctk.CTkButton(bar, text="Search", width=100, command=do_search).pack(side="left", padx=(0, 8))
    ctk.CTkButton(bar, text="Use approved clips in their beats", width=230, command=do_use).pack(side="left")
    refresh()
