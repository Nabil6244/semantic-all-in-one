"""Every running job across all styles, read from the app's own ``_<x>_running`` flags.

Read-only over existing state: nothing here starts work. Stop calls the same cancel the style's own Stop button calls,
so a job stopped from the Jobs drawer ends exactly as if it was stopped on its page.
A flag this table does not name still shows (as its own name), so a new style's job is never hidden.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable, List, NamedTuple, Optional

# flag -> (label, how to stop it). "app:<method>" calls app.<method>(); "mod:<module>" calls ui.<module>.cancel(app);
# "pkg:<dotted.module>" calls <dotted.module>.cancel(app) (styles whose page lives in their own package).
KNOWN = {
    "_running": ("Generate", "app:_on_cancel"),
    "_hybrid_running": ("Hybrid Map", "app:_on_hybrid_cancel"),
    "_overscaled_running": ("Overscaled", "app:_on_overscaled_cancel"),
    "_starmap_running": ("StarMap", "app:_on_starmap_cancel"),
    "_whatif_running": ("What If", "app:_on_whatif_cancel"),
    "_pakmap_running": ("pakMap", "app:_on_pakmap_cancel"),
    "_weather_running": ("Weather", "pkg:weather.app_section"),
    "_war_running": ("War Documentary", "pkg:cinematic_explainer.war.app_section"),
    "_rt_running": ("Rep Theory", "pkg:reptheory.app_section"),
    "_health_running": ("Health Cinema", "pkg:health_cinema.app_section"),
    "_av_running": ("Aviation", "mod:aviation_section"),
    "_ct_running": ("City Timelapse", "mod:city_timelapse_section"),
    "_ff_running": ("Food Files", "mod:foodfiles_section"),
    "_gl_running": ("Game Launch", "mod:game_launch_section"),
    "_kl_running": ("Kids Learn", "mod:kids_learn_section"),
    "_ks_running": ("Kids Stories", "mod:kids_stories_section"),
    "_oc_running": ("Ocean", "mod:ocean_section"),
    "_pc_running": ("Podcast Cut", "mod:podcastcut_section"),
    "_ph_running": ("Prepper Host", "mod:prepper_host_section"),
    "_ds_running": ("Doodle Survival", "mod:doodle_section"),
    "_pt_running": ("Product Trailer", "mod:product_trailer_section"),
    "_rc_running": ("Roblox Cinema", "mod:roblox_cinema_section"),
    "_rh_running": ("Rules Horror", "mod:rules_horror_section"),
    "_sm_running": ("Stickman", "mod:stickman_section"),
    "_st_running": ("Senior Trivia", "mod:senior_trivia_section"),
    "_ad_running": ("AI Director", "mod:ai_director_section"),
    "_tt_running": ("Toon Tales", "mod:toon_tales_section"),
    "_tv_running": ("Toy Vehicles", "mod:toy_vehicles_section"),
    "_vm_running": ("Voxel Map", "mod:voxelmap_section"),
}


class Job(NamedTuple):
    flag: str
    label: str
    stop: Optional[Callable[[], None]]


def _stopper(app: Any, how: str) -> Optional[Callable[[], None]]:
    if how.startswith("app:"):
        fn = getattr(app, how[4:], None)
        return fn if callable(fn) else None
    if how.startswith("mod:"):
        name = how[4:]

        def run() -> None:
            mod = importlib.import_module(f"ui.{name}")
            mod.cancel(app)

        return run
    if how.startswith("pkg:"):
        dotted = how[4:]

        def run_pkg() -> None:
            importlib.import_module(dotted).cancel(app)

        return run_pkg
    return None


def stop_all(app: Any) -> None:
    """Ask every running job to stop (used on quit). One failing stop never blocks the others."""
    for job in running(app):
        if job.stop is not None:
            try:
                job.stop()
            except Exception:
                pass


def running(app: Any) -> List[Job]:
    """The jobs running right now, Generate first then A-Z."""
    out: List[Job] = []
    try:
        items = list(vars(app).items())
    except Exception:
        return out
    for flag, value in items:
        if value is not True or not flag.endswith("_running") or not flag.startswith("_"):
            continue
        label, how = KNOWN.get(flag, (flag.strip("_").replace("_running", "").replace("_", " ").title(), ""))
        out.append(Job(flag, label, _stopper(app, how)))
    out.sort(key=lambda j: (j.flag != "_running", j.label.lower()))
    return out


def any_running(app: Any) -> bool:
    return bool(running(app))
