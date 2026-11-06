// Horror story mode (lib/horror.mjs): a quiet modern story, not a war film. Synthetic scripts only (general rules, not one video).
import test from 'node:test';
import assert from 'node:assert/strict';
import { storyFromText, parseStory } from '../lib/csv.mjs';
import { direct } from '../lib/director.mjs';
import { makeCharacter } from '../lib/characters.mjs';
import { assembleScene } from '../lib/assemble.mjs';
import { classifyHorror, HORROR_RECIPES } from '../lib/horror.mjs';
import { sampleStory } from './_helpers.mjs';

const SCRIPT = [
  'It is late and the street is empty. The rain keeps falling on the parked cars.',
  'An old man with a box has just stopped in front of you, smiling. He holds out a small gift.',
  'Turn around and walk away slowly. You will hear footsteps behind you, keeping pace.',
  'Inside the box there are hundreds of them. Maybe thousands, each one with a name.',
  '# Part two',
  'At home, you put the box on the kitchen table and leave the light on.',
  'Your phone rings. The voice on the line sounds like your father, but it never says your name.',
  'A long time ago, when you were small, a stranger gave you the same box at a train station.',
  'Walk until you reach someone who loves you. Stand in their doorway and let them say your name.',
].join('\n\n');

const horrorStory = () => { const s = storyFromText(SCRIPT, 'Test'); s.plan.extra.genre = 'horror'; return s; };
const plan = direct(horrorStory(), { fps: 24 });
const ARMED = new Set(['soldier', 'paratrooper', 'guard', 'officer', 'commander', 'police', 'tank_crew']);

test('a horror story plans quiet beats: small casts, no soldiers, no crowds', () => {
  assert.equal(plan.genre, 'horror');
  for (const s of plan.scenes) {
    assert.ok(HORROR_RECIPES[s.event], `${s.id} event ${s.event} is not a horror beat`);
    const people = s.cast.reduce((n, c) => n + (c.count || 1), 0);
    assert.ok(people >= 1 && people <= 3, `${s.id} has ${people} people`);
    for (const c of s.cast) { assert.ok(!ARMED.has(c.role) && c.role !== 'crowd', `${s.id} has ${c.role}`); assert.equal(c.side, 'civ'); }
  }
});

test('the narration picks the right horror beat', () => {
  const ev = plan.scenes.map((s) => s.event);
  // beat 4 says nothing new, so the pursuit goes on; beat 1 says the street is empty, so the hero is alone
  assert.deepEqual(ev, ['quiet_moment', 'encounter', 'pursuit_slow', 'pursuit_slow', 'alone_inside', 'phone_call', 'flashback', 'refuge']);
  assert.equal(classifyHorror('Nothing happens here.').type, 'quiet_moment');
});

test('a beat with nothing new keeps the stranger; a beat that says "alone" does not; numbers never pull the camera up', () => {
  const s = storyFromText('An old woman stops in front of you, smiling.\n\nShe reaches into her bag at 11:40.\n\nNow you are alone again.', 'T');
  s.plan.extra.genre = 'horror';
  const p = direct(s, { fps: 24 });
  assert.deepEqual(p.scenes.map((x) => x.event), ['encounter', 'encounter', 'quiet_moment']);
  for (const x of p.scenes) for (const sh of x.shots) assert.ok(!/scale/.test(sh.reason), `${x.id} ${sh.behaviour}: ${sh.reason}`);
});

test('the hero is the same person in every grown-up scene, and the stranger keeps one face', () => {
  const heroes = plan.scenes.flatMap((s) => s.cast.filter((c) => c.role === 'hero'));
  assert.ok(heroes.length >= 6 && heroes.every((c) => c.named && c.name === 'Hero'));
  const look = (c) => makeCharacter({ role: c.role, faction: 'civilian', era: plan.era, name: c.name, seed: 'x' });
  assert.equal(new Set(heroes.map((c) => look(c).id)).size, 1);
  const stranger = makeCharacter({ role: 'stranger', faction: 'civilian', era: 'modern', name: 'Stranger' });
  assert.equal(stranger.face.hair, 'bun');
  assert.ok(['#b8b2a6', '#d6d2c8', '#9a958c'].includes(stranger.face.hairColor), 'the stranger has grey hair');
});

test('night carries across chapters, no number callouts, spoken vehicles are one parked prop', () => {
  for (const s of plan.scenes) assert.equal(s.time, 'night', `${s.id} is ${s.time}`);
  assert.equal(plan.hud.stats.length, 0);
  const train = plan.scenes.flatMap((s) => s.vehicles).filter((v) => v.kind === 'train');
  for (const v of train) assert.deepEqual([v.count, v.motion], [1, 'park']);
});

test('indoor beats get the right room: kitchen table, phone, a doorway in the hallway', () => {
  const by = Object.fromEntries(plan.scenes.map((s) => [s.event, s]));
  assert.equal(by.alone_inside.room, 'kitchen');
  assert.equal(by.phone_call.env, 'interior');
  assert.equal(by.refuge.room, 'hallway');
});

test('pursuit: the stranger walks a few steps behind the hero', () => {
  const s = plan.scenes.find((x) => x.event === 'pursuit_slow'), A = assembleScene(JSON.parse(JSON.stringify(s)));
  const hero = A.stage.actors.find((a) => a.role === 'hero'), str = A.stage.actors.find((a) => a.role === 'stranger');
  const t = s.t0 + 0.1, h = A.actorAt(hero, t), k = A.actorAt(str, t);
  const d = Math.hypot(h.x - k.x, h.z - k.z);
  assert.ok(d > 5 && d < 16, `distance ${d.toFixed(1)}`);
});

test('a CSV plan row sets the genre; a history film takes none of these paths', () => {
  const csv = 'row,id,text,extra\nplan,,T,"{""genre"":""horror""}"\nbeat,b1,"Your phone rings in the dark."\n';
  assert.equal(direct(parseStory(csv), { fps: 24 }).scenes[0].event, 'phone_call');
  const hist = direct(sampleStory(), { fps: 24 });
  assert.equal(hist.genre, undefined);
  assert.ok(hist.scenes.some((s) => s.cast.some((c) => c.role === 'soldier')));
});

// ---- Step 2: light, camera, sound -------------------------------------------------------------------------------------------
import { shotCamera, cameraJumps, BEHAVIOURS } from '../lib/camera.mjs';

test('horror night and rooms get the horror looks and the dark music; history keeps its own', () => {
  for (const s of plan.scenes) assert.equal(s.light, s.env === 'interior' ? 'interior_night' : 'night_horror', s.id);
  assert.deepEqual(plan.audio.music.tracks, ['dark_fog', 'interloper']);
  const hist = direct(sampleStory(), { fps: 24 });
  assert.ok(hist.scenes.every((s) => !/horror|interior_night/.test(s.light)));
  assert.ok(hist.audio.ambience.every((a) => !a.bed.startsWith('horror_')));
});

test('horror shots use the slow moves, and none of them freezes or jumps', () => {
  for (const b of ['creep_in', 'hold_breathe', 'behind_follow']) assert.ok(BEHAVIOURS.includes(b));
  const used = new Set(plan.scenes.flatMap((s) => s.shots.map((x) => x.behaviour)));
  for (const b of ['creep_in', 'hold_breathe', 'behind_follow']) assert.ok(used.has(b), `${b} never used`);
  // still subject: hold_breathe still moves (alive), creep_in closes in, all within a gentle per-frame speed
  const shot = (behaviour) => ({ behaviour, t0: 0, t1: 6, yaw: 0.6, scale: 1 });
  const at = (b, t) => shotCamera(shot(b), t, () => [0, 0, 0], () => 0).pos;
  for (const b of ['creep_in', 'hold_breathe', 'behind_follow']) {
    let moved = 0; for (let t = 0; t < 6; t += 1 / 24) moved += Math.hypot(...at(b, t + 1 / 24).map((v, i) => v - at(b, t)[i]));
    if (b !== 'behind_follow') assert.ok(moved > 0.3, `${b} is frozen (${moved.toFixed(2)})`);
  }
  for (const s of plan.scenes) {
    const A = assembleScene(JSON.parse(JSON.stringify(s))), samples = [];
    for (let t = s.t0; t < s.t1; t += 1 / 24) { const c = A.cameraAt(t); samples.push({ t, pos: c.pos, target: c.target }); }
    const j = cameraJumps(samples, s.shots.map((x) => x.t0), 24);
    assert.ok(j.length === 0 || j[0].rel < 4.5, `${s.id} jump ${j[0] && j[0].rel.toFixed(2)}`);
  }
});

test('sounds the narration names land on their word, once per scene; "not footsteps" is silent', () => {
  const s = storyFromText('Your phone rings in the dark kitchen.\n\nYou hear a rustle behind you. Not footsteps.\n\nSomeone whispers your name from the street. Then slow footsteps.', 'T');
  s.plan.extra.genre = 'horror';
  const p = direct(s, { fps: 24 }), cues = p.audio.cues.filter((c) => !['whoosh', 'chapter_hit'].includes(c.cue));
  assert.deepEqual(cues.map((c) => [c.scene, c.cue]).sort(), [['s1', 'phone_ring'], ['s2', 'paper_rustle'], ['s3', 'footsteps_slow'], ['s3', 'whisper_name']].sort());
  for (const c of cues) { const sc = p.scenes.find((x) => x.id === c.scene); assert.ok(c.t >= sc.t0 && c.t < sc.t1); }
  assert.ok(p.audio.ambience.every((a) => a.bed.startsWith('horror_')));
});

// ---- Step 3: street sets -------------------------------------------------------------------------------------------------
const setStory = (text) => { const s = storyFromText(text, 'T'); s.plan.extra.genre = 'horror'; return direct(s, { fps: 24 }); };

test('a bus stop beat builds a shelter at the roadside with the hero under it, clear of houses', () => {
  const p = setStory('You wait at a bus stop in the rain. Nobody else is there.\n\nAn old woman stops in front of you, smiling.\n\nShe gives you a small gift.');
  assert.deepEqual(p.scenes.map((s) => s.set), ['bus_stop', 'bus_stop', 'bus_stop']);
  for (const s of p.scenes) {
    const A = assembleScene(JSON.parse(JSON.stringify(s))), W = A.world, sh = W.props.find((x) => x.kind === 'bus_shelter');
    assert.ok(sh && W.props.some((x) => x.kind === 'bus_stop_sign'));
    assert.ok(!W.buildings.some((b) => Math.abs(b.x - sh.x) < b.w / 2 + 7 && Math.abs(b.z - sh.z) < b.d / 2 + 3), 'a house stands in the shelter');
    const hero = A.stage.actors.find((a) => a.role === 'hero'), h = A.actorAt(hero, s.t0 + 0.2);
    assert.ok(Math.hypot(h.x - sh.x, h.z - sh.z) < 4, `hero ${Math.hypot(h.x - sh.x, h.z - sh.z).toFixed(1)} from the shelter`);
    assert.ok(W.wet && W.props.some((x) => x.kind === 'puddle'));
  }
});

test('a candy shop beat builds a lit shop with its own sign; a plain shop says SHOP; dry nights have no puddles', () => {
  const p = setStory('There is an all-night candy shop three streets down, with a warm light in the window.\n\nAt the end of the road, a shop is still open. The night is clear.');
  assert.deepEqual(p.scenes.map((s) => [s.set, s.setLabel]), [['shop', 'CANDY'], ['shop', 'SHOP']]);
  const A = assembleScene(JSON.parse(JSON.stringify(p.scenes[0]))), shop = A.world.props.find((x) => x.kind === 'shop_front');
  assert.equal(shop.label, 'CANDY');
  assert.ok(A.world.colliders.some((c) => !c.inside && c.x0 < shop.x && c.x1 > shop.x && c.z0 < shop.z && c.z1 > shop.z), 'the shop is solid to the camera');
  const dry = assembleScene(JSON.parse(JSON.stringify(p.scenes[1])));
  assert.ok(!dry.world.props.some((x) => x.kind === 'puddle'));
});

test('cameras stay out of the shop and the shelter roof and never jump in set scenes', () => {
  const p = setStory('You wait at a bus stop in the rain.\n\nAn old woman stops in front of you, smiling. She holds out her hand.\n\nYou walk past the candy shop. Something keeps pace behind you.\n\nThe candy shop window glows. A voice says come in.');
  for (const s of p.scenes) {
    const A = assembleScene(JSON.parse(JSON.stringify(s))), samples = [], shopC = A.world.colliders.find((c) => !c.inside && A.world.set === 'shop' && c.y1 > 10);
    for (let t = s.t0; t < s.t1; t += 1 / 24) {
      const c = A.cameraAt(t); samples.push({ t, pos: c.pos, target: c.target });
      if (shopC) assert.ok(!(c.pos[0] > shopC.x0 && c.pos[0] < shopC.x1 && c.pos[2] > shopC.z0 && c.pos[2] < shopC.z1 && c.pos[1] < shopC.y1), `${s.id} camera inside the shop at ${t.toFixed(2)}`);
    }
    const j = cameraJumps(samples, s.shots.map((x) => x.t0), 24);
    assert.ok(j.length === 0 || j[0].rel < 4.5, `${s.id} (${s.set}) jump ${j[0] && j[0].rel.toFixed(2)} at ${j[0] && j[0].t.toFixed(2)}`);
  }
});

// ---- Step 4: things in hands, the hand close-up, the dry circle ------------------------------------------------------------
import { dryCircles, inDry, horrorHolds } from '../lib/horror.mjs';
import { handPoint } from '../lib/assemble.mjs';

const GIVE = 'A stranger with a paper bag stops in front of you at the bus stop.\n\nShe takes out a silver candy and places it in your open hand.\n\nDo not close your fingers. Do not eat it.\n\nPut it in your inside pocket and walk away. You hear her behind you.';

test('the stranger holds her bag; the sweet passes from her hand to the hero on the words that say so, and stays until it is put away', () => {
  const p = setStory(GIVE), [s1, s2, s3, s4] = p.scenes;
  assert.ok(s1.holds.some((h) => h.role === 'stranger' && h.item === 'paper_bag' && h.hand === 'L'));
  const hers = s2.holds.find((h) => h.role === 'stranger' && h.item === 'gift_small'), mine = s2.holds.find((h) => h.role === 'hero' && h.item === 'gift_small');
  assert.ok(hers && mine && Math.abs(hers.t1 - mine.t0) < 1e-9 && mine.t0 > s2.t0 && mine.t0 < s2.t1, 'handed over inside the scene');
  assert.equal(mine.color, '#c9cdd2');   // "silver"
  const sent = s2.sentences.find((x) => /places it/.test(x.text)), w = sent.words.find((x) => x.word === 'places');
  assert.ok(Math.abs(mine.t0 - w.start) < 0.01, 'on the word');
  assert.ok(s3.holds.some((h) => h.role === 'hero' && h.item === 'gift_small' && h.t0 === s3.t0 && h.t1 === s3.t1));
  const away = s4.holds.find((h) => h.role === 'hero' && h.item === 'gift_small');
  assert.ok(away && away.t1 < s4.t1, 'put in the pocket before the scene ends');
  assert.ok(s4.holds.some((h) => h.role === 'stranger' && h.item === 'paper_bag'), 'she follows with her bag');
});

test('the hand-over gets a close shot of the hand, on the hand, never at the start of a new place', () => {
  // a hand-over now plays side on with both people (its own test below); a thing simply named in the hand still gets the close shot
  const given = setStory(GIVE).scenes[1], give = given.shots.find((x) => x.behaviour === 'handover'), gh = given.holds.find((h) => h.handover);
  assert.ok(give && gh.at >= give.t0 && gh.at < give.t1);
  const p = setStory(`The street stays empty and nothing moves out there tonight, not even the wind in the wires at all. You look at the old wrapper. It stays with you and it does not change at all tonight.`), s2 = p.scenes[0], sh = s2.shots.find((x) => x.behaviour === 'hand_close');
  assert.ok(sh && sh.subject.type === 'hand' && sh.subject.role === 'hero', s2.shots.map((x) => x.behaviour).join());
  const mine = s2.holds.find((h) => h.role === 'hero'); assert.ok(mine.at >= sh.t0 - 0.2 && mine.at < sh.t1);
  for (const s of p.scenes) assert.notEqual(s.shots[0].behaviour === 'hand_close' && s.id === 's1', true);
  const A = assembleScene(JSON.parse(JSON.stringify(s2))), t = (sh.t0 + sh.t1) / 2, cam = A.cameraAt(t);
  const hero = A.stage.actors.find((a) => a.role === 'hero'), hp = handPoint(A.actorAt(hero, t), 'R');
  const d = Math.hypot(cam.pos[0] - hp[0], cam.pos[1] - hp[1], cam.pos[2] - hp[2]);
  assert.ok(d > 2 && d < 6, `camera ${d.toFixed(1)} from the hand`);
  assert.ok(Math.hypot(cam.target[0] - hp[0], cam.target[2] - hp[2]) < 1.5, 'aimed at the hand');
  // indoors a hand is framed by the room's own props, not this shot
  const inside = setStory('At home in the kitchen you hold the letter.').scenes[0];
  assert.ok(!inside.shots.some((x) => x.behaviour === 'hand_close'));
});

test('the dry circle: rain skips her, her feet stand on a dry patch with no puddle, in every scene of that moment', () => {
  const p = setStory('An old woman stops in front of you at the bus stop in the rain.\n\nShe smiles and waits.\n\nBut the rain is not falling on her. The pavement under her is dry in a perfect circle.\n\nYou walk away down the street.');
  assert.deepEqual(p.scenes.map((s) => !!s.dry), [true, true, true, false]);
  const s = p.scenes[0], A = assembleScene(JSON.parse(JSON.stringify(s))), [c] = dryCircles(A, s.t0 + 1);
  const her = A.actorAt(A.stage.actors.find((a) => a.role === 'stranger'), s.t0 + 1);
  assert.ok(c && inDry([c], her.x, her.z) && !inDry([c], her.x + c.r + 0.5, her.z));
  assert.ok(A.world.props.some((x) => x.kind === 'dry_patch' && Math.hypot(x.x - her.x, x.z - her.z) < 0.5));
  assert.ok(!A.world.props.some((x) => x.kind === 'puddle' && Math.hypot(x.x - her.x, x.z - her.z) < c.r + 2));
  const plain = setStory('You wait in the rain at the bus stop. Nobody comes.').scenes[0];
  assert.ok(!plain.dry && dryCircles(assembleScene(JSON.parse(JSON.stringify(plain))), plain.t0).length === 0);
});

// ---- picture cards (Step 5) ----------------------------------------------------------------------------------------------------
const planOf = (text, extra = {}) => { const s = storyFromText(text, 'Cards'); Object.assign(s.plan.extra, { genre: 'horror' }, extra); return direct(s, { fps: 24 }); };
const csvPlan = (rows) => direct(parseStory(`row,id,text,location,event,environment,characters,props,camera,extra\nplan,,T,,,,,,,"{""genre"":""horror""}"\n${rows.join('\n')}\n`), { fps: 24 });
const FAR = 'The street stays empty for a long, long time and nothing moves at all out there tonight.';

test('cards: extra.card plans a card beat, as text or with exact words, timed on the named word', () => {
  const p = csvPlan([
    `beat,b1,"You open your hand slowly. There is writing on it, small and careful.",,,town,hero,,,"{""card"":{""what"":""candy wrapper with a name in blue ink"",""text"":""Sarah"",""at"":""writing""}}"`,
    `beat,b2,"${FAR} ${FAR}",,,town,hero,,,"{""card"":""drawing with blank faces""}"`,
  ]);
  const [a, b] = p.cards;
  assert.equal(a.kind, 'name'); assert.equal(a.text, 'Sarah'); assert.equal(a.surface, 'wrapper'); assert.equal(a.color, '#2f6fb0'); assert.equal(a.source, 'csv');
  const s = p.sentences.find((x) => /writing/.test(x.text)), w = s.words.find((x) => x.word === 'writing');
  assert.equal(a.t0, +w.start.toFixed(3));
  assert.equal(b.kind, 'drawing'); assert.equal(b.blankFaces, true); assert.equal(b.picture, true);
  assert.match(b.prompt, /^drawing with blank faces/);
});

test('cards: a `card:` prop makes a card and is not a thing in the room', () => {
  const p = csvPlan([`beat,b1,"You sit down at the table. You read it again and again.",Kitchen,alone_inside,interior,hero,"table; card: phone screen showing 11:40",,`]);
  assert.equal(p.cards[0].kind, 'phone_screen'); assert.equal(p.cards[0].time, '11:40');
  assert.ok(!p.scenes[0].props.some((x) => /card/.test(x)), 'the card prop stays out of the room');
  assert.ok(p.scenes[0].props.includes('table'));
});

test('cards: the narration alone plans each kind, for any script', () => {
  const kindOf = (t) => planOf(t).cards.map((c) => c.kind);
  assert.deepEqual(kindOf('You look down. Your name is printed on the wrapper in black ink.'), ['name']);
  assert.deepEqual(kindOf('Somebody wrote this in a child\'s handwriting.'), ['handwriting']);
  assert.deepEqual(kindOf('It is written with a dull pencil.'), ['handwriting']);
  assert.deepEqual(kindOf('The box is full of drawings. The people in them have blank faces.'), ['drawing']);
  assert.deepEqual(kindOf('She gives you a driver\'s license. It is blank.'), ['id_card']);
  assert.deepEqual(kindOf('Under the door there is a sealed envelope.'), ['letter']);
  assert.equal(planOf('Under the door there is a sealed envelope.').cards[0].envelope, true);
  assert.deepEqual(kindOf('Take out your phone. The time on it will be 11:40.'), ['phone_screen']);
  assert.deepEqual(kindOf('You wake up alone. The clock says three forty.'), ['clock']);
  const c = planOf('You wake up alone. The clock says three forty.').cards[0];
  assert.equal(c.time, '3:40'); assert.equal(c.picture, false);
});

test('cards: words that only look like a card make none', () => {
  for (const t of ['He drew a breath and stepped back.', 'She is drawing closer to you now.', 'You read the license plate of the car.', 'No letter ever came to the house.', 'You meet at 11:40 near the church.', 'Nothing is written about it.', 'Your name is not printed anywhere.'])
    assert.deepEqual(planOf(t).cards, [], t);
});

test('cards: extra.card false turns a narrated card off; a CSV card replaces what the narration implies', () => {
  assert.equal(csvPlan([`beat,b1,"The box is full of drawings.",,,town,hero,,,"{""card"":false}"`]).cards.length, 0);
  const p = csvPlan([`beat,b1,"The box is full of drawings.",,,town,hero,,,"{""card"":""a torn letter""}"`]);
  assert.deepEqual(p.cards.map((c) => c.kind), ['letter']);
});

test('cards: a picture card with no picture is code-made, and every kind paints something, never a blank screen', async () => {
  const { attachCardPictures, CARD_KINDS } = await import('../lib/horror.mjs');
  const { drawCard } = await import('../web/card_art.js');
  const cards = [{ id: 'c1', kind: 'drawing', picture: true }, { id: 'c2', kind: 'letter', picture: true }, { id: 'c3', kind: 'clock', picture: false, time: '3:40' }, { id: 'c4', kind: 'note', picture: true }, { id: 'c5', kind: 'note', picture: true, asset: 'own.png' }];
  const notes = attachCardPictures(cards, { c2: '/gone.png', c1: '/here.png', c4: '/here.mp4' }, { exists: (f) => f === '/here.png' || f === '/here.mp4' || f === 'own.png' });
  assert.equal(cards[0].image, '/card/c1'); assert.equal(cards[1].image, undefined); assert.equal(cards[2].image, undefined); assert.equal(cards[3].image, undefined, 'a video cannot be a card');
  assert.equal(cards[4].image, '/card/c5', "the CSV's own file");
  assert.equal(notes.length, 2);
  assert.deepEqual(attachCardPictures([{ id: 'c1', kind: 'drawing', picture: true }], null, { exists: () => false }), [], 'no notes at Generate, before anything is fetched');
  // a stand-in canvas: counts what is painted (the art never needs a browser to prove it draws)
  const paint = (card) => {
    let marks = 0, text = '';
    const g = new Proxy({}, { get: (o, k) => {
      if (k in o) return o[k];
      if (k === 'measureText') return (s) => ({ width: String(s).length * 10 });
      if (k === 'createRadialGradient' || k === 'createLinearGradient') return () => ({ addColorStop() {} });
      if (k === 'fillText') return (s) => { marks++; text += s; };
      if (k === 'fill' || k === 'fillRect' || k === 'stroke') return () => { marks++; };
      return () => {};
    }, set: (o, k, v) => { o[k] = v; return true; } });
    drawCard(g, 1280, 720, card);
    return { marks, text };
  };
  for (const kind of [...CARD_KINDS, 'unknown_kind']) for (const extra of [{}, { text: 'Sarah', style: 'pencil', child: true }, { surface: 'wrapper', style: 'crayon' }, { blank: true, blankFaces: false }, { time: '11:40' }]) {
    const r = paint({ id: 'c9', kind, color: '#222', time: '12:00', ...extra });
    assert.ok(r.marks > 3, `${kind} paints`);
  }
  assert.match(paint({ id: 'c1', kind: 'phone_screen', time: '11:40' }).text, /11:40/);
  assert.match(paint({ id: 'c1', kind: 'name', text: 'Sarah', style: 'ink', color: '#222' }).text, /S.*a.*r.*a.*h/);
  assert.match(paint({ id: 'c1', kind: 'name', style: 'pencil', color: '#222' }).text, /y.*o.*u.*r/, 'no name given: still written');
  // the same card paints the same marks whichever render part draws it
  assert.equal(paint({ id: 'c2', kind: 'drawing' }).marks, paint({ id: 'c2', kind: 'drawing' }).marks);
});

test('cards: a name card says the hero name when the plan gives one', () => {
  assert.equal(planOf('Your name is written on the wrapper.', { hero: 'Daniel' }).cards[0].text, 'Daniel');
  assert.equal(planOf('Your name is written on the wrapper.').cards[0].text, 'your name');
});

test('cards: they dissolve in and out, never overlap and never sit under the final fade', async () => {
  const { cardAt } = await import('../lib/horror.mjs');
  const p = csvPlan([
    `beat,b1,"Here it is, on the wrapper.",,,town,hero,,,"{""card"":[{""what"":""wrapper with a name"",""hold"":5},{""what"":""a torn letter"",""hold"":5}]}"`,
    `beat,b2,"The box is full of drawings.",,,town,hero,,,`,
  ]);
  const cs = p.cards;
  assert.ok(cs.length >= 2);
  cs.forEach((c, i) => { assert.equal(c.id, `c${i + 1}`); assert.ok(c.t1 > c.t0); assert.ok(c.t1 <= p.duration - 1.2 + 1e-6); if (cs[i + 1]) assert.ok(cs[i + 1].t0 >= c.t1, `${c.id} ends before the next`); });
  const c = cs[0];
  assert.equal(cardAt(cs, c.t0 - 0.01)?.card?.id === c.id, false);
  assert.ok(cardAt(cs, c.t0 + 0.01).a < 0.05, 'starts dissolving in');
  assert.ok(cardAt(cs, c.t0 + 0.9).a > 0.99, 'fully on');
  assert.ok(cardAt(cs, c.t1 - 0.01).a < 0.05, 'dissolves out');
  assert.equal(cardAt(cs, p.duration + 5), null);
});

test('cards: the camera pushes into the held thing, then the card; a CSV camera is left alone', () => {
  const p = planOf(`${FAR} ${FAR} She gives you a driver's license and it is blank. ${FAR}`);
  const c = p.cards[0], s = p.scenes.find((x) => x.id === c.scene);
  assert.equal(c.hand.role, 'hero');
  const sh = s.shots.find((x) => x.t0 < c.t0 && x.t1 >= c.t0);
  assert.equal(sh.behaviour, 'hand_close'); assert.equal(sh.subject.type, 'hand');
  assert.ok(c.t0 - sh.t0 >= 1.2, 'time for the push before the dissolve');
  assert.ok(s.holds.some((h) => h.item === 'card_id' && h.role === 'hero' && h.t0 <= sh.t0 + 1 && h.t1 >= c.t0), 'the hero holds it');
  const A = assembleScene(JSON.parse(JSON.stringify(s)));
  for (const t of [sh.t0 + 0.1, c.t0]) assert.ok(A.cameraAt(t).pos.every(Number.isFinite));
  // a CSV camera wins: no extra cut or push
  const q = csvPlan([`beat,b1,"The box is full of drawings and more of them.",,,town,hero,,static_close,`]);
  const noCard = csvPlan([`beat,b1,"The box is full of drawings and more of them.",,,town,hero,,static_close,"{""card"":false}"`]);
  assert.equal(q.scenes[0].shots[0].behaviour, 'static_close');
  assert.deepEqual(q.scenes[0].shots.map((x) => [x.behaviour, x.t0]), noCard.scenes[0].shots.map((x) => [x.behaviour, x.t0]));
  assert.equal(q.cards.length, 1, 'the card still shows');
});

test('cards: indoors the push goes to the room phone or the hands, and the camera stays valid', () => {
  const p = csvPlan([
    `beat,b1,"${FAR} Take out your phone. The time on it will be 11:40.",Kitchen,phone_call,interior,hero,,,`,
    `beat,b2,"${FAR} ${FAR} The box on the table is full of drawings.",Kitchen,alone_inside,interior,hero,,,`,
  ]);
  const [a, b] = p.cards;
  assert.equal(a.focus, 'phone'); assert.equal(b.focus, 'hands');
  assert.ok(p.scenes[0].props.includes('phone'));
  for (const c of [a, b]) {
    const s = p.scenes.find((x) => x.id === c.scene), sh = s.shots.find((x) => x.t0 < c.t0 && x.t1 >= c.t0);
    assert.equal(sh.behaviour, 'push_in'); assert.equal(sh.focus, c.focus);
    const A = assembleScene(JSON.parse(JSON.stringify(s)));
    assert.ok(A.cameraAt(c.t0).pos.every(Number.isFinite));
  }
});

test('cards: a film that is not a horror story has none of this', () => {
  const s = storyFromText('The box is full of drawings. Your name is printed on the wrapper. The clock says 11:40.', 'H');
  const p = direct(s, { fps: 24 });
  assert.equal(p.cards, undefined); assert.equal(JSON.stringify(p).includes('"cards"'), false);
});

// ---- a history-style CSV in a horror story, and the doorstep (any script) -------------------------------------------------------
test('horror wins over a CSV written for history: events, the lead, effects and high cameras', () => {
  const p = csvPlan([`beat,b1,"You open the door. A child is standing on your mat. The child holds out a hand.",Porch,consequence,town,civilian:You; child:Child,front door,aerial_geo>rise,`]);
  const s = p.scenes[0];
  assert.ok(HORROR_RECIPES[s.event], s.event);
  assert.ok(s.cast.some((c) => c.role === 'hero'), 'civilian:You is the hero');
  assert.equal(s.cast.find((c) => c.role === 'child').formation, 'front');
  for (const sh of s.shots) assert.ok(!['aerial_geo', 'rise', 'pullback_reveal', 'establishing_wide', 'crane_up'].includes(sh.behaviour), sh.behaviour);
  const q = direct(parseStory(`row,id,text,event,environment,time,characters,effects\nplan,,T,,,,,"{}"\nbeat,b1,"A quiet road.",consequence,town,night,civilian:You,fire_small\n`.replace('characters,effects\nplan,,T,,,,,"{}"', 'characters,effects,extra\nplan,,T,,,,,,"{""genre"":""horror""}"')), { fps: 24 });
  assert.deepEqual(q.scenes[0].fx, [], 'no stray fires');
});

test('the doorstep: porch words build a house front, it carries on while the story stays there, pumpkins when named', () => {
  const p = planOf(`You open the door. A child is standing on the porch, in a plain white sheet. A pumpkin burns on the step.\n\nThe child holds out a piece of candy and gives it to you.\n\nA long time ago, when you were small, you remember the fields.`);
  const [a, b, c] = p.scenes;
  assert.equal(a.set, 'porch'); assert.equal(a.pumpkin, true);
  assert.equal(b.set, 'porch', 'still there'); assert.equal(b.seed, a.seed);
  assert.notEqual(c.set, 'porch', 'a memory is somewhere else');
  const child = a.cast.find((x) => x.role === 'child');
  assert.equal(child.costume, 'sheet');
  assert.ok(!a.cast.some((x) => x.role === 'stranger'), 'the child takes the stranger\'s place');
  assert.ok((b.holds || []).some((h) => h.role === 'child') && b.holds.some((h) => h.role === 'hero'), 'handed over from the child to the hero');
  const A = assembleScene(JSON.parse(JSON.stringify(a)));
  assert.ok(A.world.props.some((x) => x.kind === 'porch_front')); assert.ok(A.world.props.some((x) => x.kind === 'pumpkin'));
  assert.ok(A.stage.actors.find((x) => x.role === 'child').look.costume === 'sheet');
  assert.ok(A.cameraAt(a.t0 + 1).pos.every(Number.isFinite));
});

test('a named child keeps their own face, not the sheet', () => {
  const p = csvPlan([`beat,b1,"A child in a white sheet waits. Eli watches from the porch.",Porch,,town,child:Eli; child:Child,,,`]);
  const cs = p.scenes[0].cast;
  assert.equal(cs.find((c) => c.name === 'Eli').costume, undefined); assert.equal(cs.find((c) => c.name === 'Child').costume, 'sheet');
});

test('a name a sentence after the writing still makes the card, printed in the words the script says', () => {
  const c = planOf('You look down. The wrapper is printed in cheap black letters. It is your full name.').cards[0];
  assert.equal(c.kind, 'name'); assert.equal(c.surface, 'wrapper'); assert.equal(c.style, 'print'); assert.equal(c.color, '#18181b');
});

test('a hall is a hallway, the room carries over when a beat does not name one, and "want to remember" is no flashback', () => {
  const p = csvPlan([`beat,b1,"You stand there and listen.",Hall,alone_inside,interior,hero,,,`, `beat,b2,"You wait a little longer.",,alone_inside,interior,hero,,,`, `beat,b3,"You go on waiting.",Kitchen,alone_inside,interior,hero,,,`]);
  assert.deepEqual(p.scenes.map((s) => s.room), ['hallway', 'hallway', 'kitchen']);
  assert.notEqual(classifyHorror("There is a detail you will want to remember.").type, 'flashback');
  assert.equal(classifyHorror('You remember the house, years ago.').type, 'flashback');
});

test('at the door: the child faces the hero, a close camera stays low, "no bag" means no bag, and the street is modern', () => {
  const p = csvPlan([`beat,b1,"You open the door. A child stands on your mat. No mask. No bag. Nothing moves at all out there.",Porch,encounter,town,hero; child:Child,,over_shoulder,`]);
  const s = p.scenes[0], A = assembleScene(JSON.parse(JSON.stringify(s)));
  const t = s.t0 + 1, hero = A.actorAt(A.stage.actors.find((a) => a.role === 'hero'), t), kid = A.actorAt(A.stage.actors.find((a) => a.role === 'child'), t);
  const toHero = Math.atan2(hero.x - kid.x, hero.z - kid.z), off = Math.abs(Math.atan2(Math.sin(kid.yaw - toHero), Math.cos(kid.yaw - toHero)));
  assert.ok(off < 0.05, `the child looks at the hero (off by ${off})`);
  assert.ok(A.cameraAt(t).pos[1] < hero.y + 9, `a low camera, not on the roof: ${A.cameraAt(t).pos[1]}`);
  assert.ok(!(s.holds || []).some((h) => h.item === 'paper_bag'), 'the script says no bag');
  for (const k of ['well', 'hay', 'cart', 'crates']) assert.ok(!A.world.props.some((q) => q.kind === k), k);
});

// ---- the camera looks after itself: any script, no per-video tuning --------------------------------------------------------------
const WORDS = ['You open the door and a child stands on your mat. The child holds out a piece of candy and gives it to you.', 'An old woman stops in front of you at the bus stop, smiling. She hands you a small gift.', 'A man waits outside the shop in the rain. He gives you a letter and steps back.', 'At home, your father stands in the kitchen. He hands you a drawing and says nothing.', 'Your mother is in the hallway with a stranger behind her. She holds out her hand and gives you a phone.'];
test('every shot of a horror film has a clear view, whatever the script says and whoever stands where', async () => {
  const { sceneCamera, viewBlock, blockedShots } = await import('../lib/assemble.mjs');
  let shots = 0, stuck = 0;
  for (let seed = 0; seed < 6; seed++) for (const line of WORDS) {
    const rows = [`beat,b1,"${line}",,,,hero; stranger,,over_shoulder>over_shoulder,"{""seed"":${seed}}"`, `beat,b2,"${line}",,,,,,,"{""seed"":${seed + 40}}"`];
    for (const s of csvPlan(rows).scenes) {
      const A = assembleScene(JSON.parse(JSON.stringify(s)));
      stuck += blockedShots(A).length;
      for (const sh of s.shots) { if (blockedShots(A).includes(sh)) continue; shots++; const t = (sh.t0 + sh.t1) / 2, c = sceneCamera(A, t); assert.ok(c.pos.every(Number.isFinite)); assert.equal(viewBlock(A, c, t, sh), null, `${s.id} ${sh.behaviour}: ${line.slice(0, 30)}`); }
    }
  }
  assert.ok(shots > 60, `${shots} shots`);
  assert.ok(stuck / (shots + stuck) < 0.1, `${stuck} of ${shots + stuck} shots had no clear side`);
});

test('a hand-over shows both people side on, then the thing in the hand, even over a CSV camera, for any giver', async () => {
  for (const [cast, giver, line] of [['hero; child:Child', 'child', 'The child holds out a piece of candy and gives it to you. You look down and say nothing at all for a long time.'], ['hero; stranger', 'stranger', 'She stops in front of you and hands you a gift. You look down and say nothing at all for a long time.']]) {
    const p = csvPlan([`beat,b1,"The road is quiet and nothing moves. ${line}",,encounter,town,${cast},,static_close,`]);
    const s = p.scenes[0], g = s.holds.find((h) => h.handover), k = s.shots.findIndex((x) => x.behaviour === 'handover');
    assert.ok(k >= 0, `${giver}: ${s.shots.map((x) => x.behaviour)}`);
    assert.equal(g.handover, giver);
    const sh = s.shots[k]; assert.ok(sh.t0 < g.at && sh.t1 > g.at + 1, 'the moment is inside the shot, with time before and after');
    assert.equal(sh.subject.type, 'between');
    assert.equal(s.shots[k + 1]?.behaviour, 'hand_close');
    const A = assembleScene(JSON.parse(JSON.stringify(s))), hero = A.stage.actors.find((a) => a.role === 'hero'), other = A.stage.actors.find((a) => a.role === giver);
    const a = A.actorAt(hero, g.at), b = A.actorAt(other, g.at);
    assert.ok(Math.hypot(a.x - b.x, a.z - b.z) < 6, 'face to face, within reach');
    const c = A.cameraAt(g.at), lead = (q) => { const d = [q.x - c.pos[0], q.z - c.pos[2]], f = [c.target[0] - c.pos[0], c.target[2] - c.pos[2]], u = (d[0] * f[0] + d[1] * f[1]) / (f[0] ** 2 + f[1] ** 2); return Math.hypot(d[0] - f[0] * u, d[1] - f[1] * u); };
    assert.ok(lead(a) > 1 && lead(b) > 1, 'one each side of the frame, not one behind the other');
  }
});

test('nobody ends up inside a house: a lone or a crowd of people on a street set stay outside', () => {
  for (const cast of ['child:Child', 'child:Child*12', 'civilian:Ruth; civilian:Dale']) for (let seed = 0; seed < 5; seed++) {
    const s = csvPlan([`beat,b1,"You open the door and look out at the porch.",Porch,,town,${cast},,,"{""seed"":${seed}}"`]).scenes[0], A = assembleScene(JSON.parse(JSON.stringify(s)));
    for (const a of A.stage.actors) { const st = A.actorAt(a, s.t0 + 1); for (const c of A.world.colliders) if (!c.inside) assert.ok(!(st.x > c.x0 && st.x < c.x1 && st.z > c.z0 && st.z < c.z1), `${cast} ${a.role} at ${st.x},${st.z}`); }
  }
});

test('people facing each other stay put, whatever actions a CSV written for another film asks for', () => {
  const p = csvPlan([`beat,b1,"The child holds out a piece of candy and gives it to you. You look down and say nothing at all for a long time.",Porch,encounter,town,hero; child:Child,,,`.replace(',,,`', ',,,')]);
  const q = direct(parseStory(`row,id,text,location,event,environment,characters,actions,extra\nplan,,T,,,,,,"{""genre"":""horror""}"\nbeat,b1,"The child holds out a piece of candy and gives it to you. You look down and say nothing at all for a long time.",Porch,encounter,town,hero; child:Child,gesture;carry;walk,\n`), { fps: 24 });
  for (const plan of [p, q]) {
    const s = plan.scenes[0], A = assembleScene(JSON.parse(JSON.stringify(s)));
    for (const role of ['hero', 'child']) { const a = A.stage.actors.find((x) => x.role === role), u = A.actorAt(a, s.t0 + 0.2), v = A.actorAt(a, s.t1 - 0.2); assert.ok(Math.hypot(u.x - v.x, u.z - v.z) < 1, `${role} moved ${Math.hypot(u.x - v.x, u.z - v.z)}`); }
  }
});

test('a history film gets the new things only when the script or CSV names them', () => {
  const hist = (rows) => direct(parseStory(`row,id,text,location,event,environment,characters,props,extra\nplan,,T,,,,,,\n${rows.join('\n')}\n`), { fps: 24 });
  const named = hist([`beat,b1,"Ruth stood on the porch by a pumpkin and held a letter. A child in a white sheet watched.",,civilian_life,town,civilian:Ruth; child:Child,,"{""card"":""a letter in pencil""}"`]);
  const s = named.scenes[0];
  assert.equal(s.set, 'porch'); assert.equal(s.pumpkin, true);
  assert.equal(s.cast.find((c) => c.role === 'child').costume, 'sheet');
  assert.ok(s.holds.some((h) => h.item === 'letter'), 'in the named lead\'s hand');
  assert.equal(named.cards[0].kind, 'letter'); assert.equal(named.genre, undefined);
  assert.ok(!s.clearView && !s.tidy, 'its cameras and streets stay as they were');
  assert.deepEqual(s.shots.filter((x) => x.behaviour === 'handover'), []);
  const plain = hist([`beat,b1,"The army took the stores of grain and a shop in the town. A letter reached the general.",,battle,town,commander:Patton; soldier*6,,`]);
  assert.equal(plain.scenes[0].set, undefined, 'stores and a passing shop build nothing');
  assert.equal(plain.scenes[0].holds, undefined, 'an armed lead keeps their hands');
  assert.equal(plain.cards, undefined, 'the narration alone makes no card');
  const set = hist([`beat,b1,"He waited there.",Candy shop,,town,civilian:Tom,,`]);
  assert.equal(set.scenes[0].set, 'shop');
});
