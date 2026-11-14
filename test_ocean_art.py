"""Ocean painted-animal library (ocean/art_flow.py): prompts, green cut-out, the drawer preferring library pictures. Offline."""

from PIL import Image, ImageDraw

from ocean import animals as A
from ocean import art_flow as AF


def _green_shark(path, w=900, h=450):
    im = Image.new("RGB", (w, h), (0, 255, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((120, 160, 760, 300), fill=(90, 100, 110))
    d.polygon([(130, 230), (40, 120), (60, 330)], fill=(90, 100, 110))
    im.save(path)
    return path


def test_prompts_are_realistic_and_on_green():
    p = AF.prompt("great_white", "side")
    assert "Not a cartoon" in p and "facing right" in p and "#00FF00" in p and p.endswith("no watermark.")
    assert "directly above" in AF.prompt("orca", "top")
    assert "mouth wide open" in AF.prompt("orca", "jaw")
    assert ("great_white", "top") in AF.ITEMS and ("tooth", "side") in AF.ITEMS


def test_cut_out_keys_green(tmp_path):
    st = AF.cut_out(_green_shark(tmp_path / "s.png"))
    assert st is not None and st.mode == "RGBA" and st.getpixel((st.width - 1, 0))[3] < 40 and st.width > 600


def test_cut_out_rejects_no_green(tmp_path):
    p = tmp_path / "n.png"
    Image.new("RGB", (800, 400), (30, 60, 90)).save(p)
    assert AF.cut_out(p) is None


def test_drawer_uses_library_picture(tmp_path, monkeypatch):
    st = AF.cut_out(_green_shark(tmp_path / "s.png"))
    st.save(tmp_path / "great_white_side.png")
    monkeypatch.setattr(AF, "ART_DIR", tmp_path)
    A._draw_cached.cache_clear()
    im = A.draw("great_white", 400)
    assert abs(im.width - 400) < 40
    sil = A.draw("great_white", 400, silhouette=True)
    assert max(p[0] for p in sil.getdata() if p[3] > 200) < 40          # silhouettes stay dark
    A._draw_cached.cache_clear()


def test_needs_for_plan_lists_only_missing_named_animals(tmp_path, monkeypatch):
    from ocean import planner as P
    monkeypatch.setattr(AF, "ART_DIR", tmp_path)                     # an empty library
    sc, t = [], 0.0
    for ln in ["A manta ray glided over the reef.", "Then two tiger sharks arrived and attacked.",
               "Researchers tracked 12 tiger sharks around the island, and not one came back."]:
        d = len(ln.split()) / 2.6
        sc.append({"text": ln, "start": t, "end": t + d})
        t += d
    pl = P.plan(sc)
    plan = {"layers": pl.layers}
    need = AF.needs_for_plan(plan)
    assert ("manta_ray", "side") in need and ("tiger_shark", "side") in need
    assert ("tiger_shark", "jaw") in need and ("tiger_shark", "top") in need
    AF.cut_out(_green_shark(tmp_path / "x.png")).save(tmp_path / "manta_ray_side.png")
    assert ("manta_ray", "side") not in AF.needs_for_plan(plan)


def test_ray_side_picture_is_seen_from_above():
    assert "from directly above" in AF.prompt("manta_ray", "side")
