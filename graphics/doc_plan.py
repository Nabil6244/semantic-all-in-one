"""Doc Style for normal videos: the News Doc looks a normal plan never asks for, placed from the narration itself.

    plan_doc_extras(aligned_rows, display_timeline, existing_specs, still_for_scene, channel="") -> [GraphicSpec]

The ordinary planner already gives names, places, numbers, titles, quotes and charts (drawn in the News Doc look by
graphics/doc_style.py). This adds the rest, each only where the narration says something it fits:

  checklist   a list of 4-6 short items ("A, B, C and D")                 paper card on the right
  rings       a list of exactly three one- or two-word items              three circles on black
  forecast    three or more day/month values ("Monday 14 ... Tuesday 18") navy day cards
  polaroids   "X versus Y" / "between X and Y"                            two pinned photos (this scene's and the next one's)
  panel       a long sentence with "because"                              navy side panel with the reason
  quote       a strong line (never, most, first, only, worst ...)         boxed words over the footage
  quote_card  the same, every other time                                  on solid black
  framed      "in <Place>"                                                the scene's own still in a frame, the place under it
  dossier     once, near the start: the subject named most often          case file with the facts found (year, place)
  glitch      a transition at a scene cut about every 75 s
  watermark   the channel name for the whole video (when one is set)

No overlap: one graphic at a time. An extra is placed only where no other graphic is on screen (with a gap), at most one
every 7 s, a full-screen one at most every 25 s and a quote at most every 30 s. Smart Text drops its own text wherever a graphic is on screen
(graphics/conflicts.py), so the two switches never draw on top of each other."""

from __future__ import annotations

import re
from typing import Any, Callable, List, Optional, Sequence, Tuple

from .schema import GraphicSpec, TextOverlaySpec

GAP_S = 7.0            # between any two extras
FULL_GAP_S = 25.0      # between two full-screen extras (about 16 % of the screen time at most, as in News Doc)
QUOTE_GAP_S = 30.0     # strong lines are common: a quote at most this often, so the other looks get their turn
PAD_S = 0.6            # clear space around every other graphic
GLITCH_EVERY_S = 75.0
FULL_SCREEN = {"checklist", "rings", "forecast", "polaroids", "quote_card", "framed", "dossier"}
LENGTH = {"checklist": 5.5, "rings": 4.2, "forecast": 5.0, "polaroids": 5.0, "panel": 6.0, "quote": 4.4, "quote_card": 4.4,
          "framed": 4.6, "dossier": 4.6}
ROLE = {"quote": "QUOTE", "quote_card": "QUOTE"}   # everything else: CALLOUT (both win over Smart Text)

_STRONG = re.compile(r"\b(never|ever|most|least|first|last|only|worst|best|biggest|largest|deadliest|costliest|"
                     r"oldest|fastest|highest|lowest|record|nobody|no one|everything|forever)\b", re.I)
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march",
         "april", "may", "june", "july", "august", "september", "october", "november", "december")
_STOP = {"The", "A", "An", "This", "That", "These", "Those", "It", "In", "On", "At", "But", "And", "Or", "So", "Then",
         "When", "What", "Why", "How", "We", "You", "They", "He", "She", "I", "If", "For", "As", "By", "Of", "To", "Its",
         "There", "Here", "Now", "Today", "One", "Two", "Three", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
         "Saturday", "Sunday"}


def _sentences(text: str) -> List[Tuple[str, float]]:
    """(sentence, where it starts in the text as a 0..1 share)."""
    text = " ".join(str(text or "").split())
    out, pos = [], 0
    for m in re.finditer(r"[^.!?]+[.!?]*", text):
        s = m.group(0).strip()
        if len(s.split()) >= 3:
            out.append((s, m.start() / max(1, len(text))))
        pos = m.end()
    return out


def _list_items(s: str) -> List[str]:
    """'A, B, C and D' -> the items (each at most four words), else []. Words before the first item (the sentence's own
    verb, as in 'Crews checked Sanibel, ...') are not part of it: the first item is cut to the length of the others."""
    m = re.search(r"((?:[\w'’-]+(?: [\w'’-]+){0,3}, ){2,5}(?:and |or )?[\w'’-]+(?: [\w'’-]+){0,3}?(?: (?:and|or) [\w'’-]+(?: [\w'’-]+){0,3})?)"
                  r"(?=[.!?;:]|$)", s)
    if not m:
        return []
    parts = [p.strip() for p in re.split(r",\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+", m.group(1)) if p.strip()]
    for k, p in enumerate(parts):   # "..., cold, but he kept going": the list ends where a new clause starts
        if k and re.match(r"(but|so|yet|then|which|who|while|because)\b", p, re.I):
            parts = parts[:k]
            break
    if len(parts) >= 3:
        first = parts[0].split()
        if sum(p[:1].isupper() for p in parts[1:]) >= len(parts[1:]) - 1:   # a list of names: the first name's own words
            k = len(first) - 1
            while k > 0 and first[k - 1][:1].isupper():
                k -= 1
            first = first[k:] if first[-1][:1].isupper() else first
        else:
            first = first[-max(len(p.split()) for p in parts[1:-1] or parts[1:]):]
        parts[0] = " ".join(first)
    return parts if 3 <= len(parts) <= 6 and all(len(p.split()) <= 4 for p in parts) else []


def _proper_nouns(s: str) -> List[str]:
    found = []
    for m in re.finditer(r"\b([A-Z][a-z’']+(?: (?:of |the )?[A-Z][a-z’']+){0,3})\b", s):
        name = m.group(1)
        if name.split()[0] in _STOP and len(name.split()) == 1:
            continue
        found.append(re.sub(r"^(The|A|An) ", "", name))
    return found


def _title_before(s: str, items: List[str]) -> str:
    head = s[: s.find(items[0])].strip(" ,:;-") if items and items[0] in s else ""
    words = head.split()[-4:]
    return " ".join(words).upper() if 1 <= len(words) <= 4 else "KEY POINTS"


def _detect(s: str, nxt_still: bool) -> Optional[Tuple[str, dict]]:
    items = _list_items(s)
    if len(items) == 3 and all(len(i.split()) <= 2 for i in items):
        return "rings", {"items": [i.upper() for i in items]}
    if len(items) >= 4:
        return "checklist", {"title": _title_before(s, items), "items": [i[:1].upper() + i[1:] for i in items]}
    pairs = re.findall(r"\b(" + "|".join(_DAYS) + r")\b[^0-9]{0,24}?(\d[\d,.]*)", s, re.I)
    if len(pairs) >= 3:
        unit = re.search(r"\d[\d,.]*\s*(feet|ft|inches|in|mph|degrees|percent|%|meters|m|km|miles)\b", s, re.I)
        return "forecast", {"title": " ".join(s.split()[:4]).upper().strip(",."), "days": [p[0][:3].upper() for p in pairs][:5],
                            "values": [p[1] for p in pairs][:5], "unit": unit.group(1).upper() if unit else ""}
    vs = re.search(r"\b([A-Z]?[\w’']+(?: [\w’']+)?)\s+(?:versus|vs\.?|compared to)\s+([\w’']+(?: [\w’']+)?)", s, re.I) or \
        re.search(r"\bbetween\s+([\w’']+(?: [\w’']+)?)\s+and\s+([\w’']+(?: [\w’']+)?)", s, re.I)
    if vs and nxt_still:
        a, b = vs.group(1).upper(), vs.group(2).upper()
        return "polaroids", {"title": f"{a} VS {b}", "labels": [a, b]}
    if re.search(r"\bbecause\b", s, re.I) and len(s.split()) >= 10:
        head, _, why = re.split(r"\b(because)\b", s, maxsplit=1, flags=re.I)
        title = " ".join(head.split()[:6]).strip(" ,") if len(head.split()) <= 8 else "WHY IT MATTERS"
        return "panel", {"title": title, "bullets": [("Because " + why.strip()).rstrip(".") + "."]}
    if _STRONG.search(s) and 6 <= len(s.split()) <= 18:
        words = s.rstrip(".!?").split()
        return "quote", {"text": s, "red": " ".join(words[-3:])}
    place = re.search(r"\b(?:in|at|near|across)\s+((?:the )?[A-Z][a-z’']+(?: [A-Z][a-z’']+){0,2})", s)
    if place and place.group(1).split()[-1] not in _STOP:
        return "framed", {"caption": re.sub(r"^the ", "", place.group(1)).upper()}
    return None


def _free(t0: float, t1: float, taken: Sequence[Tuple[float, float]], pad: float = PAD_S) -> bool:
    return all(t1 + pad <= a or t0 - pad >= b for a, b in taken)


def _spec(n: int, look: str, t0: float, t1: float, params: dict, scene: str, text: str) -> GraphicSpec:
    role = ROLE.get(look, "CALLOUT")
    # the channel name sits in a corner for the whole video: it must not count as text on screen (Smart Text stays)
    decision = "WATERMARK" if look == "watermark" else "TEXT"
    role = "UI_ELEMENT" if look == "watermark" else role
    return GraphicSpec(graphic_id=f"doc_{look}_{n:03d}", decision=decision, role=role, scene_number=scene,
                       start=round(t0, 3), end=round(t1, 3), track="GRAPHICS", reason="Doc Style",
                       text=TextOverlaySpec(role=role, text=text[:120], start=t0, end=t1),
                       payload={"doc_look": look, "doc_params": params}, animation="FADE")


def plan_doc_extras(aligned_rows: Sequence[dict], display_timeline: Sequence[Tuple[float, float]], existing: Sequence[Any],
                    still_for_scene: Callable[[int], Optional[str]], channel: str = "") -> List[GraphicSpec]:
    rows = list(aligned_rows or [])
    if not rows or len(display_timeline) != len(rows):
        return []
    duration = float(display_timeline[-1][1])
    taken: List[Tuple[float, float]] = [(float(s.start), float(s.end)) for s in existing or []]
    out: List[GraphicSpec] = []
    last_any, last_full, last_quote, quotes = -1e9, -1e9, -1e9, 0

    def place(look: str, t0: float, params: dict, scene_i: int, text: str, cap: float) -> bool:
        nonlocal last_any, last_full, last_quote, quotes
        t1 = min(t0 + LENGTH.get(look, 4.0), cap, duration - 0.3)
        if t1 - t0 < 2.4 or t0 - last_any < GAP_S or not _free(t0, t1, taken):
            return False
        if look == "quote" and t0 - last_quote < QUOTE_GAP_S:
            return False
        if look == "quote" and quotes % 2 == 1 and t0 - last_full >= FULL_GAP_S:
            look = "quote_card"   # every other strong line on solid black (boxed over the footage when one was just shown)
        if look in FULL_SCREEN and t0 - last_full < FULL_GAP_S:
            return False
        if look in ("quote", "quote_card"):
            quotes += 1
            last_quote = t0
        out.append(_spec(len(out), look, t0, t1, params, str(rows[scene_i].get("scene_number") or scene_i + 1), text))
        taken.append((t0, t1))
        last_any = t0
        if look in FULL_SCREEN:
            last_full = t0
        return True

    # the case file, once near the start: the subject named most often
    names: dict = {}
    for r in rows:
        for nme in _proper_nouns(str(r.get("script_segment") or "")):
            names[nme] = names.get(nme, 0) + 1
    subject = max(names, key=lambda k: (names[k], len(k)), default="") if names else ""
    if subject and names[subject] >= 2:
        text_all = " ".join(str(r.get("script_segment") or "") for r in rows)
        fields = []
        year = re.search(r"\b(1[0-9]\d\d|20\d\d)\b", text_all)
        if year:
            fields.append(("DATE", year.group(1)))
        where = next((n for n in names if n != subject and re.search(r"\b(?:in|at)\s+(?:the )?" + re.escape(n), text_all)), "")
        if where:
            fields.append(("PLACE", where))
        fields.append(("SUBJECT", subject))
        for i, (a, b) in enumerate(display_timeline):
            if a > 25:
                break
            if b - a >= 3.0 and place("dossier", a + 0.4, {"title": subject.upper(), "fields": fields}, i, subject, b):
                break

    for i, r in enumerate(rows):
        a, b = float(display_timeline[i][0]), float(display_timeline[i][1])
        for s, share in _sentences(str(r.get("script_segment") or "")):
            nxt_still = i + 1 < len(rows) and bool(still_for_scene(i + 1)) and bool(still_for_scene(i))
            hit = _detect(s, nxt_still)
            if hit is None:
                continue
            look, params = hit
            if look in ("polaroids", "framed"):
                stills = [still_for_scene(i)] + ([still_for_scene(i + 1)] if look == "polaroids" else [])
                if not all(stills):
                    continue
                params = dict(params, stills=stills)
            t0 = a + (b - a) * share + 0.2
            if place(look, t0, params, i, s, b + (2.0 if look in FULL_SCREEN else 0.0)):
                break   # one extra per scene at most

    # glitch transitions at cuts, about every GLITCH_EVERY_S
    last_glitch = 0.0
    for i in range(1, len(rows)):
        cut = float(display_timeline[i][0])
        if cut - last_glitch >= GLITCH_EVERY_S and _free(cut - 0.15, cut + 0.3, taken, 0.2):
            out.append(_spec(len(out), "glitch", cut - 0.12, cut + 0.3, {"seed": i}, str(rows[i].get("scene_number") or i + 1), ""))
            taken.append((cut - 0.12, cut + 0.3))
            last_glitch = cut

    if channel.strip():
        out.append(_spec(len(out), "watermark", 0.0, duration, {"text": channel.strip()}, "", ""))
    return out
