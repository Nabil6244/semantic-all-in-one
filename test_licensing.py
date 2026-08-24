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


if __name__ == "__main__":
    unittest.main()
