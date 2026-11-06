"""The page's back end (no UI): one entry point per film type, the AI scene steps, and a saved record of what was made.

    plan_film(...)      -> {"spec_path", "summary", "pack", "notes"}   Trailer, Reveal (with or without AI scenes) or Review
    ensure_references() -> the five reference pictures of the phone (rendered once, reused)
    make_scenes()       -> generate the pack's AI pictures in Flow (images only; clips are counted, never generated here)
    load_results()      -> what make_scenes() saved, so a later Generate uses the pictures

Nothing here starts on its own; the page calls these from its buttons, off the UI thread.
"""

from __future__ import annotations

import re

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

FILM_TYPES = ("Trailer", "Reveal", "Review", "UI Film")
RESULTS_FILE = "scene_results.json"


def scene_dir(out_dir) -> Path:
    return Path(out_dir) / "scene_pack"


def refs_dir(out_dir) -> Path:
    return scene_dir(out_dir) / "refs"


def _colours(phone: str, colour: str = "") -> List[str]:
    from .references import preset_colours

    return preset_colours(phone)


def vo_sentences(words: Sequence[Any]) -> List[str]:
    from .voiceover import sentences

    return sentences(words)


def bar_phones(spec: Dict[str, Any], phone: str) -> None:
    """Flat phones of the film's own model family get its camera-bar back when the phone's preset has one (Galaxy S27 Ultra): "Galaxy S27 Pro",
    "Galaxy S27 Ultra", an unlabelled phone; "Galaxy S26 Ultra" or "iPhone 18 Pro" keep their lens column."""
    import re

    from .references import _catalog, _norm

    key = _norm(phone)
    p = next((p for p in _catalog() if key and key in {_norm(p.get("id", "")), _norm(p.get("name", ""))} | {_norm(a) for a in p.get("aliases", [])}), None)
    if not p or not str((p.get("camera") or {}).get("layout", "")).startswith("galaxy_s27"):
        return
    fam = re.search(r"\b(S\d{2})\b", phone, re.I)
    for L in spec["layers"]:
        if L.get("type") != "pt_flatphones":
            continue
        for ph in L.get("phones", []):
            label = str(ph.get("label") or "")
            other = re.search(r"\b(S\d{2}|iPhone|Pixel)\b", label, re.I)
            if (fam and re.search(r"\b" + fam.group(1) + r"\b", label, re.I)) or (not other and label.lower() not in ("before", "earlier leak", "list price")):
                ph.setdefault("design", "bar")


MODEL_RE = re.compile(r"\b(iphone\s*\d+(?:\s*(?:pro\s*max|pro|plus|air|e))?|pixel\s*\d+(?:\s*(?:pro\s*xl|pro|a))?|(?:galaxy\s*)?s\d{2}(?:\s*(?:ultra|plus|\+|fe|edge|pro))?)\b", re.I)


def consistent_phones(spec: Dict[str, Any]) -> None:
    """The same phone looks the same on every flat card of a film: one colour, one lens count and one camera layout per model name (the first card's,
    corrected by the model: an Ultra has four lenses in its column, an iPhone Pro three and a plain iPhone two in the square module, a Pixel three
    in its visor). Labels that are not a model ("Earlier leak", "Before") are left as written."""
    seen: Dict[str, Dict[str, Any]] = {}
    for L in spec.get("layers", []):
        if L.get("type") != "pt_flatphones":
            continue
        for ph in L.get("phones", []):
            m = MODEL_RE.search(str(ph.get("label") or ""))
            if not m:
                continue
            key = re.sub(r"\s+|galaxy", "", m.group(1).lower())
            if key not in seen:
                look: Dict[str, Any] = {"color": ph.get("color")}
                if ph.get("design") == "bar":
                    look["design"] = "bar"
                elif key.startswith("iphone"):
                    look.update({"design": "iphone", "cams": 3 if "pro" in key else 2})
                elif key.startswith("pixel"):
                    look.update({"design": "pixel", "cams": 3 if "pro" in key else 2})
                elif "ultra" in key:
                    look["cams"] = 4
                else:
                    look["cams"] = ph.get("cams") or 3
                if look.get("design") == "bar":
                    look["cams"] = ph.get("cams") or 3
                seen[key] = look
            ph.update({k: v for k, v in seen[key].items() if v is not None})


def preset_colour(phone: str, colour: str) -> str:
    """The phone preset's colour name for a chosen colour: an exact name, else the preset colour named by its last word ("Titanium Black" -> "Black"); '' when none."""
    if not colour:
        return ""
    from .references import _catalog, _norm

    key = _norm(phone)
    names = next(([c.get("name") for c in p.get("colors", []) if c.get("name")] for p in _catalog()
                  if key and key in {_norm(p.get("id", "")), _norm(p.get("name", ""))} | {_norm(a) for a in p.get("aliases", [])}), [])
    low = {n.lower(): n for n in names}
    if colour.lower() in low:
        return low[colour.lower()]
    for w in reversed(colour.lower().split()):
        if w in low:
            return low[w]
    return ""


def load_results(out_dir) -> Dict[Any, Any]:
    """{scene n (int): {"status", "path"?}} saved by make_scenes(); {} when nothing was made yet."""
    f = scene_dir(out_dir) / RESULTS_FILE
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[Any, Any] = {}
    for k, v in raw.items():
        if isinstance(v, dict) and (v.get("status") != "done" or Path(str(v.get("path", ""))).is_file()):
            out[int(k) if str(k).isdigit() else k] = v
    return out


def save_results(out_dir, results: Dict[Any, Any]) -> Path:
    d = scene_dir(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    f = d / RESULTS_FILE
    f.write_text(json.dumps({str(k): v for k, v in results.items()}, indent=1), encoding="utf-8")
    return f


def _read_features(csv_path: str, phone: str, colour: str, disclaimer: Optional[str], disclaimer_on: bool) -> Dict[str, Any]:
    from .csv_io import read_csv

    data = read_csv(csv_path)
    prod = data.setdefault("product", {})
    if phone:
        prod["phone"] = phone
        prod.setdefault("name", phone)
    if colour:
        prod["colour"] = colour
    if disclaimer:
        prod["disclaimer"] = disclaimer
    if not disclaimer_on:
        prod["disclaimer"] = ""
    return data


def plan_pack(film_type: str, *, csv: Optional[str] = None, script: Optional[str] = None, phone: str = "", colour: str = "", disclaimer: Optional[str] = None,
              disclaimer_on: bool = True, max_clips: int = 3):
    """The AI scene pack for a film (Reveal from the CSV, Review from the script) and its parsed source; (pack, data_or_parsed)."""
    from . import review, scenepack

    cols = _colours(phone, colour)
    if film_type == "Review":
        parsed = review.parse_script(review.review_source(script, csv))
        return review.plan_review_scenes(parsed, phone or "phone", cols), parsed
    data = _read_features(csv or "", phone, colour, disclaimer, disclaimer_on)
    p = phone or data["product"].get("phone") or data["product"].get("name") or "phone"
    return scenepack.plan_scene_pack(data["features"], p, _colours(p, colour), max_clips=max_clips), data


def plan_film(film_type: str, *, out_dir, csv: Optional[str] = None, script: Optional[str] = None, phone: str = "", colour: str = "", music: Optional[str] = None,
              disclaimer: Optional[str] = None, disclaimer_on: bool = True, width: int = 1920, height: int = 1080, fps: int = 30, use_ai: bool = False,
              max_clips: int = 3, voiceover: Optional[str] = None, words: Optional[Sequence[Any]] = None, voice_seconds: Optional[float] = None, style: str = "mixed", llm_run: Optional[Callable[[str, str], str]] = None,
              stock_settings: Optional[Dict[str, Any]] = None, log: Callable[[str], None] = print, footage_chosen: Optional[Dict[int, Dict[str, str]]] = None,
              subtitles: Optional[bool] = None, news_backend: Any = None, news_footage: bool = True) -> Dict[str, Any]:
    """Write the film's spec and return {"spec_path", "summary", "pack", "notes"}. use_ai uses the pictures make_scenes() saved (a missing one is 3D).
    Review looks: "mixed" (3D + cards), "infographic" (one paper look), "news" (real footage first: YouTube runs of the phone, then stock, cards only
    for figures, documents and quotes). subtitles: None = the look's default (off for news, as the reference channels have none; on elsewhere, as before)."""
    from . import mixed, review, scenepack
    from .planner import build_spec

    if film_type not in FILM_TYPES:
        raise ValueError(f"unknown film type {film_type!r}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pack, notes, summary = None, [], ""
    footage_items: List[Dict[str, Any]] = []      # the stock clips, listed for the Visuals tab
    media = out / "media"
    if film_type == "Review":
        facts = None                                 # a feature CSV in a review: its rows are facts to show on the sentences that say them
        if csv and Path(csv).is_file() and review.is_feature_csv(Path(csv).read_text(encoding="utf-8-sig", errors="replace")):
            facts = _read_features(csv, phone, colour, disclaimer, disclaimer_on)
            phone = phone or facts["product"].get("name", "")
            colour = colour or facts["product"].get("colour", "")
            if disclaimer_on and not disclaimer:
                disclaimer = facts["product"].get("disclaimer") or ""
        script = review.review_source(script, csv)
        if not script.strip() and words:             # no script given: the narrator's own words are the script, so every line matches the voice
            script = "\n".join(review._clean(x) for x in vo_sentences(words))
            log(f"Script taken from the voice-over: {len(script.splitlines())} sentences.")
        if not script.strip():
            raise ValueError("A feature CSV holds the facts, not the narration: add the voice-over (or paste the script) too." if facts else
                             "Paste the review script, or choose a review CSV, first.")
        if csv:                                      # a supplied CSV run makes no AI calls: the built-in director and the CSV's own facts plan it
            llm_run = None
        if style not in review.STYLES:
            raise ValueError(f"unknown review style {style!r}")
        pack, parsed = plan_pack("Review", script=script, phone=phone, colour=colour)

        def put_features(parsed):
            """The CSV rows go in after the director: a row on the sentence that says it (in front of that sentence's own scene), a filler row only on
            a sentence still left without a picture."""
            if not (facts and facts.get("features")):
                return parsed
            parsed = review.place_features(parsed, facts["features"])
            n_feat = sum(1 for c in parsed["chapters"] for i in c["items"] if i["kind"] == "feature")
            log(f"Feature CSV: {n_feat} of {len(facts['features'])} rows placed on the sentences that say them.")
            return parsed

        look = style
        if style not in ("mixed", "infographic", "news"):
            parsed = put_features(parsed)
        if style in ("infographic", "news"):
            use_ai = False      # flat paper shots and real footage need no AI picture
        if style in ("mixed", "infographic", "news"):    # the auto director picks a fitting visual for each plain line
            from . import director

            from . import footage, llm_director

            from . import balance

            for ch in parsed["chapters"]:
                for it in ch["items"]:
                    if it["kind"] != "line":
                        it["_own"] = True                      # a directive the author wrote is never swapped by the variety pass
            new = llm_director.llm_direct(parsed, phone, llm_run, log) if llm_run else None
            parsed = new or director.auto_direct(parsed, phone)          # the AI's scenes, or the built-in rules when it is not available
            if look == "mixed":
                parsed = balance.balance(parsed, phone, footage=bool(stock_settings))        # keep every reference look in rotation
            parsed = put_features(parsed)
            if look == "news":                        # footage first: YouTube runs of this phone by subject, then stock for what is left
                from . import news_footage as NF

                parsed = review.news_beats(parsed)
                if news_footage:
                    got = NF.resolve(parsed, out, phone, backend=news_backend, log=log)
                    for n in got["notes"]:
                        log(n)
                for ch in parsed["chapters"]:
                    for it in ch["items"]:
                        if it.get("kind") == "footage" and not it.get("query"):
                            it["query"] = NF.TOPIC_QUERY.get(it.get("topic"), "smartphone hands on").format(p="smartphone", old="smartphone")
            if stock_settings and look != "infographic":
                got = footage.resolve_footage(parsed, out, stock_settings, log, chosen=footage_chosen, items=footage_items)
                log(f"Stock footage: {got['found']} clip(s) found, {got['missing']} not found")
            style = "follow" if look == "mixed" else look
        results = load_results(out) if use_ai else {}
        prod = {"name": phone, "phone": phone, "disclaimer": (disclaimer or "") if disclaimer_on else ""}
        if facts:                                    # the lock-screen time and date the CSV gives (#product,...,09:41,Tue 03 Nov)
            prod.update({k: facts["product"][k] for k in ("time", "date") if facts["product"].get(k)})
        if voiceover and Path(voiceover).is_file():   # timed to the narrator: every line owns its stretch of the film
            from . import voiceover as vo

            ws = list(words or [])
            dur = float(voice_seconds or 0.0) or vo.audio_seconds(voiceover) or (float(ws[-1][2]) if ws else 0.0)
            if dur <= 0:
                raise ValueError("The voice-over's length could not be read.")
            lines = [i["text"] for c in parsed["chapters"] for i in c["items"] if i["kind"] == "line"]
            spec = review.plan_review_timed(parsed, pack, results, vo.align_lines(lines, ws, dur), ws, media_dir=media, width=width, height=height, fps=fps, product=prod, style=style)
        else:
            spec = review.plan_review(parsed, pack, results, media_dir=media, width=width, height=height, fps=fps, product=prod, style=style)
        notes = spec.get("whatif", {}).get("notes", [])
        if subtitles is False or (subtitles is None and look == "news"):
            spec["layers"] = [L for L in spec["layers"] if L["type"] != "pt_subtitle"]
        bar_phones(spec, phone)
        consistent_phones(spec)
        from . import variety3d                      # new 3D every time: no move repeated back to back, each shot its own camera, a seed per film

        vo_id = ""
        if voiceover and Path(voiceover).is_file():
            st = Path(voiceover).stat()
            vo_id = f"{Path(voiceover).name}:{st.st_size}:{int(st.st_mtime)}"
        variety3d.vary_shots(spec, variety3d.film_seed(vo_id, script, phone))
        pick = preset_colour(phone, colour)
        if pick:                                     # the chosen finish on every single-phone shot (a lineup keeps the preset's range)
            for s in spec["shots"]:
                if s.get("kind") == "product" and s.get("object") == "phone":
                    s.setdefault("color", pick)
    elif use_ai and film_type != "UI Film":   # a UI film is all code-built interface: no AI scenes
        if not csv or not Path(csv).is_file():
            raise ValueError("Choose the feature CSV first.")
        pack, data = plan_pack(film_type, csv=csv, phone=phone, colour=colour, disclaimer=disclaimer, disclaimer_on=disclaimer_on, max_clips=max_clips)
        spec = mixed.plan_mixed(data, pack, load_results(out), media_dir=media, width=width, height=height, fps=fps)
        notes = spec.get("whatif", {}).get("notes", [])
    else:
        if not csv or not Path(csv).is_file():
            raise ValueError("Choose the feature CSV first.")
        if film_type == "UI Film" and voiceover and Path(voiceover).is_file() and words:   # timed to the narrator: each feature's block starts when it is said
            from . import voiceover as vo
            from .uifilm import plan_ui_timed

            data = _read_features(csv, phone, colour, disclaimer, disclaimer_on)
            spec = plan_ui_timed(data, list(words), float(voice_seconds or 0.0) or vo.audio_seconds(voiceover), width=width, height=height, fps=fps)
            if music:
                spec["product_trailer"]["music"] = music
            spec["product_trailer"]["voiceover"] = str(voiceover)
            path = out / "product_trailer_spec.json"
            path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
            return {"spec_path": str(path), "summary": f"{film_type}: {len(spec['shots'])} shots, {spec['duration']:.0f} s, timed to the voice-over", "pack": None,
                    "notes": spec["whatif"]["notes"]}
        path = build_spec(csv, music_path=music or None, out_dir=str(out), width=width, height=height, fps=fps, seed=None, phone=phone or None,
                          colour=colour or None, disclaimer=disclaimer if disclaimer_on else None, disclaimer_on=disclaimer_on,
                          pace={"Reveal": "reveal", "UI Film": "ui"}.get(film_type, "trailer"))
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
        if voiceover and Path(voiceover).is_file():   # a music-first film can still carry a voice-over on top
            spec.setdefault("product_trailer", {})["voiceover"] = str(voiceover)
            Path(path).write_text(json.dumps(spec, indent=1), encoding="utf-8")
        return {"spec_path": path, "summary": f"{film_type}: {len(spec['shots'])} shots, {spec['duration']:.0f} s", "pack": None, "notes": []}
    if music:
        spec.setdefault("product_trailer", {})["music"] = music
    if voiceover and Path(voiceover).is_file():
        spec.setdefault("product_trailer", {})["voiceover"] = str(voiceover)
    path = out / "product_trailer_spec.json"
    path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    if not use_ai:   # AI pictures were not asked for: a line planned for one simply has a 3D shot, which is not a failure to report
        notes = [n for n in notes if "had no AI picture" not in n]
    kinds = [s.get("kind") for s in spec["shots"]]
    pictures, three_d = sum(k in ("image", "video") for k in kinds), sum(k == "product" for k in kinds)
    summary = (f"{film_type}: {len(spec['shots'])} shots, {spec['duration']:.0f} s; {pictures} pictures or clips, {three_d} 3D, {len(kinds) - pictures - three_d} cards"
               + (f", {len(notes)} fell back to 3D" if notes else ""))   # counted from the film itself, not the plan's wish list
    return {"spec_path": str(path), "summary": summary, "pack": pack, "notes": notes, "footage": footage_items}


def estimate_text(pack: Dict[str, Any]) -> str:
    e = pack["estimate"]
    clip = f" {e['ai_clips']} clip(s) are planned but not made here ({e['clip_credits']} credits)." if e["ai_clips"] else ""
    return f"{e['ai_images']} AI images, 0 credits.{clip} {e['three_d_shots']} shots stay 3D."


def ensure_references(phone: str, out_dir, *, log: Callable[[str], None] = print, runner: Optional[Callable] = None) -> Path:
    """The five reference pictures in <out_dir>/scene_pack/refs (rendered once; reused while all five exist)."""
    from . import references

    d = refs_dir(out_dir)
    if all(f.is_file() for f in references.reference_files(d)):
        return d
    references.render_references(phone or "galaxy s27 ultra", d, log=log, runner=runner)
    return d


def make_scenes(pack: Dict[str, Any], out_dir, client, *, phone: str = "", log: Callable[[str], None] = print, ref_runner: Optional[Callable] = None,
                timeout_s: float = 900.0) -> Dict[Any, Any]:
    """Render the references if needed, make every AI scene's picture in Flow, save and return the results. Images only: 0 credits."""
    from . import scenepack

    d = ensure_references(phone or pack.get("phone", ""), out_dir, log=log, runner=ref_runner)
    results = scenepack.generate_scene_pack(pack, d, scene_dir(out_dir) / "run", client, log=log, timeout_s=timeout_s)
    save_results(out_dir, results)
    ok = sum(1 for r in results.values() if r["status"] == "done")
    log(f"AI scenes: {ok} of {len(results)} made; the rest become 3D shots")
    return results
