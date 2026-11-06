"""Colour cards (docs/product_trailer/REVIEW_REFERENCE_4.md, gap 3): the references show a colour sentence as a row of tall colour cards, one per
colour in the order it is said; a later "online only violet" adds a tagged card, "we don't know the exact shades" drops a "?" on every card, and
"similar to the S26 Ultra sky blue" slides that older model's colour card over the matching one. cards_for() builds the layer for the director;
follow() reads the narrator's words inside the layer's window for the follow-ups (no Gemini). Drawn by whatif-engine/layers/pt_swatches.mjs.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

MAX_CARDS = 6
UNSURE = ("dont know", "do not know", "not sure", "no confirmation", "unconfirmed", "unknown", "exact shades", "exact shade", "yet to be confirmed")
EXCLUSIVE = ("online", "exclusive")
MODEL = re.compile(r"^(?:s\d{2}|iphone|pixel|note\d*)$")
MODEL_TAIL = {"ultra": "Ultra", "plus": "Plus", "pro": "Pro", "edge": "Edge", "fe": "FE", "max": "Max"}


def _colours() -> Dict[str, str]:
    from .director import COLOURS
    return COLOURS


def _short_model(text: str, phone: str) -> str:
    m = re.search(r"(?:Galaxy )?(S\d{2}(?: (?:Plus|Pro|Edge|Ultra|FE))?|iPhone \d+(?: (?:Pro Max|Pro|Plus|Air))?)", text)
    return m.group(1) if m else re.sub(r"^Galaxy\s+", "", phone or "").strip()


def cards_for(text: str, order: Sequence[str], phone: str) -> Dict[str, Any]:
    """The pt_swatches layer for a sentence naming `order` (colour keys of director.COLOURS, in spoken order)."""
    t, C = text.lower(), _colours()
    tag_from = min([t.index(w) for w in EXCLUSIVE if w in t] or [len(t) + 1])
    cards = []
    for c in list(order)[:MAX_CARDS]:
        card = {"name": c.title(), "color": C[c]}
        if t.find(c, tag_from) >= 0 and t.index(c) > tag_from:
            card["tag"] = "Online Exclusive"
        cards.append(card)
    model = _short_model(text, phone)
    return {"type": "pt_swatches", "title": f"{model} colour options".strip(), "cards": cards}


def _find_colour(toks: List[str], i: int) -> Optional[Tuple[str, int]]:
    """The colour key that starts at toks[i] (longest first) and how many words it takes."""
    for c in sorted(_colours(), key=len, reverse=True):
        p = c.split()
        if toks[i:i + len(p)] == p:
            return c, len(p)
    return None


def _model_before(toks: List[str], i: int) -> Optional[Tuple[str, str]]:
    """'s26 ultra' just before word i -> ('s26', 'Galaxy S26 Ultra')."""
    for j in range(i - 1, max(-1, i - 4), -1):
        if MODEL.match(toks[j]):
            base = toks[j]
            tail = [MODEL_TAIL[x] for x in toks[j + 1:i] if x in MODEL_TAIL]
            name = ("Galaxy " + base.upper() if base.startswith("s") else base.title()) + "".join(" " + x for x in tail)
            return base, name
    return None


def _match(cards: List[Dict[str, Any]], colour: str) -> Optional[Dict[str, Any]]:
    want = set(colour.split())
    best = [c for c in cards if c.get("name", "").lower() == colour] or [c for c in cards if want & set(c.get("name", "").lower().split())]
    return best[0] if best else None


def follow(layers: List[Dict[str, Any]], W: Sequence[Tuple[str, float, float]]) -> List[Dict[str, Any]]:
    """Follow-ups on every pt_swatches layer from the words said inside its window (in place)."""
    for L in layers:
        if not isinstance(L, dict) or L.get("type") != "pt_swatches":
            continue
        a, b = float(L.get("start", 0.0)), float(L.get("end", 0.0))
        seq = [(w, s) for w, s, _ in W if a - 0.05 <= s <= b]
        toks = [w for w, _ in seq]
        own = (re.search(r"\b(s\d{2}|iphone|pixel)\b", str(L.get("title", "")).lower()) or [None, None])[1]
        cards = L.setdefault("cards", [])
        joined = " ".join(toks)
        if "q_at" not in L:
            for ph in UNSURE:
                m = re.search(r"(?:^| )" + re.escape(ph) + r"(?: |$)", joined)
                if m:
                    L["q_at"] = round(seq[joined[:m.start() + (1 if m.start() else 0)].count(" ")][1] - a, 2)
                    break
        i, last_model = 0, None                  # (model, word index): "...the S26 Ultra sky blue, or the pink gold" -> both are S26 colours
        while i < len(toks):
            hit = _find_colour(toks, i)
            if not hit:
                i += 1
                continue
            c, n = hit
            at = round(max(0.0, seq[i][1] - a), 2)
            nxt = _find_colour(toks, i + n) if i + n < len(toks) else None
            extra = toks[i + n:i + n + nxt[1]] if nxt else []          # "pink gold": one colour name of two colour words
            model = _model_before(toks, i)
            if model:
                last_model = (model, i)
            elif extra and last_model and i - last_model[1] <= 15:
                model = last_model[0]
            if model and model[0] != own:
                card = _match(cards, c)
                if card is not None and "ref" not in card:
                    card["ref"] = {"label": model[1], "name": " ".join(toks[i:i + n] + extra).title(), "color": _colours()[c], "at": at}
                i += n + len(extra)
                continue
            if _match(cards, c) is None and len(cards) < MAX_CARDS:
                before = toks[max(0, i - 4):i]
                card = {"name": c.title(), "color": _colours()[c], "at": at}
                if any(w in before for w in EXCLUSIVE):
                    card["tag"] = "Online Exclusive"
                cards.append(card)
            i += n + len(extra)
    return layers
