/**
 * Bulk image generation through Flow's Agent UI (not StreamChat RPC, not Create mode).
 *
 * Critical (live 2026-10-20): the bottom-bar "Agent" toggle must be aria-pressed=true
 * before pasting. If it stays false, "Start generation" is Create mode and makes ONE
 * image from the whole message. With Agent on, the same Start generation arrow plans N stills.
 *
 * Assignment: NEVER by gallery order (that mismatched scenes live). After tiles appear,
 * each tile's "Reuse prompt" is clicked — Flow fills the editor with the exact scene
 * text — then mapUiTilesToScenes / mapCallsToScenes ties tiles to scenes by that text.
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
/** page.evaluate has no timeout of its own: a frozen Flow tab used to hang a batch (and Stop) forever. */
export const PAGE_CALL_TIMEOUT_MS = 10000;

/** `promise`, or `fallback` once `ms` pass (a hung page call never holds the run). */
export function bounded(promise, ms, fallback) {
  let timer;
  const timeout = new Promise((resolve) => { timer = setTimeout(() => resolve(fallback), ms); });
  return Promise.race([Promise.resolve(promise).catch(() => fallback), timeout]).finally(() => clearTimeout(timer));
}

/** Like bounded(), but a page call that does not answer throws (callers that cannot guess a result). */
export function boundedOrThrow(promise, ms, what) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`Flow page did not answer (${what}) within ${Math.round(ms / 1000)} s`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

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
  return bounded(page
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
    }, MEDIA_HOST), PAGE_CALL_TIMEOUT_MS, []);
}

export function resolveStillUrl(url) {
  if (!url) return null;
  if (url.includes(MEDIA_HOST)) {
    const m = url.match(/\/image\/([^?]+)/);
    return m ? { mediaId: m[1], fifeUrl: url } : null;
  }
  return resolveAsbImage(url);
}

/**
 * Clear the prompt editor so a failed Reuse cannot leave the bulk agent message
 * in place (that made every tile "match" every scene and uniqueness failed).
 */
async function clearPromptEditor(page) {
  await bounded(page.evaluate(() => {
    const el = document.querySelector("div.ProseMirror");
    if (!el) return;
    el.focus();
    document.execCommand("selectAll", false, null);
    document.execCommand("delete", false, null);
  }), PAGE_CALL_TIMEOUT_MS, undefined);
}

/**
 * For each new still URL, read Flow's per-tile prompt via that tile's "Reuse prompt"
 * button (exact scene text live). Never reuse a stale editor value from a previous
 * tile or from the bulk paste. Returns [{ url, mediaId, fifeUrl, prompt, ariaLabel }].
 */
export async function readPromptsForStillUrls(page, urls) {
  const out = [];
  for (const url of urls) {
    const resolved = resolveStillUrl(url);
    if (!resolved?.mediaId) continue;
    const key = mediaKey(url);
    await clearPromptEditor(page);

    const noMeta = { ariaLabel: "", clickedReuse: false, src: "" };
    const meta = await bounded(page
      .evaluate(
        ({ wantKey }) => {
          const tokenOf = (u) => {
            const m = /\/asb\/([^=?&#]+)/.exec(u || "");
            if (m) return `asb:${m[1]}`;
            try {
              const x = new URL(u, location.href);
              return `${x.host}${x.pathname}`;
            } catch {
              return null;
            }
          };
          const asbTok = wantKey.startsWith("asb:") ? wantKey.slice(4) : null;
          for (const container of document.querySelectorAll("flow-grid-tile-container")) {
            const img = container.querySelector("img");
            const src = img?.currentSrc || img?.src || "";
            if (!src) continue;
            const k = tokenOf(src);
            const hit = k === wantKey || (asbTok && src.includes(asbTok));
            if (!hit) continue;
            const ariaLabel = container.getAttribute("aria-label") || "";
            const btn = container.querySelector('button[aria-label="Reuse prompt"]');
            if (btn) {
              btn.scrollIntoView({ block: "center", inline: "nearest" });
              btn.click();
            }
            return { ariaLabel, clickedReuse: Boolean(btn), src };
          }
          return { ariaLabel: "", clickedReuse: false, src: "" };
        },
        { wantKey: key },
      ), PAGE_CALL_TIMEOUT_MS, noMeta);

    let editorText = "";
    if (meta.clickedReuse) {
      const deadline = Date.now() + 3000;
      while (Date.now() < deadline) {
        editorText = await bounded(
          page.evaluate(() => (document.querySelector("div.ProseMirror")?.innerText || "").trim()),
          PAGE_CALL_TIMEOUT_MS, "");
        // Bulk paste is multi-line / very long; a real tile prompt is one short line.
        if (editorText && editorText.length < 500 && !/^Generate exactly \d+ still images/i.test(editorText)) {
          break;
        }
        editorText = "";
        await new Promise((r) => setTimeout(r, 200));
      }
    }

    const prompt = editorText || "";
    if (!prompt) {
      // No reliable prompt — skip (never fall back to bulk editor or order).
      out.push({
        url,
        mediaId: resolved.mediaId,
        fifeUrl: resolved.fifeUrl,
        prompt: "",
        ariaLabel: meta.ariaLabel || "",
        reuseFailed: true,
      });
      continue;
    }
    out.push({
      url,
      mediaId: resolved.mediaId,
      fifeUrl: resolved.fifeUrl,
      prompt,
      ariaLabel: meta.ariaLabel || "",
    });
  }
  return out.filter((t) => t.prompt);
}

async function mediaInventory(page) {
  return bounded(page
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
    }), PAGE_CALL_TIMEOUT_MS, null);
}

async function agentStillBusy(page) {
  // Timeout → still busy (not idle). A laggy but live tab used to fall back to
  // false, then the wait loop could stop early after 12s of no new tiles.
  return bounded(
    page.evaluate(() => /\bThinking\b|\bGenerating\b/i.test((document.body?.innerText || "").slice(0, 20000))),
    PAGE_CALL_TIMEOUT_MS, true);
}

/** Bottom-bar Agent toggle (aria-pressed true when Agent mode is on). */
function agentToggle(page) {
  return page.locator("button").filter({ hasText: /^Agent$/i }).first();
}

async function agentModeOn(page) {
  const btn = agentToggle(page);
  if ((await bounded(btn.count(), PAGE_CALL_TIMEOUT_MS, 0)) === 0) return false;
  return (await bounded(btn.getAttribute("aria-pressed", { timeout: PAGE_CALL_TIMEOUT_MS }), PAGE_CALL_TIMEOUT_MS, null)) === "true";
}

/**
 * Turn on Flow's Agent mode. Create mode's Start generation makes one image;
 * Agent mode's same button plans one still per scene in the pasted message.
 */
export async function ensureAgentMode(page, { timeoutMs = 15000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  const btn = agentToggle(page);
  await btn.waitFor({ state: "visible", timeout: timeoutMs }).catch(() => {});
  if ((await bounded(btn.count(), PAGE_CALL_TIMEOUT_MS, 0)) === 0) {
    return { ok: false, reason: "agent_toggle_missing" };
  }
  while (Date.now() < deadline) {
    if (await agentModeOn(page)) {
      // Agent instructions control appears once Agent is active (confirmed live).
      return { ok: true, reason: "pressed" };
    }
    await bounded(btn.click({ timeout: PAGE_CALL_TIMEOUT_MS }), PAGE_CALL_TIMEOUT_MS, undefined);
    await new Promise((r) => setTimeout(r, 500));
  }
  return { ok: await agentModeOn(page), reason: (await agentModeOn(page)) ? "pressed" : "toggle_stuck" };
}

async function setEditorText(page, editor, text) {
  await editor.click();
  await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
  await page.keyboard.press("Backspace");
  const ok = await boundedOrThrow(page.evaluate((t) => {
    const el =
      document.querySelector('div.ProseMirror[aria-label="What do you want to create?"]') ||
      document.querySelector("div.ProseMirror");
    if (!el) return false;
    el.focus();
    return document.execCommand("insertText", false, t);
  }, text), PAGE_CALL_TIMEOUT_MS, "paste the scene list");
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

    if (shouldStop?.()) {
      diag.outcome = "stopped_before_click";
      throw tagSubmission(new Error("Stopped before the agent request was sent"), Submission.NOT_SUBMITTED);
    }

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

    diag.stage = "reading_tile_prompts";
    // Take every new tile we saw (not only first N) so out-of-order gallery still maps by text.
    const urls = ordered.map((o) => o.url);
    const images = await readPromptsForStillUrls(page, urls);
    diag.foundCount = images.length;
    diag.rawTileCount = ordered.length;
    diag.promptedCount = images.filter((t) => t.prompt).length;
    diag.samplePrompts = images.map((t) => String(t.prompt || "").slice(0, 100));
    diag.agentModeFinal = await agentModeOn(page);
    if (images.length < n) diag.mediaInventory = await mediaInventory(page);
    diag.outcome =
      images.length >= n && images.every((t) => t.prompt)
        ? "success"
        : images.length > 0
          ? "partial"
          : shouldStop?.()
            ? "stopped"
            : "timeout_no_media";

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
