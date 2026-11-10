"""Phase 1 diagnostic (product_trailer/diagnostic.py): the sentence kinds, and that it only reads the pipeline."""
import unittest

from product_trailer import diagnostic as D


class Kinds(unittest.TestCase):
    def test_primary_purpose_and_secondary_source(self):
        c = D.classify
        self.assertEqual(c("So what is the cause?")["primary"], "question")
        self.assertEqual(c("According to iFixit, replacing the cover costs 49 dollars without AppleCare Plus, or 19 with it.")["primary"], "price")
        self.assertEqual(c("According to iFixit, replacing the cover costs 49 dollars without AppleCare Plus, or 19 with it.")["secondary"]["source"], "iFixit")
        self.assertEqual(c("Apple says there is no software fix for the hinge problems.")["primary"], "source_claim")
        self.assertEqual(c("Some owners report cracks along the fold of the inner display.")["primary"], "reported_problem")
        self.assertEqual(c("Their fluorescent powder test also showed particles reaching the hinge area.")["primary"], "test")
        self.assertEqual(c("Tell me in the comments, and subscribe for the latest updates.")["primary"], "signoff")
        self.assertEqual(c("If you're thinking about it, wait for a clear statement on the display issue.")["primary"], "advice")
        self.assertEqual(c("On October 26, it acknowledged an inner display issue.")["primary"], "date")
        self.assertEqual(c("It has a 5.4 inch outer display and a 7.6 inch inner display.")["primary"], "spec")

    def test_quote_card_needs_source_and_a_real_claim(self):
        from product_trailer import diagnostic as X
        ok = X.proposed("Apple says there is no software fix for the hinge problems.", D.classify("Apple says there is no software fix for the hinge problems."), 4.0)
        self.assertEqual(ok["layer"], "pt_tweet")
        meta = X.proposed("Here is how Apple has responded.", D.classify("Here is how Apple has responded."), 4.0)
        self.assertNotEqual(meta["layer"], "pt_tweet")

    def test_missing_problem_footage_is_marked_not_faked(self):
        from product_trailer import diagnostic as X
        s = "Some owners report cracks along the fold of the inner display."
        r = X.proposed(s, D.classify(s), 6.0)
        self.assertFalse(r["asset_ready"])
        self.assertIn("cracked", r["required_asset"])

    def test_no_hold_for_a_long_unrelated_sentence(self):
        from product_trailer import diagnostic as X
        s = "Supply is also tight."
        self.assertNotEqual(X.proposed(s, D.classify(s), 5.0)["layer"], "hold")

    def test_old_visual_counts_generic_3d(self):
        spec = {"duration": 10, "shots": [{"start": 0, "end": 10, "kind": "product"}], "layers": []}
        self.assertEqual(D.old_visual(spec, 1, 4)["visual"], "generic 3D phone (no graphic)")


if __name__ == "__main__":
    unittest.main()
