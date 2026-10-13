"""Before / after from space (phase 4, post-event): two NASA GIBS daily pictures of the same area, the first cross-fading into
the second, each labelled with its date.

    before_after   gibs:truecolor@2017-08-22|2017-08-31      (or gibs:falsecolor@..., where flood water shows dark blue)

The two pictures are one timed tile layer (weather.layers.Raster) with two frames; the big "BEFORE · AUG 22" / "AFTER · AUG 31"
label is the post_beforeafter graphic. A picture is a daily satellite pass: clouds may cover part of it (choose clear days).

extra: switch (seconds into the layer when the after picture is fully in; default: the middle), crossfade (seconds, 1.5),
opacity (1), labels (two words: ["BEFORE", "AFTER"])."""

from __future__ import annotations

from ..post import gibs
from ..post.fmt import day, named, no_digits, short
from ..provenance import Sourced
from . import Frame, LayerType, Raster, register


def _dates(row):
    parts = [p.strip() for p in row.data_source.target.split("|")]
    if len(parts) != 2:
        raise ValueError("before_after takes two dates: gibs:truecolor@2017-08-22|2017-08-31")
    a, b = day(parts[0]), day(parts[1])
    if b <= a:
        raise ValueError(f"the after picture ({b}) must be later than the before picture ({a})")
    return a, b


def _labels(row):
    labels = row.extra.get("labels", ["BEFORE", "AFTER"])
    if not (isinstance(labels, list) and len(labels) == 2):
        raise ValueError('extra labels must be two words, e.g. ["BEFORE", "AFTER"]')
    return [no_digits(str(x).upper(), "the label") for x in labels]


def _check(row) -> None:
    gibs.layer(row.data_source.product)
    _dates(row)
    _labels(row)
    if row.data_source.selector:
        raise ValueError("before_after takes no #selector")


def _fetch(row, ctx) -> None:
    """Ask GIBS whether it has a picture for each day (the pictures themselves are tiles the renderer downloads)."""
    for d in _dates(row):
        key = f"post:gibs:{row.data_source.product}:{d}"
        if key in ctx.snap.extra:
            continue
        url = gibs.domain_url(row.data_source.product, d)
        if not gibs.has_day(ctx.get_text(url)):
            raise ValueError(f"NASA GIBS has no {gibs.layer(row.data_source.product)[1]} picture for {d}")
        ctx.snap.extra[key] = {"url": url, "template": gibs.tile_template(row.data_source.product, d), "fetched": ctx.now.replace(microsecond=0).isoformat()}


def _build(row, snap, window, out) -> None:
    prod = row.data_source.product
    a, b = _dates(row)
    labels = _labels(row)
    length = window.t_out - window.t_in
    wipe = row.extra.get("transition", "crossfade") == "wipe"
    xf = min(float(row.extra.get("crossfade", 3.0 if wipe else 1.5)), length / 3)
    switch = float(row.extra.get("switch", length / 2))
    if not (xf <= switch < length):
        raise ValueError(f"extra switch {switch:g}s must fall inside the layer ({length:.1f}s) after the crossfade")
    texts = [f"{labels[0]} · {short(a)}", f"{labels[1]} · {short(b)}"]
    raster = Raster(f"wx_{row.id}", window.t_in, window.t_out,
                    frames=[Frame(0.0, gibs.provider(prod, a), texts[0]), Frame(switch, gibs.provider(prod, b), texts[1])],
                    opacity=float(row.extra.get("opacity", 1.0)), crossfade_s=xf, above_fills=False, clock=False).to_dict()
    if wipe:
        raster["wipe"] = True   # the page reveals the after picture behind a moving edge (weather-engine/page.js) instead of a fade
    out.rasters.append(raster)
    out.events.append({"id": f"wx_{row.id}_label", "type": "post_beforeafter", "t_in": window.t_in, "t_out": window.t_out,
                       "frames": [{"at": 0.0, "label": labels[0], "date": short(a, year=True)}, {"at": switch, "label": labels[1], "date": short(b, year=True)}],
                       "crossfade": xf, "foot": gibs.layer(prod)[1].upper() + " · NASA GIBS"})
    for lab, d in zip(labels, (a, b)):
        e = snap.extra.get(f"post:gibs:{prod}:{d}") or {}
        out.report.add(row.id, f"{lab.lower()} picture date", short(d, year=True),
                       Sourced(d.isoformat(), "date", f"NASA GIBS {gibs.layer(prod)[1]}", e.get("template") or gibs.tile_template(prod, d), gibs.layer(prod)[0],
                               d.isoformat(), e.get("fetched", "")))
    out.credit(gibs.CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Satellite: NASA GIBS {gibs.layer(prod)[1]}, {short(a)} and {short(b)}"}]


register(LayerType(name="before_after", products=[("gibs", p) for p in gibs.LAYERS], extra_keys=frozenset({"switch", "crossfade", "opacity", "labels", "transition"}),
                   fetch=named(_fetch), build=named(_build), check=_check,
                   about="two daily satellite pictures of the same area, cross-faded, labelled BEFORE / AFTER with their dates"))
