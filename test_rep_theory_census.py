"""No graphic Rep Theory already shows may disappear: the feature count over the 14 new-topic scripts never drops a feature to 0 or below half its baseline
(reptheory/census.py; after a deliberate change, `python -m reptheory.census --write-baseline`)."""
from __future__ import annotations
import json, unittest

from reptheory import census

class FeatureCount(unittest.TestCase):
    def test_nothing_we_have_is_lost(self):
        base = json.loads(census.BASELINE.read_text()); now = census.measure()
        self.assertEqual(census.check(now, base), [])

    def test_the_check_catches_a_lost_feature(self):
        self.assertTrue(census.check({"look:pose": 0}, {"look:pose": 30})); self.assertTrue(census.check({"look:pose": 10}, {"look:pose": 30})); self.assertFalse(census.check({"look:pose": 20}, {"look:pose": 30}))

if __name__ == "__main__":
    unittest.main()
