"""Web pictures on the sticker stage (aviation/storyweb.py), offline with fake search / capture."""

from PIL import Image

from aviation import planner as P
from aviation import storyweb as W

LINES = ["In 1966 the two governments formed Malaysia-Singapore Airlines together.",
         "Malaysia-Singapore Airlines flew its Boeing 707 to London that year.",
         "Malaysia-Singapore Airlines flew its Boeing 707 to Sydney and Hong Kong as well.",
         "Malaysia-Singapore Airlines carried more people every month."]


def _scenes(lines, step=8.0):
    return [{"scene_no": i + 1, "text": t, "start": i * step, "end": (i + 1) * step} for i, t in enumerate(lines)]


def _photo(tmp_path, name, col, flat=False):
    """A photo-like test picture around colour col (noise, so it is not a flat logo); flat=True: a one-colour logo."""
    import random
    p = tmp_path / name
    im = Image.new("RGB", (400, 260), col)
    if not flat:
        rnd = random.Random(name)
        im.putdata([tuple(max(0, min(255, c + rnd.randrange(-60, 60))) for c in col) for _ in range(400 * 260)])
    im.save(p)
    return str(p)


def test_requests_found_on_first_pass():
    pl = P.plan(_scenes(LINES), [{}, {}, {}, {"url": "https://example.com/msa"}])
    kinds = sorted(e["kind"] for _, e in W.requests(pl))
    assert "paper" in kinds and "photo_card" in kinds


def test_two_pass_places_only_passed_pictures(tmp_path):
    good = _photo(tmp_path, "msa.png", (242, 195, 0))          # MSA yellow livery colour passes the livery check
    calls = {"n": 0}

    def search(q, n):
        return [{"url": "https://en.wikipedia.org/wiki/Malaysia-Singapore_Airlines", "title": "Malaysia-Singapore Airlines"}]

    def capture_many(urls, cache_dir, wants=(), key_sentence=""):
        calls["n"] += 1
        return {u: {"ok": True, "url": u, "site": "wikipedia.org", "title": "Malaysia-Singapore Airlines",
                    "text": "Malaysia-Singapore Airlines flew the Boeing 707", "credit": "Wikipedia",
                    "elements": [{"kind": "lead", "path": good, "caption": "", "credit": "Wikipedia"}]} for u in urls}

    def capture(url, cache_dir, wants=(), key_sentence=""):
        return {"ok": False, "reason": "paywall"}

    rows = [{}, {}, {}, {"url": "https://example.com/msa"}]
    pl, rep = W.plan_with_web(_scenes(LINES), rows, tmp_path, search=search, capture=capture, capture_many=capture_many)
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    els = st["params"]["elements"]
    photos = [e for e in els if e["kind"] == "photo_card"]
    assert photos and all(e["args"].get("image") == good and e["args"]["credit"] for e in photos)
    assert not [e for e in els if e["kind"] == "paper"]                 # the paywalled page is not placed at all
    assert not W.requests(pl) or all(e["args"].get("image") for _, e in W.requests(pl))
    assert rep["photo"] >= 1 and rep["web"]


def test_photo_that_fails_checks_is_never_placed(tmp_path):
    bad = _photo(tmp_path, "other.png", (10, 120, 30))

    def search(q, n):
        return [{"url": "https://example.com/other", "title": "Something else entirely"}]

    def capture_many(urls, cache_dir, wants=(), key_sentence=""):
        return {u: {"ok": True, "url": u, "site": "example.com", "title": "Cooking tips", "text": "recipes and cakes",
                    "elements": [{"kind": "lead", "path": bad, "credit": "x"}]} for u in urls}

    pl, rep = W.plan_with_web(_scenes(LINES), None, tmp_path, search=search, capture_many=capture_many)
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    assert not [e for e in st["params"]["elements"] if e["kind"] == "photo_card"]
    assert rep["photo"] == 0


def test_backdrop_requested_per_chapter_and_placed_behind(tmp_path):
    import random
    from aviation import stage as G
    rnd = random.Random(1)
    img = Image.new("RGB", (400, 260))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(400 * 260)])
    photo = tmp_path / "p.png"
    img.save(photo)
    logo = _photo(tmp_path, "logo.png", (242, 195, 0), flat=True)
    assert W.photo_like(str(photo)) and not W.photo_like(logo)

    def search(q, n):
        return [{"url": "https://en.wikipedia.org/wiki/Malaysia-Singapore_Airlines", "title": "Malaysia-Singapore Airlines"}]

    def capture_many(urls, cache_dir, wants=(), key_sentence=""):
        return {u: {"ok": True, "url": u, "site": "wikipedia.org", "title": "Malaysia-Singapore Airlines Boeing 707",
                    "text": "Malaysia-Singapore Airlines flew the Boeing 707", "credit": "Wikipedia",
                    "elements": [{"kind": "lead", "path": str(photo), "caption": "A Malaysia-Singapore Airlines Boeing 707", "credit": "Wikipedia"}]} for u in urls}

    pl, rep = W.plan_with_web(_scenes(LINES), None, tmp_path, search=search, capture_many=capture_many)
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    bds = [e for e in st["params"]["elements"] if e["kind"] == "backdrop"]
    assert bds and all(e["args"].get("image") for e in bds) and all(e["z"] < 0 for e in bds)
    im = G.lay_stage(3.0, 32.0, st["params"])
    assert im is not None
    assert len(set(im.resize((32, 18)).convert("RGB").getdata())) > 60       # a real picture behind, not flat black


def test_backdrop_score_rules_out_the_wrong_era():
    from aviation import router as R
    c = R.classify("In the 1970s Singapore Airlines flew Boeing 747s on its longest routes.")
    assert W.backdrop_score("Singapore Airlines business class seat on the Airbus A350 in 2018", c, 1975) is None
    good = W.backdrop_score("A Singapore Airlines Boeing 747-200 at Paya Lebar in 1977", c, 1975)
    assert good is not None
    assert W.backdrop_score("An aircraft at the gate", c, 1975) is None          # names no airline: not this airline's photo


def test_stage_cuts_to_full_screen_photos(tmp_path):
    import random
    from aviation import story as ST
    rnd = random.Random(3)
    img = Image.new("RGB", (400, 260))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(400 * 260)])
    photo = tmp_path / "p.png"
    img.save(photo)

    def search(q, n):
        return [{"url": "https://en.wikipedia.org/wiki/Malaysia-Singapore_Airlines", "title": "Malaysia-Singapore Airlines"}]

    def capture_many(urls, cache_dir, wants=(), key_sentence=""):
        return {u: {"ok": True, "url": u, "site": "wikipedia.org", "title": "Malaysia-Singapore Airlines Boeing 707",
                    "text": "Malaysia-Singapore Airlines flew the Boeing 707", "credit": "Wikipedia",
                    "elements": [{"kind": "photo", "path": str(photo), "caption": "A Malaysia-Singapore Airlines Boeing 707 in 1967", "credit": "Wikipedia"}]}
                for u in urls}

    lines = LINES * 3
    pl, rep = W.plan_with_web(_scenes(lines, step=6.0), None, tmp_path, search=search, capture_many=capture_many)
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    cuts = sorted(e["t0"] for e in st["params"]["elements"] if e["kind"] == "photo_full")
    assert cuts, "the stage never cut to a full-screen photo"
    assert all(b - a >= ST.CUT_EVERY_S - 1e-6 for a, b in zip(cuts, cuts[1:]))
    from aviation import stage as G
    t = cuts[0] + 1.5
    frame = G.lay_stage(t, st["end"] - st["start"], st["params"])
    assert len(set(frame.resize((32, 18)).convert("RGB").getdata())) > 100     # a full, undimmed photo fills the frame


def test_another_airlines_photo_never_stands_in():
    from aviation import router as R
    c = R.classify("In the 1970s Singapore Airlines flew Boeing 747s on its longest routes.")
    assert W.backdrop_score("An Emirates Airbus A380 taking off", c, 1975) is None
    assert W.backdrop_score("A Singapore Airlines Boeing 747 at Paya Lebar", c, 1975) is not None


def test_chapter_balance_uses_every_flow_plate(tmp_path, monkeypatch):
    import random
    from aviation import sticker_flow as SF
    from aviation import story as ST
    rnd = random.Random(5)
    plates = {}
    for era in ("1960s",):
        im = Image.new("RGB", (400, 260))
        im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(400 * 260)])
        pth = tmp_path / f"plate_{era}.png"
        im.save(pth)
        plates[("msa", era)] = str(pth)
    monkeypatch.setattr(SF, "plate", lambda al, era, lib=None: plates.get((al, era)))
    lines = ["In 1966 the two governments formed Malaysia-Singapore Airlines together, flying Boeing 707s across the region.",
             "Malaysia-Singapore Airlines grew every year in the 1960s, with more passengers on every route it flew.",
             "Malaysia-Singapore Airlines added new aircraft in 1968 and hired more crew for its growing network."] * 3
    pl = P.plan(_scenes(lines, step=7.0), [{"mode": "story", "airline": "msa"}] * len(lines), web={})
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    cuts = [e for e in st["params"]["elements"] if e["kind"] == "photo_full"]
    assert any(e["args"]["image"] == plates[("msa", "1960s")] and e["args"]["ai"] for e in cuts)
    # with ONE picture for the chapter the 35% target cannot be met without repeating it; it is shown once, never looped
    imgs = [e["args"]["image"] for e in sorted(cuts, key=lambda e: e["t0"])]
    assert all(x != y for x, y in zip(imgs, imgs[1:]))                         # never the same picture twice in a row
