#!/usr/bin/env python3
"""
Probe Hugging Face for Qwen3-TTS model files and print JSON suitable for
tts/install_manifest.json → platforms.*.model.files.

Usage:
  python scripts/fill_model_manifest.py
  python scripts/fill_model_manifest.py --repo Qwen/Qwen3-TTS-12Hz-1.7B-Base --revision main

Requires network. Does not modify install_manifest.json unless --write is passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import requests

DEFAULT_REPO = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
DEFAULT_REVISION = "main"
# Skip LFS pointer-only / tiny sidecar noise; keep real weight blobs + configs.
SKIP_SUFFIXES = (".gitattributes", ".gitignore", "README.md", "LICENSE", "LICENSE.txt")


def list_repo_files(repo_id: str, revision: str) -> list[dict[str, Any]]:
    url = f"https://huggingface.co/api/models/{repo_id}/tree/{revision}?recursive=1"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise SystemExit(f"Unexpected HF API response: {type(data)}")
    return [e for e in data if e.get("type") == "file"]


def sha256_url(url: str) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with requests.get(url, stream=True, timeout=(30, 120)) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=1 << 20):
            if not chunk:
                continue
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def build_files(
    repo_id: str,
    revision: str,
    *,
    compute_hash: bool,
) -> list[dict[str, Any]]:
    entries = list_repo_files(repo_id, revision)
    files: list[dict[str, Any]] = []
    for entry in entries:
        path = str(entry.get("path") or "")
        if not path or path.endswith(SKIP_SUFFIXES) or Path(path).name in SKIP_SUFFIXES:
            continue
        size = int(entry.get("size") or 0)
        item: dict[str, Any] = {
            "path": path,
            "filename": Path(path).name,
            "url": "",
            "sha256": "",
            "size": size,
        }
        # Prefer LFS sha if present (oid is often raw hex; sometimes "sha256:...")
        lfs = entry.get("lfs") or {}
        oid = str(lfs.get("oid") or "").strip()
        if oid.startswith("sha256:"):
            item["sha256"] = oid.split(":", 1)[1].lower()
        elif len(oid) == 64 and all(c in "0123456789abcdef" for c in oid.lower()):
            item["sha256"] = oid.lower()
        elif compute_hash:
            resolve = f"https://huggingface.co/{repo_id}/resolve/{revision}/{path}"
            print(f"hashing {path} …", file=sys.stderr)
            digest, got = sha256_url(resolve)
            item["sha256"] = digest
            item["size"] = got
        files.append(item)
    files.sort(key=lambda f: f["path"])
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument(
        "--hash",
        action="store_true",
        help="Download files missing LFS oid to compute sha256 (slow / large).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write files[] into tts/install_manifest.json for both platforms.",
    )
    args = parser.parse_args()

    files = build_files(args.repo, args.revision, compute_hash=args.hash)
    payload = {
        "source": "huggingface",
        "repo_id": args.repo,
        "revision": args.revision,
        "files": files,
    }
    print(json.dumps(payload, indent=2))

    if args.write:
        root = Path(__file__).resolve().parent.parent
        manifest_path = root / "tts" / "install_manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for plat in data.get("platforms", {}).values():
            plat["model"] = payload
        manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {manifest_path}", file=sys.stderr)

    missing = sum(1 for f in files if not f.get("sha256"))
    if missing:
        print(
            f"Note: {missing} file(s) have empty sha256 — re-run with --hash or rely on LFS oids.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
