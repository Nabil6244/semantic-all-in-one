"""Entry point: python -m installer"""

from __future__ import annotations

import sys


def _show_error(message: str) -> None:
    print(message, file=sys.stderr)
    # Only open a dialog for the packaged stub; CLI / CI must exit cleanly without Tk.
    if not getattr(sys, "frozen", False):
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Semantic YT Studio Setup", message)
        root.destroy()
    except Exception:
        pass


def main() -> int:
    from installer.manifest import ManifestError, load_manifest, platform_spec, require_published
    from installer.platform import UnsupportedPlatformError, detect_platform

    try:
        platform_id = detect_platform()
    except UnsupportedPlatformError as exc:
        _show_error(str(exc))
        return 2

    try:
        data = load_manifest()
        spec = platform_spec(data, platform_id)
        require_published(spec)
    except ManifestError as exc:
        _show_error(str(exc))
        return 1

    from installer.ui import run_ui

    run_ui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
