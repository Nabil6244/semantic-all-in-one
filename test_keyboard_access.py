"""Keyboard access (ui/a11y.py): buttons are Tab-reachable, Space/Return press them,
disabled buttons are skipped, and the focus ring comes and goes without changing
the button's own border."""

import unittest

try:
    import customtkinter as ctk

    from ui import a11y
    import ui.theme as T

    a11y.install()
    _root = ctk.CTk()
    _root.geometry("400x200+30+30")
    HAVE_TK = True
except Exception:
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "needs Tk")
class KeyboardAccess(unittest.TestCase):
    def setUp(self):
        self.frame = ctk.CTkFrame(_root)
        self.frame.pack(fill="both", expand=True)
        self.clicks = []
        self.a = ctk.CTkButton(self.frame, text="A", command=lambda: self.clicks.append("A"),
                               border_width=1, border_color=T.BORDER)
        self.b = ctk.CTkButton(self.frame, text="B", command=lambda: self.clicks.append("B"), state="disabled")
        self.c = ctk.CTkButton(self.frame, text="C", command=lambda: self.clicks.append("C"))
        for w in (self.a, self.b, self.c):
            w.pack(pady=2)
        _root.deiconify()
        _root.update()

    def tearDown(self):
        self.frame.destroy()
        _root.update()

    def _focus(self, btn):
        btn._canvas.focus_force()
        _root.update()

    def test_space_and_return_press_the_focused_button(self):
        self._focus(self.a)
        self.a._canvas.event_generate("<space>")
        self.a._canvas.event_generate("<Return>")
        _root.update()
        self.assertEqual(self.clicks, ["A", "A"])

    def test_tab_order_skips_disabled_buttons(self):
        self.assertTrue(self.a._canvas.cget("takefocus"))
        self.assertEqual(str(self.a._canvas.tk_focusNext()), str(self.c._canvas))

    def test_disabled_button_ignores_keys(self):
        self.b._canvas.event_generate("<space>")
        _root.update()
        self.assertEqual(self.clicks, [])

    def test_focus_ring_shows_and_restores_the_original_border(self):
        self._focus(self.a)
        self.assertEqual(self.a.cget("border_color"), T.ACCENT_TEXT)
        self.assertGreaterEqual(self.a.cget("border_width"), T.FOCUS_RING_WIDTH)
        self._focus(self.c)
        self.assertEqual(self.a.cget("border_color"), T.BORDER)
        self.assertEqual(self.a.cget("border_width"), 1)

    def test_mouse_click_still_works(self):
        self.frame.focus_force()  # nothing focused: a click alone must not focus or ring the button
        _root.update()
        cv = self.c._canvas
        x, y = cv.winfo_width() // 2, cv.winfo_height() // 2
        cv.event_generate("<Enter>", x=x, y=y)
        cv.event_generate("<ButtonPress-1>", x=x, y=y)
        cv.event_generate("<ButtonRelease-1>", x=x, y=y)
        _root.update()
        self.assertEqual(self.clicks, ["C"])
        self.assertIsNone(getattr(self.c, "_sy_ring", None))  # a click leaves no focus ring

    def test_install_is_idempotent(self):
        self.assertTrue(a11y.install())
        btn = ctk.CTkButton(self.frame, text="D")
        self.assertTrue(btn._sy_keyboard)


if __name__ == "__main__":
    unittest.main()
