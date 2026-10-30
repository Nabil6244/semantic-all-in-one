from product_trailer import balance, director


def _flat(*nums):
    return {"kind": "scene", "layer": {"phones": [{"label": f"P{i}", "text": n} for i, n in enumerate(nums)], "title": "Speed"}}


def _doc(items):
    return {"chapters": [{"title": "", "items": items}]}


def _line(t):
    return {"kind": "line", "text": t}


def test_run_of_three_flat_scenes_is_broken():
    items = []
    for i in range(4):
        items += [_flat("60W"), _line(f"Sentence {i} about the screen")]
    out = balance.balance(_doc(items))
    fams = [balance.family(x) for x in out["chapters"][0]["items"] if balance.family(x)]
    assert all(not (fams[i] == fams[i + 1] == fams[i + 2]) for i in range(len(fams) - 2))
    assert len([x for x in out["chapters"][0]["items"] if x["kind"] == "line"]) == 4


def test_measured_pair_becomes_bench_when_missing():
    items = [_flat("1.2 ms", "59.2 ms"), _line("Latency was 1.2 ms against 59.2 ms.")]
    for i in range(5):
        items += [{"kind": "tweet", "author": "A", "handle": "", "text": "x", "highlight": ""} if i % 2 else _flat("5000mAh"), _line(f"Line {i}.")]
    fams = {balance.family(x) for x in balance.balance(_doc(items))["chapters"][0]["items"]}
    assert "bench" in fams and "3d" in fams


def test_authors_directive_is_kept():
    items = []
    for i in range(4):
        s = _flat("60W"); s["_own"] = True
        items += [s, _line(f"Line {i}.")]
    out = balance.balance(_doc(items))
    assert [balance.family(x) for x in out["chapters"][0]["items"] if balance.family(x)] == ["flat"] * 4
    assert not any("_own" in x for x in out["chapters"][0]["items"])


def test_footage_only_when_enabled():
    items = []
    for i in range(6):
        items += [_flat(f"{i}W") if i % 2 else {"kind": "tweet", "author": "A", "handle": "", "text": "x", "highlight": ""}, _line("It feels great in the hand." if i == 3 else f"Line {i}.")]
    assert "footage" not in {balance.family(x) for x in balance.balance(_doc(items), footage=False)["chapters"][0]["items"]}
    assert "footage" in {balance.family(x) for x in balance.balance(_doc(items), footage=True)["chapters"][0]["items"]}


from unittest_adopt import adopt
adopt(globals())
