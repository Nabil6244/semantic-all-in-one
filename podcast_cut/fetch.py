"""Podcast source: download (YouTube link) or use a local file, then the spoken words with their times.

Everything is cached in the episode's work folder, so a second Generate never downloads or transcribes again:
    source.<ext>   the audio (phase 1) or the video (later phases)
    meta.json      title, uploader, duration, chapters, SponsorBlock ranges (ads, self-promo, intro/outro)
    words.json     [[word, start, end], ...]  word keeps its punctuation (the picker splits sentences on it)

Word times come from Whisper by default (punctuation + word times). captions=True uses YouTube's automatic captions
instead: much faster for a 2-hour episode, but they have no punctuation, so thoughts are split on pauses only.
No Gemini anywhere.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "podcast_cut"
Word = Tuple[str, float, float]
LogFn = Callable[[str], None]

_YT_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")
AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"
VIDEO_FORMAT = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b"
SPONSOR_CATS = ["sponsor", "selfpromo", "interaction", "intro", "outro"]
MEDIA_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus")


class Stopped(Exception):
    pass


def is_url(src: str) -> bool:
    return str(src).strip().lower().startswith(("http://", "https://", "www.", "youtu"))


def source_id(src: str) -> str:
    """The YouTube video id, or a short stable id for a local file (name + size)."""
    s = str(src).strip()
    m = _YT_ID.search(s)
    if m:
        return m.group(1)
    p = Path(s).expanduser()
    size = p.stat().st_size if p.is_file() else 0
    return re.sub(r"[^A-Za-z0-9_-]+", "_", p.stem)[:40] + "_" + hashlib.sha1(f"{p.name}:{size}".encode()).hexdigest()[:8]


def workdir_for(src: str, root: Path = OUT) -> Path:
    d = Path(root) / source_id(src)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _check(cancel):
    if cancel and cancel():
        raise Stopped("stopped")


def cached_source(wd: Path, video: bool) -> Optional[Path]:
    want = (".mp4", ".mkv", ".webm", ".mov") if video else MEDIA_EXT
    for p in sorted(Path(wd).glob("source.*")):
        if p.suffix.lower() in want and p.stat().st_size > 1000:
            return p
    return None


def _ytdlp_opts(wd: Path, video: bool, captions: bool) -> dict:
    opts = {
        "outtmpl": str(Path(wd) / "source.%(ext)s"),
        "format": VIDEO_FORMAT if video else AUDIO_FORMAT,
        "quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
        # SponsorBlock only reads the public ad ranges for this video id; nothing about the user is sent
        "postprocessors": [{"key": "SponsorBlock", "categories": SPONSOR_CATS, "when": "after_filter"}],
    }
    if video:
        opts["merge_output_format"] = "mp4"
    if captions:
        opts.update({"writeautomaticsub": True, "writesubtitles": True, "subtitlesformat": "json3",
                     "subtitleslangs": ["en", "en-orig", "en-US", "en-GB"]})
    return opts


def meta_from_info(info: dict) -> dict:
    sb = [{"start": float(c.get("start_time") or 0), "end": float(c.get("end_time") or 0),
           "category": c.get("category") or c.get("title") or ""}
          for c in (info.get("sponsorblock_chapters") or [])]
    chapters = [{"start": float(c.get("start_time") or 0), "end": float(c.get("end_time") or 0), "title": c.get("title") or ""}
                for c in (info.get("chapters") or [])]
    return {"id": info.get("id") or "", "title": info.get("title") or "", "uploader": info.get("uploader") or info.get("channel") or "",
            "duration": float(info.get("duration") or 0), "chapters": chapters, "sponsor": sb,
            "url": info.get("webpage_url") or ""}


def download(url: str, wd: Path, video: bool = False, captions: bool = False, log: LogFn = print) -> Tuple[Path, dict]:
    """Download the episode (audio only unless video=True). Returns (file, meta)."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed, so a YouTube link can't be downloaded. Use a local file instead.") from exc
    log(f"Downloading the {'video' if video else 'audio'} of {url} …")
    with yt_dlp.YoutubeDL(_ytdlp_opts(wd, video, captions)) as ydl:
        info = ydl.extract_info(url, download=True)
    meta = meta_from_info(info or {})
    src = cached_source(wd, video)
    if not src:
        raise RuntimeError("The download finished but no media file was written (the video may be private or age-gated).")
    log(f"Downloaded {src.name} ({src.stat().st_size / 1e6:.0f} MB), {meta['duration'] / 60:.0f} min, "
        f"{len(meta['sponsor'])} ad/promo range(s) from SponsorBlock")
    return src, meta


def media_duration(path: Path) -> float:
    try:
        from providers.media_clip.ffmpeg_clip import _ffprobe
        out = subprocess.run([_ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out or 0)
    except Exception:
        return 0.0


def get_source(src: str, wd: Path, video: bool = False, captions: bool = False, log: LogFn = print, cancel=None) -> Tuple[Path, dict]:
    """The media file + meta, from the cache when there is one."""
    _check(cancel)
    meta_p = Path(wd) / "meta.json"
    if not is_url(src):
        p = Path(src).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"Podcast file not found: {p}")
        meta = {"id": source_id(src), "title": p.stem, "uploader": "", "duration": media_duration(p), "chapters": [], "sponsor": [],
                "url": ""}
        meta_p.write_text(json.dumps(meta, indent=1))
        return p, meta
    have = cached_source(wd, video)
    if have and meta_p.is_file():
        log(f"Using the downloaded {have.name}")
        return have, json.loads(meta_p.read_text())
    path, meta = download(src, wd, video=video, captions=captions, log=log)
    meta_p.write_text(json.dumps(meta, indent=1))
    return path, meta


# ---------- video sections (only the parts the cut uses) ----------

SECTION_PAD = 0.6
SECTION_WORKERS = 4
SECTION_FORMAT = "bv*[height<=1080][ext=mp4][vcodec^=avc1]/bv*[height<=1080][ext=mp4]/bv*[height<=1080]/b[height<=1080]"


def section_path(wd: Path, a: float, b: float) -> Path:
    return Path(wd) / "sections" / f"sec_{int(round(a * 100)):08d}_{int(round(b * 100)):08d}.mp4"


def fetch_sections(src: str, wd: Path, spans, log: LogFn = print, cancel=None) -> dict:
    """{(a, b): (file, file_start)} for each source span the cut uses. A YouTube video is downloaded span by span
    (only those seconds, cut exactly on the times asked), so a 3-hour episode costs a few hundred MB instead of
    several GB. A local video file is used as it is (file_start 0). Audio-only sources give {}."""
    out = {}
    if not is_url(src):
        p = Path(src).expanduser()
        if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4v"):
            return {(a, b): (p, 0.0) for a, b in spans}
        return {}
    import yt_dlp
    from concurrent.futures import ThreadPoolExecutor
    from yt_dlp.utils import download_range_func

    def one(k: int, a: float, b: float):
        _check(cancel)
        s0, s1 = max(0.0, a - SECTION_PAD), b + SECTION_PAD
        dest = section_path(wd, s0, s1)
        if not (dest.is_file() and dest.stat().st_size > 10000):
            dest.parent.mkdir(parents=True, exist_ok=True)
            log(f"Video section {k + 1}/{len(spans)} ({s1 - s0:.0f} s at {int(s0) // 60}:{int(s0) % 60:02d})")
            opts = {"outtmpl": str(dest.with_suffix("")) + ".%(ext)s", "format": SECTION_FORMAT, "quiet": True,
                    "no_warnings": True, "noprogress": True, "noplaylist": True,
                    "download_ranges": download_range_func(None, [(s0, s1)]), "force_keyframes_at_cuts": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([src])
            got = [p for p in dest.parent.glob(dest.stem + ".*") if p.suffix != ".part"]
            if not got:
                raise RuntimeError(f"The video section at {s0:.0f} s could not be downloaded.")
            if got[0] != dest:
                got[0].replace(dest)
        return (a, b), (dest, s0)

    # SECTION_WORKERS at once: one at a time, a 32-section cut spent 25 min here (each section = a page lookup + a
    # short download + a keyframe cut, mostly waiting on the network)
    with ThreadPoolExecutor(max_workers=SECTION_WORKERS) as pool:
        for key, val in pool.map(lambda kab: one(*kab), [(k, a, b) for k, (a, b) in enumerate(spans)]):
            out[key] = val
    return out


# ---------- words ----------

def caption_words(data: dict) -> List[Word]:
    """Words from a YouTube json3 caption file. Automatic captions carry only a start time per word (tOffsetMs). A word
    is given a spoken length from its letters (about 0.12 s + 0.065 s a letter, never past the next word), so real
    silences show up as gaps: the picker needs those to end thoughts, and cuts land in them instead of inside a word."""
    words: List[Word] = []
    for ev in data.get("events", []) or []:
        segs = ev.get("segs") or []
        t0 = (ev.get("tStartMs") or 0) / 1000.0
        dur = (ev.get("dDurationMs") or 0) / 1000.0
        items = []
        for s in segs:
            txt = (s.get("utf8") or "").replace("\n", " ")
            for k, piece in enumerate(txt.split()):
                items.append((piece, t0 + (s.get("tOffsetMs") or 0) / 1000.0 + 0.01 * k))
        for i, (w, s) in enumerate(items):
            nxt = items[i + 1][1] if i + 1 < len(items) else t0 + dur
            spoken = 0.12 + 0.065 * len(w)
            words.append((w, round(s, 3), round(max(s + 0.05, min(nxt - 0.01, s + spoken)), 3)))
    words.sort(key=lambda w: w[1])
    return [w for w in words if w[0] not in ("[Music]", "[Applause]", "[Laughter]")]


SR = 16000
CHUNK_S = 600.0     # Whisper piece length
PUNCT_PROMPT = "Hello, and welcome back. So, what do you think? I think it's simple: you start. Then you keep going!"


def chunk_bounds(audio, chunk_s: float = CHUNK_S, search_s: float = 8.0, sr: int = SR) -> List[Tuple[int, int]]:
    """Sample ranges of about chunk_s each, every cut at the quietest 50 ms within search_s of the mark (between words)."""
    import numpy as np
    n = len(audio)
    step, frame = int(chunk_s * sr), int(0.05 * sr)
    cuts = [0]
    while n - cuts[-1] > step + int(chunk_s * 0.3 * sr):     # the last piece may run up to 30% long
        mark = cuts[-1] + step
        lo, hi = max(cuts[-1] + frame, mark - int(search_s * sr)), min(n - frame, mark + int(search_s * sr))
        seg = np.abs(np.asarray(audio[lo:hi], dtype=np.float32))
        k = len(seg) // frame
        if k < 1:
            cuts.append(mark)
            continue
        energy = seg[:k * frame].reshape(k, frame).mean(axis=1)
        cuts.append(lo + int(energy.argmin()) * frame + frame // 2)
    cuts.append(n)
    return list(zip(cuts[:-1], cuts[1:]))


def whisper_words(media: Path, wd: Path, model_size: str = "small", log: LogFn = print) -> List[Word]:
    """Whisper word times with punctuation kept (video_generator.transcribe_audio lower-cases and strips it)."""
    import video_generator as vg
    from providers.media_clip.ffmpeg_clip import _ffmpeg
    wav = Path(wd) / "speech16k.wav"
    if not wav.is_file():
        log("Preparing the audio for Whisper …")
        subprocess.run([_ffmpeg(), "-v", "error", "-nostdin", "-y", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                       check=True, timeout=3600)
    from faster_whisper import decode_audio
    audio = decode_audio(str(wav), sampling_rate=SR)
    total = len(audio) / SR
    words: List[Word] = []
    shown = -1
    import whisper_backend
    gpu = whisper_backend.gpu_available()
    log("Whisper on the Apple GPU (mlx)" if gpu else "Whisper on the CPU")
    lang = None      # found on the first piece and kept: a piece guessing on its own once came back in Welsh
    with vg._WHISPER_LOCK:
        model = None
        # Whisper carries each window's text into the next, so once it writes one window without full stops it never
        # writes another (a real 146-min talk: none after minute 33). So: ~10-min pieces cut at a quiet moment, each
        # starting fresh on a punctuated prompt, and no carry-over inside a piece either.
        for a, b in chunk_bounds(audio):
            piece = audio[a:b]
            segments = None
            if gpu:
                segments, info = whisper_backend.transcribe_gpu(piece, model_size, log=log, initial_prompt=PUNCT_PROMPT,
                                                                condition_on_previous_text=False, language=lang,
                                                                hallucination_silence_threshold=2.0)
                gpu = segments is not None
            if segments is None:
                model = model or vg._whisper_model(model_size)
                segments, info = model.transcribe(piece, word_timestamps=True, vad_filter=True, beam_size=1, language=lang,
                                                  condition_on_previous_text=False, initial_prompt=PUNCT_PROMPT)
            off = a / SR
            for seg in segments:
                for w in (seg.words or []):
                    txt = (w.word or "").strip()
                    if txt:
                        words.append((txt, round(off + float(w.start), 3), round(off + float(w.end), 3)))
                done = off + float(seg.end)
                if total > 0 and int(100 * done / total) // 10 > shown:
                    shown = int(100 * done / total) // 10
                    log(f"Transcribing … {shown * 10}% ({int(done) // 60} of {int(total) // 60} min)")
            if lang is None and words:
                lang = getattr(info, "language", None) or None
    try:
        wav.unlink()
    except OSError:
        pass
    return words


def get_words(src: str, media: Path, wd: Path, captions: bool = False, model_size: str = "small", log: LogFn = print,
              cancel=None) -> List[Word]:
    """words.json from the cache, else from YouTube captions (captions=True) or Whisper."""
    _check(cancel)
    cache = Path(wd) / "words.json"
    if cache.is_file():
        words = [tuple(w) for w in json.loads(cache.read_text())]
        if words:
            log(f"Using the saved transcript ({len(words)} words)")
            return words
    words: List[Word] = []
    if captions:
        subs = sorted(Path(wd).glob("source*.json3"))
        if not subs and is_url(src):
            try:
                import yt_dlp
                opts = _ytdlp_opts(wd, False, True)
                opts.update({"skip_download": True, "postprocessors": []})
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info(src, download=True)
            except Exception as exc:
                log(f"Could not get YouTube captions ({exc}); using Whisper")
            subs = sorted(Path(wd).glob("source*.json3"))
        if subs:
            words = caption_words(json.loads(subs[0].read_text()))
            log(f"Got {len(words)} words from YouTube captions")
    if not words:
        words = whisper_words(media, wd, model_size=model_size, log=log)
        log(f"Got {len(words)} words from Whisper")
    if not words:
        raise RuntimeError("No words were heard in this podcast.")
    cache.write_text(json.dumps(words))
    return words
