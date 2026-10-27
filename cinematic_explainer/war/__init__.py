"""War Documentary style (Russia-Ukraine first, built to carry other conflicts): an isolated, opt-in look pack inside cinematic_explainer.

CONTRACT shared by every module in this package
-----------------------------------------------
Card:      fn(t, dur, params) -> PIL RGBA image of size (look.W, look.H) = 1280x720, or None (nothing to show). Pure function of t and params
           (same inputs -> same pixels); never touches the network or the disk except to read files named in params.
Registries: war.cards.WAR_CARDS and war.maps.MAP_CARDS map a kind string to a card function; war.registry.all_cards() merges them with
           cinematic_explainer.cards.CARDS (the Phase 1 kinds: kicker, source, number, list, portrait, shot_head).
Layer/Shot: cinematic_explainer.render.Layer(kind, start, end, params, dim) and Shot(path, start, end, seek) are reused unchanged.
Status:    every factual visual carries params["status"] in war.tokens.STATUSES (confirmed, attributed, disputed, unverified, illustrative);
           a missing status means "unverified" and is drawn that way, never as confirmed.
Plan:      war.planner.plan(scenes, ...) -> Plan(shots, layers, log, credits). A scene is a dict {text, start, end, words (optional list of
           {w, t0, t1}), footage (optional path), footage_meta (optional dict)}.
Nothing outside cinematic_explainer/ imports this package except the one additive app hook described in war/integration.py.
"""
