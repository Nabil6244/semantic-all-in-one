"""Activity log: widget writes are batched, ordered, and capped only when the
project log on disk already has every line."""

import unittest

try:
    import tkinter as tk

    import customtkinter as ctk

    import app as app_mod

    _root = ctk.CTk()
    _root.withdraw()
    HAVE_TK = True
except Exception:  # headless CI without a display
    HAVE_TK = False


class _Workspace:
    def __init__(self):
        self.written = []

    def append_log(self, chunk):
        self.written.append(chunk)


def _fake(workspace=None, visible=True):
    A = app_mod.VideoGeneratorApp
    f = type("FakeApp", (), {
        name: getattr(A, name)
        for name in ("_append_log", "_flush_log_ui", "_flush_log_disk", "_schedule_log_disk_flush",
                     "_toggle_activity_log", "_clear_log",
                     "_LOG_UI_FLUSH_MS", "_LOG_VIEW_MAX_LINES", "_LOG_VIEW_KEEP_LINES")
    })()
    f.after = _root.after
    f._heartbeat_on = True
    f.status_line_var = tk.StringVar(master=_root)
    f._workspace = workspace
    f._log_disk_buf, f._log_disk_scheduled = [], False
    f._log_backlog, f._log_ui_buf, f._log_ui_scheduled = [], [], False
    f._log_visible = visible
    f.log_box = ctk.CTkTextbox(_root)
    f.log_box.configure(state="disabled")
    f.log_toggle_btn = ctk.CTkButton(_root)
    return f


def _text(f):
    return f.log_box.get("1.0", "end-1c")


@unittest.skipUnless(HAVE_TK, "needs Tk")
class ActivityLogBatching(unittest.TestCase):
    def test_lines_arrive_in_order_in_one_flush(self):
        f = _fake()
        inserts = []
        real_insert = f.log_box.insert
        f.log_box.insert = lambda *a, **k: (inserts.append(a), real_insert(*a, **k))
        for i in range(200):
            f._append_log(f"line {i}\n")
        self.assertEqual(_text(f), "")  # nothing written until the flush
        self.assertEqual(f.status_line_var.get(), "line 199")  # status updates at once
        f._flush_log_ui()
        self.assertEqual(_text(f), "".join(f"line {i}\n" for i in range(200)))
        self.assertEqual(len(inserts), 1)

    def test_flush_runs_from_the_event_loop(self):
        f = _fake()
        f._append_log("hello\n")
        _root.after(f._LOG_UI_FLUSH_MS + 100, _root.quit)
        _root.mainloop()
        self.assertEqual(_text(f), "hello\n")

    def test_hidden_log_keeps_backlog_and_shows_it_when_opened(self):
        f = _fake(visible=False)
        f._append_log("a\n")
        f._append_log("b\n")
        f._toggle_activity_log()
        self.assertEqual(_text(f), "a\nb\n")

    def test_hiding_with_pending_lines_moves_them_to_backlog(self):
        f = _fake()
        f._append_log("a\n")
        f._log_visible = False
        f._flush_log_ui()
        self.assertEqual(_text(f), "")
        f._toggle_activity_log()
        self.assertEqual(_text(f), "a\n")

    def test_clear_drops_pending_lines(self):
        f = _fake()
        f._append_log("a\n")
        f._clear_log()
        f._flush_log_ui()
        self.assertEqual(_text(f), "")

    def test_worker_thread_lines_go_through_the_ui_queue(self):
        import queue
        import threading

        f = _fake()
        f._ui_queue = queue.Queue()
        t = threading.Thread(target=lambda: [f._append_log(f"w{i}\n") for i in range(3)])
        t.start()
        t.join()
        self.assertEqual(f._log_ui_buf, [])  # the worker touched nothing Tk-side
        self.assertEqual([f._ui_queue.get_nowait() for _ in range(3)], [("log", "w0\n"), ("log", "w1\n"), ("log", "w2\n")])

    def test_cap_applies_only_with_project_log_on_disk(self):
        ws = _Workspace()
        f = _fake(workspace=ws)
        f._LOG_VIEW_MAX_LINES, f._LOG_VIEW_KEEP_LINES = 100, 60
        for i in range(150):
            f._append_log(f"line {i}\n")
        f._flush_log_ui()
        f._flush_log_disk()
        lines = _text(f).splitlines()
        self.assertIn("earlier lines are in the project log", lines[0])
        self.assertEqual(lines[-1], "line 149")
        self.assertLessEqual(len(lines), 62)
        self.assertEqual("".join(ws.written).count("\n"), 150)  # disk has everything

        g = _fake(workspace=None)
        g._LOG_VIEW_MAX_LINES, g._LOG_VIEW_KEEP_LINES = 100, 60
        for i in range(150):
            g._append_log(f"line {i}\n")
        g._flush_log_ui()
        self.assertEqual(len(_text(g).splitlines()), 150)  # no disk copy -> never trimmed


if __name__ == "__main__":
    unittest.main()
