"""War Documentary portraits: exact-person resolution, licence gate, cache reuse, planner and credits wiring. All offline (mocked network)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import io
import json

from PIL import Image

from cinematic_explainer.war import portraits as P

ENTRY = {"id": "zelensky", "name": "Volodymyr Zelensky", "aliases": ["Zelensky", "Zelenskyy"]}


def _jpeg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (800, 1000), (120, 90, 60)).save(b, "JPEG")
    return b.getvalue()


def _claims(human=True, img="Z.jpg"):
    c = {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5" if human else "Q1"}}}}]}
    if img:
        c["P18"] = [{"mainsnak": {"datavalue": {"value": img}}, "rank": "normal"}]
    return c


def fake_http(licence="CC BY 4.0", human=True, label="Volodymyr Zelenskyy", img="Z.jpg", calls=None):
    def http(url, params):
        if calls is not None:
            calls.append(params.get("action"))
        a = params["action"]
        if a == "wbsearchentities":
            return {"search": [{"id": "Q1"}]}
        if a == "wbgetentities":
            return {"entities": {"Q1": {"labels": {"en": {"value": label}}, "aliases": {}, "claims": _claims(human, img),
                                         "descriptions": {"en": {"value": "President"}}}}}
        return {"query": {"pages": {"1": {"title": "File:Z.jpg", "imageinfo": [{"thumburl": "https://x/z.jpg", "mime": "image/jpeg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Z.jpg",
                "extmetadata": {"LicenseShortName": {"value": licence}, "Artist": {"value": "<a>Office of the President</a>"},
                                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/4.0"}, "AttributionRequired": {"value": "true"}}}]}}}}
    return http


class WarPortraitsTests(unittest.TestCase):
    def tmp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name)

    def patch(self, obj, name, value):
        p = mock.patch.object(obj, name, value)
        p.start()
        self.addCleanup(p.stop)

    def test_licence_gate(self):
        assert P.classify_licence("CC BY-SA 4.0")["reuse"] == "share_alike"
        assert P.classify_licence("CC BY 4.0")["reuse"] == "attribution_required"
        assert P.classify_licence("Public domain")["reuse"] == "free"
        assert P.classify_licence("CC0")["reuse"] == "free"
        for bad in ("", "CC BY-NC 4.0", "CC BY-ND 2.0", "Fair use", "All rights reserved"):
            assert not P.classify_licence(bad)["ok"], bad

    def test_fetch_caches_once_and_records_provenance(self):
        tmp_path = self.tmp()
        calls = []
        r = P.fetch_portrait(ENTRY, store=tmp_path, http=fake_http(calls=calls), download=lambda u: _jpeg())
        assert r and r["reuse"] == "attribution_required"
        rec = r["record"]
        assert rec["wikidata_qid"] == "Q1" and rec["licence"] == "CC BY 4.0" and rec["creator"] == "Office of the President"
        assert rec["source_url"].endswith("File:Z.jpg") and rec["licence_status"] == P.STATUS_TEXT
        assert max(Image.open(r["path"]).size) <= 1024
        n = len(calls)
        again = P.fetch_portrait(ENTRY, store=tmp_path, http=fake_http(calls=calls), download=lambda u: self.fail("downloaded twice"))
        assert again["path"] == r["path"] and len(calls) == n            # cache hit: no request at all

    def test_lookalike_and_non_human_are_rejected(self):
        tmp_path = self.tmp()
        assert P.fetch_portrait(ENTRY, store=tmp_path / "a", http=fake_http(label="Volodymyr Zelenskyi Jr"), download=lambda u: _jpeg()) is None
        assert P.fetch_portrait(ENTRY, store=tmp_path / "b", http=fake_http(human=False), download=lambda u: _jpeg()) is None
        assert P.fetch_portrait(ENTRY, store=tmp_path / "c", http=fake_http(img=None), download=lambda u: _jpeg()) is None

    def test_bad_licence_is_skipped_and_remembered(self):
        tmp_path = self.tmp()
        assert P.fetch_portrait(ENTRY, store=tmp_path, http=fake_http(licence="CC BY-NC 4.0"), download=lambda u: _jpeg()) is None
        rec = json.loads((tmp_path / "zelensky.json").read_text())
        assert rec["status"] == "skipped" and "NC" in rec["reason"]
        assert P.portrait_for("zelensky", tmp_path) is None
        # remembered: a second call makes no request
        assert P.fetch_portrait(ENTRY, store=tmp_path, http=lambda *a: self.fail("network"), download=lambda u: self.fail("dl")) is None

    def test_network_failure_leaves_name_plate_and_is_not_cached(self):
        tmp_path = self.tmp()
        def boom(*a):
            raise OSError("offline")
        assert P.fetch_portrait(ENTRY, store=tmp_path, http=boom) is None
        assert not (tmp_path / "zelensky.json").exists()

    def test_planner_uses_cached_portrait_and_credits(self):
        tmp_path = self.tmp()
        r = P.fetch_portrait(ENTRY, store=tmp_path, http=fake_http(), download=lambda u: _jpeg())
        self.patch(P, "BUNDLED_DIR", tmp_path)
        from cinematic_explainer.war import planner as PL
        from cinematic_explainer.war import semantics as S

        class Ctx:
            assets = {}
        class Ent:
            id = "zelensky"
            entry = {}
        assert PL._portrait(Ctx, Ent) == r["path"]
        Ctx.assets = {"portrait:zelensky": __file__}
        assert PL._portrait(Ctx, Ent) == __file__                      # an explicit asset still wins
        prov = P.provenance_for_path(r["path"])
        assert prov.provider == "Wikimedia Commons" and "CC BY 4.0" in prov.licence and "Office of the President" in prov.attribution
        from cinematic_explainer.war import provenance as PV
        line = PV.credits_lines([prov])[0]
        assert "Office of the President" in line and "File:Z.jpg" in line

    def test_no_cache_means_name_plate(self):
        tmp_path = self.tmp()
        self.patch(P, "BUNDLED_DIR", tmp_path / "none")
        self.patch(P, "user_dir", lambda: tmp_path / "none2")
        from cinematic_explainer.war import planner as PL

        class Ctx:
            assets = {}
        class Ent:
            id = "zelensky"
            entry = {}
        assert PL._portrait(Ctx, Ent) is None


if __name__ == "__main__":
    unittest.main()
