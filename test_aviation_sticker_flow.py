"""Flow aircraft stickers: prompt rules, green-screen cut-out, library lookup (aviation/sticker_flow.py). Offline: no Flow."""

from PIL import Image, ImageDraw

from aviation import sticker_flow as SF


def _green_plane(path, w=800, h=400):
    im = Image.new("RGB", (w, h), (0, 255, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((80, 170, 720, 230), radius=30, fill=(240, 240, 245))          # fuselage
    d.polygon([(90, 175), (140, 60), (190, 175)], fill=(20, 40, 120))                  # tail
    d.polygon([(330, 210), (470, 210), (420, 300)], fill=(200, 200, 210))              # wing
    im.save(path)
    return path


def test_prompt_rules():
    p = SF.prompt("msa", "1960s", "b707", 1966)
    assert "Boeing 707" in p and "Malaysia-Singapore Airlines" in p and "nose pointing to the right" in p
    assert "bright green" in p and p.endswith("No text, no letters, no logos, no watermark.")


def test_cut_out_keys_the_green_and_crops(tmp_path):
    st = SF.cut_out(_green_plane(tmp_path / "p.png"))
    assert st is not None and st.mode == "RGBA"
    assert st.getpixel((0, 0))[3] < 40 and st.width > 500
    assert not any(p[1] > p[0] + 40 and p[1] > p[2] + 40 and p[3] > 200 for p in st.getdata())     # no green left on the plane


def test_cut_out_refuses_a_picture_that_is_not_a_plane_on_green(tmp_path):
    p = tmp_path / "scene.png"
    Image.new("RGB", (800, 400), (90, 120, 160)).save(p)
    assert SF.cut_out(p) is None


def test_lookup_finds_a_made_sticker(tmp_path):
    from aviation import library as LIB
    st = SF.cut_out(_green_plane(tmp_path / "p.png"))
    png = tmp_path / "s.png"
    st.save(png)
    LIB.add("sticker", str(png), airline="msa", era="1960s", subject="b707", source="flow", credit="AI", ai=True,
            tags=("flow",), approved=True, lib=tmp_path / "lib")
    assert SF.lookup("msa", "1960s", "b707", lib=tmp_path / "lib")
    assert SF.lookup("msa", "1970s", "b707", lib=tmp_path / "lib")          # same type, nearest era still used
    assert SF.lookup("singapore_airlines", "1960s", "b707", lib=tmp_path / "lib") is None
