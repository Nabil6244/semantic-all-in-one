"""Health Cinema through the Visuals tab: Generate scenes fetches the footage and lists it (no video); Render uses exactly what the tab holds."""
from __future__ import annotations
import shutil, subprocess, tempfile, unittest
from pathlib import Path


ROWS = [{"text": "Your heart beats about seventy times a minute.", "start": 0.0, "end": 4.0, "visual": "footage", "footage": "heart monitor beeping"},
        {"text": "Every beat pushes blood through narrow tubes.", "start": 4.0, "end": 8.0, "visual": "footage", "footage": "blood vessels animation"}]


class HealthCinemaThroughVisuals(unittest.TestCase):
    def setUp(self):
        from health_cinema import assets
        if not assets.ffmpeg_path(): self.skipTest("ffmpeg not available")
        self.ff = assets.ffmpeg_path()
        self.d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        self.wav = self.d / "v.wav"; subprocess.run([self.ff, "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "8", str(self.wav)], check=True)
        self.clip = self.d / "stock.mp4"; subprocess.run([self.ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=640x360:r=24:d=4", "-pix_fmt", "yuv420p", str(self.clip)], check=True)

    def test_generate_scenes_lists_footage_and_render_uses_the_table(self):
        from health_cinema import engine
        asked = []
        def acq(rows):
            asked.extend(r.scene_number for r in rows)
            return {int(r.scene_number): {"ok": True, "path": str(self.clip), "source": "stock_video", "provider": "pexels", "author": "t", "source_url": "u", "query": "q", "error": ""} for r in rows}
        out = self.d / "o.mp4"
        r = engine.run_health_cinema(self.d, [dict(x) for x in ROWS], str(self.wav), str(out), quality="preview", settings={}, acquirer=acq, media_only=True)
        self.assertTrue(r["media_only"]); self.assertFalse(out.exists())
        self.assertEqual(len(r["rows"]), 2); self.assertEqual(sorted(asked), ["1", "2"])
        # the user replaced scene 1 in the Visuals tab: Render uses it and fetches only what the table does not hold
        mine = self.d / "mine.mp4"; shutil.copyfile(self.clip, mine); asked.clear()
        table = {1: {"ok": True, "path": str(mine), "source": "manual", "provider": "", "narration": r["rows"][0].script_segment, "user_override": True, "qa": {}}}
        res = engine.run_health_cinema(self.d, [dict(x) for x in ROWS], str(self.wav), str(out), quality="preview", settings={}, acquirer=acq, table=table)
        self.assertEqual(asked, ["2"])
        used = {s["scene_no"]: (s.get("asset") or {}).get("path") for s in res["scenes"] if s["kind"] == "footage"}
        self.assertIn(str(mine), used.values())
        self.assertTrue(out.is_file())

    def test_a_table_row_for_other_words_is_ignored(self):
        from health_cinema import engine
        asked = []
        def acq(rows):
            asked.extend(r.scene_number for r in rows)
            return {int(r.scene_number): {"ok": True, "path": str(self.clip), "source": "stock_video", "provider": "pexels", "query": "q", "error": ""} for r in rows}
        stale = {1: {"ok": True, "path": str(self.clip), "source": "manual", "narration": "an older script line", "qa": {}}}
        engine.run_health_cinema(self.d, [dict(x) for x in ROWS], str(self.wav), str(self.d / "o.mp4"), quality="preview", settings={}, acquirer=acq, table=stale, media_only=True)
        self.assertEqual(sorted(asked), ["1", "2"])


if __name__ == "__main__":
    unittest.main()
