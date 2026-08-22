"""Repair extracted Qwen runtimes (zip symlink stubs + missing +x bits)."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def repair_extracted_runtime(root: Path) -> None:
    """
    Zip archives often store Unix symlinks as tiny text files naming the target
    (e.g. bin/python → contents \"python3.12\") without the execute bit.

    Recreate real symlinks and chmod bin/Scripts executables so the worker can start.
    """
    root = Path(root)
    if not root.is_dir():
        return

    for path in root.rglob("*"):
        try:
            if not path.is_file() or path.is_symlink():
                continue
        except OSError:
            continue

        try:
            size = path.stat().st_size
        except OSError:
            continue

        if 0 < size < 256:
            try:
                text = path.read_text(encoding="utf-8").strip()
            except Exception:
                text = ""
            if (
                text
                and "\n" not in text
                and "/" not in text
                and "\\" not in text
                and not text.startswith("#!")
            ):
                target = path.parent / text
                if target.exists():
                    try:
                        path.unlink()
                        path.symlink_to(text)
                    except OSError:
                        pass
                    continue

        if _should_be_executable(path):
            try:
                mode = path.stat().st_mode
                if not (mode & stat.S_IXUSR):
                    path.chmod(mode | 0o755)
            except OSError:
                pass


def _should_be_executable(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    if "bin" in parts or "scripts" in parts:
        return True
    if name.startswith("python"):
        return True
    if name.endswith((".exe", ".dll", ".so", ".dylib")):
        return True
    # Shebang scripts anywhere under the runtime
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def ensure_python_executable(path: Path) -> bool:
    """Return True if path is a runnable python binary (chmod if needed)."""
    path = Path(path)
    try:
        if not path.is_file():
            return False
        if path.is_symlink() and not path.resolve().exists():
            return False
        # Reject unrepaired zip symlink stubs
        size = path.stat().st_size
        if 0 < size < 64:
            data = path.read_bytes()
            if b"\0" not in data:
                text = data.decode("utf-8", errors="ignore").strip()
                if text and "\n" not in text and (path.parent / text).exists():
                    return False
        if not os.access(path, os.X_OK):
            path.chmod(path.stat().st_mode | 0o111)
        return os.access(path, os.X_OK)
    except OSError:
        return False
