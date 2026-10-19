/**
 * Bulk image generation through Flow's Agent UI (not StreamChat RPC, not Create mode).
 *
 * Critical (live 2026-10-20): the bottom-bar "Agent" toggle must be aria-pressed=true
 * before pasting. If it stays false, "Start generation" is Create mode and makes ONE
 * image from the whole message — that was the bulk failure (diag: agentPanel false,
 * foundCount 1). With Agent on, the same Start generation arrow plans N stills.
 *
 * Mapping is by appearance order (message asks for S01… in order).
 */

import fs from "node:fs";
import path from "node:path";
import { waitForFlowReady } from "./flow-api.js";
import { Submission, tagSubmission } from "./generation-state.js";
import { resolveAsbImage } from "./flow-ui-experiment.js";

const PROMPT_EDITOR_SELECTOR = 'div.ProseMirror[aria-label="What do you want to create?"], div.ProseMirror';
const GENERATE_BUTTON_SELECTOR = 'button[aria-label="Start generation"]';
const MEDIA_HOST = "flow-content.google";
const ASB_TOKEN_RE = /\/asb\/([^=?&#]+)/;

function writeUiAgentLog(outputDir, diag) {
  if (!outputDir) return;
  try {
    const dir = path.join(outputDir, "agent");
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(path.join(dir, "ui-agent-diagnostic.log"), `${JSON.stringify(diag)}\n`);
  } catch {
    /* ignore */
  }
}

/** Stable identity for a media URL (host path or asb token). */
export function mediaKey(url) {
  if (!url) return null;
  const asb = ASB_TOKEN_RE.exec(url);
  if (asb) return `asb:${asb[1]}`;
  try {
    const u = new URL(url, "https://flow.google.com");
    return `${u.host}${u.pathname}`;
  } catch {
    return url;
  }
}

/**
 * Still-image tile URLs on the page. Gallery tiles often have empty/generic alts
 * (live: strict Option-N filter only saw 1 of 5). Skip video thumbnails and tiny icons.
 */
export async function collectStillUrls(page) {
  return page
    .evaluate((host) => {
      const out = [];
      const seen = new Set();
      const push = (src) => {
        if (!src || seen.has(src)) return;
        seen.add(src);
        out.push(src);
      };
      for (const el of document.querySelectorAll("img, video")) {
        const src = el.currentSrc || el.src || "";
        if (!src) continue;
        const alt = (el.alt || "").trim();
        if (el.tagName === "VIDEO" || /video thumbnail/i.test(alt)) continue;
        const isAsb = /\/asb\//.test(src);
        const isHost = src.includes(host);
        if (!isAsb && !isHost) continue;
        if (isHost && !/\/image\//.test(src) && !/\/asb\//.test(src)) continue;
        const w = el.naturalWidth || el.width || 0;
        const h = el.naturalHeight || el.height || 0;
        if ((w > 0 && w < 64) || (h > 0 && h < 64)) continue;
        push(src);
      }
      return out;
    }, MEDIA_HOST)
    .catch(() => []);
}

export function resolveStillUrl(url) {
  if (!url) return null;
  if (url.includes(MEDIA_HOST)) {
    const m = url.match(/\/image\/([^?]+)/);
    return m ? { mediaId: m[1], fifeUrl: url } : null;
  }
  return resolveAsbImage(url);
}

async function mediaInventory(page) {
  return page
    .evaluate(() => {
      const kind = (u) => {
        try {
          const x = new URL(u, location.href);
          return `${x.host}/${x.pathname.split("/")[1] || ""}`;
        } catch {
          return "?";
        }
      };
      const counts = {};
      for (const el of document.querySelectorAll("img, video")) {
        const src = el.currentSrc || el.src || "";
        const alt = el.alt ? ` alt="${String(el.alt).slice(0, 40)}"` : "";
        const wh = `${el.naturalWidth || 0}x${el.naturalHeight || 0}`;
        const key = `${el.tagName.toLowerCase()} ${kind(src)} ${wh}${alt}`;
        counts[key] = (counts[key] || 0) + 1;
      }
      return counts;
    })
    .catch(() => null);
}

async function agentStillBusy(page) {
  return page
    .evaluate(() => /\bThinking\b|\bGenerating\b/i.test((document.body?.innerText || "").slice(0, 20000)))
    .catch(() => false);
}

/** Bottom-bar Agent toggle (aria-pressed true when Agent mode is on). */
function agentToggle(page) {
  return page.locator("button").filter({ hasText: /^Agent$/i }).first();
}

async function agentModeOn(page) {
  const btn = agentToggle(page);
  if ((await btn.count().catch(() => 0)) === 0) return false;
  return (await btn.getAttribute("aria-pressed").catch(() => null)) === "true";
}

/**
 * Turn on Flow's Agent mode. Create mode's Start generation makes one image;
 * Agent mode's same button plans one still per scene in the pasted message.
 */
export async function ensureAgentMode(page, { timeoutMs = 15000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  const btn = agentToggle(page);
  await btn.waitFor({ state: "visible", timeout: timeoutMs }).catch(() => {});
  if ((await btn.count().catch(() => 0)) === 0) {
    return { ok: false, reason: "agent_toggle_missing" };
  }
  while (Date.now() < deadline) {
    if (await agentModeOn(page)) {
      // Agent instructions control appears once Agent is active (confirmed live).
      return { ok: true, reason: "pressed" };
    }
    await btn.click().catch(() => {});
    await new Promise((r) => setTimeout(r, 500));
  }
  return { ok: await agentModeOn(page), reason: (await agentModeOn(page)) ? "pressed" : "toggle_stuck" };
}

async function setEditorText(page, editor, text) {
  await editor.click();
  await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
  await page.keyboard.press("Backspace");
  const ok = await page.evaluate((t) => {
    const el =
      document.querySelector('div.ProseMirror[aria-label="What do you want to create?"]') ||
      document.querySelector("div.ProseMirror");
    if (!el) return false;
    el.focus();
    return document.execCommand("insertText", false, t);
  }, text);
  if (!ok) await page.keyboard.insertText(text);
}

/**
 * One Agent-UI bulk request: enable Agent mode, paste `message`, click Start
 * generation, wait until `expectedCount` new stills (or timeout / stop).
 */
export async function generateAgentBatchViaUI(page, {
  message,
  expectedCount,
  timeoutMs = 300000,
  shouldStop = null,
  outputDir = null,
} = {}) {
  const startedAt = Date.now();
  const diag = {
    ts: null,
    stage: "start",
    outcome: "unknown",
    expectedCount: Number(expectedCount) || 0,
    foundCount: 0,
    generationClickedAt: null,
    agentMode: null,
    error: null,
    totalElapsedMs: null,
  };
  const n = Math.max(0, Number(expectedCount) || 0);
  if (!message || !n) {
    diag.outcome = "bad_args";
    writeUiAgentLog(outputDir, diag);
    throw tagSubmission(new Error("UI agent requires a message and expectedCount >= 1"), Submission.NOT_SUBMITTED);
  }

  try {
    diag.stage = "waiting_for_flow_ready";
    await waitForFlowReady(page);

    diag.stage = "ensure_agent_mode";
    const mode = await ensureAgentMode(page);
    diag.agentMode = mode;
    if (!mode.ok) {
      diag.outcome = "agent_mode_off";
      writeUiAgentLog(outputDir, { ...diag, ts: new Date().toISOString(), totalElapsedMs: Date.now() - startedAt });
      throw tagSubmission(
        new Error("Flow UI Agent toggle could not be turned on (would Create one image instead of a bulk batch)"),
        Submission.NOT_SUBMITTED,
      );
    }

    diag.stage = "locating_prompt_editor";
    const editor = page.locator(PROMPT_EDITOR_SELECTOR).first();
    await editor.waitFor({ state: "visible", timeout: 20000 });

    diag.stage = "entering_message";
    await setEditorText(page, editor, message);
    diag.messageChars = String(message).length;

    // Re-check Agent is still on after typing (UI can reset the toggle).
    if (!(await agentModeOn(page))) {
      const again = await ensureAgentMode(page, { timeoutMs: 8000 });
      diag.agentModeRecheck = again;
      if (!again.ok) {
        diag.outcome = "agent_mode_lost";
        writeUiAgentLog(outputDir, { ...diag, ts: new Date().toISOString(), totalElapsedMs: Date.now() - startedAt });
        throw tagSubmission(new Error("Flow Agent mode turned off before send"), Submission.NOT_SUBMITTED);
      }
    }

    const known = new Set((await collectStillUrls(page)).map(mediaKey).filter(Boolean));
    diag.preExistingStillCount = known.size;

    diag.stage = "locating_generate_button";
    const genBtn = page.locator(GENERATE_BUTTON_SELECTOR).first();
    await genBtn.waitFor({ state: "visible", timeout: 15000 });

    diag.stage = "clicking_generate";
    diag.generationClickedAt = Date.now();
    await genBtn.click();

    diag.stage = "waiting_for_stills";
    const ordered = [];
    const seen = new Set();
    const deadline = Date.now() + timeoutMs;
    let lastNewAt = Date.now();
    while (Date.now() < deadline && !shouldStop?.()) {
      const urls = await collectStillUrls(page);
      for (const url of urls) {
        const key = mediaKey(url);
        if (!key || known.has(key) || seen.has(key)) continue;
        seen.add(key);
        ordered.push({ key, url });
        lastNewAt = Date.now();
      }
      const busy = await agentStillBusy(page);
      diag.agentBusy = busy;
      if (ordered.length >= n && !busy) break;
      if (ordered.length >= n && Date.now() - lastNewAt > 8000) break;
      if (ordered.length > 0 && ordered.length < n && !busy && Date.now() - lastNewAt > 12000) break;
      await new Promise((r) => setTimeout(r, 1500));
    }

    const images = [];
    for (const { url } of ordered.slice(0, n)) {
      const resolved = resolveStillUrl(url);
      if (resolved?.mediaId && resolved?.fifeUrl) images.push({ ...resolved, url });
    }
    diag.foundCount = images.length;
    diag.rawTileCount = ordered.length;
    diag.agentModeFinal = await agentModeOn(page);
    if (images.length < n) diag.mediaInventory = await mediaInventory(page);
    diag.outcome =
      images.length >= n ? "success" : images.length > 0 ? "partial" : shouldStop?.() ? "stopped" : "timeout_no_media";

    return { clicked: true, images, diag };
  } catch (e) {
    if (e?.submission) throw e;
    diag.outcome = diag.generationClickedAt ? "error_after_click" : "error_before_click";
    diag.error = e?.message || String(e);
    const err = e instanceof Error ? e : new Error(String(e));
    throw tagSubmission(err, diag.generationClickedAt ? Submission.UNKNOWN : Submission.NOT_SUBMITTED);
  } finally {
    diag.ts = new Date().toISOString();
    diag.totalElapsedMs = Date.now() - startedAt;
    writeUiAgentLog(outputDir, diag);
  }
}
