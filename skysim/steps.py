"""Sky Sim step CSV: one row per step (one rung of the title's ladder), not per shot.

Columns (any case, any order; ',', ';' or tab):
  step       number (order only; rows are kept in file order)
  look       landscape | lake | city | space | moon_surface | journey | helmet   (lake: real mountain silhouettes over a mirror lake)
  place      the held scene: lake_valley, desert, ocean, cracked_rock, ice, a city photo id, ...
  object     what is in the sky / in frame: sun, a star (betelgeuse), a planet, ton618, andromeda ...
  from       where we stand: a planet (space look: the Sun from Mercury) or a moon (moon_surface look)
  distance   '10.8 billion ly', '0.39 AU', '9380 km'  (helmet look: depth below the cloud tops)
  readouts   which numbers to show: distance,size,brightness,light_time,angle,temperature,horizon,depth,
             'clock:1 hour = 7 years', or 'LABEL=value' for a number physics cannot compute (pressure in a descent)
  title      spaced title for the step (blank: made from object/from where it makes sense)
  camera     drift | push | pullback | orbit | rise | descend | fly | static; landscape views: shore | high | mirror
  narration  what is said during this step (finds the step's start in the voiceover)
  note       optional context line for the landscape rung card ('The distance to the Andromeda Galaxy')

read_steps(text) never raises: it repairs what it can and says so in notes.
"""
from __future__ import annotations

import csv
import difflib
import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from . import physics as ph

LOOKS = ('landscape', 'lake', 'city', 'space', 'moon_surface', 'journey', 'helmet')
CAMERAS = ('drift', 'push', 'pullback', 'orbit', 'rise', 'descend', 'fly', 'static', 'shore', 'high', 'mirror')
READOUTS = ('distance', 'distance_au', 'size', 'brightness', 'light_time', 'angle', 'temperature', 'horizon', 'depth')
PLACES = ('lake_valley', 'desert', 'ocean', 'cracked_rock', 'ice', 'meadow', 'canyon')
COLUMNS = ('step', 'look', 'place', 'object', 'from', 'distance', 'readouts', 'title', 'camera', 'narration', 'note')
ALIASES = {'scene': 'look', 'style': 'look', 'location': 'place', 'setting': 'place', 'target': 'object', 'subject': 'object',
           'sky': 'object', 'viewer': 'from', 'vantage': 'from', 'standing_on': 'from', 'depth': 'distance', 'dist': 'distance',
           'readout': 'readouts', 'stats': 'readouts', 'numbers': 'readouts', 'heading': 'title', 'move': 'camera',
           'voiceover': 'narration', 'vo': 'narration', 'text': 'narration', 'line': 'narration', 'script': 'narration', 'id': 'step'}
LOOK_ALIASES = {'ground': 'landscape', 'sky': 'landscape', 'silhouette': 'lake', 'mirror_lake': 'lake', 'night_lake': 'lake', 'skyline': 'city', 'photo': 'city', 'dark': 'space',
                'stars': 'space', 'moon': 'moon_surface', 'surface': 'moon_surface', 'flyout': 'journey', 'trip': 'journey',
                'travel': 'journey', 'pov': 'helmet', 'descent': 'helmet', 'fall': 'helmet', 'visor': 'helmet'}

KNOWN_OBJECTS = {**{k: 'planet' for k in ph.PLANETS}, **{k: 'star' for k in ph.STARS}, **{k: 'black_hole' for k in ph.BLACK_HOLES},
                 **{k: 'moon' for k in ph.MOONS}, 'andromeda': 'galaxy', 'milky_way': 'galaxy', 'rings': 'rings', 'earth_rings': 'rings'}


@dataclass
class Step:
    n: int
    look: str
    place: str = ''
    object: str = ''
    object_kind: str = ''
    from_: str = ''
    distance_m: float | None = None
    readouts: List[str] = field(default_factory=list)
    typed: Dict[str, str] = field(default_factory=dict)      # LABEL=value cells
    clock: Tuple[float, float] | None = None                 # (planet seconds, far seconds) per unit
    title: str = ''
    camera: str = 'drift'
    narration: str = ''
    note: str = ''                                            # a line of context for the rung card ('Where TON 618 really is')


def _close(word: str, choices, cutoff: float = 0.75) -> str | None:
    m = difflib.get_close_matches(word, list(choices), n=1, cutoff=cutoff)
    return m[0] if m else None


def _object_key(name: str) -> Tuple[str, str]:
    """-> (key, kind); kind '' when unknown."""
    k = ph._key(name)
    if not k:
        return '', ''
    if k in KNOWN_OBJECTS:
        return k, KNOWN_OBJECTS[k]
    squashed = {o.replace('_', ''): o for o in KNOWN_OBJECTS}
    if k.replace('_', '') in squashed:
        o = squashed[k.replace('_', '')]
        return o, KNOWN_OBJECTS[o]
    if k.startswith('star_'):
        return _object_key(k[5:])
    c = _close(k, KNOWN_OBJECTS, 0.8)
    return (c, KNOWN_OBJECTS[c]) if c else (k, '')


_DUR = {'s': 1, 'sec': 1, 'second': 1, 'seconds': 1, 'min': 60, 'minute': 60, 'minutes': 60, 'h': 3600, 'hr': 3600,
        'hour': 3600, 'hours': 3600, 'd': 86400, 'day': 86400, 'days': 86400, 'y': ph.YEAR, 'yr': ph.YEAR, 'year': ph.YEAR,
        'years': ph.YEAR}


def _duration(text: str) -> float:
    m = re.fullmatch(r'\s*([0-9]*\.?[0-9]+)\s*([a-z]+)\s*', text.lower())
    if not m or m.group(2) not in _DUR:
        raise ValueError(text)
    return float(m.group(1)) * _DUR[m.group(2)]


def _rows(text: str) -> Tuple[List[str], List[List[str]]]:
    text = (text or '').lstrip('﻿')
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], []
    try:
        dialect = csv.Sniffer().sniff(lines[0], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO('\n'.join(lines)), dialect))
    head = [ph._key(h) for h in rows[0]]
    head = [ALIASES.get(h, h) for h in head]
    return head, rows[1:]


def infer_look(st: Step) -> str:
    if st.object_kind == 'moon' or (st.from_ and ph._key(st.from_) in ph.MOONS and ph._key(st.from_) != 'moon'):
        return 'moon_surface'
    if st.from_ and ph._key(st.from_) in ph.PLANETS:
        return 'space'
    if st.object_kind == 'galaxy':
        return 'journey'
    return 'landscape'


def read_steps(text: str) -> Tuple[List[Step], List[str]]:
    """Step CSV text -> (steps, notes). Never raises."""
    notes: List[str] = []
    try:
        head, rows = _rows(text)
    except Exception as e:  # noqa: BLE001 - a broken file still gives notes, not a crash
        return [], [f'the CSV could not be read ({e})']
    if not head:
        return [], ['the CSV is empty']
    unknown = [h for h in head if h and h not in COLUMNS]
    if unknown:
        notes.append(f'columns not used: {", ".join(unknown)}')
    if 'narration' not in head:
        notes.append('no narration column: steps are spread evenly over the voiceover')
    steps: List[Step] = []
    prev: Step | None = None
    for n, cells in enumerate(rows, start=2):
        r = {h: (cells[i].strip() if i < len(cells) else '') for i, h in enumerate(head) if h in COLUMNS}
        say = lambda msg: notes.append(f'row {n}: {msg}')  # noqa: E731
        if not any(r.values()):
            continue
        if not r.get('narration') and not r.get('object') and not r.get('distance'):
            say('no narration, object or distance; left out')
            continue
        st = Step(n=len(steps) + 1, look='')
        st.narration = re.sub(r'\s+', ' ', r.get('narration', '')).strip()
        # object
        if r.get('object'):
            st.object, st.object_kind = _object_key(r['object'])
            if not st.object_kind:
                say(f'object {r["object"]!r} is not known; drawn as a plain star of that name')
                st.object_kind = 'star_generic'
        elif prev:
            st.object, st.object_kind = prev.object, prev.object_kind
        st.from_ = ph._key(r.get('from', '')) or (prev.from_ if prev and not r.get('object') else '')
        if st.from_ and st.from_ not in ph.PLANETS and st.from_ not in ph.MOONS:
            c = _close(st.from_, list(ph.PLANETS) + list(ph.MOONS))
            say(f'standing on {r["from"]!r} is not known' + (f'; read as {c}' if c else '; left out'))
            st.from_ = c or ''
        # distance
        if r.get('distance'):
            try:
                st.distance_m = ph.parse_distance(r['distance'])
            except ValueError:
                say(f'distance {r["distance"]!r} not understood' + ('; kept from the step before' if prev and prev.distance_m else ''))
                st.distance_m = prev.distance_m if prev else None
        elif prev and prev.object == st.object:
            st.distance_m = prev.distance_m
        # look
        look = ph._key(r.get('look', ''))
        look = LOOK_ALIASES.get(look, look)
        if look and look not in LOOKS:
            c = _close(look, LOOKS, 0.6)
            say(f'look {r["look"]!r} is not known; ' + (f'read as {c}' if c else 'chosen from the row'))
            look = c or ''
        st.look = look or (prev.look if prev else '') or infer_look(st)
        # place
        st.place = ph._key(r.get('place', '')) or (prev.place if prev and prev.look == st.look else '')
        if st.look == 'lake':
            st.place = st.place or 'lake'
        if st.look == 'landscape' and not st.place:
            st.place = 'lake_valley'
        if st.look == 'landscape' and st.place not in PLACES:
            c = _close(st.place, PLACES, 0.6)
            say(f'place {st.place!r} is not a landscape; ' + (f'read as {c}' if c else 'lake_valley used'))
            st.place = c or 'lake_valley'
        # readouts
        for cell in [c.strip() for c in re.split(r'[,;|]', r.get('readouts', '')) if c.strip()]:
            if cell.lower().startswith('clock:'):
                try:
                    a, b = cell[6:].split('=')
                    st.clock = (_duration(a), _duration(b))
                except ValueError:
                    say(f'clock {cell!r} not understood (write clock:1 hour = 7 years); left out')
            elif '=' in cell:
                k, v = cell.split('=', 1)
                st.typed[k.strip().upper()] = v.strip()
            else:
                k = ph._key(cell)
                k = {'light': 'brightness', 'bright': 'brightness', 'size_in_sky': 'size', 'temp': 'temperature',
                     'travel_time': 'light_time', 'lighttime': 'light_time'}.get(k, k)
                if k in READOUTS:
                    st.readouts.append(k)
                else:
                    c = _close(k, READOUTS, 0.7)
                    say(f'readout {cell!r} is not known' + (f'; read as {c}' if c else '; left out'))
                    if c:
                        st.readouts.append(c)
        if not r.get('readouts') and prev and prev.look == st.look:
            st.readouts, st.typed, st.clock = list(prev.readouts), {}, prev.clock
        # title + camera
        st.title = r.get('title', '')
        st.note = r.get('note', '')
        cam = ph._key(r.get('camera', ''))
        if cam and cam not in CAMERAS:
            c = _close(cam, CAMERAS, 0.6)
            say(f'camera {r["camera"]!r} is not known; {c or "drift"} used')
            cam = c or 'drift'
        st.camera = cam or ('descend' if st.look == 'helmet' else 'fly' if st.look == 'journey' else 'drift')
        steps.append(st)
        prev = st
    if not steps:
        notes.append('no usable step rows')
    return steps, notes
