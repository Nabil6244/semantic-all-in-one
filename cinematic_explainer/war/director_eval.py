"""War Footage Director, Stage 0: score a footage decision report against the hand-labelled evaluation set.

docs/war/FOOTAGE_DIRECTOR_PLAN.md, Part D. The evaluation set (test_fixtures/war_director_eval.json) holds every scene of War renders 038 and 033:
the narration, its sentence types, whether footage is wanted at all, the scene's key terms, and the clips judged from their frames in the audit
(docs/war/FOOTAGE_RELEVANCE_AUDIT.md). Pure and offline: no network, no models, nothing rendered.

Report format (what the director writes as state/war/discovery_report.json; `from_manifest` builds the same thing from today's manifest):

    {"version": 1, "render": "038",
     "scenes": [{"scene": "009", "decision": "footage" | "graphics" | "ai" | "none",
                 "types": [...], "graphic_intent": "...",
                 "clip": {"video_id", "source", "source_url", "clip_start", "clip_end", "title", "channel", "description",
                          "upload_date", "authenticity", "moment_verified", "frame_flags": [...], "tile_hashes": ["16 hex digits", ...],
                          "reused": false}}]}

A placed clip is judged, in this order: a judged clip of that scene (same video, start within JUDGE_TOL_S) -> its verdict; a video in the
scene's bad_ids -> wrong; a video in the scene's likely_ok -> likely_match (title-level only); otherwise unjudged (needs a human look).

    python -m cinematic_explainer.war.director_eval --render 038 --manifest <.asset_manifest.json>
    python -m cinematic_explainer.war.director_eval --render 038 --report <discovery_report.json>
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

EVAL_PATH = Path(__file__).resolve().parents[2] / "test_fixtures" / "war_director_eval.json"
JUDGE_TOL_S = 6.0               # a placed clip is "the judged clip" when it starts this close to it in the same video
DEFAULT_CLIP_S = 8.0            # the YouTube capture length when a record has no end
HASH_NEAR = 10                  # tile hashes this close (Hamming, 64 bit) show the same picture
HASH_MIN_TILES = 2              # ... on at least this many tiles: the same footage, whatever the URL
NOT_FOOTAGE = frozenset({"talking_head", "studio_presenter", "text_screen", "graphic_screen", "other_channel_graphic", "pillarbox",
                         "not_footage", "commentary"})
EVENT_TYPES = frozenset({"EVENT", "MOVEMENT"})
AUTHENTIC = frozenset({"verified_event", "corroborated"})
PROVENANCE_KEYS = ("channel", "upload_date", "clip_start", "authenticity")
GOOD = ("match", "partial", "likely_match")


def load_eval(path: Optional[Path] = None) -> Dict[str, Any]:
    return json.loads(Path(path or EVAL_PATH).read_text(encoding="utf-8"))


def _fold(text: Any) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def _num(v: Any) -> Optional[float]:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def from_manifest(manifest: Dict[str, Any], render: str) -> Dict[str, Any]:
    """Today's manifest as a report (the baseline). Every record with a file is 'footage' (flow -> 'ai'); missing scenes are 'none'."""
    scenes = []
    for no, rec in sorted(manifest.items()):
        if not isinstance(rec, dict):
            continue
        src = str(rec.get("source") or rec.get("asset_type") or "")
        decision = "ai" if src.startswith("flow") else ("footage" if str(rec.get("status") or "complete").lower() == "complete" else "none")
        start = _num(rec.get("clip_start"))
        end = _num(rec.get("timestamp_end"))
        if start is not None and end is None:
            end = start + (_num(rec.get("clip_duration")) or DEFAULT_CLIP_S)
        vid = str(rec.get("video_id") or rec.get("provider_asset_id") or "")
        if src.startswith("stock") and vid and ":" not in vid and rec.get("provider") == "pixabay":
            vid = f"pixabay:{vid}"
        clip = {"video_id": vid, "source": src, "source_url": rec.get("source_url") or "", "clip_start": start, "clip_end": end,
                "title": rec.get("video_title") or rec.get("title") or "", "channel": rec.get("channel") or "",
                "description": rec.get("description") or "", "upload_date": rec.get("upload_date") or "",
                "authenticity": rec.get("authenticity") or "", "moment_verified": bool(rec.get("moment_verified")),
                "frame_flags": list(rec.get("frame_flags") or []), "tile_hashes": list(rec.get("tile_hashes") or []),
                "reused": bool(rec.get("reused"))}
        scenes.append({"scene": str(no).zfill(3), "decision": decision, "types": [], "graphic_intent": "", "clip": clip})
    return {"version": 1, "render": render, "scenes": scenes}


def _judge(clip: Dict[str, Any], label: Dict[str, Any]) -> Tuple[str, List[str], str]:
    vid = str(clip.get("video_id") or "")
    start = _num(clip.get("clip_start"))
    for j in label.get("judged") or []:
        if j.get("video_id") != vid:
            continue
        js = _num(j.get("start"))
        if js is None or start is None or abs(js - start) <= JUDGE_TOL_S:
            return j.get("verdict") or "unjudged", list(j.get("flags") or []), j.get("reason") or ""
    if vid and vid in (label.get("bad_ids") or []):
        return "wrong", [], "known wrong video for this scene"
    if vid and vid in (label.get("likely_ok") or []):
        return "likely_match", [], "found by a specific search (title only, frames unchecked)"
    return "unjudged", [], ""


def _hamming(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (TypeError, ValueError):
        return 64


def _same_picture(h1: Iterable[str], h2: Iterable[str]) -> bool:
    h2 = list(h2)
    return sum(1 for a in h1 if any(_hamming(a, b) <= HASH_NEAR for b in h2)) >= HASH_MIN_TILES


def repeats(placed: List[Tuple[str, Dict[str, Any]]]) -> List[Tuple[str, str, str]]:
    """(earlier scene, later scene, why) for every later clip that repeats an earlier one: the same video over overlapping seconds, or the
    same picture by tile hashes (a re-upload under another URL). A clip marked `reused` is a deliberate return and is not counted."""
    out = []
    for i, (sb, b) in enumerate(placed):
        if b.get("reused"):
            continue
        for sa, a in placed[:i]:
            va, vb = a.get("video_id"), b.get("video_id")
            a0, b0 = _num(a.get("clip_start")), _num(b.get("clip_start"))
            if va and va == vb:
                if a0 is None or b0 is None:
                    out.append((sa, sb, "same file"))
                    break
                a1 = _num(a.get("clip_end")) or a0 + DEFAULT_CLIP_S
                b1 = _num(b.get("clip_end")) or b0 + DEFAULT_CLIP_S
                if a0 < b1 - 1.0 and b0 < a1 - 1.0:
                    out.append((sa, sb, "same video, overlapping seconds"))
                    break
            if a.get("tile_hashes") and b.get("tile_hashes") and _same_picture(a["tile_hashes"], b["tile_hashes"]):
                out.append((sa, sb, "same picture (tile hashes)"))
                break
    return out


def evaluate(report: Dict[str, Any], eval_set: Optional[Dict[str, Any]] = None, render: str = "") -> Dict[str, Any]:
    """The Part D numbers for one report, plus one row per scene."""
    eval_set = eval_set or load_eval()
    rid = render or str(report.get("render") or "")
    labels = {s["scene"]: s for s in eval_set["renders"][rid]["scenes"]}
    by_no = {str(s.get("scene")).zfill(3): s for s in report.get("scenes") or []}
    rows, placed = [], []
    for no, label in labels.items():
        sc = by_no.get(no) or {"decision": "none", "clip": {}}
        clip = sc.get("clip") or {}
        decision = sc.get("decision") or "none"
        row = {"scene": no, "types": label["types"], "footage_wanted": label["footage_wanted"], "decision": decision,
               "video_id": clip.get("video_id", ""), "verdict": "", "flags": [], "reason": "", "names_entity": None}
        if decision == "footage" and clip:
            verdict, flags, reason = _judge(clip, label)
            row.update(verdict=verdict, flags=sorted(set(flags) | set(clip.get("frame_flags") or [])), reason=reason)
            hay = _fold(" ".join(str(clip.get(k) or "") for k in ("title", "description")))
            keys = [_fold(k) for k in label.get("key_terms") or [] if _fold(k)]
            # a title can name the place and still show something else (038/009: 'Kirishi' in the title, a Rostov warehouse on screen)
            row["names_entity"] = verdict != "wrong" and bool(keys) and any(re.search(rf"\b{re.escape(k)}\b", hay) for k in keys)
            placed.append((no, clip))
        rows.append(row)
    footage_rows = [r for r in rows if r["decision"] == "footage"]
    n = len(footage_rows)
    count = lambda v: sum(1 for r in footage_rows if r["verdict"] == v)  # noqa: E731
    wanted = [r for r in rows if r["footage_wanted"]]
    speakers = {no: _fold(l.get("speaker")) for no, l in labels.items() if l.get("speaker")}

    def graphics_violation(r: Dict[str, Any]) -> bool:
        if r["footage_wanted"] or r["decision"] != "footage":
            return False
        clip = (by_no.get(r["scene"]) or {}).get("clip") or {}
        if clip.get("reused"):
            return False
        if r["scene"] in speakers and ("speaker" in r["flags"] or speakers[r["scene"]] in _fold(clip.get("title"))):
            return False                    # the sentence's own speaker on screen is the subject, not filler
        return True

    events = [r for r in footage_rows if EVENT_TYPES & set(r["types"])]
    rep = repeats(placed)
    return {
        "render": rid,
        "scenes": len(rows),
        "placed": n,
        "match": count("match"), "partial": count("partial"), "likely_match": count("likely_match"),
        "generic": count("generic"), "wrong": count("wrong"), "unjudged": count("unjudged"),
        "good_share": round(sum(1 for r in footage_rows if r["verdict"] in GOOD) / n, 3) if n else 0.0,
        "footage_wanted": len(wanted),
        "entity_named": sum(1 for r in wanted if r["names_entity"]),
        "repeats": len(rep), "repeat_pairs": rep,
        "not_footage_placed": sum(1 for r in footage_rows if NOT_FOOTAGE & set(r["flags"])),
        "graphics_violations": sum(1 for r in rows if graphics_violation(r)),
        "provenance_complete": sum(1 for no, c in placed if (c.get("video_id") or c.get("source_url")) and all(c.get(k) not in (None, "") for k in PROVENANCE_KEYS)),
        "event_unverified": sum(1 for r in events if ((by_no.get(r["scene"]) or {}).get("clip") or {}).get("authenticity") not in AUTHENTIC),
        "moment_verified": sum(1 for no, c in placed if c.get("moment_verified")),
        "rows": rows,
    }


def summary(m: Dict[str, Any]) -> str:
    n = m["placed"] or 1
    return "\n".join([
        f"render {m['render']}: {m['scenes']} scenes, {m['placed']} clips placed",
        f"  verdicts      match {m['match']} | partial {m['partial']} | likely {m['likely_match']} | generic {m['generic']} | wrong {m['wrong']} | unjudged {m['unjudged']}",
        f"  good share    {m['good_share']:.0%} of placed clips (target >= 90%)",
        f"  wrong         {m['wrong']} (target 0)",
        f"  entity named  {m['entity_named']} of {m['footage_wanted']} footage scenes (target >= 70%)",
        f"  repeats       {m['repeats']} (target 0)",
        f"  not footage   {m['not_footage_placed']} placed (target 0)",
        f"  graphics      {m['graphics_violations']} claim/stat/question/transition scenes covered by footage (target 0)",
        f"  provenance    {m['provenance_complete']} of {m['placed']} complete (target all)",
        f"  event unverif {m['event_unverified']} (target 0)",
        f"  moment check  {m['moment_verified']} of {n if m['placed'] else 0} verified (target all)",
    ])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--render", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--report")
    g.add_argument("--manifest")
    ap.add_argument("--eval", default=str(EVAL_PATH))
    ap.add_argument("--rows", action="store_true", help="print one line per scene")
    a = ap.parse_args(argv)
    if a.report:
        report = json.loads(Path(a.report).read_text(encoding="utf-8"))
    else:
        report = from_manifest(json.loads(Path(a.manifest).read_text(encoding="utf-8")), a.render)
    m = evaluate(report, load_eval(Path(a.eval)), a.render)
    print(summary(m))
    if a.rows:
        for r in m["rows"]:
            print(f"  {r['scene']} {'/'.join(r['types']):38s} {r['decision']:8s} {r['video_id']:16s} {r['verdict']:12s} {','.join(r['flags'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
