#!/usr/bin/env node
// node tools/validate_spec.mjs <spec.json>
// Runs the same checks a render starts with (overlay timeline rules, camera rules, watermark) and
// prints {"ok":bool,"errors":[...],"warnings":[...]} -- no browser, no network. The Python
// compiler calls this so the rules live in one place.
import fs from 'node:fs';
import { validateEvents, validateWatermark, freezeWindows } from '../lib/events.mjs';
import { validateCamera } from '../lib/camera.mjs';

const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const errors = [], warnings = [];
const num = (v) => typeof v === 'number' && Number.isFinite(v) && v > 0;
if (![spec.width, spec.height, spec.fps, spec.duration].every(num)) errors.push('spec needs positive width, height, fps and duration');
errors.push(...validateWatermark(spec.watermark));
const tl = validateEvents(spec.events || [], spec.duration);
errors.push(...tl.errors); warnings.push(...tl.warnings);
errors.push(...validateCamera(spec.camera, spec.duration, freezeWindows(spec.events)));
process.stdout.write(JSON.stringify({ ok: errors.length === 0, errors, warnings }) + '\n');
