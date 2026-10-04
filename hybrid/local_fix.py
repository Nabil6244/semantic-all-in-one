"""Repairs that code can make perfectly, so no AI is asked: a caption that is too long, a chip that appears too late to be read, a stat
format that writes the number itself, a wide camera frame outside the opening, and text layers piling up. Each returns whether it changed
anything; the caller validates again afterwards. Nothing here changes a beat's mode, times, words or pictures."""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from .plan import HybridPlan
from .validate import MAX_CAPTION_CHARS, MIN_READABLE_S, Finding


def _beat(plan: HybridPlan, bid: str):
    return next((b for b in plan.beats if b.id == bid), None)


def _shorten(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-—")
    return cut if len(cut) >= limit // 2 else text[:limit].rstrip()


def fix(plan: HybridPlan, findings: Sequence[Finding]) -> Tuple[int, List[str]]:
    """Apply every deterministic repair the findings call for. Returns (how many fixes, what was done)."""
    from .compile import layer_end

    done: List[str] = []
    recamera = False
    for f in findings:
        b = _beat(plan, f.beat) if f.beat else None
        if b is None:
            continue
        if f.code == "text_too_long":
            for l in b.layers:
                if l.type == "caption" and len((l.text or "").strip()) > MAX_CAPTION_CHARS:
                    l.text = _shorten(l.text, MAX_CAPTION_CHARS)
                    done.append(f"{b.id}: shortened a caption to fit the screen")
        elif f.code == "stat_format":
            for l in b.layers:
                if l.type != "stat" or l.value_to is None:
                    continue
                m = re.match(r"^\s*(\d[\d,]*(?:\.\d+)?)\s*(.*)$", l.format or "")
                if m and abs(float(m.group(1).replace(",", "")) - l.value_to) <= max(1.0, abs(l.value_to) * 0.01):
                    l.format = ("#,##0 " if float(l.value_to).is_integer() else "0.0 ") + m.group(2).strip()
                    l.format = l.format.strip()
                    done.append(f"{b.id}: wrote the number format as a pattern")
        elif f.code == "layer_late":
            for l in b.layers:
                if l.type in ("stat", "caption", "hud_title"):
                    end = layer_end(plan, b, l)
                    if end - l.t < MIN_READABLE_S and end - (MIN_READABLE_S + 0.2) >= b.start:
                        l.t = round(end - (MIN_READABLE_S + 0.2), 2)
                        done.append(f"{b.id}: moved a {l.type} earlier so it can be read")
        elif f.code == "wide_view":
            if b.cam_frame in ("globe", "continental"):
                b.cam_frame = "region"
                recamera = True
                done.append(f"{b.id}: closed a wide camera view to region")
        elif f.code == "overlay_conflict" and "text layers" in f.message:
            # too much text at once: let the oldest layer that was being carried forward leave with its own beat
            carried = sorted((l.t, bb, l) for bb in plan.beats for l in bb.layers if l.until in ("after_footage", "end") and l.hold is None and l.t < b.start)
            if carried:
                _, bb, l = carried[0]
                l.until = "beat_end"
                done.append(f"{bb.id}: a carried-over {l.type} now leaves with its own beat")
    if recamera:
        from .director import derive_cameras

        derive_cameras(plan)
    return len(done), done
