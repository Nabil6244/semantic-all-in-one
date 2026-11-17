"""Sound-effect times for each scene template (seconds from the verse start). Plain Python, no Blender, so the song
director and the templates read the same list. Keep these in step with the animation times in templates.py."""
from toycolors import timeline as T

EGG_CRACK = 3.8                  # templates.egg: tc
WHEELS_OFF, WHEELS_ON = 1.8, 3.6  # templates.wheels: t_off, t_on

EVENTS = {
    "pour": [{"t": 1.6, "sfx": "boing"}, {"t": 2.4, "sfx": "whoosh"}, {"t": 5.0, "sfx": "sparkle"},
             {"t": 5.8, "sfx": "success"}],
    "egg": [{"t": 0.3, "sfx": "pop"}, {"t": EGG_CRACK - 0.6, "sfx": "drumroll"}, {"t": EGG_CRACK, "sfx": "burst"},
            {"t": EGG_CRACK + 0.3, "sfx": "sparkle"}, {"t": EGG_CRACK + 2.0, "sfx": "boing"}],
    "garage": [{"t": 1.6, "sfx": "drumroll"}, {"t": 2.8, "sfx": "chime"}, {"t": 3.2, "sfx": "whoosh"},
               {"t": 5.0, "sfx": "boing"}],
    "portal": [{"t": 0.3, "sfx": "chime"}, {"t": 2.7, "sfx": "whoosh"}, {"t": 3.0, "sfx": "sparkle"},
               {"t": 4.4, "sfx": "boing"}],
    "wheels": [{"t": WHEELS_OFF, "sfx": "pop"}, {"t": WHEELS_OFF + 0.8, "sfx": "boing"}, {"t": WHEELS_ON, "sfx": "whoosh"},
               {"t": WHEELS_ON + 0.7, "sfx": "ding_1"}, {"t": WHEELS_ON + 1.6, "sfx": "success"}],
    "convoy": [{"t": 0.2, "sfx": "whoosh"}] + [{"t": 4 * b * T.BEAT, "sfx": "boing"} for b in range(4)],
}
