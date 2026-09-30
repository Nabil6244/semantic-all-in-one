/**
 * UI-driven Flow image generation.
 *
 * Drives Flow's actual web UI (real prompt editor, real "Start generation"
 * button) instead of calling the private `ogiZ0b` batchexecute RPC. Built
 * because the direct-RPC path (flow-api.js/generateOneImage) has been
 * consistently rejected by Google with PUBLIC_ERROR_UNUSUAL_ACTIVITY on this
 * account, while this UI-driven path completed successfully in live testing
 * (2026-09-23) — so `generateOneImageViaUI` is now used as the image
 * generation path in batch-runner.js. It does not call `ogiZ0b`,
 * `batchexecute`, or any private RPC anywhere in this file.
 *
 * No stealth/anti-detection behavior: `pressSequentially()` (real per-
 * character keyboard events) is used only because Flow's prompt box is a
 * ProseMirror contenteditable editor that requires real keyboard events to
 * register input at all. No artificial delay is added anywhere.
 *
 * Honest limitation: the "generation complete" detector is a best-effort
 * heuristic (poll for a new <img>/<video> served from the confirmed Flow
 * media CDN host, flow-content.google) rather than a captured, documented
 * DOM signal — it has worked in live testing but hasn't been proven against
 * every UI state (e.g. a failed generation shown in the UI itself).
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { waitForFlowReady, MissingMediaIdError } from "./flow-api.js";

const PROMPT_EDITOR_SELECTOR = "div.ProseMirror";
const GENERATE_BUTTON_SELECTOR = 'button[aria-label="Start generation"]';
/**
 * Two legitimate Flow toolbar variants confirmed live (2026-09-23): a
 * project can render either "Settings trigger" (the original selector) or,
 * on accounts assigned to what looks like an "Agent" toolbar experiment
 * cohort, a differently-labeled "Settings" button instead — with the legacy
 * "Settings trigger" element still present in the DOM but explicitly
 * `hidden`. Preference order matches which one has been observed working:
 * "Settings trigger" first (the original, still-common case), "Settings"
 * second. Never assumes either variant is the only one, and never clicks a
 * hidden/disabled element.
 */
const SETTINGS_CONTROL_SELECTORS = ['button[aria-label="Settings trigger"]', 'button[aria-label="Settings"]'];
/** Real button labels confirmed live in the settings panel's mode toggle
 * group (role="radio" buttons: Image / Video / Frames / Ingredients). */
const MODE_TOGGLE_LABEL = { image: "Image", video: "Video" };
/** Confirmed live in earlier ogiZ0b response captures this investigation. */
const MEDIA_HOST = "flow-content.google";
/**
 * Second result-URL shape (confirmed live 2026-09-30 in a real project): a
 * finished video tile is an <img alt="Generated video thumbnail"> on
 * flow.google.com/asb/<token>, which becomes a <video> on
 * flow.google.com/asb/<token>=mm,22,15 (thumbnail and video share the token).
 * Neither lives on MEDIA_HOST nor has "/video/" in it, so a run whose page
 * only ever shows this shape was never detected: the video finished on Flow
 * but the wait loop timed out and it was never downloaded. GET on the
 * "=mm,22,15" URL returns the full video/mp4 with the account's session.
 */
const ASB_VIDEO_SUFFIX = "=mm,22,15";
const ASB_TOKEN_RE = /\/asb\/([^=?&#]+)/;

/**
 * Turns an asb thumbnail/video URL into the {mediaId, fifeUrl} pair the rest
 * of the pipeline expects. The token is a signed media reference, so it is
 * never used as the id itself (ids are logged) -- a short hash of it is.
 */
export function resolveAsbVideo(url) {
  const m = ASB_TOKEN_RE.exec(url || "");
  if (!m) return null;
  const base = String(url).split(/[=?&#]/)[0];
  return {
    mediaId: `asb-${createHash("sha256").update(m[1]).digest("hex").slice(0, 16)}`,
    fifeUrl: `${base}${ASB_VIDEO_SUFFIX}`,
  };
}
/** Any radio in the mode-toggle group is a reliable "settings panel is open"
 * signal, independent of which mode we're about to select. */
const SETTINGS_PANEL_SIGNAL_SELECTOR = 'button[role="radio"]';

/**
 * Reads a candidate Settings control's current state without touching
 * anything — used both to log instrumentation and to decide whether a click
 * actually caused a transition. Never touches cookies/session data.
 */
async function inspectSettingsControl(page, control) {
  const attached = await control
    .count()
    .then((c) => c > 0)
    .catch(() => false);
  if (!attached) return { attached: false, visible: false, enabled: null, rect: null, radioCount: 0 };
  const visible = await control.isVisible().catch(() => false);
  const enabled = await control.isEnabled().catch(() => null);
  const rect = await control.boundingBox().catch(() => null);
  const radioCount = await page.locator(SETTINGS_PANEL_SIGNAL_SELECTOR).count().catch(() => 0);
  return { attached, visible, enabled, rect, radioCount };
}

/**
 * Picks the first visible AND enabled Settings control on this page, live,
 * every call — never a stored/cached choice, so it's inherently correct per
 * Page/account and adapts automatically if a page's variant changes between
 * calls. Never returns a hidden or disabled element.
 */
async function findVisibleSettingsControl(page) {
  const checked = [];
  for (const selector of SETTINGS_CONTROL_SELECTORS) {
    const locator = page.locator(selector).first();
    const state = await inspectSettingsControl(page, locator);
    checked.push({ selector, ...state });
    if (state.attached && state.visible && state.enabled) {
      return { selector, locator, checked };
    }
  }
  return { selector: null, locator: null, checked };
}

/**
 * Clicks whichever Settings control is actually visible/clickable on this
 * page and verifies the panel opened (any mode-toggle radio becomes
 * visible), retrying a bounded number of times if it doesn't — rather than
 * sleeping a fixed duration. Confirmed live (2026-09-23 investigation):
 * "Settings trigger" is not the only legitimate control — some accounts
 * render a different "Settings" button instead, with "Settings trigger"
 * present but `hidden`. Re-checks which control is visible on every attempt
 * (not just once) so this adapts even if the variant changes mid-run.
 */
async function openSettingsPanelWithRetry(page, diag, { maxAttempts = 3, perAttemptTimeoutMs = 4000 } = {}) {
  const attempts = [];
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const { selector, locator, checked } = await findVisibleSettingsControl(page);

    if (!locator) {
      attempts.push({
        attempt,
        ts: new Date().toISOString(),
        candidatesChecked: checked,
        selectedSelector: null,
        clickError: "no visible/enabled Settings control found",
        domChanged: false,
        imageRadioVisibleAfter: false,
      });
      // Confirmed live (2026-09-24 investigation): a fresh project's — and
      // in fact ANY project's — composer/Settings UI takes ~1.4-4.7s to
      // mount after navigation (waitForFlowReady only checks reCAPTCHA + a
      // project URL, not the actual Angular UI). This branch used to `continue`
      // immediately with no wait, so all `maxAttempts` could burn through in
      // well under a second — nowhere near that real render delay. Actually
      // wait for either control to become visible before retrying the find.
      await page
        .waitForSelector(SETTINGS_CONTROL_SELECTORS.join(", "), {
          state: "visible",
          timeout: perAttemptTimeoutMs,
        })
        .catch(() => {});
      continue; // bounded retry — the control may become available shortly
    }

    const before = checked.find((c) => c.selector === selector);

    let clickError = null;
    try {
      await locator.click({ timeout: perAttemptTimeoutMs });
    } catch (e) {
      clickError = e?.message || String(e);
    }

    let imageRadioVisibleAfter = false;
    try {
      await page.locator(SETTINGS_PANEL_SIGNAL_SELECTOR).first().waitFor({ state: "visible", timeout: perAttemptTimeoutMs });
      imageRadioVisibleAfter = true;
    } catch {
      imageRadioVisibleAfter = false;
    }

    const after = await inspectSettingsControl(page, locator);

    attempts.push({
      attempt,
      ts: new Date().toISOString(),
      candidatesChecked: checked,
      selectedSelector: selector,
      controlHiddenOrDisabled: !(before.visible && before.enabled),
      radioCountBefore: before.radioCount,
      radioCountAfter: after.radioCount,
      clickError,
      domChanged: after.radioCount !== before.radioCount,
      imageRadioVisibleAfter,
    });

    if (imageRadioVisibleAfter) {
      diag.settingsTriggerClickAttempts = attempts;
      diag.selectedSettingsSelector = selector;
      return true;
    }
  }
  diag.settingsTriggerClickAttempts = attempts;
  const anyControlEverFound = attempts.some((a) => a.selectedSelector);
  diag.selectedSettingsSelector = attempts.find((a) => a.selectedSelector)?.selectedSelector || null;
  if (!anyControlEverFound) {
    diag.noVisibleSettingsControl = true;
  }
  return false;
}

function writeUiLog(outputDir, entry) {
  try {
    const dir = outputDir || os.tmpdir();
    const logPath = path.join(dir, "flow-ui-generation.log");
    fs.appendFileSync(logPath, JSON.stringify(entry) + "\n");
  } catch (writeErr) {
    console.error(
      `[flow-ui] failed to write log: ${writeErr?.code || "?"} ${writeErr?.message || writeErr}`,
    );
  }
}

/**
 * Core UI-driven generation. Returns the media URL (never downloads it) plus
 * a mediaId parsed from that URL, matching what extractOgiZ0bImageResult
 * already does for the RPC path's response — same {mediaId, fifeUrl} shape.
 */
async function runUiGeneration(page, prompt, opts = {}) {
  const timeoutMs = opts.timeoutMs || 20000;
  const generationTimeoutMs = opts.generationTimeoutMs || 120000;
  const startedAt = Date.now();

  const diag = {
    ts: null,
    stage: "start",
    outcome: "unknown",
    projectPageReached: false,
    modeSelected: null,
    promptEditorFound: false,
    promptEntered: false,
    generationButtonFound: false,
    settingsTriggerClickAttempts: null,
    selectedSettingsSelector: null,
    noVisibleSettingsControl: false,
    preExistingMediaCount: null,
    generationClickedAt: null,
    generationCompletedAt: null,
    generatedImageDetected: false,
    mediaUrlDetected: false,
    totalElapsedMs: null,
    error: null,
  };

  let mediaUrl = null;

  try {
    diag.stage = "waiting_for_flow_ready";
    await waitForFlowReady(page);
    diag.projectPageReached = true;

    if (opts.mode && MODE_TOGGLE_LABEL[opts.mode]) {
      diag.stage = "selecting_mode";
      const modeBtn = page
        .locator('button[role="radio"]')
        .filter({ hasText: MODE_TOGGLE_LABEL[opts.mode] })
        .first();

      // Reading the panel's live DOM state on every call (never a stored/
      // shared flag) so this is inherently correct per Page/account — state
      // lives only in that page's own DOM. Confirmed live this is NOT a
      // toggle-state bug: `panelAlreadyOpen` was already correctly `false`
      // on every failing attempt. The actual issue (see
      // openSettingsPanelWithRetry's doc comment) is that the trigger click
      // itself sometimes has no effect, specifically right after a
      // generation completes — handled by retrying the click until the
      // panel's own DOM signal confirms it opened.
      const panelAlreadyOpen = await modeBtn.isVisible().catch(() => false);
      let usedAgentDefaults = false;
      if (!panelAlreadyOpen) {
        const opened = await openSettingsPanelWithRetry(page, diag);
        if (!opened) {
          diag.outcome = diag.noVisibleSettingsControl
            ? "no_visible_settings_control"
            : "settings_trigger_click_no_transition";
          return { mediaId: null, fifeUrl: null, diag };
        }

        // Confirmed live (2026-09-23): the Settings control this opens is
        // not always the classic per-generation Image/Video toggle. On the
        // "Agent" UI variant it instead opens a global generation-defaults
        // dialog (aspect ratio/count/model for image and video, no
        // Image/Video radio) — its own role="radio" buttons (aspect ratio,
        // count) are what satisfied SETTINGS_PANEL_SIGNAL_SELECTOR above.
        // Detect that case by the absence of a matching-labeled radio, close
        // the dialog with its own Back control (not relied on to respond to
        // Escape), and proceed straight to the prompt editor — Agent UI has
        // no per-generation mode step, it just uses the saved defaults.
        const hasModeToggle = (await modeBtn.count().catch(() => 0)) > 0;
        if (!hasModeToggle) {
          usedAgentDefaults = true;
          const backBtn = page.locator('button[aria-label="Back"]').first();
          if (await backBtn.isVisible().catch(() => false)) {
            await backBtn.click().catch(() => {});
          } else {
            await page.keyboard.press("Escape").catch(() => {});
          }
        } else {
          await modeBtn.waitFor({ state: "visible", timeout: timeoutMs }).catch(() => {});
        }
      }

      if (usedAgentDefaults) {
        diag.modeSelected = "agent-defaults";
      } else {
        const alreadySelected = (await modeBtn.getAttribute("aria-checked").catch(() => null)) === "true";
        if (!alreadySelected) {
          await modeBtn.click();
        }
        diag.modeSelected = opts.mode;

        if (!panelAlreadyOpen) {
          await page.keyboard.press("Escape");
        }
      }
    }

    diag.stage = "locating_prompt_editor";
    const editor = page.locator(PROMPT_EDITOR_SELECTOR).first();
    await editor.waitFor({ state: "visible", timeout: timeoutMs });
    diag.promptEditorFound = true;

    diag.stage = "entering_prompt";
    await editor.click();
    await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
    await page.keyboard.press("Backspace");
    // Flow's Agent UI has no Image/Video switch: its agent decides from the
    // wording, and motion words ("drone glide", "water flow") made it plan a
    // paid 10 s video when an image was requested. Say what we want.
    const typed = diag.modeSelected === "agent-defaults" ? agentPromptFor(prompt, opts.mode) : prompt;
    diag.agentInstructionAdded = typed !== prompt;
    await editor.pressSequentially(typed);
    diag.promptEntered = true;

    diag.stage = "locating_generate_button";
    const genBtn = page.locator(GENERATE_BUTTON_SELECTOR).first();
    await genBtn.waitFor({ state: "visible", timeout: timeoutMs });
    diag.generationButtonFound = true;

    // A batch reuses the same page across multiple images (see batch-runner.js's
    // per-slot loop), so a prior generation's <img src="flow-content.google/...">
    // is still sitting in the DOM. Without this snapshot, the very first poll
    // after clicking Generate could match that leftover element and report it
    // as this generation's result — confirmed live as the "wrong/old image"
    // bug (2026-09-23 investigation): the first image in a fresh project has
    // no pre-existing flow-content.google element and detects correctly, but
    // any subsequent image in the same batch does.
    const preExistingMediaUrls = await page
      .evaluate((host) => {
        const els = Array.from(document.querySelectorAll("img[src], video[src]"));
        return els.filter((el) => el.src && (el.src.includes(host) || el.src.includes("/asb/"))).map((el) => el.src);
      }, MEDIA_HOST)
      .catch(() => []);
    diag.preExistingMediaCount = preExistingMediaUrls.length;

    diag.stage = "clicking_generate";
    diag.generationClickedAt = Date.now();
    await genBtn.click();

    diag.stage = "waiting_for_completion";
    const deadline = Date.now() + generationTimeoutMs;
    while (Date.now() < deadline && !mediaUrl && !opts.shouldStop?.()) {
      mediaUrl = await page
        .evaluate(
          ({ host, known, wantVideo }) => {
            // Video mode must only ever accept a real /video/ URL: a result
            // tile's poster/thumbnail <img> (an /image/ URL) can appear first,
            // and returning it saved image bytes as the scene's .mp4.
            const els = Array.from(document.querySelectorAll("img[src], video[src]"));
            const hit = els.find(
              (el) =>
                el.src &&
                el.src.includes(host) &&
                !known.includes(el.src) &&
                (!wantVideo || el.src.includes("/video/")),
            );
            if (hit) return hit.src;
            if (!wantVideo) return null;
            // flow.google.com/asb/<token> video tiles (see ASB_VIDEO_SUFFIX):
            // a thumbnail <img> while idle, a <video> once hovered. Compared
            // by token, since the thumbnail and video URLs differ by suffix.
            const tokenOf = (u) => {
              const m = /\/asb\/([^=?&#]+)/.exec(u || "");
              return m ? m[1] : null;
            };
            const knownTokens = new Set(known.map(tokenOf).filter(Boolean));
            const tile = els.find((el) => {
              const t = tokenOf(el.src);
              if (!t || knownTokens.has(t)) return false;
              return el.tagName === "VIDEO" || /video thumbnail/i.test(el.alt || "");
            });
            return tile ? tile.src : null;
          },
          { host: MEDIA_HOST, known: preExistingMediaUrls, wantVideo: opts.mode === "video" },
        )
        .catch(() => null);
      if (!mediaUrl) await new Promise((r) => setTimeout(r, 1500));
    }

    if (!mediaUrl) {
      diag.outcome = opts.shouldStop?.() ? "stopped" : "timeout_no_media_detected";
      if (diag.outcome === "timeout_no_media_detected") {
        // What the page actually showed when detection gave up: element
        // counts by host / first path segment / alt text only (never a full
        // URL or token), so a future miss can be told apart in the log.
        diag.mediaInventory = await page
          .evaluate(() => {
            const kind = (u) => {
              try {
                const x = new URL(u, location.href);
                return x.host + "/" + (x.pathname.split("/")[1] || "");
              } catch {
                return "?";
              }
            };
            const counts = {};
            for (const el of document.querySelectorAll("img, video")) {
              const alt = el.alt ? ` alt="${String(el.alt).slice(0, 30)}"` : "";
              const key = `${el.tagName.toLowerCase()} ${kind(el.currentSrc || el.src || "")}${alt}`;
              counts[key] = (counts[key] || 0) + 1;
            }
            return counts;
          })
          .catch(() => null);
      }
      return { mediaId: null, fifeUrl: null, diag };
    }
    diag.generationCompletedAt = Date.now();
    diag.generatedImageDetected = true;
    diag.mediaUrlDetected = true;
    diag.outcome = "success";

    if (opts.mode === "video" && !mediaUrl.includes(MEDIA_HOST)) {
      const asb = resolveAsbVideo(mediaUrl);
      if (asb) {
        diag.mediaUrlKind = "asb";
        return { mediaId: asb.mediaId, fifeUrl: asb.fifeUrl, diag };
      }
    }
    const m =
      opts.mode === "video"
        ? mediaUrl.match(/\/video\/([^?]+)/)
        : mediaUrl.match(/\/image\/([^?]+)/) || mediaUrl.match(/\/video\/([^?]+)/);
    const mediaId = m ? m[1] : null;
    return { mediaId, fifeUrl: mediaUrl, diag };
  } catch (e) {
    diag.outcome = diag.outcome === "unknown" ? "error" : diag.outcome;
    diag.error = e?.message || String(e);
    return { mediaId: null, fifeUrl: null, diag };
  } finally {
    diag.ts = new Date().toISOString();
    diag.totalElapsedMs = Date.now() - startedAt;
    writeUiLog(opts.outputDir, diag);
  }
}

/**
 * Drop-in replacement for generateOneImage(page, projectId, prompt,
 * settings, promptIndex) — same contract ({mediaId, fifeUrl}), same
 * caller-visible errors (MissingMediaIdError on failure/timeout), so
 * batch-runner.js's existing download/retry/error-handling logic works
 * unchanged. `projectId`/`promptIndex` aren't needed by the UI path itself
 * (the page is already on the right project) but are accepted to match the
 * signature exactly.
 */

/**
 * Prompt text for Flow's Agent UI, which picks image vs video from the words
 * alone. Image requests get an explicit "one still image, not a video"
 * instruction; video requests are left as they are.
 */
export function agentPromptFor(prompt, mode) {
  if (mode !== "image") return prompt;
  return `Generate one still image only (a single photo, not a video, no motion): ${prompt}`;
}

export async function generateOneImageViaUI(page, projectId, prompt, settings, promptIndex) {
  const { mediaId, fifeUrl, diag } = await runUiGeneration(page, prompt, {
    outputDir: settings?.outputDir,
    mode: "image",
  });
  if (!mediaId) {
    throw new MissingMediaIdError(
      `Flow UI generation did not produce an image (outcome: ${diag.outcome}${diag.error ? `, ${diag.error}` : ""})`,
    );
  }
  return { mediaId, fifeUrl, width: null, height: null };
}

/**
 * Drop-in replacement for generateOneVideo(page, projectId, prompt,
 * settings, promptIndex) — the direct-RPC video path (flow-api.js's
 * YhhmEf/as29s calls) was unreliable in the same way the old direct-RPC
 * image path was, and was never migrated to the UI-based approach when
 * generateOneImageViaUI replaced generateOneImage. Same contract
 * ({mediaId, fifeUrl}), same caller-visible MissingMediaIdError on
 * failure/timeout, so batch-runner.js's existing download/retry/error-
 * handling logic works completely unchanged — only which function it calls
 * for a video slot changes (see batch-runner.js). runUiGeneration already
 * handles both modes identically (the Image/Video radio selection, prompt
 * entry, Generate click, and DOM-based media-URL polling are mode-agnostic
 * — see its own `/\/image\/([^?]+)/ || /\/video\/([^?]+)/` match); this
 * simply calls it with mode: "video" and a longer default generation
 * timeout (video generation is well known to take longer than image
 * generation), same as generateOneImageViaUI does for images. No direct
 * RPC, no header/fingerprint changes, no anti-abuse bypass — same waits-
 * for-real-UI-state, no-fixed-sleep synchronization already proven for
 * images.
 */
export async function generateOneVideoViaUI(page, projectId, prompt, settings, promptIndex, { shouldStop } = {}) {
  const { mediaId, fifeUrl, diag } = await runUiGeneration(page, prompt, {
    outputDir: settings?.outputDir,
    mode: "video",
    shouldStop,
    // Flow video jobs routinely run past 3 minutes under load (and several
    // run concurrently across accounts). The old 180s window gave up while
    // Flow was still rendering: the video then finished on Flow, but since
    // Generate was already clicked it was never re-clicked, downloaded, or
    // added. Waiting longer costs no extra credit (still exactly one click)
    // and stays under the app's 12-minute per-scene watchdog.
    generationTimeoutMs: settings?.generationTimeoutMs || 540000,
  });
  if (!mediaId) {
    const err = new MissingMediaIdError(
      `Flow UI generation did not produce a video (outcome: ${diag.outcome}${diag.error ? `, ${diag.error}` : ""})`,
    );
    // Whether Flow's paid "Start generation" was actually clicked before
    // detection gave up -- batch-runner.js must not re-click it then, since
    // the first request may still complete (and bill) on Google's side.
    err.generateClicked = Boolean(diag.generationClickedAt);
    throw err;
  }
  return { mediaId, fifeUrl, width: null, height: null };
}

/**
 * Standalone helper for manual/one-off testing: runs the UI generation AND
 * downloads the result to disk itself (the production path above leaves
 * downloading to the existing downloadMedia()/batch-runner.js machinery).
 */
export async function generateImageViaFlowUI(page, prompt, opts = {}) {
  const { mediaId, fifeUrl, diag } = await runUiGeneration(page, prompt, opts);
  if (!fifeUrl) return { ok: false, savedPath: null, mediaUrl: null, diag };
  const resp = await page.context().request.get(fifeUrl);
  if (!resp.ok()) {
    return { ok: false, savedPath: null, mediaUrl: fifeUrl, diag: { ...diag, outcome: "download_failed" } };
  }
  const body = await resp.body();
  const outDir = opts.outputDir || os.tmpdir();
  fs.mkdirSync(outDir, { recursive: true });
  const ext = opts.mode === "video" ? "mp4" : "png";
  const savedPath = path.join(outDir, `flow-ui-experiment-${Date.now()}.${ext}`);
  fs.writeFileSync(savedPath, body);
  return { ok: true, savedPath, mediaUrl: fifeUrl, diag };
}
