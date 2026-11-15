"""Sky Sim preflight: CSV + voiceover timing -> spec + a report, without rendering anything.

problems: things that would show wrong on screen (gaps, a frozen stretch, a readout with no value).
warnings: worth a look, never blocks (a very long step, a step whose words were not found).
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from . import planner
from .steps import read_steps

STILL_S = 4.0         # no-still-screens rule: a held scene must change within this long
LONG_STEP_S = 45.0


def _same_sky(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    keys = ('object', 'angular_deg', 'flux_x', 'depth_m')
    return all(a.get(k) == b.get(k) for k in keys)


def check_spec(spec: Dict[str, Any]) -> Dict[str, List[str]]:
    problems: List[str] = []
    warnings: List[str] = []
    shots = spec.get('shots', [])
    dur = float(spec.get('duration', 0))
    if not shots:
        problems.append('no steps')
        return {'problems': problems, 'warnings': warnings}
    if shots[0]['start'] > 0.01:
        problems.append(f'nothing on screen before {shots[0]["start"]:.1f} s')
    for x, y in zip(shots, shots[1:]):
        if y['start'] > x['end'] + 0.01:
            problems.append(f'gap {x["end"]:.1f}-{y["start"]:.1f} s between {x["id"]} and {y["id"]}')
        if y['start'] < x['end'] - 0.01:
            problems.append(f'{x["id"]} and {y["id"]} overlap')
    if shots[-1]['end'] < dur - 0.01:
        problems.append(f'nothing on screen after {shots[-1]["end"]:.1f} s')
    for s in shots:
        length = s['end'] - s['start']
        if length <= 0:
            problems.append(f'{s["id"]} has no length')
        if length > STILL_S and s['camera'] == 'static' and ('sky_from' not in s or _same_sky(s['sky_from'], s['sky'])):
            problems.append(f'{s["id"]}: {length:.0f} s with a static camera and a sky that does not change (still screen)')
        if length > LONG_STEP_S:
            warnings.append(f'{s["id"]} lasts {length:.0f} s; the references change every 15-40 s')
        if not s['sky'].get('object') and s['look'] != 'journey':
            warnings.append(f'{s["id"]}: nothing named in the sky')
    for L in spec.get('layers', []):
        for r in L.get('rows', []):
            if not str(r.get('value', '')).strip():
                problems.append(f'{L["type"]} at {L["start"]:.1f} s: {r["label"]} has no value')
    return {'problems': problems, 'warnings': warnings}


def dry_run(csv_text: str, words: Sequence[Any], duration: float, title: str = '') -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
    """Read, repair, plan and check. Never raises; the report says what was repaired and what is still wrong."""
    steps, notes = read_steps(csv_text)
    if not steps:
        return {}, {'problems': notes or ['no steps'], 'warnings': [], 'repaired': notes}
    spec = planner.plan(steps, words, duration, title=title)
    rep = check_spec(spec)
    rep['repaired'] = notes
    return spec, rep
