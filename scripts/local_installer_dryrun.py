#!/usr/bin/env python3
"""
Local-only dry-run for the optional macOS online installer stub
(not the primary team deliverable).

Does NOT invent GitHub Release URLs. Serves tiny fake archives from localhost,
patches the *built* .app bundled manifest (with backup), then you can click
through the progress UI.

WARNING: A successful dry-run extracts to real destinations:
  - /Applications/Semantic YT Studio.app  (fake stub .app)
  - ~/.videogen/runtime/qwen/darwin-arm64/
  - ~/.videogen/qwen3-tts/Qwen3-TTS-12Hz-1.7B-Base/

Production repo file tts/install_manifest.json is left unchanged.

Usage:
  python3 scripts/local_installer_dryrun.py          # prepare + serve
  # in another terminal / after launch:
  open dist/Semantic YT Studio Setup.app

  python3 scripts/local_installer_dryrun.py --restore # restore bundled manifest
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import shutil
import socketserver
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "dist" / "Semantic YT Studio Setup.app"
BUNDLED = APP / "Contents" / "Resources" / "tts" / "install_manifest.json"
BACKUP = BUNDLED.with_suffix(".json.bak-dryrun")
PORT = 8765
HOST = "127.0.0.1"
BASE = f"http://{HOST}:{PORT}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_fixtures(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)

    # Fake macOS .app zip
    app_zip = out / "Semantic-YT-Studio-macOS.zip"
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "Semantic YT Studio.app" / "Contents" / "MacOS"
        bundle.mkdir(parents=True)
        exe = bundle / "Semantic YT Studio"
        exe.write_text("#!/bin/sh\necho dry-run Semantic YT Studio\n", encoding="utf-8")
        exe.chmod(0o755)
        (bundle.parent / "Info.plist").write_text(
            '<?xml version="1.0"?><plist version="1.0"><dict>'
            "<key>CFBundleIdentifier</key><string>com.example.dryrun</string>"
            "</dict></plist>\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(app_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in Path(tmp).rglob("*"):
                if p.is_file():
                    zf.write(p, p.relative_to(tmp).as_posix())

    # Fake runtime tar.gz
    runtime_tg = out / "qwen-runtime-darwin-arm64.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir()
        py = bin_dir / "python3"
        py.write_text("#!/bin/sh\necho dry-run python\n", encoding="utf-8")
        py.chmod(0o755)
        with tarfile.open(runtime_tg, "w:gz") as tf:
            tf.add(bin_dir, arcname="bin")

    # Tiny model blob
    model_blob = out / "config.json"
    model_blob.write_text('{"dry_run": true}\n', encoding="utf-8")

    files = {
        "app": app_zip,
        "runtime": runtime_tg,
        "model": model_blob,
    }
    return {k: (v, _sha256(v), v.stat().st_size) for k, v in files.items()}


def _write_manifest(fixtures: dict) -> dict:
    app_path, app_sha, app_size = fixtures["app"]
    rt_path, rt_sha, rt_size = fixtures["runtime"]
    model_path, model_sha, model_size = fixtures["model"]
    return {
        "schema_version": 1,
        "platforms": {
            "darwin-arm64": {
                "app": [
                    {
                        "url": f"{BASE}/{app_path.name}",
                        "sha256": app_sha,
                        "filename": app_path.name,
                        "size": app_size,
                    }
                ],
                "runtime": [
                    {
                        "url": f"{BASE}/{rt_path.name}",
                        "sha256": rt_sha,
                        "filename": rt_path.name,
                        "size": rt_size,
                    }
                ],
                "model": {
                    "source": "huggingface",
                    "repo_id": "local/dry-run",
                    "revision": "main",
                    "files": [
                        {
                            "url": f"{BASE}/{model_path.name}",
                            "sha256": model_sha,
                            "filename": "config.json",
                            "path": "config.json",
                            "size": model_size,
                        }
                    ],
                },
            },
            # Keep win key present but unpublished so we don't accidentally claim Windows is ready.
            "win-amd64": {
                "app": [{"url": "", "sha256": "", "filename": "Semantic-YT-Studio-Windows.zip", "size": 0}],
                "runtime": [{"url": "", "sha256": "", "filename": "qwen-runtime-win-amd64.zip", "size": 0}],
                "model": {
                    "source": "huggingface",
                    "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                    "revision": "main",
                    "files": [],
                },
            },
        },
    }


def prepare_and_patch(serve_dir: Path) -> None:
    if not APP.is_dir():
        raise SystemExit(f"Missing {APP}. Build first: pyinstaller -y Installer.spec")
    if not BUNDLED.is_file():
        raise SystemExit(f"Missing bundled manifest at {BUNDLED}")

    fixtures = _make_fixtures(serve_dir)
    manifest = _write_manifest(fixtures)

    if not BACKUP.is_file():
        shutil.copy2(BUNDLED, BACKUP)
        print(f"Backed up bundled manifest -> {BACKUP}")
    BUNDLED.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Patched bundled manifest -> {BUNDLED}")
    print(f"Serving fixtures from {serve_dir}")
    for name, (path, sha, size) in fixtures.items():
        print(f"  {name}: {path.name} ({size} bytes) sha256={sha[:12]}…")


def restore() -> None:
    if not BACKUP.is_file():
        raise SystemExit(f"No backup at {BACKUP}")
    shutil.copy2(BACKUP, BUNDLED)
    BACKUP.unlink()
    print(f"Restored bundled manifest from backup: {BUNDLED}")


def serve(serve_dir: Path) -> None:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(serve_dir), **kwargs)

    with socketserver.TCPServer((HOST, PORT), Handler) as httpd:
        print(f"\nHTTP server: {BASE}/")
        print("Launch installer:")
        print(f"  open {APP}")
        print("When done: Ctrl+C, then:")
        print("  python3 scripts/local_installer_dryrun.py --restore")
        print(
            "\nNote: dry-run writes to /Applications/Semantic YT Studio.app and ~/.videogen/ …"
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def main() -> int:
    global PORT, BASE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--restore", action="store_true", help="Restore .app bundled empty manifest")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    PORT = args.port
    BASE = f"http://{HOST}:{PORT}"

    if args.restore:
        restore()
        return 0

    serve_dir = ROOT / "dist" / "installer_dryrun_fixtures"
    prepare_and_patch(serve_dir)
    serve(serve_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
