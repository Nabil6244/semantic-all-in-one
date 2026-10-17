"""Two managers on one folder (a Generate run and a Retry from the Visual Plan) must not undo each other's records:
the Voyager run (2026-10-16) fetched 061.mp4 on Retry, then the run's stale copy saved scene 61 back as FAILED."""

import tempfile
import threading
import unittest
from pathlib import Path

from asset_manager import AssetManifest


class SharedManifest(unittest.TestCase):
    def test_a_stale_copy_never_puts_back_an_old_record(self):
        with tempfile.TemporaryDirectory() as d:
            run, retry = AssetManifest(Path(d)), AssetManifest(Path(d))
            run.set("61", {"status": "failed", "error": "stock asset exceeded 200MB"})
            retry.set("61", {"status": "complete", "local_path": "061.mp4"})
            run.set("60", {"status": "complete", "local_path": "060.png"})       # the run saves another scene later
            fresh = AssetManifest(Path(d))
            self.assertEqual(fresh.get("61")["status"], "complete")
            self.assertEqual(fresh.get("60")["status"], "complete")
            self.assertEqual(run.get("61")["status"], "complete", "the run reads what the retry wrote")

    def test_writers_in_parallel_keep_every_scene(self):
        with tempfile.TemporaryDirectory() as d:
            def write(start):
                m = AssetManifest(Path(d))
                for i in range(start, 200, 4):
                    m.set(str(i), {"status": "complete", "n": i})
            threads = [threading.Thread(target=write, args=(k,)) for k in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(len(AssetManifest(Path(d)).all()), 200)


if __name__ == "__main__":
    unittest.main()
