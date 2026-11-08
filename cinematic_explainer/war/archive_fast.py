"""War Documentary's Internet Archive search: fast, and only footage of what the CSV asked for.

The shared ArchiveProvider (protected by the Enoch / Weather manifests, unchanged) runs up to 12 searches per scene ending in single words
("In", "That", "German"), fetches every result's metadata one by one (~100 requests), then tries up to 44 candidates with a 180 s download
limit each. A Stalingrad project (2026-11-08) took 2-5 minutes per scene and picked "Applebees Cheetos" and "GTA V Snipers".

War's version (installed by app_section.war_manager on the War downloader only):
  queries    the CSV's own searches ("a || b") and one shorter form of each (never under two words), at most 4
  search     the searches and the metadata lookups run in parallel; a search stops early once enough relevant candidates are in
  relevance  a candidate's title / description / identifier must share a name or a year with the CSV's search (Stalingrad, 1942,
             Zaitsev ...), or two of its plain words; anything else is never downloaded
  download   the best 5 at most, 60 s each; a scene with nothing relevant fails fast and gets the War style's map / cards instead
"""

from __future__ import annotations

import concurrent.futures as cf
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from providers.archive.ia_backend import ArchiveCandidate, InternetArchiveBackend
from providers.archive.provider import ArchiveProvider
from providers.base import AssetResult, MediaType, SceneRow, SceneStatus, sniff_media_kind

MAX_QUERIES = 4
ROWS_PER_QUERY = 12
ENOUGH = 8
MAX_TRIES = 5
PARALLEL = 3
SCENE_BUDGET_S = 90.0
DOWNLOAD_TIMEOUT_S = 75
MIN_SIDE = 360
CLIP_S = 8.0
_STOP = {"the", "a", "an", "of", "in", "on", "at", "and", "or", "to", "for", "by", "with", "from", "into", "as", "is", "was", "that", "this",
         "then", "footage", "archive", "archival", "video", "film", "clip", "clips", "newsreel", "historical", "history", "documentary", "real",
         "rare", "original", "hd", "4k", "color", "colour", "black", "white", "scenes", "scene"}
_NEWS = re.compile(r"newsreel|wochenschau|prelinger|universal|pathe|british movietone|national archives|nara|ww2|wwii|world war|signal corps",
                   re.IGNORECASE)


def csv_queries(scene: SceneRow) -> List[str]:
    raw = [str(q).strip() for q in (getattr(scene, "search_queries", None) or [])] or [p.strip() for p in str(scene.prompt or "").split("||")]
    out: List[str] = []
    for q in raw:
        q = " ".join(re.sub(r"[^\w\s'-]", " ", q).split())
        words = [w for w in q.split() if w.lower() not in _STOP]
        for cand in (q, " ".join(words[:3]) if len(words) > 3 else ""):
            if cand and len(cand.split()) >= 2 and cand.lower() not in {x.lower() for x in out}:
                out.append(cand)
    return out[:MAX_QUERIES]


def key_terms(queries: List[str]) -> Tuple[Set[str], Set[str]]:
    """(names and years, plain words) from the CSV's searches: capitalised words / numbers are names, the rest plain (>= 4 letters)."""
    names, plain = set(), set()
    for q in queries:
        for w in re.findall(r"[\w'-]+", q):
            lw = w.lower()
            if lw in _STOP or len(lw) < 3:
                continue
            if w[0].isupper() or w.isdigit():
                names.add(lw)
            elif len(lw) >= 4:
                plain.add(lw.rstrip("s"))
    return names, plain


_PERIOD_WORDS = re.compile(r"\b(newsreel|wochenschau|kriegsberichter|ww ?ii|ww2|world war|wartime|war film|archive film|universal newsreel|"
                           r"pathe|movietone|signal corps|army pictorial|nazi|wehrmacht|luftwaffe|red army|soviet|third reich|allied|axis|"
                           r"d-day|propaganda|historic(?:al)? footage|19[0-9]0s)\b", re.IGNORECASE)


def period_ok(text: str, years: Set[int]) -> bool:
    """History searches (a year before 2000 in the CSV's search) only take items that belong to that time: a year within 3 of it, or a
    period word (newsreel, Wochenschau, WWII, Wehrmacht ...). Modern items that only share a name (an 'Armin-Paulus' for Paulus) fail."""
    old = {y for y in years if y < 2000}
    if not old:
        return True
    found = {int(y) for y in re.findall(r"\b(1[89]\d\d)\b", text)}
    if any(abs(y - o) <= 3 for y in found for o in old):
        return True
    if found and all(y >= 2000 for y in found):
        return False
    return bool(_PERIOD_WORDS.search(text)) and not re.search(r"\b(20[0-2]\d)\b", text[:120])


def query_years(queries: List[str]) -> Set[int]:
    return {int(y) for q in queries for y in re.findall(r"\b(1[89]\d\d|20[0-2]\d)\b", q)}


def relevance(c: ArchiveCandidate, names: Set[str], plain: Set[str], years: Optional[Set[int]] = None) -> float:
    text = " ".join((c.title or "", c.description or "", c.identifier or "", c.collection or "")).lower()
    if years and not period_ok(text, years):
        return 0.0
    hit_names = sum(1 for n in names if re.search(r"\b" + re.escape(n), text))
    hit_plain = sum(1 for p in plain if re.search(r"\b" + re.escape(p), text))
    if hit_names == 0 and hit_plain < 2:
        return 0.0
    score = 2.0 * hit_names + hit_plain
    if _NEWS.search(text):
        score += 1.5                                 # newsreels and national archives are what an archive_video row is for
    if c.width and c.height and min(c.width, c.height) < MIN_SIDE:
        return 0.0                                   # too small for a 1080p film (the shared search rejects these too)
    return score


class WarArchiveProvider(ArchiveProvider):
    """ArchiveProvider with War's query, relevance and time rules (see module doc). Same results format, same manifest records."""

    def _youtube_mirror(self, jobs, log, t_end):
        return _mirror_download(self, jobs, log, t_end)

    def _search_fast(self, scene: SceneRow, log, exclude_ids: Set[str]) -> List[ArchiveCandidate]:
        queries = csv_queries(scene)
        if not queries:
            return []
        names, plain = key_terms(queries)
        years = query_years(queries)
        backend: InternetArchiveBackend = self.backend
        sn = scene.scene_number

        def ids_for(q: str) -> List[str]:
            try:
                resp = backend._session.get("https://archive.org/advancedsearch.php",
                                            params={"q": f"({q}) AND mediatype:(movies OR video)", "fl[]": ["identifier", "title", "description"],
                                                    "rows": ROWS_PER_QUERY, "page": 1, "output": "json"}, timeout=20)
                resp.raise_for_status()
                docs = (resp.json().get("response") or {}).get("docs") or []
            except Exception as exc:  # noqa: BLE001
                log(f"[ARCHIVE] Scene {sn} -> search failed: {exc}")
                return []
            keep = []
            for d in docs:                               # the search's own title / description screen out junk before any metadata request
                stub = ArchiveCandidate(identifier=str(d.get("identifier") or ""), title=str(d.get("title") or ""),
                                        description=str(d.get("description") or "")[:600])
                if stub.identifier and stub.identifier not in exclude_ids and relevance(stub, names, plain, years) > 0:
                    keep.append(stub.identifier)
            return keep

        log(f"[ARCHIVE] Scene {sn} -> {len(queries)} search(es) from the CSV: " + " | ".join(queries))
        idents: List[str] = []
        with cf.ThreadPoolExecutor(max_workers=min(4, len(queries))) as ex:
            for got in ex.map(ids_for, queries):
                for i in got:
                    if i not in idents:
                        idents.append(i)
        if not idents:
            return []
        idents = idents[:ENOUGH * 2]
        cands: List[ArchiveCandidate] = []
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for c in ex.map(lambda i: _safe_resolve(backend, i), idents):
                if c is not None:
                    cands.append(c)
        scored = sorted(((relevance(c, names, plain, years), c) for c in cands), key=lambda x: -x[0])
        ranked = [c for s, c in scored if s > 0]
        log(f"[ARCHIVE] Scene {sn} -> {len(ranked)} relevant candidate(s) of {len(cands)}")
        return ranked

    def _resolve(self, scene: SceneRow, images_dir: Path, log, exclude_ids: Set[str]) -> AssetResult:
        if not scene.prompt and not scene.search_queries:
            return super()._resolve(scene, images_dir, log, exclude_ids)
        if str(scene.prompt or "").startswith("identifier:"):
            return super()._resolve(scene, images_dir, log, exclude_ids)
        candidates = self._search_fast(scene, log, exclude_ids)
        if not candidates:
            return AssetResult(scene.scene_number, None, None, self.source, SceneStatus.FAILED,
                               error="Internet Archive: nothing matching the CSV's search (the War style uses a map or cards here).")
        from providers.media_clip.ffmpeg_clip import _ffmpeg, _tls_opts
        from providers import hidden_subprocess
        from providers.youtube.base import compute_clip_window, compute_fallback_timestamp

        last = ""
        n = int(str(scene.scene_number).strip())
        target = Path(images_dir) / f"{n:03d}.mp4"
        used = _USED.setdefault(str(images_dir), {})
        candidates = sorted(candidates, key=lambda c: used.get(c.identifier, 0))[:MAX_TRIES]   # items no other scene used come first
        words = set(re.findall(r"[a-z]{4,}", f"{scene.script_segment} {scene.prompt}".lower())) - _STOP
        sess = backend_session(self)
        jobs = []
        for idx, c in enumerate(candidates, start=1):
            c = web_copy(sess, c)
            start, clip_len = pick_moment(sess, c, self.clip_duration, words, used.get(c.identifier, 0), n)
            tmp = target.with_name(f"{target.stem}_war{idx}_tmp.mp4")       # its own temp name: a concurrent retry never collides
            cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, start):.3f}", *_tls_opts(c.download_url), "-i",
                   c.download_url, "-t", f"{max(0.1, clip_len):.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
                   "-movflags", "+faststart", "-f", "mp4", "-y", str(tmp)]
            jobs.append({"idx": idx, "c": c, "start": start, "len": clip_len, "tmp": tmp, "cmd": cmd, "proc": None, "t0": 0.0})
        # archive.org can be slow (minutes for one cut): the best few download at once, the first good clip in rank order wins, and the whole
        # scene has SCENE_BUDGET_S before it moves on to YouTube, then stock (the declared fallbacks)
        import subprocess as _sp
        import time as _time

        t_end = _time.time() + SCENE_BUDGET_S
        win = self._youtube_mirror(jobs, log, t_end)     # archive items copied from YouTube: the same film, cut from YouTube (fast, HD)
        if win is not None:
            win["tmp"].replace(target)
            c = win["c"]
            used[c.identifier] = used.get(c.identifier, 0) + 1
            log(f"[ARCHIVE] Scene {scene.scene_number} -> downloaded {target.name} (from the YouTube original)")
            return AssetResult(scene_number=scene.scene_number, path=target, media_type=MediaType.VIDEO, source=self.source,
                               status=SceneStatus.READY,
                               metadata={"provider": self.name, "provider_asset_id": c.asset_id, "title": c.title, "source_url": c.source_url,
                                         "channel": "YouTube (archive.org copy)", "clip_start": win["start"], "clip_duration": win["len"],
                                         "selection_method": "war_relevance", "via": "youtube_mirror",
                                         "matched_text": f"{scene.script_segment} {scene.prompt}"[:200]})
        jobs = [j for j in jobs if not j.get("tried_yt_ok")]
        pending = list(jobs)
        running: List[dict] = []
        done_ok: Dict[int, dict] = {}
        flags = {"creationflags": 0x08000000} if os.name == "nt" else {}
        try:
            while (pending or running) and _time.time() < t_end:
                if self._scene_stopped(scene):
                    return AssetResult(scene.scene_number, None, None, self.source, SceneStatus.CANCELLED, error="Cancelled.")
                while pending and len(running) < PARALLEL:
                    j = pending.pop(0)
                    log(f"[ARCHIVE] Candidate {j['idx']} -> \"{j['c'].title}\" ({j['c'].filename or 'original'}, {j['start']:.0f}s)")
                    j["proc"] = _sp.Popen(j["cmd"], stdout=_sp.DEVNULL, stderr=_sp.PIPE, **flags)
                    j["t0"] = _time.time()
                    running.append(j)
                for j in list(running):
                    rc = j["proc"].poll()
                    if rc is None:
                        if _time.time() - j["t0"] > DOWNLOAD_TIMEOUT_S:
                            j["proc"].kill()
                            running.remove(j)
                            last = "timed out"
                            log(f"[ARCHIVE] Candidate {j['idx']} -> timed out")
                        continue
                    running.remove(j)
                    tmp = j["tmp"]
                    if rc != 0 or not tmp.is_file() or tmp.stat().st_size < 20_000 or sniff_media_kind(tmp) != "video":
                        last = "download failed" if rc else "empty clip"
                        tmp.unlink(missing_ok=True)
                        log(f"[ARCHIVE] Candidate {j['idx']} -> {last}")
                        continue
                    bad = frame_problem(str(tmp))
                    if bad:                             # credits, a title card or black: not footage of the event
                        tmp.unlink(missing_ok=True)
                        last = bad
                        used[j["c"].identifier] = used.get(j["c"].identifier, 0) + 1
                        log(f"[ARCHIVE] Candidate {j['idx']} -> {bad} at {j['start']:.0f}s: skipped")
                        continue
                    done_ok[j["idx"]] = j
                # the best-ranked finished clip wins once nothing ranked above it is still running
                for j in sorted(jobs, key=lambda x: x["idx"]):
                    if j["idx"] in done_ok:
                        if all(r["idx"] > j["idx"] for r in running):
                            win = j
                            break
                        win = None
                        break
                    if j in running or j in pending:
                        win = None
                        break
                else:
                    win = None
                if win is not None:
                    win["tmp"].replace(target)
                    c = win["c"]
                    used[c.identifier] = used.get(c.identifier, 0) + 1
                    log(f"[ARCHIVE] Scene {scene.scene_number} -> downloaded {target.name}")
                    return AssetResult(scene_number=scene.scene_number, path=target, media_type=MediaType.VIDEO, source=self.source,
                                       status=SceneStatus.READY,
                                       metadata={"provider": self.name, "provider_asset_id": c.asset_id, "title": c.title,
                                                 "source_url": c.source_url, "clip_start": win["start"], "clip_duration": win["len"],
                                                 "selection_method": "war_relevance", "matched_text": f"{scene.script_segment} {scene.prompt}"[:200]})
                _time.sleep(0.25)
            if done_ok:                                 # out of time with a good clip in hand: take the best one
                win = done_ok[min(done_ok)]
                win["tmp"].replace(target)
                c = win["c"]
                used[c.identifier] = used.get(c.identifier, 0) + 1
                log(f"[ARCHIVE] Scene {scene.scene_number} -> downloaded {target.name}")
                return AssetResult(scene_number=scene.scene_number, path=target, media_type=MediaType.VIDEO, source=self.source,
                                   status=SceneStatus.READY,
                                   metadata={"provider": self.name, "provider_asset_id": c.asset_id, "title": c.title, "source_url": c.source_url,
                                             "clip_start": win["start"], "clip_duration": win["len"], "selection_method": "war_relevance",
                                             "matched_text": f"{scene.script_segment} {scene.prompt}"[:200]})
            if pending or running:
                last = f"archive.org too slow: no clip within {SCENE_BUDGET_S:.0f} s"
                log(f"[ARCHIVE] Scene {scene.scene_number} -> {last}; trying the next source")
        finally:
            for j in jobs:                              # nothing left running, no temp file left behind
                if j["proc"] is not None and j["proc"].poll() is None:
                    j["proc"].kill()
                if j["tmp"].exists() and j["tmp"] != target:
                    try:
                        j["tmp"].unlink()
                    except OSError:
                        pass
        return AssetResult(scene.scene_number, None, None, self.source, SceneStatus.FAILED,
                           error=f"Internet Archive: the relevant candidates did not download ({last}).")


_USED: Dict[str, Dict[str, int]] = {}      # per project folder: how often each archive item has been cut this session


_YT_ID = re.compile(r"^youtube-([\w-]{11})$")
YT_TIMEOUT_S = 60.0


def _mirror_download(self, jobs: List[dict], log, t_end: float) -> Optional[dict]:
    """Archive items named 'youtube-<id>' are copies of YouTube videos: cut the same moment from YouTube with the app's own downloader.
    archive.org measured ~18 KB/s here (one 8 s cut took 350 s); YouTube serves the same film in seconds. Up to two tries."""
    import threading
    import time as _time

    yt = getattr(self, "_war_yt", None)
    if yt is None:
        return None
    from providers.youtube.base import VideoCandidate

    tried = 0
    for j in jobs:
        m = _YT_ID.match(j["c"].identifier or "")
        if not m or tried >= 2 or _time.time() > t_end - 10:
            continue
        tried += 1
        vid = m.group(1)
        cand = VideoCandidate(video_id=vid, url=f"https://www.youtube.com/watch?v={vid}", title=j["c"].title, channel="", duration=j["c"].duration)
        box: Dict[str, Any] = {}

        def run() -> None:
            try:
                yt.download_segment(cand, j["start"], j["len"], j["tmp"], log=lambda m_: None)
                box["ok"] = True
            except Exception as exc:  # noqa: BLE001
                box["err"] = str(exc)[-160:]

        th = threading.Thread(target=run, daemon=True, name=f"war-yt-mirror-{vid}")
        log(f"[ARCHIVE] Candidate {j['idx']} -> the YouTube original {vid} ({j['start']:.0f}s)")
        th.start()
        th.join(min(YT_TIMEOUT_S, max(5.0, t_end - _time.time())))
        tmp = j["tmp"]
        if th.is_alive() or not box.get("ok") or not tmp.is_file() or tmp.stat().st_size < 20_000:
            log(f"[ARCHIVE] Candidate {j['idx']} -> YouTube original not available ({box.get('err') or 'too slow'})")
            continue
        bad = frame_problem(str(tmp))
        if bad:
            tmp.unlink(missing_ok=True)
            log(f"[ARCHIVE] Candidate {j['idx']} -> {bad}: skipped")
            continue
        j["tried_yt_ok"] = True
        return j
    return None


def backend_session(provider: "WarArchiveProvider"):
    return getattr(getattr(provider, "backend", None), "_session", None)


def _srt_cues(text: str) -> List[Tuple[float, str]]:
    cues = []
    for m in re.finditer(r"(?:(\d+):)?(\d+):(\d+)[,.](\d+)\s*-->\s*[\d:,.]+[^\n]*\n(.+?)(?:\n\s*\n|\Z)", text, re.S):
        h, mi, se, ms = (int(x or 0) for x in m.groups()[:4])
        cues.append((h * 3600 + mi * 60 + se + ms / 1000.0, " ".join(m.group(5).split())))
    return cues


_META: "Dict[str, dict]" = {}


def item_meta(session, ident: str) -> dict:
    """The item's metadata (files list), fetched once per session."""
    if ident in _META:
        return _META[ident]
    meta: dict = {}
    if session is not None:
        try:
            meta = session.get(f"https://archive.org/metadata/{ident}", timeout=15).json() or {}
        except Exception:  # noqa: BLE001
            meta = {}
    _META[ident] = meta
    return meta


def web_copy(session, c: ArchiveCandidate) -> ArchiveCandidate:
    """The archive's own H.264 MP4 derivative of the item when it has one (index at the front: a cut deep into an hour-long film seeks in
    seconds), instead of the large original (.mov / .webm / .mpeg) the shared search picks, which timed out at 60 s."""
    from urllib.parse import quote

    files = item_meta(session, c.identifier).get("files") or []
    best = None
    for f in files:
        name = str(f.get("name") or "")
        if not name.lower().endswith(".mp4") or "h.264" not in str(f.get("format") or "").lower():
            continue
        h = int(float(f.get("height") or 0) or 0)
        if h and h < MIN_SIDE:
            continue
        key = (0 if str(f.get("source") or "") == "derivative" else 1, -h)
        if best is None or key < best[0]:
            best = (key, f)
    if best is None:
        return c
    f = best[1]
    out = ArchiveCandidate(**{k: getattr(c, k) for k in ("identifier", "title", "description", "collection", "source_url")})
    out.download_url = f"https://archive.org/download/{c.identifier}/{quote(str(f['name']))}"
    out.filename = str(f["name"])
    try:
        out.duration = float(f.get("length")) if f.get("length") else c.duration
    except (TypeError, ValueError):
        out.duration = c.duration
    out.width, out.height = int(float(f.get("width") or 0) or c.width or 0), int(float(f.get("height") or 0) or c.height or 0)
    return out


def subtitle_moment(session, c: ArchiveCandidate, words: Set[str]) -> Optional[float]:
    """The second where the item's own English subtitles best match the narration (archive items such as '[ENG-SUB] Wochenschau' carry
    .srt / .vtt files); None when there are none or nothing matches."""
    if session is None or not words:
        return None
    try:
        meta = item_meta(session, c.identifier)
        subs = [f["name"] for f in meta.get("files") or [] if str(f.get("name", "")).lower().endswith((".srt", ".vtt"))]
        if not subs:
            return None
        subs.sort(key=lambda n: (0 if re.search(r"\b(en|eng|english)\b", n.lower()) else 1, n))
        from urllib.parse import quote

        txt = session.get(f"https://archive.org/download/{c.identifier}/{quote(subs[0])}", timeout=15).text
    except Exception:  # noqa: BLE001
        return None
    best, best_t = 1, None
    for t, line in _srt_cues(txt):
        hit = len(words & set(re.findall(r"[a-z]{4,}", line.lower())))
        if hit > best:
            best, best_t = hit, t
    return best_t


def pick_moment(session, c: ArchiveCandidate, clip_s: float, words: Set[str], reuse: int, scene_no: int) -> Tuple[float, float]:
    """(start, length): the subtitle match when there is one; else a point inside the item's body, away from opening and closing credits
    (newsreels open with a credit roll), spread by scene so two scenes never cut the same moment; a reused item moves further on."""
    d = float(c.duration or 0.0)
    clip = float(clip_s)
    if d and d < clip + 1.0:
        return 0.0, max(0.5, d - 0.2)
    if not d:
        return 30.0 + 23.0 * (reuse + scene_no % 5), clip
    lo = min(max(20.0, d * 0.12), max(0.0, d - clip - 1.0))
    hi = max(lo, min(d - 45.0, d * 0.85) - clip)
    sub = subtitle_moment(session, c, words) if reuse == 0 else None
    if sub is not None and lo <= sub <= hi + clip:
        return max(lo, sub - 1.0), clip
    span = max(0.0, hi - lo)
    frac = ((scene_no * 0.37) + reuse * 0.29) % 1.0
    return lo + span * frac, clip


def frame_problem(path: str) -> str:
    """'' when the clip looks like footage; else why not, judged on three frames at 256x144:
      'text / credits'  a dark plate with sharp type (measured on a Wochenschau credit roll: ~77 % dark pixels, edge density ~0.12;
                        real footage stayed at or under ~0.08)
      'black frames'    nearly all dark and no detail"""
    import subprocess as _sp

    W_, H_ = 256, 144
    n = W_ * H_
    try:
        r = _sp.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps=1,scale={W_}:{H_},format=gray", "-frames:v", "3", "-f", "rawvideo", "-"],
                    capture_output=True, timeout=30)
        data = r.stdout
    except Exception:  # noqa: BLE001
        return ""
    frames = [data[i:i + n] for i in range(0, len(data) - n + 1, n)]
    if not frames:
        return ""
    black = text = 0
    for f in frames:
        dark = sum(1 for v in f if v < 60) / n
        bright = sum(1 for v in f if v > 170) / n
        edges = sum(1 for j in range(n - 1) if (j + 1) % W_ and abs(f[j] - f[j + 1]) > 70) / n
        if dark > 0.95 and edges < 0.005:
            black += 1
        elif edges >= 0.10 and dark + bright >= 0.80:
            text += 1
    if black * 2 > len(frames):
        return "black frames"
    if text * 2 > len(frames):
        return "text / credits"
    return ""


def _safe_resolve(backend: InternetArchiveBackend, ident: str) -> Optional[ArchiveCandidate]:
    try:
        return backend.resolve_identifier(ident)
    except Exception:  # noqa: BLE001 - one bad item never stops the search
        return None


def install(manager) -> bool:
    """Give the War downloader this archive search (the manager is rebuilt when another style becomes active)."""
    ap = getattr(manager, "archive_provider", None)
    if ap is None or isinstance(ap, WarArchiveProvider):
        return False
    if isinstance(ap, ArchiveProvider):
        ap.__class__ = WarArchiveProvider
        ap.clip_duration = max(float(getattr(ap, "clip_duration", 0) or 0), CLIP_S)    # scenes run 5-10 s: a 3.5 s cut froze on its last frame
        ap._war_yt = getattr(getattr(manager, "youtube_provider", None), "backend", None)  # archive copies of YouTube films are cut from YouTube
        return True
    return False
