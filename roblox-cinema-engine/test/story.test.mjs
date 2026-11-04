// Story CSV, narration reading and timing. Run: node --test test/
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseStory, storyFromText, validateStory } from '../lib/csv.mjs';
import { VOCAB } from '../lib/director.mjs';
import { splitSentences, extractDates, dateLabel, extractNumbers, wordsToNumber, alignTiming, estimateTiming, classifyEvent } from '../lib/narration.mjs';
import { sampleStory } from './_helpers.mjs';

test('the sample story parses and validates with no errors', () => {
  const s = sampleStory();
  assert.equal(s.beats.length, 17); assert.equal(s.chapters.length, 5);
  assert.deepEqual(validateStory(s, VOCAB), []);
});
test('plain narration becomes beats, # lines become chapters', () => {
  const s = storyFromText('# One\n\nThe army marched.\n\nIt rained.', 'T');
  assert.equal(s.chapters.length, 1); assert.equal(s.beats.length, 2);
});
test('bad names are reported with the line', () => {
  const s = parseStory('row,id,text,event\nbeat,b1,Hello there.,not_an_event\n');
  assert.ok(validateStory(s, VOCAB).some((e) => /unknown event/.test(e)));
});
test('sentences, dates and numbers in words', () => {
  assert.equal(splitSentences('It began. Then it ended!').length, 2);
  const d = extractDates('On the twenty-fifth of August, 1944, Paris was liberated.');
  assert.equal(d[0].year, 1944); assert.match(dateLabel(d[0]), /25 AUGUST 1944/);
  assert.equal(wordsToNumber(['one', 'hundred', 'fifty', 'six', 'thousand']), 156000);
  assert.ok(extractNumbers('nearly seven thousand ships').some((n) => n.value === 7000));
});
test('events are classified from the words', () => {
  assert.equal(classifyEvent('Soldiers waded through the surf and took cover as bullets flew.').type, 'landing_operation');
  assert.equal(classifyEvent('The army signed the treaty and peace agreement in the palace.').type, 'peace_agreement');
});
test('voice timing: words are matched in order, misheard words are interpolated, nothing goes backwards', () => {
  const beats = [{ text: 'The army marched north.' }, { text: 'Then it rained heavily on the hills.' }];
  const words = [['the', 1], ['army', 1.3], ['marched', 1.7], ['north', 2.2], ['then', 3.5], ['it', 3.7], ['reigned', 3.9], ['heavily', 4.3], ['on', 4.6], ['the', 4.7], ['hills', 5]].map(([word, start]) => ({ word, start, end: start + 0.25 }));
  const r = alignTiming(beats, words);
  assert.equal(r.sentences.length, 2); assert.equal(r.sentences[1].start, 3.5);
  const ts = r.sentences.flatMap((s) => s.words.map((w) => w.start)); for (let i = 1; i < ts.length; i++) assert.ok(ts[i] >= ts[i - 1] - 1e-9);
  assert.ok(estimateTiming(beats).end > 3);
});

test('back-to-back beats on the same map are one continuous map scene, not the map re-opening per beat', async () => {
  const { direct } = await import('../lib/director.mjs');
  const m = '"{""map"": {""pins"": [""Rome"", ""Carthage""]}}"';
  const csv = `row,id,chapter,text,location,event,environment,extra
chapter,,One,,,,,
beat,b1,,Rome was founded on a river. That story is a legend. What is real is weirder.,Mediterranean Sea,map,map,${m}
beat,b2,,A muddy village grew into an empire that lasted a thousand years.,Mediterranean Sea,map,map,${m}
beat,b3,,So we cover about 1200 years of history and it is a mess.,Mediterranean Sea,map,map,
beat,b4,,The twins Romulus and Remus were raised by a wolf by the river.,Tiber River,establishing,river,
beat,b5,,Rome fought Carthage across the sea.,Mediterranean Sea,map,map,"{""map"": {""pins"": [""Rome"", ""Carthage""], ""arrows"": [[""Rome"", ""Carthage""]]}}"`;
  const p = direct(parseStory(csv));
  const maps = p.scenes.filter((s) => s.env === 'map');
  assert.equal(p.scenes[0].env, 'map'); assert.equal(p.scenes[1].env, 'river', 'the three opening map beats are one scene');
  assert.equal(maps.length, 2, 'a map with new arrows later is still its own scene');
  const s1 = p.scenes[0];
  assert.equal(s1.sentences.length, 5); const names = s1.map.pins.map((q) => q.name); assert.ok(names.length >= 1 && new Set(names).size === names.length, 'pins appear once');
  assert.ok(s1.shots.length >= 2 && s1.shots.slice(1).every((sh) => sh.transition === 'continuous' && sh.zoom < 1), 'a long map keeps moving in one unbroken descent');
  assert.equal(p.audio.cues.filter((c) => c.t < s1.t1 && /whoosh/.test(c.name || c.cue || c.type || '')).length <= 1, true);
});
test('"1200 years" is a length of time, not the year 1200', () => {
  assert.equal(extractDates('We cover about 1200 years of history.').length, 0);
  assert.equal(extractDates('By 1453 the city had fallen.')[0].year, 1453);
});
