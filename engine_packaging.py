"""Which files of the newer engines ship inside the packaged app (used by VideoGenerator.spec, tested by test_engine_packaging.py).

Roblox Cinema, Voxel Map, Kids Learn (cartoon3d-engine) and City Timelapse (citygrow-engine) load their engine folder by path at run time, so PyInstaller never sees them:
every file they read has to be listed here. Also shipped: the music beds in assets/music (Roblox Cinema, Voxel Map and City Timelapse mix them in),
the Rules Horror prompts and samples, and the three.js add-ons these 3D pages import beyond what StarMap ships.

Files are the engine's git-tracked files (outputs, caches and worlds are git-ignored), minus tests, docs and build-only tools."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Tuple

ENGINES = ("roblox-cinema-engine", "voxelmap-engine", "cartoon3d-engine", "citygrow-engine")
SKIP_DIRS = {"test", "tests", "docs", "out", "cache", "worlds", "node_modules", "__pycache__", "authoring", "revisions"}
SKIP_SUFFIXES = {".md", ".pyc"}
THREE_ADDONS = ("three/examples/jsm/environments/RoomEnvironment.js", "three/examples/jsm/geometries/RoundedBoxGeometry.js",
                "three/examples/jsm/objects/Reflector.js", "three/examples/jsm/loaders/GLTFLoader.js",
                "three/examples/jsm/utils/BufferGeometryUtils.js")
RULES_HORROR_DATA = ("*.txt", "samples/*.csv", "samples/*.txt")


def _tracked(root: Path, folder: str) -> List[Path]:
    """git-tracked files under folder; without git, every file outside the skipped folders."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", folder], cwd=str(root), capture_output=True, timeout=60)
        names = [n for n in out.stdout.decode("utf-8", "replace").split("\0") if n] if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        names = []
    if names:
        return [root / n for n in names]
    return [p for p in (root / folder).rglob("*") if p.is_file()]


def _keep(rel: Path) -> bool:
    return not (set(rel.parts[1:-1]) & SKIP_DIRS) and rel.suffix.lower() not in SKIP_SUFFIXES


def data_files(root: Path) -> List[Tuple[str, str]]:
    """(source file, destination folder relative to the app root) for every shipped file. Raises when something the app needs is missing."""
    root = Path(root)
    out: List[Tuple[str, str]] = []
    add = lambda f: out.append((str(f), str(f.parent.relative_to(root)).replace("\\", "/")))
    for eng in ENGINES:
        files = [f for f in _tracked(root, eng) if f.is_file() and _keep(f.relative_to(root))]
        if not any(f.name == "runner.py" for f in files):
            raise FileNotFoundError(f"{root / eng / 'runner.py'} is missing: {eng} must ship with the app")
        for f in files:
            add(f)
    music = sorted((root / "assets" / "music").glob("*.opus"))
    if not music:
        raise FileNotFoundError(f"{root / 'assets' / 'music'} has no .opus beds: Roblox Cinema and Voxel Map need them")
    for f in music:
        add(f)
    for pattern in RULES_HORROR_DATA:
        for f in sorted((root / "rules_horror").glob(pattern)):
            add(f)
    nm = root / "starmap-engine" / "node_modules"
    for rel in THREE_ADDONS:
        f = nm / rel
        if not f.is_file():
            raise FileNotFoundError(f"{f} is missing: run `npm ci --omit=dev` in starmap-engine/ before building")
        add(f)
    return list(dict.fromkeys(out))


# Python modules the engine scripts import (they are loaded by path, so PyInstaller cannot follow them).
HIDDEN_IMPORTS = ["script_runner", "wave", "argparse", "runpy", "zlib", "kids_audio", "kids_audio.chant", "kids_audio.library",
                  "kids_audio.mixer", "kids_audio.synth", "rules_horror", "rules_horror.runner", "rules_horror.profiles"]
