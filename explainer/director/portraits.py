"""Portraits of the people a narration names, for the Explainer's archive library (the folder `DirectorOptions.archive_dir` already reads: archive.json = [{"file", "subjects", "reason"}]).

The script is read for proper names of people (two or three capitalised words that do not end in a place or institution word: "Napoleon Bonaparte", "Vasco da Gama"). For each, Wikimedia Commons
(through the application's own Openverse backend, collection `wikimedia`, public-domain / CC licences only) is asked for the person; a result is kept ONLY when its title, tags or page address
name the person (every distinctive word of the name) and look like a portrait, painting or engraving, never a modern photograph. The picture is saved once under <work>/explainer/archive/ and listed
with the reason it was chosen; its credit goes in credits.txt beside it. Nothing is guessed: a person with no vetted picture simply has none, and the beat keeps its illustrated scene. Never raises; offline
or any failure returns None."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import compose_pictures as CP

PLACE_HEADS = frozenset("""sea ocean lagoon east west north south gulf strait bay island islands mountains mountain river lake city empire empires republic kingdom dynasty union states state canal desert
peninsula coast coastline valley plains territory province war wars battle treaty church cathedral palace arsenal""".split())
MAX_PEOPLE = 4
TIMEOUT_S = 25
OLD_ART = frozenset("portrait painting painted oil canvas engraving etching drawing sketch lithograph miniature bust statue fresco museum gallery".split())
MODERN = frozenset("selfie actor actress film movie poster logo stamp coin banknote statuette cosplay costume reenactment reenactor".split())
SUFFIX = "portrait painting"           # the words the picture check (pakmap/sourcing) and the planner use for a person's picture


FIRST_NOT_NAME = frozenset("eastern western northern southern middle central upper lower great new old north south east west holy grand".split())


def _is_place(word: str) -> bool:
    """True when the offline atlas knows the word as a sea, country or region (Mediterranean, Adriatic, Balkan)."""
    try:
        from hybrid import geo
        return str(geo.resolve(word).kind) in ("sea", "country", "region")
    except Exception:
        return False


def people(script: Optional[str], places: Sequence[str] = ()) -> List[str]:
    """Names of people in the script, first mention first, at most MAX_PEOPLE."""
    placew = {w.lower() for p in places for w in re.findall(r"[A-Za-z]+", p)}
    out: List[str] = []
    for ph in CP.cased_phrases(script):
        ws = re.findall(r"[A-Za-z]+", ph)
        if len(ws) < 2 or ws[-1].lower() in PLACE_HEADS or ws[0].lower() in PLACE_HEADS or ws[0].lower() in FIRST_NOT_NAME or any(w.lower() in placew for w in ws) or _is_place(ws[-1]) or ph in out:
            continue
        out.append(ph)
    return out[:MAX_PEOPLE]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _vet(name: str, cand: Any) -> Optional[str]:
    """Why this candidate may be used as `name`'s portrait (a reason), or None."""
    ex = getattr(cand, "extra", {}) or {}
    blob = " ".join([str(ex.get("alt", "")), str(ex.get("tags", "")), str(getattr(cand, "source_url", "")), str(getattr(cand, "url", ""))]).lower().replace("_", " ").replace("-", " ").replace("%20", " ")
    ws = set(re.findall(r"[a-z]+", blob))
    need = [w for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 2]
    if not need or any(w not in ws for w in need):
        return None
    if ws & MODERN:
        return None
    if not (ws & OLD_ART):
        return None
    if int(getattr(cand, "width", 0) or 0) < 500 or int(getattr(cand, "height", 0) or 0) < 500:
        return None
    return f"its title names {name} and it is a portrait, painting or engraving"


def build_library(script: Optional[str], places: Sequence[str], work_dir: "str | Path", log: Callable[[str], None] = lambda m: None) -> Optional[str]:
    """The folder with archive.json for the named people (cached: a picture already saved is kept), or None when there is nobody to show or nothing could be vetted."""
    try:
        names = people(script, places)
        if not names:
            return None
        import requests
        from providers.stock.openverse import OpenverseBackend, USER_AGENT
        d = Path(work_dir) / "explainer" / "archive"
        d.mkdir(parents=True, exist_ok=True)
        idx = d / "archive.json"
        have: Dict[str, Any] = {}
        if idx.is_file():
            try:
                have = {tuple(e["subjects"]): e for e in json.loads(idx.read_text(encoding="utf-8"))}
            except Exception:
                have = {}
        entries: List[Dict[str, Any]] = []
        credits: List[str] = []
        be = OpenverseBackend(source="wikimedia")
        offline = False
        for name in names:
            subj = [name.lower()] + [w for w in [name.split()[0].lower()] if len(w) >= 5 and name.split()[0].lower() not in ("the", "saint")]
            old = have.get(tuple(subj))
            if old and Path(old["file"]).is_file():
                entries.append(old)
                continue
            got = None
            if offline:
                break
            for q in (f"{name} portrait", name):
                try:
                    cands = be.search(q, media_type="image", per_page=12)
                except Exception as exc:
                    log(f"[Explainer] portraits: the search for {name} failed ({str(exc)[:80]}); no more searches this time")
                    offline = True
                    break
                for c in cands:
                    why = _vet(name, c)
                    if why:
                        got = (c, why)
                        break
                if got:
                    break
            if not got:
                log(f"[Explainer] portraits: no vetted picture of {name}; the beat keeps its illustrated scene")
                continue
            c, why = got
            try:
                r = requests.get(c.url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
                r.raise_for_status()
                from io import BytesIO
                from PIL import Image
                im = Image.open(BytesIO(r.content)).convert("RGB")
                im.thumbnail((1600, 1600))
                f = d / f"{_slug(name)}.jpg"
                im.save(f, quality=90)
            except Exception as exc:
                log(f"[Explainer] portraits: the picture of {name} could not be saved ({str(exc)[:80]})")
                continue
            entries.append({"file": str(f), "subjects": subj, "reason": f"portrait of {name}: {why}", "source": c.source_url, "author": c.author, "license": (c.extra or {}).get("license", "")})
            credits.append(f"{name}: {c.source_url} ({c.author or 'unknown author'}, {(c.extra or {}).get('license', '')})")
        if not entries:
            return None
        idx.write_text(json.dumps(entries, indent=1), encoding="utf-8")
        if credits:
            (d / "credits.txt").write_text("\n".join(credits) + "\n", encoding="utf-8")
        log(f"[Explainer] portraits: {len(entries)} vetted picture(s) of people in the narration")
        return str(d)
    except Exception as exc:
        log(f"[Explainer] portraits: skipped ({str(exc)[:100]})")
        return None
