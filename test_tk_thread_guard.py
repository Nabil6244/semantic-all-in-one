"""The app froze for good (2026-10-19): a worker importing a module (holding its import lock) had its garbage collection delete a Tk variable,
which waits for the main thread, while the main thread waited for that import. tk_thread_guard queues such cleanups for the main thread."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# the main thread, inside mainloop, waits for a lock a worker holds while the worker lets go of a Tk variable (and a Pillow image)
SCENARIO = textwrap.dedent("""
    import gc, sys, threading, time, tkinter
    sys.path.insert(0, %r)
    GUARD = sys.argv[1] == "guard"
    if GUARD:
        import tk_thread_guard
        tk_thread_guard.install()
    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:
        print("NO_DISPLAY", exc); sys.exit(0)
    root.withdraw()
    lock = threading.Lock()
    holder = {"var": tkinter.StringVar(root, value="x")}
    try:
        from PIL import Image, ImageTk
        holder["img"] = ImageTk.PhotoImage(Image.new("RGB", (4, 4)), master=root)
    except Exception:
        pass
    ready = threading.Event()
    result = {}

    def worker():
        with lock:                       # like a module being imported
            ready.set()
            time.sleep(0.3)              # the main thread is now waiting for the lock
            holder.clear()               # last references go: __del__ runs on this thread
            gc.collect()

    def on_main():
        ready.wait(5)
        t0 = time.monotonic()
        result["got"] = lock.acquire(timeout=3)
        result["s"] = time.monotonic() - t0
        if result["got"]:
            lock.release()
        if GUARD:
            tk_thread_guard.drain()
            result["left"] = tk_thread_guard.pending()
        root.after(50, root.quit)

    threading.Thread(target=worker, daemon=True).start()
    root.after(0, on_main)
    root.mainloop()
    print("RESULT", result["got"], round(result["s"], 2), result.get("left"))
""") % str(ROOT)


def run(mode: str) -> str:
    r = subprocess.run([sys.executable, "-c", SCENARIO, mode], capture_output=True, text=True, timeout=60)
    return (r.stdout or "") + (r.stderr or "")[-500:]


class Deadlock(unittest.TestCase):
    def test_with_the_guard_the_main_thread_gets_the_lock_at_once_and_the_cleanup_runs_on_it(self):
        out = run("guard")
        if out.startswith("NO_DISPLAY"):
            self.skipTest(out.strip())
        self.assertIn("RESULT True", out, out)
        secs = float(out.split("RESULT True")[1].split()[0])
        self.assertLess(secs, 1.5, out)
        self.assertTrue(out.strip().endswith(" 0"), out)          # nothing left queued after drain()

    def test_without_the_guard_it_deadlocks_until_the_timeout(self):
        out = run("plain")
        if out.startswith("NO_DISPLAY"):
            self.skipTest(out.strip())
        self.assertIn("RESULT False", out, out)               # the lock never came: the freeze the guard removes


class Install(unittest.TestCase):
    def test_install_is_idempotent_and_main_thread_cleanup_is_unchanged(self):
        out = subprocess.run([sys.executable, "-c", textwrap.dedent(f"""
            import sys, tkinter; sys.path.insert(0, {str(ROOT)!r})
            import tk_thread_guard as g
            a = g.install(); b = g.install()
            print(sorted(a) == sorted(b), "tkinter.Variable" in a, "tkinter.Image" in a, "tkinter.font.Font" in a)
            print(tkinter.Variable.__del__.__wrapped__.__qualname__)
        """)], capture_output=True, text=True, timeout=60).stdout.split()
        self.assertEqual(out[:4], ["True", "True", "True", "True"])
        self.assertEqual(out[4], "Variable.__del__")

    def test_the_app_installs_it_before_the_window_and_drains_it_on_the_main_thread(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        main = src[src.index("def main() -> None:"):]
        self.assertLess(main.index("_guard_tk_cleanups()"), main.index("VideoGeneratorApp()"))
        pump = src[src.index("    def _pump_thread_after(self) -> None:"):src.index("    def __init__(self) -> None:\n        super().__init__()")]
        self.assertIn("_drain_tk_cleanups()", pump)
        self.assertIn('hiddenimports += ["tk_thread_guard"]', (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
