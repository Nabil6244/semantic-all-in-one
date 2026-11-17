"""One shared timeline for the paint-board test: the song, the sounds and the Blender animation all read these times.

Everything sits on the 112 bpm grid of the `sunny` bed. Each block is one 8-beat bar pair (4.29 s).
"""
BPM = 112
BEAT = 60.0 / BPM
BLOCK = 8 * BEAT                     # 4.286 s
FPS = 24

COLOURS = [  # name, linear RGB for Blender
    ("red", (0.80, 0.03, 0.02)),
    ("orange", (0.95, 0.30, 0.01)),
    ("yellow", (0.98, 0.78, 0.02)),
    ("green", (0.10, 0.55, 0.04)),
    ("blue", (0.02, 0.18, 0.85)),
]

INTRO = 0.0                          # block 0: camera settles on the empty board
def colour_start(i):                 # blocks 1-5: one bucket each
    return BLOCK * (1 + i)
OUTRO = BLOCK * 6                    # block 6: the toy car drives in and changes colour on each sung word
DURATION = BLOCK * 7                 # 30.0 s

# sung lines: (start, text, tune). tune = one list of [midi, beats] per word; None is a rest.
_END_HI = [[72, 2], [None, 2]]
_END_LO = [[67, 2], [None, 2]]


def song_lines():
    lines = [(INTRO, "Paint with me, let's go!",
              [[[60, 1]], [[64, 1]], [[67, 1]], [[72, 1]], [[72, 2], [None, 2]]])]
    for i, (name, _) in enumerate(COLOURS):
        end = _END_HI if i % 2 == 0 else _END_LO
        first = 67 if i % 2 == 0 else 69
        lines.append((colour_start(i), f"{name.capitalize()}, {name}, this is {name}!",
                      [[[first, 1]], [[first, 1]], [[69, 1]], [[71, 1]], end]))
    lines.append((OUTRO, "Red, orange, yellow, green, blue!",
                  [[[60, 1]], [[64, 1]], [[67, 1]], [[69, 1]], [[72, 2], [None, 2]]]))
    return lines


def outro_word_times():
    """When the car changes colour: on each sung word of the recap line (beats 0-4 of the outro)."""
    return [OUTRO + b * BEAT for b in range(5)]


def sfx():
    out = [{"t": 0.25, "name": "whoosh", "gain_db": -6}]
    for i in range(len(COLOURS)):
        t = colour_start(i)
        out += [{"t": t + 0.05, "name": "pop", "gain_db": -2},
                {"t": t + 3.3, "name": "sparkle", "gain_db": -4}]
    out += [{"t": OUTRO - 0.35, "name": "whoosh", "gain_db": -4}]
    out += [{"t": t, "name": f"ding_{k + 1}", "gain_db": -8} for k, t in enumerate(outro_word_times())]
    out += [{"t": OUTRO + 6 * BEAT, "name": "success", "gain_db": -2}]
    return out
