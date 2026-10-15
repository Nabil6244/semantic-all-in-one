#!/usr/bin/env node
// node tools/validate_weather.mjs <spec.json>
// Every check a Weather render starts with, on the final spec (Hybrid's compiled spec + the weather layers), with no browser and no
// network: pakMap's timeline and camera rules on spec.events / spec.camera, and Weather's own layer and raster rules on spec.weather.
// Prints {"ok":bool,"errors":[...],"warnings":[...],"dropped":[...]} -- used by weather/preflight.py (the dry run).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateEvents, validateWatermark, freezeWindows } from '../../pakmap-engine/lib/events.mjs';
import { validateCamera } from '../../pakmap-engine/lib/camera.mjs';
import { sanitizeWeather } from '../lib/wx_sanitize.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(HERE, '..', 'lib', 'layers');
const plugins = [];
for (const n of fs.readdirSync(dir).filter((f) => f.endsWith('.mjs')).sort()) plugins.push((await import(path.join(dir, n))).default);

const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const errors = [], warnings = [];
errors.push(...validateWatermark(spec.watermark));
const tl = validateEvents(spec.events || [], spec.duration);
errors.push(...tl.errors); warnings.push(...tl.warnings);
errors.push(...validateCamera(spec.camera, spec.duration, freezeWindows(spec.events)));
// the weather layers as the renderer will draw them: a refused graphic is left out there too (lib/wx_sanitize.mjs), so it is a
// warning here, not an error
const clean = sanitizeWeather(spec.weather || {}, spec.duration, plugins);
warnings.push(...clean.dropped);
process.stdout.write(JSON.stringify({ ok: errors.length === 0, errors, warnings, dropped: clean.dropped }) + '\n');
