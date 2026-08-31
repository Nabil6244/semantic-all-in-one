"""Unit tests for friend login gate (mocked HTTP)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from licensing.auth_client import AuthClient, AuthError, AuthSession
from licensing import session_store


class TestAuthClient(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._session_file = Path(self._tmpdir.name) / "auth_session.json"
        self._path_patch = patch.object(session_store, "session_path", return_value=self._session_file)
        self._path_patch.start()
        self.addCleanup(self._path_patch.stop)
        self._device_file = Path(self._tmpdir.name) / "device_id.json"

        def _fake_collect():
            return {
                "device_id": "dev-test-1",
                "hostname": "test-host",
                "os_name": "Darwin",
                "os_version": "24",
                "arch": "arm64",
                "last_seen_at": "2026-01-01T00:00:00+00:00",
            }

        self._device_patch = patch("licensing.device.collect_device_info", side_effect=_fake_collect)
        self._device_patch.start()
        self.addCleanup(self._device_patch.stop)
        self.client = AuthClient(url="https://example.supabase.co", anon_key="anon-test")

    def _resp(self, status: int, payload):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = payload
        return r

    def _post_router(self, login_body=None, login_status=200, device_status=201):
        def _post(url, **kwargs):
            if "devices" in str(url):
                return self._resp(device_status, [])
            return self._resp(login_status, login_body if login_body is not None else {})
        return _post

    def test_login_ok_and_active(self):
        login_body = {
            "access_token": "at",
            "refresh_token": "rt",
            "user": {"id": "u1", "email": "a@b.com"},
        }
        profile_body = [{"active": True, "display_name": "Friend"}]

        with patch("licensing.auth_client.requests.post", side_effect=self._post_router(login_body)) as post:
            with patch("licensing.auth_client.requests.get", return_value=self._resp(200, profile_body)) as get:
                session = self.client.login("a@b.com", "secret")

        self.assertEqual(session.user_id, "u1")
        self.assertEqual(session.display_name, "Friend")
        self.assertTrue(self._session_file.is_file())
        stored = json.loads(self._session_file.read_text())
        self.assertEqual(stored["refresh_token"], "rt")
        urls = [str(c.args[0]) for c in post.call_args_list]
        self.assertTrue(any("token" in u for u in urls))
        self.assertTrue(any("devices" in u for u in urls))
        device_call = next(c for c in post.call_args_list if "devices" in str(c.args[0]))
        body = device_call.kwargs.get("json") or {}
        self.assertEqual(body["user_id"], "u1")
        self.assertEqual(body["device_id"], "dev-test-1")
        self.assertEqual(body["hostname"], "test-host")
        get.assert_called_once()

    def test_login_records_device_even_if_upsert_fails(self):
        login_body = {
            "access_token": "at",
            "refresh_token": "rt",
            "user": {"id": "u1", "email": "a@b.com"},
        }
        with patch(
            "licensing.auth_client.requests.post",
            side_effect=self._post_router(login_body, device_status=500),
        ):
            with patch(
                "licensing.auth_client.requests.get",
                return_value=self._resp(200, [{"active": True, "display_name": ""}]),
            ):
                session = self.client.login("a@b.com", "secret")
        self.assertEqual(session.user_id, "u1")
        self.assertTrue(self._session_file.is_file())

    def test_login_invalid_credentials(self):
        with patch("licensing.auth_client.requests.post", return_value=self._resp(400, {"error": "x"})):
            with self.assertRaises(AuthError) as ctx:
                self.client.login("a@b.com", "wrong")
        self.assertEqual(ctx.exception.code, "invalid")
        self.assertEqual(ctx.exception.message, "Invalid login")

    def test_login_active_false_denies(self):
        login_body = {
            "access_token": "at",
            "refresh_token": "rt",
            "user": {"id": "u1", "email": "a@b.com"},
        }
        with patch("licensing.auth_client.requests.post", return_value=self._resp(200, login_body)):
            with patch(
                "licensing.auth_client.requests.get",
                return_value=self._resp(200, [{"active": False, "display_name": ""}]),
            ):
                with self.assertRaises(AuthError) as ctx:
                    self.client.login("a@b.com", "secret")
        self.assertEqual(ctx.exception.code, "disabled")
        self.assertEqual(ctx.exception.message, "Account disabled")

    def test_login_missing_profile_denies(self):
        login_body = {
            "access_token": "at",
            "refresh_token": "rt",
            "user": {"id": "u1", "email": "a@b.com"},
        }
        with patch("licensing.auth_client.requests.post", return_value=self._resp(200, login_body)):
            with patch("licensing.auth_client.requests.get", return_value=self._resp(200, [])):
                with self.assertRaises(AuthError) as ctx:
                    self.client.login("a@b.com", "secret")
        self.assertEqual(ctx.exception.code, "disabled")

    def test_refresh_401_after_password_change(self):
        session_store.save_session({
            "access_token": "old",
            "refresh_token": "old-rt",
            "user_id": "u1",
            "email": "a@b.com",
        })
        with patch("licensing.auth_client.requests.post", return_value=self._resp(401, {"error": "x"})):
            with self.assertRaises(AuthError) as ctx:
                self.client.verify_stored_session()
        self.assertEqual(ctx.exception.code, "revoked")

    def test_verify_active_false_clears_session(self):
        session_store.save_session({
            "access_token": "old",
            "refresh_token": "rt",
            "user_id": "u1",
            "email": "a@b.com",
        })
        refresh_body = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "user": {"id": "u1", "email": "a@b.com"},
        }
        with patch("licensing.auth_client.requests.post", side_effect=self._post_router(refresh_body)):
            with patch(
                "licensing.auth_client.requests.get",
                return_value=self._resp(200, [{"active": False}]),
            ):
                with self.assertRaises(AuthError) as ctx:
                    self.client.verify_stored_session()
        self.assertEqual(ctx.exception.code, "disabled")
        self.assertFalse(self._session_file.is_file())

    def test_verify_ok_updates_tokens(self):
        session_store.save_session({
            "access_token": "old",
            "refresh_token": "rt",
            "user_id": "u1",
            "email": "a@b.com",
        })
        refresh_body = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "user": {"id": "u1", "email": "a@b.com"},
        }
        with patch("licensing.auth_client.requests.post", side_effect=self._post_router(refresh_body)) as post:
            with patch(
                "licensing.auth_client.requests.get",
                return_value=self._resp(200, [{"active": True, "display_name": "N"}]),
            ):
                session = self.client.verify_stored_session()
        self.assertEqual(session.access_token, "new-at")
        stored = session_store.load_session()
        self.assertEqual(stored["refresh_token"], "new-rt")
        self.assertEqual(stored["display_name"], "N")
        self.assertTrue(any("devices" in str(c.args[0]) for c in post.call_args_list))

    def test_clear_session(self):
        session_store.save_session({
            "access_token": "a",
            "refresh_token": "b",
            "user_id": "u",
        })
        self.assertTrue(self._session_file.is_file())
        session_store.clear_session()
        self.assertFalse(self._session_file.is_file())
        self.assertIsNone(session_store.load_session())


class TestRevalidateLicenseResilience(unittest.TestCase):
    """app.VideoGeneratorApp._revalidate_license / _continue_offline_or_login:
    a network failure (or any non-deny error) must NOT be treated the same as
    a definitive server-side revoke — see Release Readiness Audit, Phase 1.2.
    Exercises the real methods directly on a bare (un-__init__'d) instance,
    same pattern as test_research_staleness_and_ambiguity.py, so no real
    Tk window is created."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._session_file = Path(self._tmpdir.name) / "auth_session.json"
        self._path_patch = patch.object(session_store, "session_path", return_value=self._session_file)
        self._path_patch.start()
        self.addCleanup(self._path_patch.stop)

    def _make_app_instance(self, *, auth_required=True, auth_session=None):
        import app as app_module

        instance = app_module.VideoGeneratorApp.__new__(app_module.VideoGeneratorApp)
        instance._auth_required = lambda: auth_required
        instance._auth_session = auth_session
        return instance

    def test_network_failure_keeps_an_already_verified_session(self):
        instance = self._make_app_instance(
            auth_session=AuthSession(access_token="at", refresh_token="rt", user_id="u1")
        )
        with patch("licensing.config.is_configured", return_value=True):
            with patch(
                "licensing.auth_client.get_auth_client",
                return_value=MagicMock(
                    verify_stored_session=MagicMock(
                        side_effect=AuthError("Could not reach login server: timeout", code="network")
                    )
                ),
            ):
                ok, err = instance._revalidate_license()
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_unexpected_exception_keeps_an_already_verified_session(self):
        instance = self._make_app_instance(
            auth_session=AuthSession(access_token="at", refresh_token="rt", user_id="u1")
        )
        with patch("licensing.config.is_configured", return_value=True):
            with patch(
                "licensing.auth_client.get_auth_client",
                return_value=MagicMock(
                    verify_stored_session=MagicMock(side_effect=ValueError("bad json"))
                ),
            ):
                ok, err = instance._revalidate_license()
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_revoked_still_denies_even_with_an_existing_session(self):
        instance = self._make_app_instance(
            auth_session=AuthSession(access_token="at", refresh_token="rt", user_id="u1")
        )
        with patch("licensing.config.is_configured", return_value=True):
            with patch(
                "licensing.auth_client.get_auth_client",
                return_value=MagicMock(
                    verify_stored_session=MagicMock(
                        side_effect=AuthError("Access revoked or password changed", code="revoked")
                    )
                ),
            ):
                ok, err = instance._revalidate_license()
        self.assertFalse(ok)
        self.assertEqual(err, "Access revoked or password changed")

    def test_disabled_still_denies_even_with_an_existing_session(self):
        instance = self._make_app_instance(
            auth_session=AuthSession(access_token="at", refresh_token="rt", user_id="u1")
        )
        with patch("licensing.config.is_configured", return_value=True):
            with patch(
                "licensing.auth_client.get_auth_client",
                return_value=MagicMock(
                    verify_stored_session=MagicMock(
                        side_effect=AuthError("Account disabled", code="disabled")
                    )
                ),
            ):
                ok, err = instance._revalidate_license()
        self.assertFalse(ok)
        self.assertEqual(err, "Account disabled")

    def test_network_failure_with_no_existing_session_still_denies(self):
        instance = self._make_app_instance(auth_session=None)
        with patch("licensing.config.is_configured", return_value=True):
            with patch(
                "licensing.auth_client.get_auth_client",
                return_value=MagicMock(
                    verify_stored_session=MagicMock(
                        side_effect=AuthError("Could not reach login server: timeout", code="network")
                    )
                ),
            ):
                ok, err = instance._revalidate_license()
        self.assertFalse(ok)

    def test_successful_verify_updates_the_held_session(self):
        instance = self._make_app_instance(auth_session=None)
        fresh = AuthSession(access_token="new-at", refresh_token="new-rt", user_id="u1")
        with patch("licensing.config.is_configured", return_value=True):
            with patch(
                "licensing.auth_client.get_auth_client",
                return_value=MagicMock(verify_stored_session=MagicMock(return_value=fresh)),
            ):
                ok, err = instance._revalidate_license()
        self.assertTrue(ok)
        self.assertIs(instance._auth_session, fresh)

    def test_not_auth_required_short_circuits_without_any_network_call(self):
        instance = self._make_app_instance(auth_required=False)
        ok, err = instance._revalidate_license()
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_continue_offline_or_login_uses_stored_session_when_present(self):
        instance = self._make_app_instance()
        instance.after = lambda _ms, fn: fn()  # run "later" callbacks immediately
        session_store.save_session({
            "access_token": "at", "refresh_token": "rt", "user_id": "u1", "email": "a@b.com",
        })

        seen = {}

        def fake_on_auth_ok(session, *, then=None):
            seen["session"] = session
            if then:
                then()

        instance._on_auth_ok = fake_on_auth_ok
        picker_called = []
        login_called = []
        instance._continue_offline_or_login(
            lambda: picker_called.append(True),
            lambda m="": login_called.append(m),
            "Could not reach login server: timeout",
        )
        self.assertEqual(seen["session"].refresh_token, "rt")
        self.assertEqual(picker_called, [True])
        self.assertEqual(login_called, [])

    def test_continue_offline_or_login_shows_login_when_nothing_stored(self):
        instance = self._make_app_instance()
        instance.after = lambda _ms, fn: fn()
        self.assertIsNone(session_store.load_session())

        login_called = []
        instance._continue_offline_or_login(
            lambda: None,
            lambda m="": login_called.append(m),
            "Could not reach login server: timeout",
        )
        self.assertEqual(login_called, ["Could not reach login server: timeout"])


if __name__ == "__main__":
    unittest.main()


class TestPasswordReset(unittest.TestCase):
    """Recovery email request — must never leak whether an account exists."""

    def setUp(self):
        self.client = AuthClient(url="https://example.supabase.co", anon_key="anon-test")

    def _resp(self, status):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = {}
        return r

    def test_posts_to_the_recover_endpoint_with_the_email(self):
        with patch("licensing.auth_client.requests.post", return_value=self._resp(200)) as post:
            self.client.request_password_reset("  Someone@Example.com  ")
        url = post.call_args[0][0]
        self.assertTrue(url.endswith("/auth/v1/recover"), url)
        self.assertEqual(post.call_args.kwargs["json"], {"email": "Someone@Example.com"})

    def test_no_redirect_url_is_sent(self):
        """Reset happens in the browser against the project's Site URL."""
        with patch("licensing.auth_client.requests.post", return_value=self._resp(200)) as post:
            self.client.request_password_reset("a@b.co")
        self.assertNotIn("redirect_to", post.call_args.kwargs["json"])

    def test_unknown_address_is_indistinguishable_from_a_known_one(self):
        """A 4xx must not become an error the UI could use to enumerate users."""
        for status in (200, 400, 401, 404, 422):
            with patch("licensing.auth_client.requests.post", return_value=self._resp(status)):
                self.assertIsNone(self.client.request_password_reset("a@b.co"))

    def test_rate_limiting_is_surfaced(self):
        with patch("licensing.auth_client.requests.post", return_value=self._resp(429)):
            with self.assertRaises(AuthError) as ctx:
                self.client.request_password_reset("a@b.co")
        self.assertEqual(ctx.exception.code, "rate_limited")

    def test_server_failure_is_surfaced(self):
        with patch("licensing.auth_client.requests.post", return_value=self._resp(503)):
            with self.assertRaises(AuthError) as ctx:
                self.client.request_password_reset("a@b.co")
        self.assertEqual(ctx.exception.code, "server")

    def test_network_failure_is_surfaced(self):
        import requests as _requests
        with patch("licensing.auth_client.requests.post",
                   side_effect=_requests.RequestException("down")):
            with self.assertRaises(AuthError) as ctx:
                self.client.request_password_reset("a@b.co")
        self.assertEqual(ctx.exception.code, "network")

    def test_missing_address_never_reaches_the_network(self):
        with patch("licensing.auth_client.requests.post") as post:
            for bad in ("", "   ", "not-an-email"):
                with self.assertRaises(AuthError) as ctx:
                    self.client.request_password_reset(bad)
                self.assertEqual(ctx.exception.code, "invalid")
        post.assert_not_called()

    def test_unconfigured_app_never_reaches_the_network(self):
        client = AuthClient(url="", anon_key="")
        with patch("licensing.auth_client.requests.post") as post:
            with self.assertRaises(AuthError) as ctx:
                client.request_password_reset("a@b.co")
        self.assertEqual(ctx.exception.code, "misconfigured")
        post.assert_not_called()

    def test_no_password_or_token_is_ever_sent(self):
        with patch("licensing.auth_client.requests.post", return_value=self._resp(200)) as post:
            self.client.request_password_reset("a@b.co")
        body = post.call_args.kwargs["json"]
        self.assertEqual(set(body), {"email"})
        headers = post.call_args.kwargs["headers"]
        self.assertNotIn("Authorization", headers)
