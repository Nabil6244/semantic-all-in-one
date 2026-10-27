"""War Documentary equipment photographs: licence and identity gates, one-time cached fetch (mocked network), lookup, planner and card hookup."""
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from cinematic_explainer.war import cards as C
from cinematic_explainer.war import catalog
from cinematic_explainer.war import equipment_images as EI

ENTRY = {"id": "t-72", "name": "T-72", "aliases": ["T-72", "T-72B3"]}
HIMARS = catalog.get_equipment("m142-himars")


def _json(title="File:Foo HIMARS.jpg", lic="CC BY-SA 4.0", desc="A HIMARS launcher", artist="<a href='x'>Jane Doe</a>"):
    def get(params):
        return {"query": {"pages": {"1": {"title": title, "imageinfo": [{"url": "https://u/x.jpg", "thumburl": "https://u/t.jpg", "width": 4000, "height": 3000,
                "descriptionurl": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
                "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": artist}, "ImageDescription": {"value": desc},
                                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"}}}]}}}}
    return get


def _bytes(_url):
    b = io.BytesIO()
    Image.new("RGB", (2000, 1000), (90, 110, 70)).save(b, "JPEG")
    return b.getvalue()


@pytest.mark.parametrize("lic,ok", [("Public domain", True), ("CC0", True), ("CC BY 4.0", True), ("CC BY-SA 3.0", True), ("CC BY-NC 4.0", False),
                                    ("CC BY-ND 2.0", False), ("", False), ("Fair use", False), ("Unknown", False), ("Copyrighted free use", False)])
def test_licence_gate(lic, ok):
    assert EI.acceptable_licence(lic) is ok


def test_identity_requires_the_exact_designation():
    assert EI.identity_ok(HIMARS, "File:HIMARS - missile launched.jpg", "")
    assert EI.identity_ok(ENTRY, "File:T-72B in Chebarkul.jpg", "")
    assert EI.identity_ok(ENTRY, "File:x.jpg", "A T-72B3 tank")
    assert not EI.identity_ok(ENTRY, "File:T-90 on parade.jpg", "A T-90 main battle tank")     # same class, different system
    assert not EI.identity_ok(ENTRY, "File:T-720 thing.jpg", "")                              # longer number is not a match
    assert not EI.identity_ok(HIMARS, "File:M270 MLRS.jpg", "A multiple launch rocket system")


def test_fetch_stores_once_with_credit(tmp_path):
    rec = EI.fetch_and_store("m142-himars", "Foo HIMARS.jpg", HIMARS, cache_dir=tmp_path, get_json=_json(), get_bytes=_bytes)
    assert rec["creator"] == "Jane Doe" and rec["licence"] == "CC BY-SA 4.0" and "not independently verified" in rec["verification"]
    assert rec["source_url"].startswith("https://commons.wikimedia.org/wiki/") and rec["retrieved"]
    im = Image.open(tmp_path / "m142-himars.jpg")
    assert max(im.size) <= EI.MAX_W
    got = EI.lookup("m142-himars", cache_dir=tmp_path, shipped_index=tmp_path / "none.json")
    assert got and Path(got["path"]).is_file()
    assert EI.credit_line(got) == "Photo: Jane Doe · CC BY-SA 4.0 · Wikimedia Commons"


def test_rejections_write_nothing(tmp_path):
    with pytest.raises(ValueError):
        EI.fetch_and_store("m142-himars", "Foo HIMARS.jpg", HIMARS, cache_dir=tmp_path, get_json=_json(lic="CC BY-NC 4.0"), get_bytes=_bytes)
    with pytest.raises(ValueError):
        EI.fetch_and_store("m142-himars", "Foo.jpg", HIMARS, cache_dir=tmp_path, get_json=_json(title="File:Foo.jpg", desc="A rocket truck"), get_bytes=_bytes)
    assert not list(tmp_path.iterdir())


def test_lookup_ignores_missing_file_and_bad_licence(tmp_path):
    idx = tmp_path / "i.json"
    idx.write_text(json.dumps({"version": 1, "images": {"a": {"file": "a.jpg", "licence": "CC BY 4.0"}, "b": {"file": "b.jpg", "licence": "CC BY-NC 4.0"}}}))
    (tmp_path / "b.jpg").write_bytes(_bytes(""))
    nocache = tmp_path / "nocache"
    assert EI.lookup("a", shipped_index=idx, shipped_dir=tmp_path, cache_dir=nocache) is None      # file missing
    assert EI.lookup("b", shipped_index=idx, shipped_dir=tmp_path, cache_dir=nocache) is None      # licence not allowed
    assert EI.lookup("", shipped_index=idx, cache_dir=nocache) is None


def test_shipped_index_is_complete_and_honest():
    d = json.loads(EI.SHIPPED_INDEX.read_text(encoding="utf-8"))["images"]
    assert len(d) >= 10
    for eid, rec in d.items():
        assert catalog.get_equipment(eid), eid
        assert EI.acceptable_licence(rec["licence"]), eid
        assert rec["creator"] and rec["source_url"].startswith("https://commons.wikimedia.org/wiki/File:") and rec["retrieved"], eid
        assert "not independently verified" in rec["verification"], eid
        assert EI.identity_ok(catalog.get_equipment(eid), rec["commons_title"], rec.get("description", ""), ["Iskander", "Shahed", "Pantsir"]), eid
        assert (EI.SHIPPED_DIR / rec["file"]).is_file() and max(Image.open(EI.SHIPPED_DIR / rec["file"]).size) <= EI.MAX_W, eid


def _card_params(**kw):
    p = catalog.equipment_card_params(HIMARS)
    p.update({"confidence": "stated", "icon": HIMARS.get("class", ""), "status": "attributed"})
    p.update(kw)
    return p


def test_card_with_photo_shows_credit_and_no_silhouette_chip(tmp_path):
    rec = EI.lookup("m142-himars")
    assert rec
    with_photo = C.equipment_card(3.0, 8.0, _card_params(image=rec["path"], image_credit=EI.credit_line(rec)))
    no_credit = C.equipment_card(3.0, 8.0, _card_params(image=rec["path"]))
    silhouette = C.equipment_card(3.0, 8.0, _card_params(image=None))
    assert with_photo is not None and no_credit is not None and silhouette is not None
    assert with_photo.tobytes() != no_credit.tobytes()            # the credit strip is drawn
    assert with_photo.tobytes() != silhouette.tobytes()


def test_planner_uses_photo_and_credits_it_and_falls_back():
    from cinematic_explainer.war import planner

    def scene(txt):
        return [{"scene_no": "1", "text": txt, "start": 0.0, "end": 12.0, "footage": None}]

    txt = "The M142 HIMARS launcher has a range of about 80 kilometres and Ukraine received it in 2022."
    plan = planner.plan(scene(txt), config={"first_at": 0.5, "check_kinds": False})
    eq = [ly for ly in plan.layers if ly.kind == "equipment_card"]
    if not eq:
        pytest.skip("planner chose another visual for this sentence")
    assert eq[0].params.get("image") and "Wikimedia Commons" in eq[0].params.get("image_credit", "")
    assert "image_record" not in eq[0].params
    assert any("Wikimedia Commons" in c or "Jabbari" in c or "U.S. Army" in c for c in plan.credits), plan.credits
    off = planner.plan(scene(txt), config={"first_at": 0.5, "check_kinds": False, "equipment_photos": False})
    eq2 = [ly for ly in off.layers if ly.kind == "equipment_card"]
    assert eq2 and not eq2[0].params.get("image")                 # silhouette fallback is unchanged
