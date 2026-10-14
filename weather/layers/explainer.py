"""Explainer cards: fixed, words-only explanations a weather story often needs, in the National Weather Service's own terms.

    explainer   no data_source   extra {"template": "watch_warning"}

    watch_warning   TORNADO WATCH: conditions are favorable for tornadoes — be prepared
                    TORNADO WARNING: a tornado has been sighted or indicated by weather radar — take action now
                    (NWS: https://www.weather.gov/safety/tornado-ww)

The words are fixed here, never written by the AI or the engine, and hold no numbers."""

from __future__ import annotations

from . import LayerType, register

TEMPLATES = {
    "watch_warning": {
        "cards": [
            {"kicker": "TORNADO WATCH", "text": "CONDITIONS ARE FAVORABLE FOR TORNADOES", "act": "BE PREPARED", "color": "#FFD43B"},
            {"kicker": "TORNADO WARNING", "text": "A TORNADO HAS BEEN SIGHTED OR INDICATED BY WEATHER RADAR", "act": "TAKE ACTION NOW",
             "color": "#E8364F"},
        ],
        "source": "Definitions: National Weather Service (weather.gov/safety/tornado-ww)",
    },
}


def _check(row) -> None:
    if row.extra.get("template") not in TEMPLATES:
        raise ValueError(f"explainer extra template is one of {', '.join(TEMPLATES)}")


def _build(row, snap, window, out) -> None:
    t = TEMPLATES[row.extra["template"]]
    out.events.append({"id": f"wx_{row.id}", "type": "explainer", "t_in": window.t_in, "t_out": window.t_out, "cards": t["cards"]})
    out.shown[row.id] = [{"kind": "text", "text": t["source"]}]


register(LayerType(name="explainer", products=(), extra_keys=frozenset({"template"}), build=_build, check=_check,
                   about="fixed NWS explanations (watch vs warning), words only"))
