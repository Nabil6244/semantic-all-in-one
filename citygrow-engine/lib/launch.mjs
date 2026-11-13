// Start headless Chromium on any Mac or PC, whatever browsers it has. The app's own check counts any old Playwright
// Chromium as "installed", but each Playwright version needs its own build (e.g. chromium_headless_shell-1234), so a
// machine with an older build failed with "Executable doesn't exist". Order: the Playwright build -> the installed
// Google Chrome -> download the matching build once (playwright install chromium) and try again.
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const missing = (e) => /Executable doesn't exist|browserType\.launch.*(not found|ENOENT)|playwright install/i.test(String(e && e.message || e));

/** chromium: playwright's chromium; opts: launch options; flowDir: the folder whose node_modules holds playwright; emit: progress lines. */
export async function launchChromium(chromium, opts, { flowDir, emit = () => {} } = {}) {
  const channel = process.env.RENDER_BROWSER_CHANNEL || opts.channel;
  const first = channel ? { ...opts, channel } : opts;
  try { return await chromium.launch(first); } catch (e) {
    if (!missing(e) && !channel) throw e;
    if (channel) { try { return await chromium.launch({ ...opts, channel: undefined }); } catch (e2) { if (!missing(e2)) throw e2; } }
  }
  // the system Chrome, when there is one
  try { return await chromium.launch({ ...opts, channel: 'chrome' }); } catch (e) { if (!missing(e) && !/chrome/i.test(String(e.message))) throw e; }
  // download the build this Playwright needs, once
  const cli = flowDir && path.join(flowDir, 'node_modules', 'playwright', 'cli.js');
  if (!cli || !fs.existsSync(cli)) throw new Error('no browser to draw with: install Google Chrome, or reinstall the app (Playwright is missing)');
  emit({ event: 'warning', message: 'downloading the browser the renderer needs (one time, about 150 MB)…' });
  const r = spawnSync(process.execPath, [cli, 'install', 'chromium'], { cwd: flowDir, encoding: 'utf8', timeout: 20 * 60 * 1000 });
  if (r.status !== 0) throw new Error(`could not download the browser (${(r.stderr || r.stdout || r.error || '').toString().trim().split('\n').pop()}); install Google Chrome and try again`);
  return chromium.launch(opts);
}
