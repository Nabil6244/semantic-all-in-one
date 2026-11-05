"""Builds samples/rome_history.csv from samples/rome_script.txt. The narration in every beat is the script's own text, word for word:
beats only group whole sentences; nothing is shortened, reworded or reordered (checked at the end)."""
import csv, json, re, sys
from pathlib import Path
here = Path(__file__).parent
paras = [p.strip() for p in (here / 'rome_script.txt').read_text(encoding='utf-8').split('\n\n') if p.strip()]
assert len(paras) == 32, len(paras)

CH = {0: ('The Legend', 'THE FIRST LEGENDS'), 2: ('Kings and the Republic', '753 - 450 BC'), 6: ('Carthage', '270 - 146 BC'), 11: ('The Republic Cracks', '133 - 44 BC'),
      18: ('Augustus and the Empire', '31 BC - 180 AD'), 22: ('Crisis and Division', '160 - 395 AD'), 26: ('The Fall', '410 - 1453 AD')}
# per paragraph: location, event, environment, time, weather, characters, vehicles, effects, extra-map pins
M = [
 dict(loc='Mediterranean Sea', ev='map', env='map', pins=['Rome', 'Carthage', 'Constantinople'], margin=2.0),
 dict(loc='Tiber River', ev='establishing', env='river', t='dawn', c='civilian*6; farmer*3', date='753 BC'),
 dict(loc='Rome', ev='civilian_life', env='city', t='day', c='civilian*10; worker*4; leader:Tarquin the Proud', date='509 BC'),
 dict(loc='Roman Forum', ev='political_meeting', env='monument', t='day', c='leader*2; civilian*12; crowd*8'),
 dict(loc='Roman Forum', ev='protest', env='city', t='day', c='civilian*14; farmer*4; soldier*4; crowd*10', date='450 BC'),
 dict(loc='Rome', ev='defensive_position', env='city', t='dusk', w='clear', c='soldier*14; officer*2; civilian*8', fx='fire', date='390 BC'),
 dict(loc='Carthage', ev='naval_operation', env='port', t='day', c='sailor*6; civilian*6', v='galley*4>patrol', date='270 BC', map=['Rome', 'Carthage', 'Sicily'], margin=3.0),
 dict(loc='Sicily', ev='naval_operation', env='sea', t='day', c='sailor*8; soldier*8', v='galley*6>advance', date='264 BC'),
 dict(loc='Alps', ev='military_invasion', env='mountains', t='day', w='snow', c='soldier*16; leader:Hannibal; officer*2', v='horse*4>advance', date='218 BC', map=['Carthage', 'Alps', 'Cannae'], margin=3.0),
 dict(loc='Zama', ev='battle', env='desert', t='day', c='soldier*20; officer*3', v='horse*4>advance', date='202 BC'),
 dict(loc='Carthage', ev='aftermath', env='port', t='dusk', c='soldier*10; civilian*6', fx='smoke; fire', date='146 BC'),
 dict(loc='Rome', ev='civilian_life', env='farmland', t='day', c='farmer*8; civilian*6; worker*4', v='cart*2>convoy'),
 dict(loc='Roman Forum', ev='assassination', env='monument', t='day', c='leader:Tiberius Gracchus; crowd*14; civilian*10', date='133 BC'),
 dict(loc='Rome', ev='city_occupation', env='city', t='day', c='soldier*20; commander:Sulla; officer*2', date='88 BC'),
 dict(loc='Italy', ev='battle', env='hills', t='day', c='soldier*14; civilian*12', date='73 BC'),
 dict(loc='Rome', ev='political_meeting', env='interior', t='day', c='leader:Pompey; leader:Crassus; commander:Caesar', date='60 BC'),
 dict(loc='Rubicon River', ev='military_invasion', env='river', t='dawn', c='soldier*24; commander:Caesar; officer*3', v='horse*3>advance', date='49 BC', map=['Gaul', 'Rubicon River', 'Rome', 'Egypt'], margin=3.0),
 dict(loc='Roman Forum', ev='assassination', env='monument', t='day', c='leader*8; commander:Caesar', date='44 BC'),
 dict(loc='Actium', ev='naval_operation', env='sea', t='day', c='sailor*10; soldier*8', v='galley*8>advance', date='31 BC'),
 dict(loc='Rome', ev='political_meeting', env='monument', t='sunset', c='leader:Augustus; crowd*16; soldier*6', date='27 BC'),
 dict(loc='Rome', ev='civilian_life', env='city', t='day', c='leader*3; civilian*10; soldier*4', date='64 AD', fx='fire'),
 dict(loc='Britain', ev='infrastructure_construction', env='hills', t='day', c='worker*12; soldier*8; commander:Hadrian', date='117 AD', map=['Rome', 'Britain', 'Mesopotamia'], margin=4.0),
 dict(loc='Rome', ev='consequence', env='city', t='dusk', w='fog', c='civilian*10; soldier*4; leader:Commodus', date='180 AD'),
 dict(loc='Rome', ev='retreat', env='battlefield', t='day', w='overcast', c='soldier*18; officer*2', date='235 AD'),
 dict(loc='Milvian Bridge', ev='battle', env='river', t='day', c='soldier*18; commander:Constantine; officer*2', date='312 AD'),
 dict(loc='Adrianople', ev='battle', env='battlefield', t='day', w='overcast', c='soldier*20; officer*3', v='horse*4>advance', date='378 AD', map=['Rome', 'Constantinople', 'Adrianople'], margin=3.0),
 dict(loc='Rome', ev='city_occupation', env='city', t='night', w='clear', c='soldier*16; civilian*10', fx='fire; smoke', date='410 AD'),
 dict(loc='Rome', ev='surrender', env='interior', t='day', c='leader*2; soldier*6', date='476 AD'),
 dict(loc='Constantinople', ev='establishing', env='port', t='day', c='civilian*10; soldier*6', v='galley*3>patrol', date='1453'),
 dict(loc='Rome', ev='aftermath', env='monument', t='sunset', c='civilian*8'),
 dict(loc='Roman Forum', ev='consequence', env='monument', t='dusk', c='civilian*6'),
 dict(loc='Rome', ev='establishing', env='city', t='sunset', c='civilian*8; child*2'),
]
assert len(M) == 32, len(M)

def sentences(p):
    out, cur = [], ''
    for w in p.split(' '):
        cur = (cur + ' ' + w).strip()
        if re.search(r'[.!?]["”’)]*$', w): out.append(cur); cur = ''
    if cur: out.append(cur)
    return out

def groups(sents, maxw=34, maxs=3):
    out, cur, n = [], [], 0
    for s in sents:
        k = len(s.split())
        if cur and (n + k > maxw or len(cur) >= maxs): out.append(' '.join(cur)); cur, n = [], 0
        cur.append(s); n += k
    if cur: out.append(' '.join(cur))
    return out

cols = ['row', 'id', 'chapter', 'text', 'date', 'location', 'event', 'environment', 'time', 'weather', 'characters', 'actions', 'vehicles', 'props', 'effects', 'camera', 'subtitle', 'audio', 'transition', 'duration', 'extra']
rows = [dict(row='plan', text='The Whole History of Rome', date='753 BC', extra=json.dumps({'side_a': 'roman', 'side_b': 'carthage', 'era': 'ancient', 'music': 'stormfront'}))]
n = 0; seed = 100; allbeats = []
for pi, p in enumerate(paras):
    if pi in CH: rows.append(dict(row='chapter', chapter=CH[pi][0], date=CH[pi][1]))
    m = M[pi]
    for bi, text in enumerate(groups(sentences(p))):
        n += 1; seed += 1; allbeats.append(text)
        ex = {'seed': seed}
        r = dict(row='beat', id=f'b{n}', text=text, location=m['loc'], event=m['ev'], environment=m['env'], time=m.get('t', ''), weather=m.get('w', ''), characters=m.get('c', ''),
                 vehicles=m.get('v', ''), effects=m.get('fx', ''))
        if bi == 0 and m.get('date'): r['date'] = m['date']
        if m['ev'] == 'map' or (bi == 0 and m.get('map')):
            pins = m.get('pins') or m['map']
            ex['map'] = {'pins': pins, 'margin': m.get('margin', 2.0)}
            if m['ev'] != 'map': r['event'] = 'map'; r['environment'] = 'map'
        r['extra'] = json.dumps(ex)
        rows.append(r)
out = here / 'rome_history.csv'
with open(out, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow({c: r.get(c, '') for c in cols})
# word-for-word proof: the beats, joined, are exactly the script
assert ' '.join(allbeats) == ' '.join(p.replace('\n', ' ') for p in paras), 'beats differ from the script'
print(f'{out.name}: {n} beats, {len(" ".join(allbeats).split())} words, identical to the script')
