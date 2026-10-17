"""Design-system guards found by scripts/ui_audit.py: readable token pairs in
both themes, segmented controls readable in both states, and the top-bar hint
shortening with "…" instead of losing its end."""

import unittest

import ui.theme as T


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


SURFACES = ("background", "surface", "surface_alt", "surface_elevated", "row_alt")
TEXT_TOKENS = ("text_primary", "text_secondary", "text_tertiary", "accent_text")


class TokenContrast(unittest.TestCase):
    def test_every_text_token_reads_on_every_surface(self):
        for name, table in (("dark", T.DARK), ("light", T.LIGHT)):
            for text in TEXT_TOKENS:
                for surface in SURFACES:
                    with self.subTest(theme=name, text=text, surface=surface):
                        self.assertGreaterEqual(contrast(table[text], table[surface]), 4.5)

    def test_accent_text_reads_on_the_selected_row(self):
        for table in (T.DARK, T.LIGHT):
            self.assertGreaterEqual(contrast(table["accent_text"], table["selected"]), 4.5)

    def test_white_on_accent_buttons(self):
        for table in (T.DARK, T.LIGHT):
            self.assertGreaterEqual(contrast(table["accent_on_accent"], table["accent"]), 4.5)
            self.assertGreaterEqual(contrast(table["accent_on_accent"], table["accent_hover"]), 4.5)

    def test_light_status_text_on_surfaces(self):
        for token in ("success", "warning", "error"):
            for surface in ("background", "surface", "surface_elevated", "surface_alt"):
                with self.subTest(token=token, surface=surface):
                    self.assertGreaterEqual(contrast(T.LIGHT[token], T.LIGHT[surface]), 4.5)

    def test_segmented_selection_is_readable_and_visible(self):
        th = {}
        try:
            import customtkinter as ctk

            T.install_ctk_theme()
            th = ctk.ThemeManager.theme["CTkSegmentedButton"]
        except Exception:
            self.skipTest("customtkinter not available")
        for i, table in enumerate((T.LIGHT, T.DARK)):
            text, sel, unsel = th["text_color"][i], th["selected_color"][i], th["unselected_color"][i]
            self.assertGreaterEqual(contrast(text, sel), 4.5)
            self.assertGreaterEqual(contrast(text, unsel), 4.5)
            self.assertGreater(contrast(sel, unsel), 1.5)  # the selected segment stands out

    def test_text_hierarchy_kept(self):
        for table, bg in ((T.DARK, "surface"), (T.LIGHT, "surface")):
            p, s, t = (contrast(table[k], table[bg]) for k in ("text_primary", "text_secondary", "text_tertiary"))
            self.assertGreater(p, s)
            self.assertGreater(s, t)

    def test_token_values_unique_within_each_theme_for_new_tokens(self):
        # The live theme switch maps colours by value; a new token must not collide with an old one.
        for table in (T.DARK, T.LIGHT):
            others = {k: v.upper() for k, v in table.items() if k != "accent_text"}
            self.assertNotIn(table["accent_text"].upper(), others.values())


class NoInvisibleButtons(unittest.TestCase):
    """A CTkButton with fg_color="transparent" and no text_color inherits the theme's white
    text-on-accent colour: invisible on a light background (found in Settings and four dialogs)."""

    FILES = ("app.py", "ui/views.py", "ui/shell.py", "ui/widgets.py", "project_picker.py")

    def test_transparent_buttons_set_their_text_colour(self):
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parent
        bad = []
        for rel in self.FILES:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", getattr(node.func, "id", None))
                if name != "CTkButton" or any(k.arg is None for k in node.keywords):
                    continue  # **style dicts (make_button / button_style) set both colours
                kw = {k.arg: k.value for k in node.keywords}
                fg = kw.get("fg_color")
                if isinstance(fg, ast.Constant) and fg.value == "transparent" and "text_color" not in kw:
                    bad.append(f"{rel}:{node.lineno}")
        self.assertEqual(bad, [])


try:
    import customtkinter as ctk

    _root = ctk.CTk()
    _root.withdraw()
    HAVE_TK = True
except Exception:
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "needs Tk")
class ElidingLabelTest(unittest.TestCase):
    def setUp(self):
        from ui.widgets import ElidingLabel

        self.var = ctk.StringVar(master=_root, value="short")
        self.frame = ctk.CTkFrame(_root, width=200, height=40)
        self.frame.grid_propagate(False)
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.pack()
        self.label = ElidingLabel(self.frame, source_var=self.var, font=ctk.CTkFont(size=12), anchor="w")
        self.label.grid(row=0, column=0, sticky="ew")
        _root.update()

    def tearDown(self):
        self.frame.destroy()

    def shown(self):
        return self.label._label.cget("text")

    def test_short_text_is_shown_whole_without_tooltip(self):
        self.assertEqual(self.shown(), "short")
        self.assertEqual(self.label._tip.text, "")

    def test_long_text_is_shortened_to_fit_and_tooltip_has_it_all(self):
        long = "Import your CSV, then check the plan before you press Generate on the Visuals page " * 2
        self.var.set(long)
        _root.update()
        shown = self.shown()
        self.assertTrue(shown.endswith("…"))
        self.assertTrue(long.startswith(shown[:-1].rstrip()))
        self.assertLessEqual(self.label._font.measure(shown), self.label.winfo_width())
        self.assertEqual(self.label._tip.text, long)
        self.var.set("short again")
        _root.update()
        self.assertEqual(self.shown(), "short again")
        self.assertEqual(self.label._tip.text, "")

    def test_elide_helper(self):
        from ui.widgets import ElidingLabel

        measure = len  # one "pixel" per character
        self.assertEqual(ElidingLabel.elide("abcdef", 10, measure), "abcdef")
        self.assertEqual(ElidingLabel.elide("abcdef", 4, measure), "abc…")
        self.assertEqual(ElidingLabel.elide("abcdef", 0, measure), "abcdef")

    def test_destroy_removes_the_trace(self):
        before = len(self.var.trace_info())
        self.label.destroy()
        self.assertEqual(len(self.var.trace_info()), before - 1)


if __name__ == "__main__":
    unittest.main()
