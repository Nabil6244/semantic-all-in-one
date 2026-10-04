"""The AI router, entirely with fake providers and mocked HTTP: no network, no credits."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_router import AIRouter, AllRoutesUnavailable, Route, classify
from ai_router.errors import (AUTH, BAD_MODEL, BAD_REQUEST, DENIED, NETWORK, QUOTA_HARD, RATE_TEMP, SERVER, ProviderError)
from ai_router.providers import Completion, GroqProvider


class Fake:
    def __init__(self, name, script, configured=True):
        self.name, self.script, self.calls, self._cfg = name, list(script), [], configured

    def configured(self):
        return self._cfg

    def complete(self, system, user, *, model, thinking="low", max_output=0, timeout=0):
        self.calls.append(model)
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return Completion(text=step, usage={"input": 10, "output": 5})


def E(status, msg, retry=None, quota=""):
    return ProviderError(msg, status=status, retry_after=retry, quota_id=quota)


def make(gem, groq=None, state_dir=None, sleeps=None):
    clock = {"t": 1000.0}
    sl = sleeps if sleeps is not None else []

    def sleep(s):
        sl.append(s)
        clock["t"] += s

    routes = {"director": [Route("gemini", "g-main"), Route("gemini", "g-second"), Route("groq", "q-big")],
              "critic": [Route("groq", "q-big"), Route("gemini", "g-light")], "repair": [Route("groq", "q-big"), Route("gemini", "g-light")]}
    provs = {"gemini": gem, "groq": groq or Fake("groq", ["{}"], configured=False)}
    r = AIRouter(routes, provs, state_dir=state_dir, sleep=sleep, clock=lambda: clock["t"])
    return r, clock, sl


class TestClassification(unittest.TestCase):
    def test_each_failure_gets_the_right_meaning(self):
        cases = [((429, "You exceeded your current quota, please check your plan"), QUOTA_HARD),
                 ((429, "Rate limit reached ... on tokens per minute (TPM): Limit 6000. Please try again in 5.2s"), RATE_TEMP),
                 ((429, "Rate limit reached ... on tokens per day (TPD) ... Please try again in 14m2.3s"), QUOTA_HARD),
                 ((403, "Your project has been denied access. Please contact support."), DENIED),
                 ((401, "Invalid API Key"), AUTH), ((503, "The model is overloaded"), SERVER), ((404, "models/x is not found"), BAD_MODEL),
                 ((400, "Request contains an invalid argument."), BAD_REQUEST), ((None, "Gemini request failed: timed out"), NETWORK)]
        for (status, msg), kind in cases:
            with self.subTest(status=status):
                self.assertEqual(classify(status, msg).kind, kind)

    def test_a_hard_quota_is_never_retried_and_rests_for_a_long_time(self):
        f = classify(429, "Rate limit reached ... tokens per day (TPD) ... Please try again in 14m2.3s")
        self.assertFalse(f.retry_same)
        self.assertGreater(f.cooldown_s, 800)


class TestRouting(unittest.TestCase):
    def test_the_first_route_answers_and_usage_is_counted_by_provider_and_task(self):
        gem = Fake("gemini", ['{"a":1}'])
        r, _, _ = make(gem)
        out = r.run("director", "sys", "user")
        self.assertEqual((out.text, out.route.key), ('{"a":1}', "gemini/g-main"))
        self.assertEqual(r.usage.calls, {"gemini": {"director": 1}})
        self.assertEqual(r.usage.tokens["input"], 10)

    def test_a_hard_quota_goes_straight_to_the_next_route_without_retrying_and_the_route_rests(self):
        gem = Fake("gemini", [E(429, "You exceeded your current quota"), "from second"])
        r, _, sl = make(gem)
        out = r.run("director", "s", "u")
        self.assertEqual(out.route.key, "gemini/g-second")
        self.assertEqual(gem.calls, ["g-main", "g-second"])
        self.assertEqual(sl, [], "no waiting, no retry of an exhausted quota")
        gem.calls.clear()
        r.run("director", "s", "u2")
        self.assertEqual(gem.calls, ["g-second"], "the exhausted route is skipped on later requests")

    def test_director_falls_back_to_groq_when_every_gemini_route_is_gone(self):
        gem = Fake("gemini", [E(429, "You exceeded your current quota")])
        groq = Fake("groq", ["from groq"])
        r, _, _ = make(gem, groq)
        out = r.run("director", "s", "u")
        self.assertEqual((out.text, out.route.provider), ("from groq", "groq"))
        self.assertEqual(r.usage.fallbacks, 2)

    def test_critic_prefers_groq_and_escalates_to_gemini_only_when_groq_fails(self):
        gem, groq = Fake("gemini", ["gem"]), Fake("groq", ["groq answer"])
        r, _, _ = make(gem, groq)
        self.assertEqual(r.run("critic", "s", "u").route.provider, "groq")
        self.assertEqual(gem.calls, [])
        groq.script = [E(429, "Rate limit reached ... tokens per day (TPD) ... Please try again in 1h0m0s")]
        self.assertEqual(r.run("critic", "s", "u2").route.provider, "gemini")

    def test_a_denied_or_invalid_or_missing_model_route_is_retired_for_the_session(self):
        for status, msg in ((403, "Your project has been denied access."), (401, "Invalid API Key"), (404, "models/g-main is not found")):
            with self.subTest(status=status):
                gem = Fake("gemini", [E(status, msg), "ok"])
                r, clock, _ = make(gem)
                r.run("director", "s", "u")
                clock["t"] += 10 ** 6                       # even a day later it stays retired
                gem.calls.clear()
                r.run("director", "s", "u3")
                self.assertNotIn("g-main", gem.calls)

    def test_a_busy_service_is_retried_a_bounded_number_of_times_then_the_next_route_is_used(self):
        gem = Fake("gemini", [E(503, "The model is overloaded")])
        groq = Fake("groq", ["groq"])
        r, _, sl = make(gem, groq)
        out = r.run("director", "s", "u")
        self.assertEqual(out.route.provider, "groq")
        self.assertEqual(sl, [3.0, 9.0, 3.0, 9.0], "two short retries on each Gemini model, then Groq")

    def test_a_per_minute_limit_rests_the_route_a_short_time_and_a_lone_route_waits_once(self):
        gem = Fake("gemini", [E(429, "Rate limit ... per minute ... Please try again in 5s"), "ok"])
        r, _, sl = make(gem)
        r.routes["director"] = [Route("gemini", "g-main")]
        out = r.run("director", "s", "u")
        self.assertEqual(out.text, "ok")
        self.assertEqual(len(sl), 1)
        self.assertLess(sl[0], 10)

    def test_a_bad_request_is_not_sent_anywhere_else(self):
        gem, groq = Fake("gemini", [E(400, "Request contains an invalid argument.")]), Fake("groq", ["never"])
        r, _, _ = make(gem, groq)
        with self.assertRaises(ProviderError):
            r.run("director", "s", "u")
        self.assertEqual(groq.calls, [])

    def test_an_unreadable_answer_gets_one_corrective_retry_then_the_next_route(self):
        gem = Fake("gemini", ["not json", "still not json"])
        groq = Fake("groq", ['{"ok": 1}'])
        r, _, _ = make(gem, groq)
        ok = lambda t: t.startswith("{")
        out = r.run("director", "s", "u", accept=ok)
        self.assertEqual((out.text, out.route.provider), ('{"ok": 1}', "groq"))
        self.assertEqual(gem.calls, ["g-main", "g-main", "g-second", "g-second"])   # one corrective retry per route, then on

    def test_a_route_that_keeps_failing_is_not_asked_again_for_the_same_answer(self):
        gem = Fake("gemini", [E(503, "The model is overloaded")])
        r, _, sl = make(gem)
        with self.assertRaises(AllRoutesUnavailable):
            r.run("director", "s", "u")
        self.assertEqual(gem.calls.count("g-main"), 3)      # the first try and two short retries, once; never a second round
        self.assertLessEqual(len(sl), 4)

    def test_when_nothing_can_answer_it_stops_cleanly_with_a_reason(self):
        gem = Fake("gemini", [E(429, "You exceeded your current quota")])
        r, _, _ = make(gem)
        with self.assertRaises(AllRoutesUnavailable) as cm:
            r.run("director", "s", "u")
        self.assertIn("Progress is saved", str(cm.exception))
        self.assertIn("gemini/g-main", str(cm.exception))


class TestCacheStateAndLog(unittest.TestCase):
    def test_an_accepted_result_is_reused_and_a_rejected_one_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            gem = Fake("gemini", ['{"v": 1}'])
            r, _, _ = make(gem, state_dir=d)
            r.run("director", "sys", "narration   text", accept=lambda t: t.startswith("{"))
            gem.script = ['{"v": 2}']
            again = r.run("director", "sys", "narration text", accept=lambda t: True)       # whitespace differences do not matter
            self.assertTrue(again.from_cache)
            self.assertEqual(again.text, '{"v": 1}')
            self.assertEqual(len(gem.calls), 1)
            self.assertEqual(r.usage.cache_hits, 1)
            r.run("director", "sys", "other narration", accept=lambda t: True)
            self.assertEqual(len(gem.calls), 2)
            # a cached answer the caller no longer accepts is ignored
            gem.script = ['{"v": 3}']
            fresh = r.run("director", "sys", "narration text", accept=lambda t: '"v": 3' in t)
            self.assertFalse(fresh.from_cache)

    def test_a_daily_quota_is_remembered_across_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            gem = Fake("gemini", [E(429, "You exceeded your current quota"), "ok"])
            r, clock, _ = make(gem, state_dir=d)
            r.run("director", "s", "u")
            gem2 = Fake("gemini", ["ok"])
            r2 = AIRouter(r.routes, {"gemini": gem2, "groq": Fake("groq", ["g"], configured=False)}, state_dir=d, clock=lambda: clock["t"] + 5)
            r2.run("director", "s", "u9")
            self.assertEqual(gem2.calls, ["g-second"], "g-main is still exhausted after the restart")

    def test_the_call_log_has_safe_metadata_only(self):
        with tempfile.TemporaryDirectory() as d:
            gem = Fake("gemini", ["answer"])
            r, _, _ = make(gem, state_dir=d)
            r.run("critic", "SECRET-SYSTEM-PROMPT", "SECRET-USER-TEXT", label="chapter 2")
            rows = [json.loads(l) for l in (Path(d) / "ai_calls.jsonl").read_text().splitlines()]
            self.assertEqual({k: rows[-1][k] for k in ("task", "label", "ok")}, {"task": "critic", "label": "chapter 2", "ok": True})
            blob = (Path(d) / "ai_calls.jsonl").read_text()
            self.assertNotIn("SECRET", blob)

    def test_status_reports_ready_resting_and_unavailable(self):
        gem = Fake("gemini", [E(403, "denied access"), "ok"])
        r, _, _ = make(gem)
        r.run("director", "s", "u")
        states = {(x["task"], x["model"]): x["state"] for x in r.status()}
        self.assertEqual(states[("director", "g-main")], "UNAVAILABLE")
        self.assertEqual(states[("director", "g-second")], "READY")
        self.assertEqual(states[("director", "q-big")], "NOT CONFIGURED")


class FakeResp:
    def __init__(self, status, body, headers=None):
        self.status_code, self._b, self.headers, self.text = status, body, headers or {}, json.dumps(body)

    def json(self):
        return self._b


class TestGroqProvider(unittest.TestCase):
    def test_a_success_is_parsed_with_usage_and_limits(self):
        body = {"choices": [{"message": {"content": '{"x": 1}'}}], "usage": {"prompt_tokens": 120, "completion_tokens": 30}}
        with mock.patch("ai_router.providers.requests.post", return_value=FakeResp(200, body, {"x-ratelimit-remaining-requests": "11", "x-ratelimit-remaining-tokens": "5000"})) as post:
            out = GroqProvider("gsk_TESTKEY").complete("sys", "user", model="m", max_output=500)
        self.assertEqual((out.text, out.usage["input"], out.limits["remaining_requests"]), ('{"x": 1}', 120, "11"))
        sent = json.loads(post.call_args.kwargs["data"])
        self.assertEqual((sent["model"], sent["response_format"]), ("m", {"type": "json_object"}))

    def test_a_daily_limit_and_a_per_minute_limit_are_told_apart_and_the_key_stays_secret(self):
        for msg, kind in (("Rate limit reached for model m in organization o on tokens per day (TPD): Limit 100000. Please try again in 14m2.3s.", QUOTA_HARD),
                          ("Rate limit reached for model m on tokens per minute (TPM): Limit 6000. Please try again in 5.2s.", RATE_TEMP)):
            with self.subTest(kind=kind):
                with mock.patch("ai_router.providers.requests.post", return_value=FakeResp(429, {"error": {"message": msg}})):
                    with self.assertRaises(ProviderError) as cm:
                        GroqProvider("gsk_TESTKEY").complete("s", "u", model="m")
                self.assertEqual(classify(cm.exception.status, str(cm.exception), cm.exception.retry_after).kind, kind)
                self.assertNotIn("gsk_TESTKEY", str(cm.exception))

    def test_the_key_test_reports_states_by_alias(self):
        with mock.patch("ai_router.providers.requests.post", return_value=FakeResp(401, {"error": {"message": "Invalid API Key"}})):
            row = GroqProvider("gsk_TESTKEY").test("m")[0]
        self.assertEqual((row["alias"], row["state"], row["model"]), ("Groq key", "INVALID", "m"))
        self.assertNotIn("gsk_TESTKEY", json.dumps(row))

    def test_an_unconfigured_groq_is_not_selected(self):
        self.assertFalse(GroqProvider("").configured())


if __name__ == "__main__":
    unittest.main()
