"""Scene variety (opt-in, DirectorOptions.variety; phase E of the upgrade plan, re-scoped).

1. NO FAMILY THREE TIMES IN A ROW. The picture-layout family of a board beat is the set of element styles its phrases use (for example line+tile, circle+line, line+scroll). When the two beats before this
   one had the same family as the one just authored, the beat is authored once more with the mirror variant (`variant + 1`, the same parameter the director already uses to alternate sides and picture
   shapes); the new authoring is kept only when its family differs. Nothing is invented: it is the same sentences, words, pictures and rules.
2. DOSSIER BACKDROP. A beat whose own narration says secret, classified, confidential, spy, conspiracy, intelligence, cipher or dossier is drawn on the lamp-lit "dossier" paper instead of the plan's
   background: at most one beat in three, never the first board beat. It is a per-clip look (the clip name includes it); no cue, text or timing changes.
Not built from the plan's phase E list: dialogue bubbles (a board beat has no speaker figure to hang a bubble on) and split/sort/seesaw layouts (separate, larger work)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .segment import norm

DARK = frozenset("secret secrets secretly classified confidential spy spies conspiracy conspirators intelligence cipher ciphers encrypted dossier espionage".split())
MAX_SAME_FAMILY = 2
DOSSIER_EVERY = 3                      # at most one dossier beat in any three board beats


def signature(br) -> Tuple[str, ...]:
    return tuple(sorted({p["as"] for p in br.phrases}))


def variety_pass(br, b, k: int, words, cased, opt, table, roles, narrator_mode: str, carry: str, sig_hist: List[Tuple[str, ...]], dossier_hist: List[bool]):
    """Returns (board result to use, background for this clip, record)."""
    rec: Dict[str, Any] = {}
    sig = signature(br)
    if sig and len(sig_hist) >= MAX_SAME_FAMILY and all(h == sig for h in sig_hist[-MAX_SAME_FAMILY:]):
        from .compose_ref import author_ref
        alt = author_ref(b.id, b.start, b.end, b.sents, words, cased, opt, table, roles, narrator_mode, carry, variant=k + 1)
        sig2 = signature(alt)
        if sig2 != sig:
            rec["family"] = {"was": list(sig), "now": list(sig2), "why": f"the two beats before had the same family {list(sig)}"}
            br, sig = alt, sig2
        else:
            rec["family_kept"] = f"the same family {list(sig)} a third time: the mirror authoring gives the same family"
    sig_hist.append(sig)
    bg = opt.background
    said = [norm(w[0]) for w in words if b.start - 1e-6 <= w[1] < b.end - 1e-6]
    hit = next((t for t in said if t in DARK), None)
    use = hit is not None and bool(dossier_hist) and not any(dossier_hist[-(DOSSIER_EVERY - 1):])
    if hit is not None and not use:
        rec["dossier_skipped"] = f"{hit!r} is spoken, but " + ("it is the first board beat" if not dossier_hist else "a dossier beat was among the last two")
    dossier_hist.append(use)
    if use:
        from ..board import backdrops
        bg = backdrops.DOSSIER
        rec["dossier"] = hit
    rec["signature"] = list(sig)
    return br, bg, rec
