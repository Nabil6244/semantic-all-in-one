"""Transitions between the sticker stage, the flight map and news (aviation/transitions.py)."""

from aviation import planner as P
from aviation import transitions as TR
from aviation import stage as G

LINES = ["In 1966 the two governments formed Malaysia-Singapore Airlines together.",
         "By 1972 the joint airline split into Singapore Airlines and Malaysia Airlines.",
         "On 4 July 2019 Vistara flight 611 took off from Srinagar for Jammu.",
         "The crew climbed to 11,000 feet over the mountains.",
         "In 1980 Singapore Airlines was renamed nothing at all, it simply grew."]


def _scenes(lines, step=6.0):
    return [{"scene_no": i + 1, "text": t, "start": i * step, "end": (i + 1) * step} for i, t in enumerate(lines)]


def test_transition_at_each_look_change_only():
    pl = P.plan(_scenes(LINES))
    tr = [s for s in pl.shots if s.get("transition")]
    kinds = [s["transition"] for s in tr]
    assert "stage->map" in kinds
    base = TR._base(pl)
    changes = sum(1 for a, b in zip(base, base[1:]) if TR.look_of(a) != TR.look_of(b) and abs(a["end"] - b["start"]) < 0.05)
    assert len(tr) == changes
    for s in tr:
        assert s["end"] - s["start"] <= max(TR.OUT_S, TR.WIPE_S) + 1e-6


def test_lay_out_shrinks_the_outgoing_stage_off_screen():
    pl = P.plan(_scenes(LINES))
    sh = next(s for s in pl.shots if s.get("transition") == "stage->map")
    p, dur = sh["params"], sh["end"] - sh["start"]
    a = TR.lay_out(0.02, dur, p)
    b = TR.lay_out(dur * 0.6, dur, p)
    assert a is not None and a.size == (G.W, G.H)
    opaque = lambda im: sum(1 for x in range(0, G.W, 16) for y in range(0, G.H, 16) if im.getpixel((x, y))[3] > 200)
    assert opaque(a) > opaque(b) * 2                     # the card has shrunk and moved off
    assert TR.lay_out(dur, dur, p) is None


def test_card_motion():
    s0, x0, _, _, a0 = TR.card_at(0.0)
    s1, x1, _, _, a1 = TR.card_at(1.0)
    assert s0 == 1.0 and s1 < 0.4 and x1 < 0 and a1 == 0.0 and a0 == 1.0


def test_no_transitions_inside_one_look():
    pl = P.plan(_scenes(LINES[:2]))
    assert not [s for s in pl.shots if s.get("transition")]
