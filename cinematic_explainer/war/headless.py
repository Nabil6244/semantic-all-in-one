"""War Documentary without the app window: Generate scenes, then Render, with the app's own download settings.

    python3 -m cinematic_explainer.war.headless scenes <project_dir> <scenes.csv> <voiceover.mp3>
    python3 -m cinematic_explainer.war.headless render <project_dir> <scenes.csv> <voiceover.mp3> <out.mp4>

Why this exists (2026-11-09): a hand-written script built its own YouTube downloader with transcript matching off, so every clip was cut
from the blind middle of its video (a Pentagon briefing for "Moskva sinks"). Anything that runs War outside the app must build its
downloaders here, from the same settings keys and defaults the app uses (app.py: youtube_clip_duration 3.5, youtube_search_results 5,
youtube_transcript_matching True). test_war_headless.py checks the defaults still match app.py.

Word times: an Edge voice-over's <voiceover>.words.json (edge_voiceover.synthesize writes it) is used when present; otherwise faster-whisper.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
YOUTUBE_DEFAULTS: Dict[str, Any] = {"youtube_clip_duration": 3.5, "youtube_search_results": 5, "youtube_transcript_matching": True}


def load_settings() -> Dict[str, Any]:
    """The app's settings file (the project folder in development, ~/.videogen when packaged)."""
    for p in (ROOT / "settings.json", Path.home() / ".videogen" / "settings.json"):
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return {}


def youtube_options(settings: Dict[str, Any]) -> Tuple[float, int, bool]:
    """(clip seconds, search results, transcript matching) exactly as the app derives them from settings."""
    try:
        clip = float(settings.get("youtube_clip_duration", YOUTUBE_DEFAULTS["youtube_clip_duration"]))
    except (TypeError, ValueError):
        clip = YOUTUBE_DEFAULTS["youtube_clip_duration"]
    try:
        n = int(settings.get("youtube_search_results", YOUTUBE_DEFAULTS["youtube_search_results"]))
    except (TypeError, ValueError):
        n = YOUTUBE_DEFAULTS["youtube_search_results"]
    return max(1.0, min(10.0, clip)), max(1, n), bool(settings.get("youtube_transcript_matching", YOUTUBE_DEFAULTS["youtube_transcript_matching"]))


def build_manager(images_dir: Path, settings: Optional[Dict[str, Any]] = None, log: Callable[[str], None] = print) -> Any:
    """Stock + YouTube + archive + NASA, as app._build_asset_manager builds them for a CSV run (no Flow: AI clips need the app)."""
    import os

    from asset_manager import AssetManager
    from providers.stock.factory import build_stock_provider

    from . import app_section as A

    settings = load_settings() if settings is None else settings
    images_dir = Path(images_dir)
    stock = build_stock_provider(images_dir, pexels_api_key=settings.get("pexels_api_key", "") or os.environ.get("PEXELS_API_KEY", ""),
                                 pixabay_api_key=settings.get("pixabay_api_key", "") or os.environ.get("PIXABAY_API_KEY", ""), include_openverse=True)
    clip, n, transcript = youtube_options(settings)
    youtube = archive = nasa = None
    try:
        from providers.youtube.base import YouTubeProvider
        from providers.youtube.ytdlp_backend import YtDlpBackend

        youtube = YouTubeProvider(YtDlpBackend(), max_results=n, clip_duration=clip, transcript_matching=transcript)
    except RuntimeError as exc:
        log(f"[war] YouTube unavailable: {exc}")
    try:
        from providers.archive.provider import ArchiveProvider
        from providers.nasa.provider import NasaProvider

        archive, nasa = ArchiveProvider(clip_duration=clip), NasaProvider(clip_duration=clip)
    except Exception as exc:  # noqa: BLE001
        log(f"[war] archive / NASA unavailable: {exc}")
    return A.war_manager(AssetManager(images_dir, stock_provider=stock, youtube_provider=youtube, archive_provider=archive, nasa_provider=nasa,
                                      log=log, settings=settings))


def _duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def word_times(voiceover: Path) -> List[Tuple[str, float, float]]:
    side = Path(str(voiceover) + ".words.json")
    if side.is_file():
        return [(w["word"], float(w["start"]), float(w["end"])) for w in json.loads(side.read_text(encoding="utf-8"))]
    from faster_whisper import WhisperModel      # the app's own aligner needs the window; this is the same model family

    model = WhisperModel("base", compute_type="int8")
    segs, _info = model.transcribe(str(voiceover), word_timestamps=True)
    return [(w.word.strip(), float(w.start), float(w.end)) for s in segs for w in (s.words or [])]


def scenes_for(csv_path: Path, voiceover: Path, log: Callable[[str], None] = print) -> List[dict]:
    from health_cinema import scenes_csv

    from . import app_section as A

    scenes = A.read_scenes_csv(str(csv_path))
    if A.needs_alignment(scenes):
        scenes, frac = scenes_csv.align_to_words(scenes, word_times(voiceover), _duration(voiceover))
        log(f"[war] {len(scenes)} scenes aligned to the voice-over: {scenes_csv.match_note(frac)}")
    return scenes


def generate_scenes(project_dir: Path, csv_path: Path, voiceover: Path, log: Callable[[str], None] = print) -> List[Any]:
    """Fetch the CSV's footage into <project>/assets (repeats replaced). Returns the Visuals-table rows."""
    from . import app_section as A

    images = Path(project_dir) / "assets"
    images.mkdir(parents=True, exist_ok=True)
    scenes = scenes_for(Path(csv_path), Path(voiceover), log)
    mgr = build_manager(images, log=log)
    _scenes, rows = A.fetch_csv_footage(scenes, mgr, images, lambda m: log(f"[war] {m}"), ai_cap=0, fetch=True)
    return rows


def render(project_dir: Path, csv_path: Path, voiceover: Path, out: Path, log: Callable[[str], None] = print) -> Dict[str, Any]:
    """Render from what <project>/assets holds (nothing is fetched)."""
    from . import app_section as A, integration

    images = Path(project_dir) / "assets"
    scenes = scenes_for(Path(csv_path), Path(voiceover), log)
    scenes, _rows = A.fetch_csv_footage(scenes, None, images, lambda m: log(f"[war] {m}"), ai_cap=0, fetch=False)
    return integration.run_war_documentary(str(project_dir), scenes, str(voiceover), str(out),
                                           progress_cb=lambda k, m: log(f"[render] {int(k * 100)}% {m}"))


def main(argv: List[str]) -> int:
    if len(argv) >= 4 and argv[0] == "scenes":
        generate_scenes(Path(argv[1]), Path(argv[2]), Path(argv[3]))
        return 0
    if len(argv) >= 5 and argv[0] == "render":
        res = render(Path(argv[1]), Path(argv[2]), Path(argv[3]), Path(argv[4]))
        print(f"[war] done ok={res.get('ok')} out={res.get('out')}")
        return 0 if res.get("ok") else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main(sys.argv[1:]))
