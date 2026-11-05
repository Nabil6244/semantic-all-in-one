// Indoor stories: the room comes from the story, people stay inside it, the camera keeps them in frame, and props named by the row are on the set.
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseStory } from '../lib/csv.mjs';
import { direct } from '../lib/director.mjs';
import { assembleScene } from '../lib/assemble.mjs';
import { roomKindFor, propsIn } from '../lib/rooms.mjs';

const HEAD = 'row,id,chapter,text,date,location,event,environment,time,weather,characters,actions,vehicles,props,effects,camera,subtitle,audio,transition,duration,extra\n';
const MOVES = ['establishing_interior', 'establishing_wide', 'dolly_in', 'push_in', 'dolly_out', 'pullback_reveal', 'crane_up', 'rise', 'low_angle', 'follow', 'side_track', 'orbit', 'static_close', 'over_shoulder'];
const ROOMS = [['Bathroom', 'mirror', 'She stared into the mirror above the sink and waited a long while before she moved.'], ['Kitchen', 'kitchen table', 'He sat at the kitchen table and read the letter a second time before he spoke.'],
  ['Hallway', 'door', 'The door at the end of the hallway stood open and nobody had touched it all night.'], ['Bedroom', 'bed', 'The bed had not been slept in and the room was colder than it should have been.'], ['The Old Farm', 'phone', 'The phone rang once and then the whole house went completely quiet again.']];
function story() {
  let csv = HEAD + 'plan,,,"Indoors",2026,,,,,,,,,,,,,,,,\nchapter,,"One",,,,,,,,,,,,,,,,,,\n', n = 0;
  for (const [place, prop, text] of ROOMS) for (const cam of MOVES) { n++; csv += `beat,b${n},,"${text}",,${place},civilian_life,interior,night,clear,civilian:Ana; civilian:Ben,point,,${prop},,${cam},,,cut,,\n`; }
  return direct(parseStory(csv), { fps: 24 });
}
const plan = story();
const solo = direct(parseStory(HEAD + 'plan,,,"Solo",2026,,,,,,,,,,,,,,,,\nchapter,,"One",,,,,,,,,,,,,,,,,,\n' + MOVES.map((c, i) => `beat,b${i},,"You look up at the mirror and you do not remember walking here at all tonight.",,Bathroom,consequence,interior,night,clear,civilian:You,walk,,mirror; sink,,${c},,,cut,,`).join('\n') + '\n'), { fps: 24 });

test('the room comes from the location, then the props, then the words; a meeting keeps the war room', () => {
  assert.equal(roomKindFor({ location: 'Bathroom' }), 'bathroom');
  assert.equal(roomKindFor({ location: 'Dayton Ohio', props: ['coffee pot', 'kitchen table'] }), 'kitchen');
  assert.equal(roomKindFor({ text: 'he walked into the bedroom', civilian: true }), 'bedroom');
  assert.equal(roomKindFor({ location: 'Washington', event: 'political_meeting' }), 'war');
  assert.equal(roomKindFor({ civilian: false }), 'war');
  assert.equal(roomKindFor({ civilian: true }), 'living');
  assert.deepEqual(propsIn('a glass of water by the mirror'), ['cup', 'mirror']);
});

for (const [name, p] of [['two people', plan], ['one person, walking', solo]]) test(`every indoor move keeps people in the room and in frame (${name})`, () => {
  for (const s of p.scenes) {
    const A = assembleScene(s), R = A.world.room; assert.ok(R, `${s.id} has no room`);
    for (let k = 0; k <= 12; k++) {
      const t = s.t0 + (s.t1 - s.t0 - 0.01) * k / 12, c = A.cameraAt(t);
      for (const a of A.stage.actors) { const q = A.actorAt(a, t); assert.ok(q.x > R.x0 && q.x < R.x1 && q.z > R.z0 && q.z < R.z1, `${s.id} ${s.camera}: actor outside the walls at ${t.toFixed(1)}`); }
      assert.ok(c.pos[0] >= R.x0 - 0.01 && c.pos[0] <= R.x1 + 0.01 && c.pos[2] >= R.z0 - 0.01 && c.pos[2] <= R.z1 + 0.01, `${s.id} ${s.camera}: camera outside`);
      const lead = A.actorAt(A.stage.actors[0], t), head = [lead.x, lead.y + 4, lead.z], v = head.map((x, i) => x - c.pos[i]), d = Math.hypot(...v);
      assert.ok(d > 3.5, `${s.id} ${s.camera}: camera inside a person (${d.toFixed(1)})`);
      const f = c.target.map((x, i) => x - c.pos[i]), fl = Math.hypot(...f), cos = (f[0] * v[0] + f[1] * v[1] + f[2] * v[2]) / (fl * d);
      // the shot looks at the lead or the thing being spoken of; never at a bare wall beyond them
      const onProp = Object.values(A.world.focus).some((q) => Math.hypot(q[0] - c.target[0], q[1] - c.target[1], q[2] - c.target[2]) < 1);
      assert.ok(cos > Math.cos((c.fov * 0.9) * Math.PI / 180) || onProp || c.fov === 52, `${s.id} ${s.camera}: subject out of frame at ${t.toFixed(1)}`);
    }
  }
});

test('props the row names are on the set, and a civilian does the action the row asks for', () => {
  const kinds = (s) => assembleScene(s).world.props.map((p) => p.kind);
  assert.ok(kinds(plan.scenes[0]).includes('mirror') && kinds(plan.scenes[0]).includes('vanity'));
  assert.ok(!kinds(plan.scenes[0]).includes('table_map'), 'a bathroom is not the war room');
  const A = assembleScene(plan.scenes[0]);
  assert.ok(A.stage.actors[0].schedule.some((x) => x.state === 'point'), 'the row said point');
});

test('the reflection acts on the spoken word, and the person in the room does not copy it', () => {
  const beat = (i, text, extra = 'mirror') => `beat,b${i},,"${text}",,Bathroom,consequence,interior,night,clear,civilian:You,look,,${extra},,push_in,,,cut,,\n`;
  const p = direct(parseStory(HEAD + 'plan,,,"Glass",2026,,,,,,,,,,,,,,,,\nchapter,,"One",,,,,,,,,,,,,,,,,,\n'
    + beat(1, 'You look up at the mirror and your reflection smiles at you.') + beat(2, 'Nothing else in the bathroom has changed at all tonight.')
    + beat(3, 'It got ahead of you by half a second tonight.') + beat(4, 'The reflection turned its head and looked at her.') + beat(5, 'The mirror was empty when she came back.')
    + beat(6, 'People who check are the ones who see it blink in the dark.') + beat(7, 'Its face is pressed against the glass and it waits.') + beat(8, 'The glass will stutter and then it stops.')), { fps: 24 });
  const acts = p.scenes.map((s) => (s.mirrorPlay || []).map((x) => x.act));
  assert.ok(acts[0].includes('smile') && acts[2].includes('ahead') && acts[3].includes('turn') && acts[4].includes('empty') && acts[5].includes('blink') && acts[6].includes('press') && acts[7].includes('still'));
  assert.ok(p.scenes[1].mirrorPlay.some((x) => x.act === 'smile' && x.carried), 'a smile stays on through the chapter');
  assert.ok(!acts[4].includes('smile'), 'an empty mirror has no smile');
  const s0 = p.scenes[0], A0 = assembleScene(s0), a0 = A0.stage.actors[0], at = s0.mirrorPlay[0].t0;
  assert.equal(a0.look.face.mouth, 'flat', 'you have not smiled yet');
  assert.equal(A0.reflectionAt(a0, at + 0.2).face.mouth, 'grin');
  assert.equal(A0.reflectionAt(a0, at - 0.2).face.mouth, null, 'not before the word');
  const c = A0.cameraAt(at + 0.2); assert.ok(c.fov < 25 && c.target[2] < A0.world.focus.mirror[2], 'the shot looks into the glass');
  const wide = direct(parseStory(HEAD + 'plan,,,"W",2026,,,,,,,,,,,,,,,,\nchapter,,"One",,,,,,,,,,,,,,,,,,\n' + beat(1, 'You look up at the mirror and your reflection smiles at you.').replace('push_in', 'establishing_wide')), { fps: 24 }).scenes[0];
  assert.ok(assembleScene(wide).cameraAt(wide.mirrorPlay[0].t0 + 0.2).fov < 25, 'a wide shot gives way to the moment in the glass');
  const s2 = p.scenes[2], A2 = assembleScene(s2), a2 = A2.stage.actors[0], t2 = s2.mirrorPlay.find((x) => x.act === 'ahead').t0 + 0.2;
  assert.ok(A2.reflectionAt(a2, t2).pose.head.yaw !== A2.actorAt(a2, t2).pose.head.yaw, 'it moves before you do');
  const s4 = p.scenes[4], A4 = assembleScene(s4); assert.equal(A4.reflectionAt(A4.stage.actors[0], s4.mirrorPlay[0].t0 + 0.2).visible, false);
  const s6 = p.scenes[6], A6 = assembleScene(s6), v = A6.reflectionAt(A6.stage.actors[0], s6.t1 - 0.1); assert.ok(v.z < A6.world.focus.mirror[2] + 2, 'up against the glass');
});
