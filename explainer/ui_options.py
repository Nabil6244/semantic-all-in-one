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


def sync(app: Any, *_args: Any) -> None:
    """The menus are usable only while the Explainer switch is on."""
    on = bool(app._hybrid_explainer_var.get())
    for menu in getattr(app, "_hybrid_explainer_opt_menus", []):
        menu.configure(state="normal" if on else "disabled")


def needs_scenes(plan: Any) -> bool:
    """True when the plan has a clip that names one of the application's footage sources (the Visual Plan then has something to fetch)."""
    for beat in getattr(plan, "beats", None) or []:
        for clip in getattr(beat, "clips", None) or []:
            asset = str(getattr(clip, "asset", "") or "")
            if ":" in asset and asset.split(":", 1)[0] in SOURCES:
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
    app._hybrid_explainer_var.trace_add("write", lambda *a: sync(app))
    sync(app)
