"""Sky Sim planner: steps + the voiceover's timed words -> the renderer's spec (shot kind `sky` + sk_* layers).

Rules (docs/skysim/PLAN.md):
- A step starts where its narration starts in the voiceover; it ends where the next one starts.
- Steps that keep the same look and place are one held scene: the sky moves from the last step's state to this one's
  during the step (`sky_from` -> `sky`), with no cut. A new look or place crossfades.
- Every number on screen comes from skysim.physics; only LABEL=value cells (things physics cannot compute) are typed.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import physics as ph
from .steps import Step

WIDTH, HEIGHT, FPS = 1920, 1080, 30
FADE_S = 0.8
LEADER_BELOW_DEG = 0.3          # smaller than this in the sky: a label with a leader line points at it

LABELS = {'distance': 'DISTANCE', 'distance_au': 'DISTANCE FROM THE SUN', 'size': 'SIZE IN THE SKY', 'brightness': 'LIGHT',
          'light_time': 'LIGHT TRAVEL TIME', 'angle': 'ANGLE IN THE SKY', 'temperature': 'AVERAGE TEMPERATURE ON EARTH',
          'horizon': 'EVENT HORIZON', 'depth': 'DEPTH'}


def _name(key: str) -> str:
    special = {'ton618': 'TON 618', 'sagittarius_a': 'Sagittarius A*', 'm87': 'M87*', '2mass_j0523': '2MASS J0523',
               'trappist_1': 'TRAPPIST-1', 'stephenson_2_18': 'Stephenson 2-18', 'uy_scuti': 'UY Scuti'}
    return special.get(key, key.replace('_', ' ').title())


# ---- one step's sky ---------------------------------------------------------------------------------------------
def sky_of(st: Step) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """-> (sky state the renderer draws, readout values by readout name)."""
    o, kind, d = st.object, st.object_kind, st.distance_m
    sky: Dict[str, Any] = {'object': o, 'kind': kind}
    val: Dict[str, str] = {}
    if d:
        val['distance'] = ph.fmt_distance(d)
        val['distance_au'] = f'{ph.fmt_distance(d, "au")} · {ph.fmt_distance(d, "km")}'
        val['light_time'] = ph.fmt_light_time(ph.light_time_s(d))
    if st.look == 'space' and st.from_ in ph.PLANETS and o in ('sun', ''):
        r = ph.sun_from_planet(st.from_)
        sky.update(object='sun', kind='star', angular_deg=r['angular_deg'], flux_x=r['brightness_x'], scale_x=r['size_x'])
        val.update(distance=val.get('distance') or ph.fmt_distance(r['distance_m']),
                   distance_au=f'{ph.fmt_distance(r["distance_m"], "au")} · {ph.fmt_distance(r["distance_m"])}',
                   size=wider(r['size_x']), brightness=brighter(r['brightness_x']),
                   light_time=ph.fmt_light_time(r['light_s']))
    elif st.look == 'moon_surface' and st.from_ in ph.MOONS:
        r = ph.parent_from_moon(st.from_)
        sky.update(object=r['parent'], kind='planet', angular_deg=r['angular_deg'], flux_x=1.0)
        val.update(distance=ph.fmt_distance(r['distance_m']), angle=f'{ph.fmt_angle(r["angular_deg"])} · {ph.fmt_ratio(r["moon_x"], "our Moon")}')
    elif kind == 'black_hole':
        r = ph.black_hole_at(o, d or ph.LY)
        sky.update(angular_deg=r['angular_deg'], flux_x=r['flux_x'], horizon_au=r['horizon_au'])
        val['horizon'] = f'{ph.fmt_big(r["horizon_au"])} AU across' if r['horizon_au'] < 1e6 else ph.fmt_distance(r['horizon_m'])
        val['brightness'] = brighter(r['flux_x']) if r['flux_x'] >= 0.02 else 'a point of light'
    elif kind in ('star', 'star_generic'):
        star = o if kind == 'star' else 'sun'
        r = ph.star_in_place_of_sun(star, d or ph.AU)
        sky.update(angular_deg=r['angular_deg'], flux_x=r['flux_x'], temp_k=r['temp_k'], scale_x=r['sun_x'])
        val.update(size=wider(r['sun_x'], 'our Sun'), brightness=brighter(r['full_moon_x'], 'the full Moon')
                   if r['flux_x'] < 0.01 else brighter(r['flux_x']), temperature=ph.fmt_temp(r['earth_temp_c']))
    elif kind == 'planet' and st.look in ('city', 'landscape', 'lake'):
        r = ph.planet_as_moon(o)
        sky.update(angular_deg=r['angular_deg'], flux_x=1.0, scale_x=r['size_x'])
        val.update(size=wider(r['size_x'], 'the Moon'), brightness=brighter(r['brightness_x'], 'the full Moon'))
    elif kind == 'planet' and st.look == 'helmet':
        sky.update(depth_m=d or 0.0)
        val['depth'] = ph.fmt_distance(d or 0.0, 'km')
    if 'flux_x' in sky:
        sky['stage'] = ph.heat_stage(sky['flux_x'])
    return sky, val


def wider(x: float, where: str = 'from Earth') -> str:
    """Size against our view, in our own words: '2.6× wider than from Earth', '19% as wide as from Earth'."""
    if 0.95 <= x < 1.05:
        return f'as wide as {where}'
    return f'{ph.fmt_ratio(x)} wider than {where}' if x >= 1.05 else f'{ph.fmt_ratio(x)} as wide as {where}'


def brighter(x: float, what: str = "Earth's sunlight") -> str:
    """Light against ours: '6.7× brighter than on Earth', '4% of Earth's sunlight', '1/904 of Earth's sunlight'."""
    if 0.95 <= x < 1.05:
        return f'the same as {what}'
    return f'{ph.fmt_ratio(x)} {what}' if x >= 1.05 else f'{ph.fmt_ratio(x)} of {what}'


def _readouts(st: Step, val: Dict[str, str]) -> List[Dict[str, str]]:
    rows = [{'label': LABELS[k], 'value': val[k]} for k in st.readouts if k in val]
    rows += [{'label': k, 'value': v} for k, v in st.typed.items()]
    return rows


CARD_S = 7.0


def rung_card(st: Step, sky: Dict[str, Any], val: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """The landscape rung card: the distance big, then two short facts (a context note, how bright, what it does to Earth)."""
    if st.look not in ('landscape', 'lake') or 'flux_x' not in sky or not st.distance_m:
        return None
    light = ph.light_fact(sky['flux_x'])
    lines = [st.note, light] if st.note else [light, ph.heat_fact(sky['flux_x'])]
    return {'value': val.get('distance', ph.fmt_distance(st.distance_m)).upper(), 'lines': [x for x in lines if x]}


def default_title(st: Step) -> str:
    if st.title:
        return st.title
    if st.look == 'space' and st.from_ in ph.PLANETS and st.object in ('sun', ''):
        return f'THE SUN FROM {_name(st.from_).upper()}'
    if st.look == 'moon_surface' and st.from_:
        return _name(st.from_).upper()
    return ''


# ---- timing -----------------------------------------------------------------------------------------------------
def _norm(t: str) -> List[str]:
    return [w for w in re.sub(r"[^\w\s']", ' ', t.lower()).split() if w]


def align(steps: Sequence[Step], words: Sequence[Any], duration: float) -> List[Tuple[float, float]]:
    """Each step's (start, end) in the voiceover. A step whose words are not found sits where its share of words would."""
    total = sum(max(len(_norm(s.narration)), 1) for s in steps) or 1
    est, acc = [], 0
    for s in steps:
        est.append(duration * acc / total)
        acc += max(len(_norm(s.narration)), 1)
    starts: List[Optional[float]] = [None] * len(steps)
    norms = [getattr(w, 'norm', None) or ' '.join(_norm(getattr(w, 'text', ''))) for w in words]
    cur = 0
    for i, s in enumerate(steps):
        head = _norm(s.narration)[:4]
        if not head or not words:
            continue
        best = None
        for j in range(cur, min(len(words), cur + 400)):
            hit = sum(1 for k, h in enumerate(head) if j + k < len(norms) and norms[j + k] == h)
            if hit >= max(2, len(head) - 1) or (len(head) == 1 and hit == 1):
                best = j
                break
        if best is not None:
            starts[i] = float(words[best].start)
            cur = best + len(head)
    out: List[float] = []
    for i, s in enumerate(starts):
        v = s if s is not None else est[i]
        if out and v <= out[-1]:
            v = out[-1] + 0.5
        out.append(0.0 if i == 0 else v)
    ends = out[1:] + [duration]
    return [(round(a, 3), round(max(b, a + 0.5), 3)) for a, b in zip(out, ends)]


MAX_LINE_WORDS = 14


def _halves(grp: List[Any]) -> List[List[Any]]:
    """A long sentence splits in two: at the comma nearest the middle, else at the middle. Never leaves one word alone."""
    if len(grp) <= MAX_LINE_WORDS:
        return [grp]
    mid = len(grp) / 2
    commas = [i + 1 for i, w in enumerate(grp[:-1]) if re.search(r'[,;:—]$', w.text) and 3 <= i + 1 <= len(grp) - 3]
    cut = min(commas, key=lambda i: abs(i - mid)) if commas else round(mid)
    return _halves(grp[:cut]) + _halves(grp[cut:])


def _sentences(st: Step, a: float, b: float, words: Sequence[Any]) -> List[Dict[str, Any]]:
    """Centred subtitle lines inside the step: from the timed words when there are any, else spread by length."""
    inside = [w for w in words if a - 0.05 <= float(w.start) < b - 0.05]
    out: List[Dict[str, Any]] = []
    if inside:
        groups: List[List[Any]] = []
        cur: List[Any] = []
        for w in inside:
            cur.append(w)
            if re.search(r'[.?!]["”]?$', w.text):
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        for grp in groups:
            for part in _halves(grp):
                out.append({'text': ' '.join(x.text for x in part), 'start': float(part[0].start), 'end': float(part[-1].end)})
    else:
        parts = [p.strip() for p in re.split(r'(?<=[.?!])\s+', st.narration) if p.strip()]
        n = sum(len(p) for p in parts) or 1
        t = a
        for p in parts:
            dt = (b - a) * len(p) / n
            out.append({'text': p, 'start': t, 'end': t + dt - 0.15})
            t += dt
    for i, s in enumerate(out):                       # hold each line until the next one (no flashing gaps)
        nxt = out[i + 1]['start'] if i + 1 < len(out) else b
        s['end'] = round(min(max(s['end'] + 0.4, s['start'] + 1.2), nxt, b), 3)
        s['start'] = round(s['start'], 3)
    return out


# ---- the spec ---------------------------------------------------------------------------------------------------
def plan(steps: Sequence[Step], words: Sequence[Any], duration: float, *, title: str = '') -> Dict[str, Any]:
    times = align(steps, words, duration)
    shots: List[Dict[str, Any]] = []
    layers: List[Dict[str, Any]] = []
    prev_sky: Optional[Dict[str, Any]] = None
    prev: Optional[Step] = None
    scene = 0
    for st, (a, b) in zip(steps, times):
        sky, val = sky_of(st)
        held = bool(prev and prev.look == st.look and prev.place == st.place and st.look in ('landscape', 'lake', 'city', 'helmet', 'journey')
                    and prev.object == st.object)
        if not held:
            scene += 1
        shot = {'id': f'step{st.n}', 'start': a, 'end': b, 'kind': 'sky', 'look': st.look, 'place': st.place, 'from': st.from_, 'scene': f'scene{scene}',
                'camera': st.camera, 'sky': sky, 'enter': 'continue' if held else ('fade' if shots else 'open'),
                'fade_s': 0.0 if held else FADE_S}
        if held and prev_sky:
            shot['sky_from'] = prev_sky
        if st.look == 'helmet':
            shot['hud'] = True
        shots.append(shot)
        rows = _readouts(st, val)
        card = rung_card(st, sky, val)
        if card:                                      # the landscape look: a big rung card top-left, nothing repeated top-right
            layers.append({'type': 'sk_rungcard', **card, 'start': round(a + 0.3, 3), 'end': round(b, 3)})   # held for the whole rung
            rows = [r for r in rows if r['label'] not in (LABELS['distance'], LABELS['brightness'])]   # the card already says both
        if rows:
            layers.append({'type': 'sk_stats' if len(rows) > 1 else 'sk_readout', 'rows': rows, 'start': a, 'end': b,
                           'anchor': 'tl' if len(rows) > 1 else 'tr', 'count': held})
        if st.clock:
            k = ph.dilation_factor(*st.clock)
            layers.append({'type': 'sk_clocks', 'start': a, 'end': b, 'rate': k,
                           'labels': ['TIME HERE', 'TIME ON EARTH'], 'anchor': 'tr'})
        t = default_title(st)
        if t:
            layers.append({'type': 'sk_title', 'text': t.upper(), 'start': round(a + 0.3, 3), 'end': b})
        if st.look == 'space' and sky.get('scale_x', 0) > 1.05:
            layers.append({'type': 'sk_scalering', 'ratio': round(1 / sky['scale_x'], 4), 'label': 'THE SUN FROM EARTH', 'start': a, 'end': b})
        if 0 < sky.get('angular_deg', 1) < LEADER_BELOW_DEG and sky.get('kind') in ('planet', 'moon'):   # a star glows; a far planet needs pointing at
            layers.append({'type': 'sk_leader', 'text': _name(sky['object']).upper(), 'start': a, 'end': b})
        for s in _sentences(st, a, b, words):
            layers.append({'type': 'sk_subtitle', **s})
        prev, prev_sky = st, sky
    return {'style': 'skysim', 'width': WIDTH, 'height': HEIGHT, 'fps': FPS, 'duration': round(duration, 3), 'title': title,
            'shots': shots, 'layers': layers}
