"""War Documentary: narration-derived footage queries, optional provider discovery, and a clean-clip helper.

What it does
------------
scene_queries(text)           pure and offline: 1-3 search queries per scene from what the narration names (a place + a visual noun, a system, a
                              country marker). Named PEOPLE are never searched for as stock (a stock clip of "Putin" is not the person).
discover(scenes, project_dir, config, provider=None)
                              fills weak or empty scenes with `footage_candidates` that the matcher then scores like any other clip.
                              1. clips already discovered by an earlier run (Images/war_discovered/, its own AssetManifest) are reused, nothing fetched;
                              2. ONLY when config['discover_footage'] is True and a provider exists, the app's own StockProvider.resolve() is called
                                 (the same search -> filter -> rank -> download pipeline the app uses) for at most config['discover_max_clips']
                                 (default 4) scenes per run. The render never needs the network: with the flag off, with no provider/key, or when a
                                 search fails, the scene is left as it was and the report says why.
prepare_clean_clip(...)       ffmpeg: cut a shot from a source video, crop caption/logo bands (aspect kept) and rescale; cached by content key.

Downloaded files go to <project>/Images/war_discovered/ (never over a numbered project file) with a manifest there written through the app's
AssetManifest; the record keeps provider, provider_asset_id, author, source_url, width/height/duration and the search query. A provider's
published licence name is added only for Pexels and Pixabay (their own licence terms, as published; not verified per clip).

Classes (footage_match.classify): verified_event | user_supplied | relevant_stock | illustrative | ai_generated. A Flow-generated record, or a file marked
`ai_generated`, is class ai_generated: generic=True, labelled as an illustration, never footage of a named event.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger("cinematic_explainer.war.footage_discovery")

DISCOVER_DIR = "war_discovered"
DEFAULT_MAX_CLIPS = 4
_LICENCE_BY_PROVIDER = {"pexels": "Pexels License", "pixabay": "Pixabay Content License"}

# (words in the narration) -> a visual noun that stock libraries actually carry. Generic visuals only: no event, unit or battle names.
_VISUALS: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("refinery", "refineries", "oil depot", "fuel depot", "oil terminal"), "oil refinery"),
    (("drone", "drones", "uav", "uavs"), "drone flying"),
    (("air defense", "air defence", "anti-aircraft", "missile defense", "interceptor"), "air defense missile launcher"),
    (("missile", "missiles", "rocket", "rockets"), "missile launcher"),
    (("tank", "tanks", "armour", "armor"), "main battle tank"),
    (("trench", "trenches", "frontline", "front line", "infantry", "soldiers"), "soldiers trench"),
    (("winter", "snow", "frozen", "freezing", "cold"), "winter snow soldiers"),
    (("convoy", "trucks", "supply road", "logistics"), "military convoy road"),
    (("substation", "power line", "power lines", "electricity", "power grid", "blackout"), "electrical substation"),
    (("railway", "train", "trains", "rail"), "railway freight train"),
    (("pipeline", "pipelines", "natural gas", "gas pipe"), "gas pipeline"),
    (("port", "ports", "ship", "ships", "grain exports", "black sea"), "cargo ship port"),
    (("airport", "airfield", "aircraft", "fighter jet", "jets", "air force"), "military aircraft"),
    (("parliament", "ministry", "government", "council", "summit"), "government building"),
    (("kremlin", "red square"), "Kremlin Red Square"),
    (("satellite", "satellites"), "satellite earth orbit"),
    (("command", "headquarters", "general staff", "operations room"), "command center screens"),
    (("fuel", "gasoline", "petrol", "pump", "pumps"), "gas station fuel pump"),
    (("tunnel", "tunnels", "underground", "bunker"), "underground tunnel"),
)
_NIGHT = ("night", "overnight", "darkness", "after dark")
_BROAD_PLACES = {"ukraine", "russia", "europe", "the black sea", "black sea", "belarus"}   # too broad to help a stock search


def _has(text: str, words: Sequence[str]) -> bool:
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def scene_queries(text: str, max_queries: int = 3) -> List[str]:
    """Search queries for one narration sentence, most specific first. Offline, deterministic, never contains a person's name."""
    t = str(text or "").lower()
    if not t.strip():
        return []
    places: List[str] = []
    systems: List[str] = []
    try:
        from . import footage_match as FM

        prof = FM.narration_profile(str(text))
        places = [n for n in prof.hits["place"].values() if n and n.lower() not in _BROAD_PLACES]
        systems = [n for n in prof.hits["equipment"].values() if n]
    except Exception:
        pass
    nouns = [noun for words, noun in _VISUALS if _has(t, words)]
    night = " night" if _has(t, _NIGHT) else ""
    out: List[str] = []

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", q).strip()
        if q and q.lower() not in [x.lower() for x in out]:
            out.append(q)

    for s in systems[:1]:
        add(f"{s}")
    if places and nouns:
        add(f"{places[0]} {nouns[0]}{night}")
    for n in nouns[:2]:
        add(f"{n}{night}")
    if places:
        add(f"{places[0]} city" + night)
    return out[:max_queries]


# --------------------------------------------------------------------------------------------------------------------- provider + cache
def _keys(config: Dict[str, Any]) -> Dict[str, str]:
    """API keys from the config, the environment, then settings.json (values are never logged)."""
    keys = {"pexels": str(config.get("pexels_api_key") or os.environ.get("PEXELS_API_KEY") or ""),
            "pixabay": str(config.get("pixabay_api_key") or os.environ.get("PIXABAY_API_KEY") or "")}
    if not all(keys.values()):
        try:
            s = json.loads((Path(__file__).resolve().parents[2] / "settings.json").read_text(encoding="utf-8"))
            for k in ("pexels", "pixabay"):
                keys[k] = keys[k] or str(s.get(f"{k}_api_key") or "")
        except (OSError, ValueError):
            pass
    return keys


def default_provider(project_dir: Path, config: Dict[str, Any]) -> Tuple[Optional[Any], str]:
    """(StockProvider or None, reason). Built from the app's own factory; Openverse (no key) only when config['discover_openverse'] is true."""
    try:
        from providers.stock.factory import build_stock_provider
    except Exception as exc:
        return None, f"stock providers unavailable ({type(exc).__name__})"
    k = _keys(config)
    ov = bool(config.get("discover_openverse"))
    if not (k["pexels"] or k["pixabay"] or ov):
        return None, "no stock provider key configured"
    try:
        d = Path(project_dir) / "Images" / DISCOVER_DIR
        d.mkdir(parents=True, exist_ok=True)
        prov = build_stock_provider(d, pexels_api_key=k["pexels"], pixabay_api_key=k["pixabay"], include_openverse=ov)
    except Exception as exc:
        return None, f"stock provider not built ({type(exc).__name__})"
    return (prov, "") if prov else (None, "no stock provider key configured")


def _discover_dir(project_dir: Path) -> Path:
    return Path(project_dir) / "Images" / DISCOVER_DIR


def _manifest(project_dir: Path):
    from asset_manager import AssetManifest        # the app's own reader/writer; imported lazily so the style renders without it

    return AssetManifest(_discover_dir(project_dir))


def cached_pool(project_dir: Path) -> List[Dict[str, Any]]:
    """Clips discovered by earlier runs, as {path, meta} candidates (their own manifest records). Empty when there are none."""
    d = _discover_dir(project_dir)
    if not (d / ".asset_manifest.json").is_file():
        return []
    try:
        recs = _manifest(project_dir).all()
    except Exception:
        try:
            recs = json.loads((d / ".asset_manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    out: List[Dict[str, Any]] = []
    for _k, rec in (recs or {}).items():
        if not isinstance(rec, dict) or str(rec.get("status") or "").lower() not in ("complete", "completed", "ok", "done"):
            continue
        lp = rec.get("local_path")
        if lp and Path(lp).is_file() and Path(lp).suffix.lower() in (".mp4", ".mov", ".m4v", ".webm", ".mkv"):
            out.append({"path": str(lp), "rec": dict(rec)})
    return out


def _record_for_result(scene_no: str, text: str, query: str, result: Any) -> Dict[str, Any]:
    md = dict(getattr(result, "metadata", None) or {})
    rec = {"source": getattr(getattr(result, "source", None), "value", "stock_video"), "asset_type": "stock_video", "type": "video",
           "script_segment": text, "stock_query": query, "local_path": str(result.path) if getattr(result, "path", None) else None,
           "status": "complete" if getattr(result, "ok", False) else "failed", "error": getattr(result, "error", None)}
    rec.update(md)
    prov = str(rec.get("provider") or "").lower()
    if prov in _LICENCE_BY_PROVIDER and not rec.get("license"):
        rec["license"] = _LICENCE_BY_PROVIDER[prov]
        rec["license_note"] = "provider licence as published; not verified for this clip"
    return rec


def discover(scenes: Sequence[Dict[str, Any]], project_dir: Any, config: Optional[Dict[str, Any]] = None, *, provider: Any = None,
             logger: Optional[Callable[[str], None]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """(scenes with `footage_candidates` added for weak/empty scenes, {scene_no: {queries, tried, source, candidate, note}}).

    Never raises and never needs the network: any failure leaves the scene as it was. Scenes that already have a pinned (user-supplied) clip, or a
    clip the matcher rates relevant, are not touched."""
    from . import footage_match as FM
    from .integration import footage_meta_for

    cfg = dict(config or {})
    pd = Path(project_dir)
    say = logger or (lambda m: log.info(m))
    out = [dict(s) for s in scenes]
    report: Dict[str, Dict[str, Any]] = {}
    cache = []
    try:
        cache = cached_pool(pd)
    except Exception as exc:
        say(f"discovery cache not read ({exc})")
    enabled = bool(cfg.get("discover_footage"))
    prov, why = (provider, "") if provider is not None else ((None, "discover_footage is off") if not enabled else default_provider(pd, cfg))
    budget = int(cfg.get("discover_max_clips", DEFAULT_MAX_CLIPS) or 0)
    fetched = 0
    for sc in out:
        no = str(sc.get("scene_no"))
        try:
            text = str(sc.get("text") or "")
            meta = sc.get("footage_meta") or {}
            if sc.get("footage") and (meta.get("user_supplied") or meta.get("pinned") or meta.get("kind") == "user"):
                continue
            narr = FM.narration_profile(text)
            if sc.get("footage"):
                cur = FM.score_clip(narr, meta, str(sc["footage"]))
                if FM.classify(meta, cur) in ("verified_event", "relevant_stock"):
                    continue
            queries = scene_queries(text)
            if not queries:
                continue
            row = report.setdefault(no, {"queries": queries, "tried": [], "source": "none", "candidate": None, "note": ""})
            # 1) a clip an earlier run already fetched, scored with the same estimator
            best, best_score = None, 0.0
            for c in cache:
                m = footage_meta_for(c["rec"], None, scene_file=Path(c["path"]).name)
                s = FM.score_clip(narr, m, c["path"])
                if s["score"] >= FM.RELEVANT_MIN and s["score"] > best_score and not s["contradictions"]:
                    best, best_score = {"path": c["path"], "meta": m}, s["score"]
            if best:
                sc["footage_candidates"] = list(sc.get("footage_candidates") or []) + [best]
                row.update(source="cache", candidate=Path(best["path"]).name, note="reused from an earlier discovery (nothing fetched)")
                continue
            # 2) the app's own stock provider, only when asked for and available
            if prov is None:
                row["note"] = why or "no provider"
                continue
            if fetched >= budget:
                row["note"] = f"discovery budget of {budget} clips reached"
                continue
            from providers.base import SceneRow

            d = _discover_dir(pd)
            d.mkdir(parents=True, exist_ok=True)
            for q in queries[:2]:
                row["tried"].append(q)
                try:
                    res = prov.resolve(SceneRow(scene_number=no, script_segment=text, asset_type="stock_video", stock=q), d, say)
                except Exception as exc:
                    say(f"discovery search failed for '{q}': {type(exc).__name__}")
                    continue
                if not getattr(res, "ok", False):
                    continue
                rec = _record_for_result(no, text, q, res)
                try:
                    _manifest(pd).set(_unique_key(pd, no), rec)
                except Exception as exc:
                    say(f"discovery record not written ({exc})")
                m = footage_meta_for(rec, None, scene_file=Path(rec["local_path"]).name)
                sc["footage_candidates"] = list(sc.get("footage_candidates") or []) + [{"path": rec["local_path"], "meta": m}]
                fetched += 1
                row.update(source="provider", candidate=Path(rec["local_path"]).name, note=f"found with '{q}' ({rec.get('provider')})")
                break
            else:
                row["note"] = "no usable result for the queries"
        except Exception as exc:
            say(f"discovery skipped scene {no}: {type(exc).__name__}: {exc}")
    return out, report


def _unique_key(project_dir: Path, no: str) -> str:
    """The discovered folder's manifest key: the scene number (files are named by it); a later fetch for the same scene replaces it."""
    return str(no)


# --------------------------------------------------------------------------------------------------------------------- clean demo clips
def _key(src: Path, t0: float, dur: float, crop_top: float, crop_bottom: float, scale_to: Tuple[int, int]) -> str:
    st = src.stat()
    raw = f"{src.resolve()}|{st.st_size}|{int(st.st_mtime)}|{t0:.3f}|{dur:.3f}|{crop_top:.4f}|{crop_bottom:.4f}|{scale_to[0]}x{scale_to[1]}|v1"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def prepare_clean_clip(src: Any, out: Any, t0: float, dur: float, crop_bottom: float = 0.14, crop_top: float = 0.0,
                       scale_to: Tuple[int, int] = (1280, 720)) -> str:
    """Cut [t0, t0+dur) from `src`, remove burned-in caption/logo bands and write an H.264 clip (no audio) of size `scale_to`.

    The band is cropped from the top/bottom (fractions of the height) and the width is cropped by the same factor, centred, so the picture is never
    stretched; it is then scaled to `scale_to` (a mild upscale, about 1/(1-top-bottom)). `out` is a directory (the file is named by a content key
    of source, times and crop, so an identical request reuses the file) or an explicit .mp4 path. Returns the file path; raises RuntimeError on failure."""
    s = Path(src)
    if not s.is_file():
        raise RuntimeError(f"source not found: {s}")
    if not (0.0 <= crop_top < 0.5 and 0.0 <= crop_bottom < 0.5) or dur <= 0 or t0 < 0:
        raise RuntimeError("bad crop or time arguments")
    o = Path(out)
    key = _key(s, t0, dur, crop_top, crop_bottom, tuple(scale_to))
    target = o if o.suffix.lower() == ".mp4" else o / f"clip_{key}.mp4"
    stamp = target.with_name(target.name + ".key")           # an explicit file name is reused only when the same request made it
    if target.is_file() and target.stat().st_size > 0:
        try:
            if o.suffix.lower() != ".mp4" or stamp.read_text(encoding="utf-8").strip() == key:
                return str(target)
        except OSError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    keep = 1.0 - crop_top - crop_bottom
    w, h = scale_to
    vf = (f"crop=trunc(iw*{keep:.5f}/2)*2:trunc(ih*{keep:.5f}/2)*2:(iw-trunc(iw*{keep:.5f}/2)*2)/2:ih*{crop_top:.5f},"
          f"scale={w}:{h}:flags=lanczos,setsar=1,fps=25,format=yuv420p")
    tmp = target.with_name(target.stem + ".part.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(s), "-an", "-vf", vf, "-c:v", "libx264", "-preset", "medium",
           "-crf", "18", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-movflags", "+faststart", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg failed: " + (r.stderr or "")[-300:])
    tmp.replace(target)
    try:
        stamp.write_text(key, encoding="utf-8")
    except OSError:
        pass
    return str(target)
