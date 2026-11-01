"""Phase 2 meters and numbers (reptheory/meters.py): tokens, weight share, load meter, effort bar, stopwatch target; any topic, from sentence shape."""
from __future__ import annotations
import unittest

from reptheory import meters as M, variety as V, states as ST, draw as D, scenes as S

def _sc(text, no=1, s0=0.0, kind="callout"):
    ws = [{"w": w, "t0": s0 + 0.3 * i} for i, w in enumerate(text.split())]
    return {"no": no, "kind": kind, "start": s0, "end": s0 + 0.3 * len(ws) + 1, "words": ws, "text": text, "pages": [], "decisions": [], "art": "", "section": "X", "topic": ""}

class Meters(unittest.TestCase):
    def test_tokens(self):
        for t, want in (("Three holds of 15 seconds.", (3, 15, "S")), ("Do 4 sets of 10 reps.", (4, 10, "REPS")), ("Then 6 x 2 s lift-offs.", (6, 2, "S"))):
            tk = M.tokens(_sc(t), t); self.assertEqual((tk["sets"], tk["each"], tk["unit"]), want, t)
        self.assertIsNone(M.tokens(_sc("Hold it for a while."), "Hold it for a while."))
        self.assertIn("tokens", V.evidence(_sc("Three holds of 15 seconds.")))

    def test_share_steps(self):
        t = "A knee push up puts half your body weight on your hands, a normal push up two thirds of your weight."
        sh = M.share(_sc(t), t); self.assertEqual([s["value"] for s in sh["steps"]], [50, 66])
        self.assertIsNone(M.share(_sc("Half the battle is sleep."), "Half the battle is sleep."))

    def test_meter_and_effort_overlays(self):
        scs = [_sc("Add ten kilos and it gets heavier at the far end.", 1, 0.0), _sc("Shorten the bar and it gets lighter.", 2, 5.0), _sc("Push as hard as you can.", 3, 9.0)]
        self.assertGreaterEqual(M.plan(scs), 3); self.assertGreater(scs[0]["meter"]["steps"][-1]["level"], scs[1]["meter"]["steps"][-1]["level"]); self.assertIn("effort", scs[2])
        self.assertNotIn("meter", _sc("Sleep eight hours.")); 

    def test_stopwatch_target(self):
        scs = [_sc("Now hold it there for 30 seconds.", 1, 0.0), _sc("The moment your hips drop, stop the clock.", 2, 4.0)]
        ST.stopwatch(scs); self.assertEqual(scs[0]["stopwatch"]["target"], 30)

    def test_draws(self):
        ctx = D.Ctx(640, 360)
        for t, k in (("Three holds of 15 seconds.", "tokens"), ("Half your body weight is on your hands.", "share")):
            sc = _sc(t); sc[k] = V.evidence(sc)[k][1]; sc["kind"] = k; self.assertEqual(S.frame(ctx, sc, 2.0, tag=False).size, (640, 360))

if __name__ == "__main__":
    unittest.main()
