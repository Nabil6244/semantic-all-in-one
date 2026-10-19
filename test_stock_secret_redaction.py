"""Real-log bug (#016): a Pixabay 400 error quoted its request URL, which carries the API key, into generation.log;
and a Flow-prompt-length query (over Pixabay's 100 characters) failed every search."""
import unittest

from providers.stock.base import Candidate, StockBackend, StockProvider, redact_url_secrets
from providers.stock.pixabay import MAX_QUERY_CHARS, PixabayBackend, fit_query


class _Resp:
    def __init__(self, status, reason="Bad Request"):
        self.status_code = status
        self.reason = reason

    def raise_for_status(self):   # what requests would raise: the full URL with the key
        raise RuntimeError(f"{self.status_code} Client Error: {self.reason} for url: https://pixabay.com/api/?key=SECRET123&q=x")


class _FailingBackend(StockBackend):
    name = "fake"

    def search(self, query, media_type="all", per_page=15):
        raise RuntimeError("400 Client Error: Bad Request for url: https://pixabay.com/api/videos/?key=SECRET123&q=long+words&per_page=15")


class RedactionTest(unittest.TestCase):
    def test_search_failure_log_hides_the_key(self):
        lines = []
        StockProvider([_FailingBackend()])._search_all("long words", "video", lines.append)
        self.assertEqual(len(lines), 1)
        self.assertNotIn("SECRET123", lines[0])
        self.assertIn("key=REDACTED", lines[0])
        self.assertIn("per_page=15", lines[0])   # the rest of the message is kept

    def test_pixabay_error_has_no_url(self):
        for status in (400, 403, 500):
            with self.assertRaises(RuntimeError) as cm:
                PixabayBackend._raise_for_status(_Resp(status))
            self.assertNotIn("SECRET123", str(cm.exception))
            self.assertNotIn("http", str(cm.exception))
            self.assertIn(str(status), str(cm.exception))

    def test_ok_response_passes(self):
        PixabayBackend._raise_for_status(_Resp(200, "OK"))

    def test_redact_variants(self):
        self.assertEqual(redact_url_secrets("a?api_key=abc&b=1"), "a?api_key=REDACTED&b=1")
        self.assertEqual(redact_url_secrets("x access_token=zz y"), "x access_token=REDACTED y")
        self.assertEqual(redact_url_secrets("no secrets here"), "no secrets here")
        self.assertEqual(redact_url_secrets(""), "")


class QueryLengthTest(unittest.TestCase):
    def test_long_query_is_cut_at_a_word(self):
        long = ("Cinematic, realistic CG for a serious space documentary, like NASA and ESA mission animation: deep black space, "
                "a real star field, accurate scale and lighting")
        q = fit_query(long)
        self.assertLessEqual(len(q), MAX_QUERY_CHARS)
        self.assertTrue(long.startswith(q))
        self.assertFalse(q.endswith(" "))
        self.assertTrue(long[len(q)] == " ")

    def test_short_query_unchanged(self):
        self.assertEqual(fit_query("Voyager 1 launch 1977"), "Voyager 1 launch 1977")
        self.assertEqual(fit_query("  two   spaces "), "two spaces")

    def test_one_huge_word(self):
        self.assertEqual(len(fit_query("x" * 300)), MAX_QUERY_CHARS)


if __name__ == "__main__":
    unittest.main()
