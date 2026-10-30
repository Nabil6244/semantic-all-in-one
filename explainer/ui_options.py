"""The Explainer's option menus in the Hybrid panel (footage share and source, board background, narrator look), kept here so the application only adds a few lines that call it (patch v2).
Everything is stored in the application's machine settings under explainer_footage_share, explainer_footage_source, explainer_background and explainer_narrator; explainer.integration reads
the same keys when 'Direct with Explainer' runs. Defaults when nothing was saved: no footage, stock_video, paper, serious. The menus are usable only while the Explainer switch is on."""

from __future__ import annotations

from typing import Any, Dict

SHARE_LABELS = (("Off", 0.0), ("10%", 0.1), ("20%", 0.2), ("30%", 0.3), ("40%", 0.4))
SOURCES = ("stock_video", "youtube_video", "flow_video", "stock_image", "flow_image")
BACKGROUNDS = ("paper", "grid", "warm", "grey")
NARRATORS = ("serious", "cartoon")
DEFAULTS = {"share": "Off", "source": "stock_video", "background": "paper", "narrator": "serious"}
KEYS = {"share": "explainer_footage_share", "source": "explainer_footage_source", "background": "explainer_background", "narrator": "explainer_narrator"}


def from_settings(settings: Any) -> Dict[str, str]:
    """The four options as the menus show them, from the saved settings; anything missing or unknown is the default (a hand-edited share shows the nearest choice)."""
    s = settings if isinstance(settings, dict) else {}
    try:
        share = float(s.get(KEYS["share"], 0.0) or 0.0)
    except (TypeError, ValueError):
        share = 0.0
    if share != share or share <= 0:
        share = 0.0
    label = min(SHARE_LABELS, key=lambda lv: abs(lv[1] - share))[0]
    pick = lambda key, allowed: s.get(KEYS[key]) if s.get(KEYS[key]) in allowed else DEFAULTS[key]
    return {"share": label, "source": pick("source", SOURCES), "background": pick("background", BACKGROUNDS), "narrator": pick("narrator", NARRATORS)}


def save(app: Any, _value: Any = None) -> None:
    """A menu changed: remember all four options in the machine settings (nothing else in the application reads them)."""
    v = getattr(app, "_hybrid_explainer_opt_vars", None)
    if not v:
        return
    ok = lambda key, allowed: v[key].get() if v[key].get() in allowed else DEFAULTS[key]
    app._settings[KEYS["share"]] = dict(SHARE_LABELS).get(v["share"].get(), 0.0)
    app._settings[KEYS["source"]] = ok("source", SOURCES)
    app._settings[KEYS["background"]] = ok("background", BACKGROUNDS)
    app._settings[KEYS["narrator"]] = ok("narrator", NARRATORS)
    try:
        app._persist_global_settings()
    except Exception:
        pass


HINT = "Copy the CSV prompt, paste it into any AI with your script and save the reply as a .csv. Then click Load beat CSV and pick it, then Direct with Explainer."


def _show(widget: Any, on: bool) -> None:
    """grid() / grid_remove(): a hidden widget keeps its place and comes back exactly where it was."""
    if widget is None:
        return
    try:
        if not on:
            widget.grid_remove()
            widget._explainer_hidden = True
        elif getattr(widget, "_explainer_hidden", False):   # only a widget this hid is put back
            widget.grid()
            widget._explainer_hidden = False
    except Exception:
        pass


def _hint_label(app: Any) -> Any:
    """The one-line help under the Hybrid buttons (app.py builds it after install runs, so it is found when first needed)."""
    label = getattr(app, "_hybrid_hint_label", None)
    if label is not None:
        return label
    controls = getattr(getattr(app, "_hybrid_explainer_opt_row", None), "master", None)
    controls = getattr(controls, "master", None)
    for w in (controls.grid_slaves(row=3, column=0) if controls is not None else []):
        try:
            if str(w.cget("text")).startswith("Load beat CSV:"):
                app._hybrid_hint_label, app._hybrid_hint_text = w, w.cget("text")
                return w
        except Exception:
            pass
    return None


def sync(app: Any, *_args: Any) -> None:
    """The Explainer switch decides which buttons the panel shows. On: Load beat CSV, Copy the CSV prompt (the Explainer scene prompt),
    Direct with Explainer and the four menus. Off: the Hybrid Map buttons only. Write plan with AI and Copy graphics prompt make Hybrid
    Map plans, so the Explainer page does not show them."""
    on = bool(app._hybrid_explainer_var.get())
    for menu in getattr(app, "_hybrid_explainer_opt_menus", []):
        menu.configure(state="normal" if on else "disabled")
    _show(getattr(app, "_hybrid_plan_btn", None), not on)
    _show(getattr(app, "_hybrid_copy_graphics_btn", None), not on)
    _show(getattr(app, "_hybrid_explainer_btn", None), on)
    _show(getattr(app, "_hybrid_explainer_opt_row", None), on)
    copy_btn = getattr(app, "_hybrid_copy_csv_btn", None)
    if copy_btn is not None:
        style = "explainer_scenes" if on else "hybrid"
        copy_btn.configure(command=lambda: app._copy_csv_prompt(style, app._hybrid_status_var, graphics=False))
    label = _hint_label(app)
    if label is not None:
        label.configure(text=HINT if on else getattr(app, "_hybrid_hint_text", ""))


def take_scene_csv(app: Any, path: str) -> bool:
    """Load beat CSV picked the Explainer's scene CSV (explainer/scene_csv.py): it is not a Hybrid plan, so it is not imported. It is kept
    as the loaded file, and Direct with Explainer reads it. -> False for any other file (the Hybrid import goes on as before)."""
    from . import scene_csv

    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError:
        return False
    if not scene_csv.is_scene_csv(text):
        return False
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    if not bool(app._hybrid_explainer_var.get()):
        app._hybrid_status_var.set(f"{name} is an Explainer scene CSV. Turn on the Explainer look, then load it again.")
        return True
    scenes = sum(1 for line in text.splitlines() if line.lstrip().lower().startswith("scene,"))
    app._hybrid_file_var.set(str(path))
    app._hybrid_status_var.set(f"Scene CSV loaded: {name}, {scenes} scene(s). Click Direct with Explainer to make the plan.")
    return True


def needs_scenes(plan: Any) -> bool:
    """True when the plan has a clip that names one of the application's footage sources (the Visual Plan then has something to fetch)."""
    for beat in getattr(plan, "beats", None) or []:
        for clip in getattr(beat, "clips", None) or []:
            asset = str(getattr(clip, "asset", "") or "")
            if ":" in asset and asset.split(":", 1)[0] in SOURCES:
                return True
    return False


def is_explainer_plan(plan: Any) -> bool:
    """True when the plan was made by the Explainer director: its board and cartoon clips are files under <hybrid dir>/explainer/ (a plan from Write plan with AI or a loaded CSV has none)."""
    for beat in getattr(plan, "beats", None) or []:
        for clip in getattr(beat, "clips", None) or []:
            asset = str(getattr(clip, "asset", "") or "").replace("\\", "/")
            if "/explainer/" in asset or asset.startswith("explainer/"):
                return True
    return False


def status_after_plan(app: Any, plan: Any) -> None:
    """The status line after an Explainer plan: it asks for 'Get scenes' only when there is something to fetch (board and cartoon clips are already files)."""
    if not needs_scenes(plan):
        app._hybrid_status_var.set(f"Explainer plan ready: {len(plan.beats)} beats. Check the plan, then render as usual.")


def install(app: Any, actions: Any) -> None:
    """Build the four option menus in a row under the Explainer switch (row 3 of the Hybrid actions frame) and keep them in step with the switch."""
    import customtkinter as ctk

    app._hybrid_explainer_opt_vars = {k: ctk.StringVar(value=v) for k, v in from_settings(app._settings).items()}
    app._hybrid_explainer_opt_menus = []
    opts = ctk.CTkFrame(actions, fg_color="transparent")
    opts.grid(row=3, column=0, columnspan=5, sticky="w", pady=(6, 0))
    for col, (label, key, values) in enumerate((("Footage", "share", [lab for lab, _v in SHARE_LABELS]), ("from", "source", list(SOURCES)),
                                               ("Background", "background", list(BACKGROUNDS)), ("Narrator", "narrator", list(NARRATORS)))):
        ctk.CTkLabel(opts, text=label, font=ctk.CTkFont(size=11)).grid(row=0, column=2 * col, padx=(0 if col == 0 else 14, 4))
        menu = ctk.CTkOptionMenu(opts, values=values, variable=app._hybrid_explainer_opt_vars[key], command=lambda value=None: save(app, value),
                                 width=130 if key == "source" else 90, font=ctk.CTkFont(size=11))
        menu.grid(row=0, column=2 * col + 1)
        app._hybrid_explainer_opt_menus.append(menu)
    app._hybrid_explainer_opt_row = opts
    # The panel's one Copy the CSV prompt (row 0, column 2): sync points it at the scene prompt while the Explainer look is on.
    try:
        app._hybrid_copy_csv_btn = next(iter(actions.grid_slaves(row=0, column=2)), None)
    except Exception:
        app._hybrid_copy_csv_btn = None
    app._hybrid_explainer_var.trace_add("write", lambda *a: sync(app))
    sync(app)
    if hasattr(actions, "after_idle"):
        actions.after_idle(lambda: sync(app))   # again once app.py has built the hint line under the buttons
