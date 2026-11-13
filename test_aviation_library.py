import json
import threading
from pathlib import Path

from PIL import Image

from aviation import library as L


def img(p: Path, color=(200, 30, 30), size=(64, 48)):
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(p)
    return p


def test_era_of():
    assert L.era_of(1947) == "1940s"
    assert L.era_of("1969-07-01") == "1960s"
    assert L.era_of(2024) == "2020s"
    assert L.era_of(1920) == "1940s"
    assert L.era_of("x") == "any"
    assert L.era_of(None) == "any"


def test_root_default_and_setting(tmp_path):
    assert L.root({}).as_posix().endswith("assets/aviation/library")
    assert L.root({L.SETTING: str(tmp_path)}) == tmp_path


def test_add_dedup_approve_reject(tmp_path):
    lib = tmp_path / "lib"
    f = img(tmp_path / "a.png")
    e = L.add("sticker", f, airline="Air France", era="1960s", subject="Boeing 707", source="flow", credit="AI", ai=True, lib=lib)
    assert (lib / e["path"]).is_file() and f.is_file()
    assert e["path"].startswith("air_france/1960s/sticker/")
    assert e["w"] == 64 and e["approved"] is False
    e2 = L.add("sticker", f, airline="Air France", era="1960s", subject="boeing 707", source="flow", credit="AI", ai=True, lib=lib)
    assert e2["id"] == e["id"] and L.stats(lib=lib)["total"] == 1
    assert L.find("sticker", lib=lib) == []
    L.approve([e["id"]], lib=lib)
    assert len(L.find("sticker", lib=lib)) == 1
    r = L.reject(e["id"], lib=lib)
    assert r and not (lib / e["path"]).exists()
    moved = lib / "_rejected" / "air_france" / "1960s" / "sticker" / Path(e["path"]).name
    assert moved.is_file()
    assert L.find("sticker", approved_only=False, lib=lib) == []
    assert L.stats(lib=lib)["rejected"] == 1


def test_find_ranking(tmp_path):
    lib = tmp_path / "lib"
    f1, f2, f3, f4 = (img(tmp_path / f"{i}.png", (i * 40, 0, 0)) for i in range(1, 5))
    kw = dict(source="s", credit="c", ai=False, approved=True, lib=lib)
    g = L.add("hero", f1, airline="", era="", subject="A350", **kw)
    ae = L.add("hero", f2, airline="Delta", era="2010s", subject="A350", **kw)
    a = L.add("hero", f3, airline="Delta", era="1990s", subject="A350", **kw)
    other = L.add("hero", f4, airline="KLM", era="2010s", subject="A350", **kw)
    ids = [e["id"] for e in L.find("hero", airline="Delta", era="2010s", subject="A350", lib=lib)]
    assert ids[0] == ae["id"]
    assert ids == [ae["id"], g["id"]]
    assert other["id"] not in ids
    ids2 = [e["id"] for e in L.find("hero", airline="Delta", subject="A350", lib=lib)]
    assert set(ids2[:2]) == {ae["id"], a["id"]} and ids2[-1] == g["id"]
    assert L.best("hero", airline="Qantas", subject="A350", lib=lib)["id"] == g["id"]
    assert L.best("hero", subject="B777", lib=lib) is None


def test_mark_used(tmp_path):
    lib = tmp_path / "lib"
    e = L.add("photo", img(tmp_path / "a.png"), lib=lib)
    L.mark_used(e["id"], "p1", lib=lib)
    L.mark_used(e["id"], "p1", lib=lib)
    assert L.find("photo", approved_only=False, lib=lib)[0]["used_in"] == ["p1"]


def test_import_capture_and_clip(tmp_path):
    lib = tmp_path / "lib"
    page = img(tmp_path / "cap" / "page.png", size=(100, 60))
    lead = img(tmp_path / "cap" / "lead.jpg", (0, 90, 200))
    scroll = tmp_path / "cap" / "scroll.mp4"
    scroll.write_bytes(b"not really a video")
    cap = {"ok": True, "url": "https://en.wikipedia.org/wiki/Joon", "site": "wikipedia.org", "title": "Joon", "credit": "Wikipedia",
           "page": {"png": str(page)}, "scroll": {"path": str(scroll), "duration": 4.0, "found": True},
           "elements": [{"kind": "lead", "path": str(lead), "caption": "A321", "credit": "Photo: X"}],
           "data": [{"kind": "founded", "value": 2017, "text": "founded 2017", "source": "wikipedia.org"}]}
    out = L.import_capture(cap, {"airline": "Joon", "era": "2010s", "subject": "Joon launch"}, lib=lib)
    assert sorted(e["kind"] for e in out) == ["data", "page", "photo", "scroll"]
    assert all(not e["approved"] and e["url"] == cap["url"] for e in out)
    assert [e for e in out if e["kind"] == "photo"][0]["credit"] == "Photo: X"
    assert L.import_capture({"ok": False}, {}, lib=lib) == []
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"clipdata")
    ce = L.import_clip({"local_path": str(clip), "source_url": "https://youtu.be/x", "channel": "Chan", "duration": 5.5},
                       {"airline": "Joon", "subject": "A321"}, lib=lib)
    assert ce["kind"] == "clip" and ce["duration"] == 5.5 and "Chan" in ce["credit"]


def test_contact_sheet(tmp_path):
    lib = tmp_path / "lib"
    es = [L.add("sticker", img(tmp_path / f"{i}.png", (i * 30, 50, 50)), credit="c", approved=bool(i % 2), lib=lib) for i in range(1, 4)]
    es.append(L.add("clip", _fake(tmp_path), lib=lib))
    out = L.contact_sheet(es, tmp_path / "sheet.png", cols=2, lib=lib)
    assert out.is_file() and Image.open(out).width > 400


def _fake(tmp_path):
    p = tmp_path / "v.mp4"
    p.write_bytes(b"bad")
    return p


def test_concurrent_adds(tmp_path):
    lib = tmp_path / "lib"
    files = [img(tmp_path / f"t{i}.png", (i, i * 2 % 255, 7)) for i in range(30)]

    def work(chunk):
        for f in chunk:
            L.add("photo", f, airline="x", era="1990s", subject="s", lib=lib)

    ts = [threading.Thread(target=work, args=(files[i::3],)) for i in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    d = json.loads((lib / "index.json").read_text())
    assert len(d["entries"]) == 30 and len({e["id"] for e in d["entries"]}) == 30
    assert not list(lib.glob(".index_*.tmp"))


def test_build_list_skips_approved(tmp_path):
    lib = tmp_path / "lib"
    bible = {"fleet": [{"airline": "Air France", "aircraft": "Concorde", "era": "1970s", "livery": "white"},
                       {"airline": "Air France", "aircraft": "A380", "era": "2010s"}],
             "cast": [{"role": "captain"}], "places": ["Paris CDG", {"name": "JFK"}]}
    first = L.build_list(bible, lib=lib)
    assert {(n["kind"], n["subject"]) for n in first} >= {("hero", "Concorde"), ("hero", "A380"), ("cast", "captain"),
                                                         ("place", "Paris CDG"), ("place", "JFK")}
    assert next(n for n in first if n["kind"] == "hero" and n["subject"] == "Concorde")["prompt"]
    L.add("hero", img(tmp_path / "h.png"), airline="Air France", era="1970s", subject="Concorde", approved=True, lib=lib)
    L.add("place", img(tmp_path / "p.png", (1, 2, 3)), subject="JFK", approved=True, lib=lib)
    L.add("cast", img(tmp_path / "c.png", (3, 2, 1)), subject="captain", approved=False, lib=lib)
    second = L.build_list(bible, lib=lib)
    subs = {(n["kind"], n["subject"]) for n in second}
    assert ("hero", "Concorde") not in subs and ("place", "JFK") not in subs
    assert ("cast", "captain") in subs and ("hero", "A380") in subs


def test_build_list_lenient():
    assert L.build_list({}) == [] or isinstance(L.build_list({}), list)
    assert L.build_list(None) == []
    L.build_list({"fleet": "A320", "cast": {"pilot": {"look": "x"}}, "places": None, "liveries": 3})


def test_needs_from_bible_uses_bible_eras_and_skips_approved(tmp_path):
    from PIL import Image
    from aviation import bible as BB
    from aviation import library as L
    b = BB.read(["In 1966 the two governments formed Malaysia-Singapore Airlines, flying Boeing 707s.",
                 "A captain flew the first Boeing 747 for Singapore Airlines in 1973."])
    need = L.needs_from_bible(b, lib=tmp_path)
    heroes = [n for n in need if n["kind"] == "hero"]
    assert {(n["airline"], n["era"]) for n in heroes} >= {("msa", "1960s"), ("singapore_airlines", "1970s")}
    assert all(n["prompt"].endswith("No text, no letters, no logos, no watermark.") for n in need)
    img = tmp_path / "h.png"
    Image.new("RGB", (64, 32), (240, 200, 0)).save(img)
    e = L.add("hero", str(img), airline="msa", era="1960s", subject="b707", source="flow", credit="AI", ai=True, lib=tmp_path)
    L.approve([e["id"]], lib=tmp_path)
    left = L.needs_from_bible(b, lib=tmp_path)
    assert not [n for n in left if n["kind"] == "hero" and n["airline"] == "msa"]


def test_import_capture_files_under_the_airline_id(tmp_path):
    from PIL import Image
    from aviation import library as L, router as R
    img = tmp_path / "p.png"
    Image.new("RGB", (64, 40), (10, 60, 120)).save(img)
    c = R.classify("In 1972 Singapore Airlines flew the Boeing 747.")
    ents = L.import_capture({"ok": True, "url": "https://x", "site": "x", "credit": "x", "title": "t",
                             "elements": [{"kind": "photo", "path": str(img), "caption": "a 747", "credit": "x"}]}, c, lib=tmp_path / "lib")
    assert ents and all(e["airline"] == "singapore_airlines" for e in ents)
