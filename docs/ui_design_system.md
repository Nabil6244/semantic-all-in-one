# UI design system and audit

The look of every screen comes from `ui/theme.py` (tokens) and `ui/widgets.py`
(shared components). This page covers what was added in the October 2026 upgrade
and how to keep it consistent.

## Tokens

- Colours live in the `DARK` / `LIGHT` tables in `ui/theme.py`. App code uses the
  `T.XXX` / `_XXX` constants and never hex literals, so a live theme switch can
  remap them.
- **Readable by rule.** Each text token (`text_primary`, `text_secondary`,
  `text_tertiary`, `accent_text`) reaches at least 4.5:1 on every surface, in both
  themes. `test_ui_design_system.py` enforces this.
- **`accent` vs `accent_text`.**
  - `accent` is a fill colour; white text on it is at least 4.5:1.
  - `accent_text` is for accent-coloured text (links, "NEXT STEP", the stage chip).
  - No single colour can do both jobs on the dark selected background, so use
    `text_color=_ACCENT_TEXT` (app.py) or `T.ACCENT_TEXT` (ui/), never `_ACCENT`.
- **Segmented controls** use the accent tint (`accent_border`) for the selected
  segment. CustomTkinter gives a segmented button one text colour for every
  segment, so a solid accent would make the selected label unreadable.
- **Type scale:** the `FONT_*` constants. Empty states and stat values use
  `FONT_EMPTY_TITLE`, `FONT_EMPTY_ICON` and `FONT_DISPLAY`.

## Components added

- `ElidingLabel` (`ui/widgets.py`): a one-line label that shortens with "…" to the
  width it is given and shows the full text on hover. Used for the top-bar hint.
- `ui/a11y.py`: every `CTkButton` can be reached with Tab and pressed with Space
  or Return. It shows a focus ring for keyboard focus only (not after a mouse
  click), and Tab skips disabled buttons.
- `ui/ctk_perf.py`: two CustomTkinter fixes.
  1. A scrollbar redraw no longer forces a full-app layout pass. The window builds
     about 40% faster, and scrollbars paint exactly as before
     (`test_ctk_perf.py` checks this).
  2. A scrollable frame removes its app-wide mouse-wheel and Shift handlers when it
     is destroyed. Before, every closed dialog left handlers that ran on every
     later wheel event.

## Rules that tests enforce

- A `CTkButton(..., fg_color="transparent")` must set `text_color`. Otherwise it
  inherits white and is invisible in light mode (`test_ui_design_system.py`).
- A second `bind("<Destroy>", ...)` on a plain Tk/CTkToplevel window needs
  `add="+"`, or it replaces the first one. This is how the Settings window used to
  forget its last tab (`test_settings_window_lifecycle.py`).

## The audit

`scripts/ui_audit.py` builds the real app and visits every view, in every style,
at several window sizes and in both themes. With `--dialogs` it also opens
Settings (every tab), the project picker and the error dialog. It reports:

- contrast below WCAG (4.5:1, or 3:1 for large text),
- clipped text,
- controls past the window edge,
- font sizes off the scale,
- CustomTkinter placeholder text.

It never starts the Flow engine and restores `settings.json` when it finishes.

```bash
python scripts/ui_audit.py --dialogs --json /tmp/audit.json
```

`test_ui_audit.py` runs a smaller pass and requires zero findings.

Results:

| | Contrast | Off-scale fonts | Clipped | Total |
|---|---|---|---|---|
| Before (468 screens) | 3,328 | 504 | 36 | 3,868 |
| After (480 screens incl. dialogs) | 0 | 0 | 0 | 0 |
