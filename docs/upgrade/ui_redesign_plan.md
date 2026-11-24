# App redesign plan (2026-11-21)

Goal: a cleaner, faster-to-use app for 30+ styles, **without breaking any workflow**
(every style's Generate / Render, CSV load, Voiceover, Visuals, Export, autorun, exe/dmg).

## What we have today

- `app.py` (17.4k lines) owns all state and handlers; `ui/shell.py` draws the chrome
  (top bar, sidebar, page stack, inspector, status bar).
- 15 nav pages (`ui/theme.py` `NAV_ITEMS`): 8 production + 7 tools.
- 30+ styles in one Visual Director picker (`ui/style_registry.py` groups, `ui/style_pages.py`).
  Groups were patched in one style at a time, so "Documentary" now holds Roblox Cinema,
  and kids/host/character styles have no group of their own.
- Newer styles are self-contained modules: `ui/*_section.py` with `build(app, parent)`.
- Tokens in `ui/theme.py`, shared widgets in `ui/widgets.py`, contrast enforced by
  `test_ui_design_system.py`.
- `app.py` is in `test_fixtures/weather_protected.json`: removed lines need approval,
  so app.py changes must be **additive**.

## Rules that protect the workflows

1. **No engine code changes.** Only `ui/` and additive hooks in `app.py`.
2. **Same names.** Every `app._xxx` widget/var that handlers, saved state or tests read
   keeps its name. New layout re-parents or wraps; it doesn't rename.
3. **Section contract stays.** `ui/*_section.py` `build(app, parent)` is unchanged; the new
   style page is a frame they drop into.
4. **Old nav keys stay valid** (`"visual_plan"`, `"render"`, ...) so `navigate()` calls
   everywhere keep working.
5. **New look behind a switch** (Settings: "New layout", default on after Phase 2 passes),
   with the old layout one click away for one release.
6. **Nothing starts until Generate** still holds: no new screen auto-runs anything.
7. One phase = one commit, asked for first. Only touched tests run.

## Phases

### Phase 0: Safety net (first, before any look change)
- `test_ui_workflow_smoke.py`: build the app headless, open every nav page and every
  style page, and check that each style's Generate / Render / file-pick controls exist
  and are wired to the same callbacks as before.
- Snapshot the saved-state keys (`export_state.py`, per-style settings) so a redesign
  can't lose a saved setting.
- One screenshot per page for before/after.

### Phase 1: Design tokens v2
- New palette, spacing scale, type scale and radius in `ui/theme.py` (values only;
  the contrast test keeps them readable in light and dark).
- Buttons, cards, inputs and segmented controls restyled in `ui/widgets.py`, so every
  page changes at once with no layout risk.

### Phase 2: New shell and navigation
- **Home** page: Continue last project, recent projects, Start new video (pick style).
- Sidebar: **Create** (Home, Styles) / **Production** as a numbered stepper
  (Script > Voiceover > Visuals > Audio > Graphics > Export, each with a done/needs tick) /
  **Tools** (collapsed).
- One **Jobs** drawer in the status bar: every running render across styles (from the
  existing `_*_running` flags), with progress, Stop and Open output. Read-only over
  current state at first.

### Phase 3: Style picker and style pages
- Search box, favourites and recent styles at the top.
- Regrouped: General, Maps, Space, Explainers, Theory (Rep/Cat/Jung/Elder/Survival),
  Documentary, Kids (Kids Learn, Kids Stories, Toon Tales, Toy Vehicles),
  Characters & Hosts (Stickman, Prepper Host, Roblox Cinema), Specialist.
- One shared style-page template: header + "What you need" checklist (CSV / voice /
  music, ticked when picked) + the style's own controls + Generate / Render + outputs.
  Existing sections move in unchanged.

### Phase 4: Core pages polish
- Script, Voiceover, Visuals (scene list + inspector), Export: same controls,
  clearer layout, empty states, and one primary action per page.

### Phase 5: Release check
- Full suite once (asked for first), Windows CI, exe/dmg build, the old-layout switch
  tested, and one real Generate > Render per style family.

## Not in this plan
- Moving off CustomTkinter to a web/Electron UI. It would mean rewriting the 17k-line
  controller and every section, and would risk exactly the workflows we want to keep.
  We can revisit it later as its own project.

## Status 2026-11-24 (uncommitted)

- Phase 1 v2: "Obsidian + Iris" palette in `ui/theme.py` (deeper neutrals, indigo accent #5B5FEF dark / #4C55E0 light,
  softer family tints); Segoe UI on Windows (CustomTkinter's default Roboto is rarely installed there).
- Phase 2: Overview is now **Home** (recent projects, start with a pinned/recent style, running jobs).
  Sidebar numbers the 7 production steps (`T.STEP_KEYS`) and ticks each when done; Tools folds (remembered).
  Status bar **Jobs** button + drawer (`ui/jobs.py`, `ui/home.py`): every `_*_running` flag, Stop = the style's own cancel.
  One additive hook in `app._build_ui` calls `ui.home.install`.
- Phase 3: Quick-pick chips (pinned + recent) under the style search; Pin button on each style page (`ui/prefs.py`,
  saved through `app._settings`).
- Phase 4: shortcuts (Cmd on Mac / Ctrl on Windows): 0 Home, 1-7 steps, J Jobs, K search styles, comma Settings.
- Phase 5: UI tests + smoke pass. Not done: Windows CI run, exe/dmg build, full suite, by-eye screenshot check.
