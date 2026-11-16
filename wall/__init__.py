"""Wall Moments (docs/wall/PLAN.md): for about a fifth of a film the camera pulls back from full-screen footage onto one dark evidence
wall, where counters, stamps, pen rings, notes and red string land on the spoken word, then dives into the next clip full screen.

    wall.engine    the renderer: Wall(params).render(t), lay_wall(t, dur, params) as a shared-renderer layer ("wall.lay_wall")
    wall.frames    decoded clip frames for the video prints (one ffmpeg decode per clip window, ping-pong past it)
    wall.facts     numbers, money, percents, dates, verdicts and twist lines in a sentence, timed by the Whisper words
    wall.planner   picks the wall moments (about 20 % of the runtime) and writes each one's params
    wall.sfx       the synthesised item sounds (assets/bundled-sfx/wall/, made once)
    wall.probe     stills and a contact sheet of a plan, for checks without a render
Style-neutral: a style only needs an adapter that hands the planner its scenes and swaps its layers (aviation/wall_moments.py).
"""

from .engine import CARDS, lay_wall  # noqa: F401
