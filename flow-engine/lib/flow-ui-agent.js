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

export function writeUiAgentLog(outputDir, diag) {
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
      // Gallery tiles only when the page has them: the chat-panel layout also shows small copies of each image in the
      // agent's replies (live 2026-10-21, Accounts 6 and 9), which are not tiles and must not count as new stills.
      const tiles = document.querySelectorAll("flow-grid-tile-container img, flow-grid-tile-container video");
      for (const el of tiles.length ? tiles : document.querySelectorAll("img, video")) {
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

/**
 * Flow's gallery is a virtual scroll list (live 2026-10-20: "cdk-virtual-scrollable", ~10 of 24+ tiles in the DOM at once).
 * A tile scrolled out of view does not exist on the page: it can be neither counted nor have its Reuse prompt clicked.
 * scrollGallery moves that list: "top", "down" (most of one screen) or "keep"; returns where it is.
 */
async function scrollGallery(page, how) {
  return bounded(page.evaluate((mode) => {
    const first = document.querySelector("flow-grid-tile-container");
    let el = first?.parentElement;
    while (el && el !== document.body) {
      if (/(auto|scroll)/.test(getComputedStyle(el).overflowY) && el.scrollHeight > el.clientHeight + 4) break;
      el = el.parentElement;
    }
    if (!el || el === document.body) el = document.scrollingElement || document.documentElement;
    if (mode === "top") el.scrollTop = 0;
    else if (mode === "down") el.scrollTop = el.scrollTop + Math.max(200, el.clientHeight * 0.8);
    return { top: el.scrollTop, atEnd: el.scrollTop + el.clientHeight >= el.scrollHeight - 4 };
  }, how), PAGE_CALL_TIMEOUT_MS, { top: 0, atEnd: true });
}

const SCROLL_SETTLE_MS = 350;
/** A request with some but not all stills is over only after this long with no new tile (12 s cut 24-scene runs short). */
export const PARTIAL_QUIET_MS = 45000;
const MAX_SCROLL_STEPS = 80;

/** Video tile URLs on the page (a <video>, its "Generated video thumbnail", or a flow-content.google /video/ URL). */
export async function collectVideoUrls(page) {
  return bounded(page
    .evaluate((host) => {
      const out = [];
      for (const el of document.querySelectorAll("img, video")) {
        const src = el.currentSrc || el.src || "";
        if (!src || out.includes(src)) continue;
        const isVideo = el.tagName === "VIDEO" || /video thumbnail/i.test(el.alt || "");
        if ((isVideo && /\/asb\//.test(src)) || (src.includes(host) && /\/video\//.test(src))) out.push(src);
      }
      return out;
    }, MEDIA_HOST), PAGE_CALL_TIMEOUT_MS, []);
}

/** Every video in the project, by scrolling the whole virtual gallery (ends back at the top). */
export async function collectAllVideoUrls(page) {
  return collectAllStillUrls(page, collectVideoUrls);
}

/** Every still in the project, top to bottom, by scrolling the whole virtual gallery (ends back at the top). */
export async function collectAllStillUrls(page, collect = collectStillUrls) {
  const out = [];
  const seen = new Set();
  const add = (urls) => {
    for (const u of urls) {
      const k = mediaKey(u);
      if (k && !seen.has(k)) { seen.add(k); out.push(u); }
    }
  };
  await scrollGallery(page, "top");
  await new Promise((r) => setTimeout(r, SCROLL_SETTLE_MS));
  for (let step = 0; step < MAX_SCROLL_STEPS; step++) {
    add(await collect(page));
    const pos = await scrollGallery(page, "down");
    if (pos.atEnd) {
      await new Promise((r) => setTimeout(r, SCROLL_SETTLE_MS));
      add(await collect(page));
      break;
    }
    await new Promise((r) => setTimeout(r, SCROLL_SETTLE_MS));
  }
  await scrollGallery(page, "top");
  return out;
}

/** Scroll until the tile for `key` is in the DOM: down from where the list is, then once more from the top. */
async function revealTile(page, key) {
  const present = () => bounded(page.evaluate((wantKey) => {
    const asbTok = wantKey.startsWith("asb:") ? wantKey.slice(4) : null;
    for (const c of document.querySelectorAll("flow-grid-tile-container")) {
      const src = c.querySelector("img")?.getAttribute("src") || "";
      if (asbTok ? src.includes(asbTok) : src.includes(wantKey.split("/").pop())) return true;
    }
    return false;
  }, key), PAGE_CALL_TIMEOUT_MS, false);
  for (let pass = 0; pass < 2; pass++) {
    if (pass === 1) {
      await scrollGallery(page, "top");
      await new Promise((r) => setTimeout(r, SCROLL_SETTLE_MS));
    }
    for (let step = 0; step < MAX_SCROLL_STEPS; step++) {
      if (await present()) return true;
      const pos = await scrollGallery(page, "down");
      await new Promise((r) => setTimeout(r, SCROLL_SETTLE_MS));
      if (pos.atEnd) {
        if (await present()) return true;
        break;
      }
    }
  }
  return false;
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
 * The bulk scene list we pasted (not one tile's prompt): its header, or two or more "S01:" scene lines. Real tile prompts
 * are often 1,500-2,500 chars (style blocks), so length is never the test — a 500-char cap dropped every tile (2026-10-20).
 */
export function isBulkAgentMessage(text) {
  const t = String(text || "");
  return /^Generate exactly \d+ still images/i.test(t.trim()) || (t.match(/^\s*S\d{2,3}:/gm) || []).length >= 2;
}

const squash = (t) => String(t || "").replace(/\s+/g, " ").trim();

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
    await revealTile(page, key);
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
    let lastSeen = "";
    if (meta.clickedReuse) {
      const deadline = Date.now() + 6000;
      while (Date.now() < deadline) {
        editorText = await bounded(
          page.evaluate(() => (document.querySelector("div.ProseMirror")?.innerText || "").trim()),
          PAGE_CALL_TIMEOUT_MS, "");
        lastSeen = editorText || lastSeen;
        if (editorText && !isBulkAgentMessage(editorText)) {
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
        why: !meta.src ? "tile_not_found" : !meta.clickedReuse ? "no_reuse_button" : lastSeen ? "bulk_text_in_editor" : "editor_stayed_empty",
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
  const kept = out.filter((t) => t.prompt);
  // Why each unread tile was dropped (diagnostic log only).
  Object.defineProperty(kept, "failures", { value: out.filter((t) => !t.prompt).map((t) => t.why), enumerable: false });
  return kept;
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

/**
 * The other Flow layout (live 2026-10-21, Account 6): no Agent toggle at all — the agent is a chat panel that is always
 * open on the right, with the same "What do you want to create?" editor and Start generation button. Its "Agent
 * instructions" button only shows while the agent is active (same signal as the toggle layout).
 */
async function agentPanelOpen(page) {
  const panel = page.locator('button[aria-label="Agent instructions"]').first();
  if ((await bounded(panel.count(), PAGE_CALL_TIMEOUT_MS, 0)) === 0) return false;
  return Boolean(await bounded(panel.isVisible(), PAGE_CALL_TIMEOUT_MS, false));
}

async function agentModeOn(page) {
  const btn = agentToggle(page);
  if ((await bounded(btn.count(), PAGE_CALL_TIMEOUT_MS, 0)) === 0) return agentPanelOpen(page);
  return (await bounded(btn.getAttribute("aria-pressed", { timeout: PAGE_CALL_TIMEOUT_MS }), PAGE_CALL_TIMEOUT_MS, null)) === "true";
}

/**
 * Turn on Flow's Agent mode. Create mode's Start generation makes one image;
 * Agent mode's same button plans one still per scene in the pasted message.
 */
export async function ensureAgentMode(page, { timeoutMs = 15000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  const btn = agentToggle(page);
  // Either layout's control: the toggle, or the chat panel's "Agent instructions" (no 15 s wait for a toggle that is not there).
  await Promise.any([
    btn.waitFor({ state: "visible", timeout: timeoutMs }),
    page.locator('button[aria-label="Agent instructions"]').first().waitFor({ state: "visible", timeout: timeoutMs }),
  ]).catch(() => {});
  if ((await bounded(btn.count(), PAGE_CALL_TIMEOUT_MS, 0)) === 0) {
    // Chat-panel layout: no toggle to press; the agent is on when its panel is open.
    if (await agentPanelOpen(page)) return { ok: true, reason: "agent_panel" };
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

    // Flow may cut a very long paste: never send a scene list that lost scenes (the runner splits the batch and retries).
    const pasted = await bounded(
      page.evaluate(() => (document.querySelector("div.ProseMirror")?.innerText || "")), PAGE_CALL_TIMEOUT_MS, null);
    diag.pastedChars = pasted == null ? null : squash(pasted).length;
    if (pasted != null && squash(pasted).length < squash(message).length * 0.97) {
      diag.outcome = "paste_truncated";
      await clearPromptEditor(page);
      const err = new Error(`Flow kept ${diag.pastedChars} of ${squash(message).length} characters of the scene list`);
      err.pasteTruncated = true;
      throw tagSubmission(err, Submission.NOT_SUBMITTED);
    }

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

    const known = new Set((await collectAllStillUrls(page)).map(mediaKey).filter(Boolean));
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
      // The whole gallery, not just the rendered window: new tiles below it were invisible and the wait ended early.
      const urls = await collectAllStillUrls(page);
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
      // Some stills but not all: the agent paints in bursts and its busy text is not reliable, so allow a long quiet gap.
      if (ordered.length > 0 && ordered.length < n && !busy && Date.now() - lastNewAt > PARTIAL_QUIET_MS) break;
      await new Promise((r) => setTimeout(r, 1500));
    }

    diag.stage = "reading_tile_prompts";
    // Take every new tile we saw (not only first N) so out-of-order gallery still maps by text.
    // Gallery order (top to bottom), so each tile is found by scrolling a little further down.
    const wanted = new Set(ordered.map((o) => o.key));
    const urls = (await collectAllStillUrls(page)).filter((u) => wanted.has(mediaKey(u)));
    for (const o of ordered) if (!urls.some((u) => mediaKey(u) === o.key)) urls.push(o.url);
    const images = await readPromptsForStillUrls(page, urls);
    diag.foundCount = images.length;
    diag.rawTileCount = ordered.length;
    diag.promptedCount = images.filter((t) => t.prompt).length;
    diag.samplePrompts = images.map((t) => String(t.prompt || "").slice(0, 100));
    diag.promptLengths = images.map((t) => String(t.prompt || "").length);
    diag.reuseFailures = images.failures || [];
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
