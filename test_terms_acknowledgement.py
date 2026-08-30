"""About & Ownership acknowledgement: version, lookup, identity, persistence.

Network is always faked — these must never touch Supabase.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from licensing import terms
from licensing.auth_client import AuthError, AuthSession

V1 = "2026-08-30-v1"


# The module refuses to talk to an unconfigured backend (raises
# "misconfigured" before any request), so tests supply credentials.
def _creds():
    return patch.object(terms, "supabase_credentials",
                        return_value=("https://example.supabase.co", "anon-key"))


def _session(uid="user-123", name="Muhammad Nabil"):
    return AuthSession(access_token="tok", refresh_token="ref", user_id=uid,
                       email="x@example.com", display_name=name)


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class TestTermsVersion(unittest.TestCase):
    def test_version_is_defined_centrally(self):
        self.assertEqual(terms.CURRENT_TERMS_VERSION, V1)

    def test_version_string_appears_in_exactly_one_module(self):
        """Must not be scattered — a future bump has to be a one-line change."""
        repo = Path(__file__).resolve().parent
        hits = []
        for p in list(repo.glob("*.py")) + list((repo / "licensing").glob("*.py")) \
                + list((repo / "ui").glob("*.py")):
            if p.name.startswith("test_"):
                continue
            if V1 in p.read_text(encoding="utf-8"):
                hits.append(p.name)
        self.assertEqual(hits, ["terms.py"], f"version literal leaked into {hits}")


class TestAcknowledgementLookup(unittest.TestCase):
    def setUp(self):
        self._creds = _creds(); self._creds.start()
        self.addCleanup(self._creds.stop)

    def _get(self, payload, status=200):
        return patch.object(requests, "get", return_value=_Resp(status, payload))

    def test_acknowledged_current_version_returns_true(self):
        with self._get([{"acknowledged": True, "terms_version": V1}]):
            self.assertTrue(terms.has_acknowledged(_session()))

    def test_no_record_returns_false(self):
        with self._get([]):
            self.assertFalse(terms.has_acknowledged(_session()))

    def test_only_old_version_returns_false(self):
        """A v1 row must not satisfy a v2 requirement."""
        with patch.object(requests, "get") as g:
            g.return_value = _Resp(200, [])
            self.assertFalse(terms.has_acknowledged(_session(), version="2026-09-01-v2"))
            self.assertEqual(g.call_args.kwargs["params"]["terms_version"], "eq.2026-09-01-v2")

    def test_query_filters_on_acknowledged_true(self):
        """acknowledged=false must not count as accepted."""
        with patch.object(requests, "get") as g:
            g.return_value = _Resp(200, [])
            terms.has_acknowledged(_session())
            self.assertEqual(g.call_args.kwargs["params"]["acknowledged"], "is.true")

    def test_network_failure_raises_and_never_reports_true(self):
        with patch.object(requests, "get", side_effect=requests.RequestException("down")):
            with self.assertRaises(AuthError) as ctx:
                terms.has_acknowledged(_session())
            self.assertEqual(ctx.exception.code, "network")

    def test_server_error_raises_rather_than_passing(self):
        with self._get(None, status=500):
            with self.assertRaises(AuthError):
                terms.has_acknowledged(_session())

    def test_unsigned_session_is_not_acknowledged(self):
        self.assertFalse(terms.has_acknowledged(_session(uid="")))

    def test_unconfigured_backend_raises_rather_than_passing(self):
        with patch.object(terms, "supabase_credentials", return_value=("", "")):
            with self.assertRaises(AuthError):
                terms.has_acknowledged(_session())


class TestIdentity(unittest.TestCase):
    def test_heading_uses_session_display_name(self):
        self.assertEqual(terms.welcome_heading("Muhammad Nabil"), "Welcome, Muhammad Nabil")

    def test_heading_falls_back_neutrally(self):
        self.assertEqual(terms.welcome_heading(""), "Welcome")
        self.assertEqual(terms.welcome_heading("   "), "Welcome")

    def test_acknowledgement_lead_is_personalised(self):
        self.assertEqual(terms.acknowledgement_lead("Ayesha"), "Ayesha, I acknowledge that:")
        self.assertEqual(terms.acknowledgement_lead(""), "I acknowledge that:")

    def test_no_person_name_is_hardcoded_in_ui_strings(self):
        blob = " ".join(
            [terms.INTRO, terms.CHECKBOX_LABEL, terms.LEGAL_NOTE]
            + [p for _h, ps in terms.SECTIONS for p in ps]
            + list(terms.ACKNOWLEDGEMENT_POINTS)
        )
        self.assertNotIn("Muhammad", blob)
        # "Nabil" legitimately appears as the owner in the agreement body, but
        # must never be baked into the personalised greeting.
        self.assertNotIn("Nabil", terms.welcome_heading("Someone Else"))


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self._creds = _creds(); self._creds.start()
        self.addCleanup(self._creds.stop)

    def test_successful_write_sends_correct_payload(self):
        with patch.object(requests, "post", return_value=_Resp(201)) as post:
            terms.save_acknowledgement(_session())
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["user_id"], "user-123")
        self.assertEqual(body["display_name"], "Muhammad Nabil")
        self.assertEqual(body["terms_version"], V1)
        self.assertIs(body["acknowledged"], True)

    def test_acknowledged_at_is_not_sent_by_the_client(self):
        """Regression: the client used to send the literal string "now()",
        which is not a valid timestamptz input (only the bare word 'now' is),
        so every write would have failed with 400. The DB stamps it instead,
        which also keeps the audit time independent of the client clock."""
        with patch.object(requests, "post", return_value=_Resp(201)) as post:
            terms.save_acknowledgement(_session())
        body = post.call_args.kwargs["json"]
        self.assertNotIn("acknowledged_at", body)
        self.assertNotIn("now()", str(body))

    def test_upsert_is_keyed_on_user_and_version(self):
        with patch.object(requests, "post", return_value=_Resp(201)) as post:
            terms.save_acknowledgement(_session())
        self.assertEqual(post.call_args.kwargs["params"]["on_conflict"], "user_id,terms_version")
        self.assertIn("merge-duplicates", post.call_args.kwargs["headers"]["Prefer"])

    def test_no_credentials_are_persisted(self):
        with patch.object(requests, "post", return_value=_Resp(201)) as post:
            terms.save_acknowledgement(_session())
        body = post.call_args.kwargs["json"]
        for banned in ("access_token", "refresh_token", "password", "email", "apikey"):
            self.assertNotIn(banned, body)

    def test_write_failure_raises_so_caller_cannot_continue(self):
        with patch.object(requests, "post", return_value=_Resp(500)):
            with self.assertRaises(AuthError):
                terms.save_acknowledgement(_session())

    def test_network_failure_raises(self):
        with patch.object(requests, "post", side_effect=requests.RequestException("x")):
            with self.assertRaises(AuthError) as ctx:
                terms.save_acknowledgement(_session())
            self.assertEqual(ctx.exception.code, "network")

    def test_unsigned_session_cannot_write(self):
        with self.assertRaises(AuthError):
            terms.save_acknowledgement(_session(uid=""))


class TestSecurity(unittest.TestCase):
    def setUp(self):
        self._creds = _creds(); self._creds.start()
        self.addCleanup(self._creds.stop)

    def test_user_id_always_comes_from_the_session(self):
        """The UI has no way to submit an arbitrary user_id."""
        import inspect

        src = inspect.getsource(terms.save_acknowledgement)
        self.assertIn("session.user_id", src)
        sig = inspect.signature(terms.save_acknowledgement)
        self.assertNotIn("user_id", sig.parameters)

    def test_lookup_is_scoped_to_the_session_user(self):
        with patch.object(requests, "get") as g:
            g.return_value = _Resp(200, [])
            terms.has_acknowledged(_session(uid="abc"))
            self.assertEqual(g.call_args.kwargs["params"]["user_id"], "eq.abc")


class TestMigration(unittest.TestCase):
    def setUp(self):
        p = Path(__file__).resolve().parent / "supabase" / "migrations"
        files = sorted(p.glob("*user_terms_acknowledgements.sql"))
        if not files:
            self.skipTest("migration not present")
        self.sql = files[0].read_text(encoding="utf-8").lower()

    def test_unique_constraint_on_user_and_version(self):
        self.assertIn("unique (user_id, terms_version)".lower(), self.sql)

    def test_rls_enabled(self):
        self.assertIn("enable row level security", self.sql)

    def test_policies_scope_to_auth_uid(self):
        self.assertIn("auth.uid()", self.sql)
        for op in ("for select", "for insert", "for update"):
            self.assertIn(op, self.sql)

    def test_no_user_delete_policy(self):
        self.assertNotIn("for delete", self.sql)

    def test_acknowledged_at_is_stamped_server_side(self):
        """The trigger must cover INSERT too, not just UPDATE — the first
        acknowledgement is an insert, and it is the one that matters."""
        self.assertIn("before insert or update", self.sql)
        self.assertIn("new.acknowledged_at = now()", self.sql)

    def test_required_columns_present(self):
        for col in ("user_id", "display_name", "terms_version", "acknowledged",
                    "acknowledged_at", "created_at", "updated_at"):
            self.assertIn(col, self.sql)


if __name__ == "__main__":
    unittest.main()


class TestAuthGateContract(unittest.TestCase):
    """The gate lives at the single existing auth boundary (_on_auth_ok).

    The App class is far too heavy to instantiate headlessly, so these assert
    the contract at source level plus the behaviour of the functions it calls.
    """

    def _src(self, name):
        import inspect
        import app as _app
        return inspect.getsource(getattr(_app.VideoGeneratorApp, name))

    def test_gate_is_wired_into_the_existing_auth_boundary(self):
        self.assertIn("_require_terms_ack", self._src("_on_auth_ok"))

    def test_failed_lookup_shows_the_screen_and_never_proceeds(self):
        """A lookup that cannot be completed must NOT be read as accepted."""
        src = self._src("_require_terms_ack")
        self.assertIn("except Exception", src)
        self.assertIn("done = False", src)
        self.assertNotIn("done = True", src)

    def test_gate_only_proceeds_when_lookup_is_true(self):
        src = self._src("_require_terms_ack")
        self.assertIn("proceed() if d else self._show_terms_dialog", src)

    def test_declining_does_not_open_the_workflow(self):
        """Closing the dialog must not fall through into the application."""
        src = self._src("_show_terms_dialog")
        self.assertIn("def cancelled", src)
        cancelled = src.split("def cancelled", 1)[1].split("self._terms_dialog = TermsDialog", 1)[0]
        self.assertIn("self.destroy()", cancelled)
        self.assertNotIn("then()", cancelled)

    def test_licensing_is_not_replaced_by_the_gate(self):
        """The acknowledgement is layered on top of auth, not instead of it."""
        src = self._src("_on_auth_ok")
        self.assertIn("self._auth_session = session", src)


class TestSingleSourceOfTerms(unittest.TestCase):
    def test_dialog_and_page_read_the_same_module(self):
        import inspect
        import ui.views as views
        from licensing import terms_dialog

        page = inspect.getsource(views.AboutOwnershipView)
        dialog = inspect.getsource(terms_dialog.TermsDialog)
        for src, label in ((page, "page"), (dialog, "dialog")):
            self.assertIn("SECTIONS", src, label)
            self.assertIn("ACKNOWLEDGEMENT_POINTS", src, label)
            self.assertIn("LEGAL_NOTE", src, label)

    def test_neither_hardcodes_agreement_prose(self):
        import inspect
        import ui.views as views
        from licensing import terms_dialog

        for src in (inspect.getsource(views.AboutOwnershipView),
                    inspect.getsource(terms_dialog.TermsDialog)):
            self.assertNotIn("internal YouTube content production", src)
            self.assertNotIn("50% ownership interest", src)


class TestNoSensitiveDataInUi(unittest.TestCase):
    def test_page_shows_display_name_only(self):
        import inspect
        import ui.views as views

        src = inspect.getsource(views.AboutOwnershipView)
        self.assertIn("display_name", src)
        for banned in ("access_token", "refresh_token", ".email", "user_id", "apikey"):
            self.assertNotIn(banned, src, f"page exposes {banned}")

    def test_dialog_shows_display_name_only(self):
        import inspect
        from licensing import terms_dialog

        src = inspect.getsource(terms_dialog.TermsDialog)
        for banned in ("access_token", "refresh_token", ".email", "apikey", "supabase_credentials"):
            self.assertNotIn(banned, src, f"dialog exposes {banned}")


class TestNavigationPlacement(unittest.TestCase):
    def test_about_is_the_final_nav_item_after_qa(self):
        from ui.theme import NAV_ITEMS

        keys = [k for k, _label in NAV_ITEMS]
        self.assertEqual(keys[-1], "about")
        self.assertEqual(keys[-2], "qa")

    def test_nav_label_matches_the_terms_title(self):
        from ui.theme import NAV_ITEMS
        from licensing import terms

        self.assertEqual(dict(NAV_ITEMS)["about"], terms.TITLE)


class TestFailureBoundaries(unittest.TestCase):
    """Every unhappy path must fail CLOSED: unknown is never 'accepted'."""

    def setUp(self):
        self._creds = _creds(); self._creds.start()
        self.addCleanup(self._creds.stop)

    # --- expired / revoked session -------------------------------------
    def test_expired_session_on_lookup_is_revoked_not_accepted(self):
        for status in (401, 403):
            with patch.object(requests, "get", return_value=_Resp(status, [])):
                with self.assertRaises(AuthError) as ctx:
                    terms.has_acknowledged(_session())
                self.assertEqual(ctx.exception.code, "revoked", status)

    def test_expired_session_on_write_is_revoked(self):
        for status in (401, 403):
            with patch.object(requests, "post", return_value=_Resp(status)):
                with self.assertRaises(AuthError) as ctx:
                    terms.save_acknowledgement(_session())
                self.assertEqual(ctx.exception.code, "revoked", status)

    # --- malformed responses -------------------------------------------
    def test_unparseable_lookup_response_raises(self):
        class Bad:
            status_code = 200
            def json(self):
                raise ValueError("not json")

        with patch.object(requests, "get", return_value=Bad()):
            with self.assertRaises(AuthError):
                terms.has_acknowledged(_session())

    def test_non_list_lookup_response_is_not_accepted(self):
        with patch.object(requests, "get", return_value=_Resp(200, {"unexpected": True})):
            self.assertFalse(terms.has_acknowledged(_session()))

    def test_row_present_but_empty_list_is_not_accepted(self):
        with patch.object(requests, "get", return_value=_Resp(200, [])):
            self.assertFalse(terms.has_acknowledged(_session()))

    # --- missing profile / display_name --------------------------------
    def test_missing_display_name_still_writes_and_sends_null(self):
        with patch.object(requests, "post", return_value=_Resp(201)) as post:
            terms.save_acknowledgement(_session(name=""))
        body = post.call_args.kwargs["json"]
        self.assertIsNone(body["display_name"])
        self.assertEqual(body["user_id"], "user-123")

    def test_missing_display_name_does_not_block_acknowledgement(self):
        with patch.object(requests, "get", return_value=_Resp(200, [{"acknowledged": True}])):
            self.assertTrue(terms.has_acknowledged(_session(name="")))

    # --- lookup vs write are independent boundaries ---------------------
    def test_lookup_failure_does_not_write_anything(self):
        with patch.object(requests, "get", side_effect=requests.RequestException("x")), \
             patch.object(requests, "post") as post:
            with self.assertRaises(AuthError):
                terms.has_acknowledged(_session())
            post.assert_not_called()

    # --- no credential leakage on any path -----------------------------
    def test_errors_never_contain_the_anon_key(self):
        with patch.object(requests, "get", return_value=_Resp(500, [])):
            try:
                terms.has_acknowledged(_session())
            except AuthError as exc:
                self.assertNotIn("anon-key", str(exc))
                self.assertNotIn("tok", str(exc))


class TestClientDoesNotControlTimestamp(unittest.TestCase):
    """Phase 6: the acknowledgement time is the server's, not the client's."""

    def setUp(self):
        self._creds = _creds(); self._creds.start()
        self.addCleanup(self._creds.stop)

    def test_no_now_literal_anywhere_in_the_client_payload(self):
        with patch.object(requests, "post", return_value=_Resp(201)) as post:
            terms.save_acknowledgement(_session())
        blob = str(post.call_args.kwargs["json"])
        self.assertNotIn("now()", blob)
        self.assertNotIn("acknowledged_at", blob)

    def test_source_contains_no_now_literal(self):
        import inspect
        self.assertNotIn('"now()"', inspect.getsource(terms.save_acknowledgement))
