"""Gemini credential pool: several keys, rotation only on retryable quota/busy failures, never on permanent errors, no key value in any message."""

from __future__ import annotations

import json
import unittest
from unittest import mock

import requests

from visual_director import llm as L

KEYS = ["fake-test-key-A-1", "fake-test-key-B-2", "fake-test-key-C-3"]


def ok_body(text="{}"):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def err(status, message, st=""):
    return Resp(status, {"error": {"message": message, "status": st}})


class Scripted:
    """Stands in for requests.post: answers by key."""

    def __init__(self, by_key):
        self.by_key, self.calls = by_key, []

    def __call__(self, url, headers=None, data=None, timeout=None):
        key = headers["x-goog-api-key"]
        self.calls.append(key)
        answer = self.by_key[key]
        if isinstance(answer, Exception):
            raise answer
        return answer


def fresh(keys):
    L._POOLS.clear()
    return L.GeminiLLM(settings={"gemini_api_key": keys[0], **{f"gemini_api_key_{i}": k for i, k in enumerate(keys[1:], 1)}}, timeout=5)


class TestKeyList(unittest.TestCase):
    def test_primary_first_then_numbered_from_settings_and_environment_without_duplicates(self):
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "", "GEMINI_API_KEY_2": "E2", "GEMINI_API_KEY_1": "S1"}, clear=False):
            self.assertEqual(L.resolve_gemini_api_keys({"gemini_api_key": "P", "gemini_api_key_1": "S1", "gemini_api_key_3": "S3"}), ["P", "S1", "E2", "S3"])
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
            self.assertEqual(L.resolve_gemini_api_keys({"gemini_api_key": "only"}), ["only"])   # the single-key setup is unchanged
            self.assertEqual(L.resolve_gemini_api_keys({}), [])

    def test_an_explicit_key_is_a_pool_of_one(self):
        L._POOLS.clear()
        self.assertEqual(L.GeminiLLM(api_key="solo").credentials.keys, ["solo"])


class TestRotation(unittest.TestCase):
    def run_with(self, by_key, keys=KEYS):
        llm = fresh(keys)
        post = Scripted(by_key)
        with mock.patch("visual_director.llm.requests.post", post):
            try:
                return llm, post, llm.complete("s", "u")
            except L.LLMError as exc:
                return llm, post, exc

    def test_a_quota_failure_moves_to_the_next_key_and_the_answer_comes_back(self):
        llm, post, out = self.run_with({KEYS[0]: err(429, "You exceeded your current quota", "RESOURCE_EXHAUSTED"), KEYS[1]: Resp(200, ok_body('{"a":1}')), KEYS[2]: Resp(200, ok_body("no"))})
        self.assertEqual(out, '{"a":1}')
        self.assertEqual(post.calls, [KEYS[0], KEYS[1]])
        self.assertEqual(llm.credentials.rotations, 1)

    def test_transient_and_network_failures_rotate_too(self):
        for first in (err(503, "The model is overloaded. Please try again later."), requests.ConnectTimeout("timed out")):
            with self.subTest(type(first).__name__):
                llm, post, out = self.run_with({KEYS[0]: first, KEYS[1]: Resp(200, ok_body("fine")), KEYS[2]: Resp(200, ok_body("no"))})
                self.assertEqual(out, "fine")
                self.assertEqual(post.calls, [KEYS[0], KEYS[1]])

    def test_a_resting_key_is_not_tried_first_next_time(self):
        llm, post, _ = self.run_with({KEYS[0]: err(429, "quota"), KEYS[1]: Resp(200, ok_body("one")), KEYS[2]: Resp(200, ok_body("x"))})
        post.calls.clear()
        with mock.patch("visual_director.llm.requests.post", post):
            llm.complete("s", "u")
        self.assertEqual(post.calls, [KEYS[1]])        # key 1 is resting; key 2 answers straight away

    def test_a_bad_request_never_rotates_because_every_key_would_refuse_it(self):
        for status, msg in ((400, "Request contains an invalid argument."), (400, "Invalid JSON payload received."), (404, "models/x is not found")):
            with self.subTest(status=status, msg=msg):
                llm, post, out = self.run_with({KEYS[0]: err(status, msg), KEYS[1]: Resp(200, ok_body("never")), KEYS[2]: Resp(200, ok_body("never"))})
                self.assertIsInstance(out, L.LLMError)
                self.assertEqual(post.calls, [KEYS[0]])
                self.assertEqual(llm.credentials.rotations, 0)
                self.assertEqual(llm.credentials.usable, 3, "and no key is retired for it")

    def test_a_denied_or_invalid_key_is_retired_and_the_next_key_is_tried(self):
        for status, msg in ((403, "Your project has been denied access. Please contact support."), (403, "Permission denied"), (401, "Request had invalid authentication credentials"),
                            (400, "API key not valid. Please pass a valid API key.")):
            with self.subTest(status=status, msg=msg):
                llm, post, out = self.run_with({KEYS[0]: err(status, msg), KEYS[1]: Resp(200, ok_body("from key 2")), KEYS[2]: Resp(200, ok_body("never"))})
                self.assertEqual(out, "from key 2")
                self.assertEqual(post.calls, [KEYS[0], KEYS[1]])
                self.assertEqual(llm.credentials.usable, 2)
                post.calls.clear()
                with mock.patch("visual_director.llm.requests.post", post):
                    llm.complete("s", "u")
                self.assertNotIn(KEYS[0], post.calls, "a retired key is not tried again on later requests")

    def test_the_reported_case_quota_then_quota_then_denied_then_the_fourth_key(self):
        four = KEYS + ["fake-test-key-D-4"]
        llm, post, out = self.run_with({four[0]: err(429, "You exceeded your current quota"), four[1]: err(429, "You exceeded your current quota"),
                                        four[2]: err(403, "Your project has been denied access. Please contact support."), four[3]: Resp(200, ok_body("fourth"))}, keys=four)
        self.assertEqual(out, "fourth")
        self.assertEqual(post.calls, four)                      # in the configured order, each once
        self.assertEqual(llm.credentials.usable, 3)             # only the denied key is gone; the two resting ones recover
        post.calls.clear()
        with mock.patch("visual_director.llm.requests.post", post):
            self.assertEqual(llm.complete("s", "u"), "fourth")
        self.assertEqual(post.calls, [four[3]], "the resting keys wait, the dead key is skipped, the working key answers at once")

    def test_when_every_key_is_refused_it_fails_once_and_then_without_asking_again(self):
        llm, post, out = self.run_with({k: err(403, "Your project has been denied access.") for k in KEYS})
        self.assertIsInstance(out, L.LLMError)
        self.assertEqual(sorted(post.calls), sorted(KEYS))
        post.calls.clear()
        with mock.patch("visual_director.llm.requests.post", post):
            with self.assertRaises(L.LLMError) as cm:
                llm.complete("s", "u")
        self.assertEqual(post.calls, [], "nothing left to try: no request is sent")
        self.assertIn("refused", str(cm.exception))

    def test_when_every_key_is_exhausted_each_is_tried_once_and_the_error_surfaces(self):
        llm, post, out = self.run_with({k: err(429, "You exceeded your current quota") for k in KEYS})
        self.assertIsInstance(out, L.LLMError)
        self.assertEqual(sorted(post.calls), sorted(KEYS))          # bounded: one attempt per key, no loop
        self.assertIn("quota", str(out))

    def test_no_message_or_note_ever_contains_a_key(self):
        shaped = ["AI" + "za" + "Sy" + c * 33 for c in "XYZ"]      # shaped like real Google keys (built here so no such text sits in the file)
        llm, post, out = self.run_with({k: err(429, f"quota exhausted for key {k}") for k in shaped}, keys=shaped)
        text = str(out) + " ".join(llm.credentials.notes)
        for k in shaped:
            self.assertNotIn(k, text)

    def test_the_director_critic_and_repair_copies_share_one_pool(self):
        llm = fresh(KEYS)
        tuned = L.GeminiLLM(api_key=llm.api_key, model=llm.model, base_url=llm.base_url, timeout=9, credentials=llm.credentials)
        self.assertIs(tuned.credentials, llm.credentials)

    def test_the_only_key_is_never_retired_so_a_single_key_setup_behaves_as_before(self):
        llm = fresh(KEYS[:1])
        post = Scripted({KEYS[0]: err(403, "Your project has been denied access.")})
        with mock.patch("visual_director.llm.requests.post", post):
            for _ in range(2):
                with self.assertRaises(L.LLMError) as cm:
                    llm.complete("s", "u")
                self.assertIn("denied access", str(cm.exception))
        self.assertEqual(post.calls, [KEYS[0], KEYS[0]])

    def test_a_single_key_behaves_exactly_as_before(self):
        llm = fresh(KEYS[:1])
        post = Scripted({KEYS[0]: err(429, "quota")})
        with mock.patch("visual_director.llm.requests.post", post):
            with self.assertRaises(L.LLMError):
                llm.complete("s", "u")
        self.assertEqual(post.calls, [KEYS[0]])
        self.assertEqual(llm.credentials.rotations, 0)


if __name__ == "__main__":
    unittest.main()
