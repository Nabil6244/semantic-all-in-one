/**
 * Real functional coverage for flow-ui-experiment.js's UI-based generation
 * path — until now, generateOneImageViaUI (already the production path for
 * images) had NO test coverage at all, and the direct-RPC generateOneVideo
 * (flow-api.js) was still wired for video (see batch-runner.js), never
 * migrated to the same UI-based approach. This suite:
 *
 *   1. Proves generateOneVideoViaUI enters the UI-based path (mode: "video"
 *      selection, prompt entry, Generate click) exactly like
 *      generateOneImageViaUI does for images — same runUiGeneration core,
 *      just mode-parameterized.
 *   2. Proves the UI generation actually "completes" (waits for a real
 *      DOM-visible media element, not a fixed sleep) and returns a valid
 *      {mediaId, fifeUrl} the existing downstream pipeline
 *      (batch-runner.js's download/retry machinery) already consumes
 *      unchanged.
 *   3. Proves the existing MissingMediaIdError failure contract still holds
 *      on timeout, for both image and video.
 *   4. Proves batch-runner.js no longer imports/calls the old direct-RPC
 *      generateOneVideo for video generation.
 *   5. Confirms generateOneImageViaUI's own behavior is unaffected
 *      (regression) by this change.
 *
 * No live network/browser: a minimal fake Playwright `page` simulates only
 * what runUiGeneration actually touches (a handful of locators + evaluate
 * calls, in the exact order the real code issues them) — this exercises
 * the REAL orchestration logic (mode selection, prompt entry, generate
 * click, poll-for-new-media loop, mediaId extraction), not a source-level
 * grep. Run: node --test test/flow-ui-generation.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { generateOneImageViaUI, generateOneVideoViaUI } = await import(
  "../lib/flow-ui-experiment.js"
);

const PROJECT_ID = "3fe16e7e-e725-4dc0-852b-80593cffdd9f";
const PROMPT = "a small red ball rolling slowly across a white studio floor";

// --- Minimal fake locator/page --------------------------------------------
// Mirrors only the Playwright surface runUiGeneration actually calls, in
// the exact call order the real code issues them (verified against
// flow-ui-experiment.js directly). The mode-toggle button is made visible
// from the start so openSettingsPanelWithRetry's own (separately-scoped)
// retry logic is never exercised here — this suite is about the image/
// video generation path, not the settings-panel-opening path.

function makeLocator({ selector, hasText, state }) {
  const self = {
    filter: ({ hasText: text } = {}) => makeLocator({ selector, hasText: text, state }),
    first: () => self,
    count: async () => (selector === 'button[role="radio"]' ? 1 : 0),
    isVisible: async () => {
      if (selector === 'button[role="radio"]') return true; // panel "already open"
      return false;
    },
    waitFor: async () => {},
    click: async () => {
      if (selector === 'button[role="radio"]') state.modeClicked = hasText;
      if (selector === 'button[aria-label="Start generation"]') state.generateClicked = true;
    },
    getAttribute: async (name) => {
      if (selector === 'button[role="radio"]' && name === "aria-checked") return "false";
      return null;
    },
    pressSequentially: async (text) => {
      state.promptText = text;
    },
  };
  return self;
}

function makeFakePage({ mediaKind, mediaId, neverFindsMedia = false }) {
  const state = { modeClicked: null, generateClicked: false, promptText: null, evalCalls: 0 };
  const mediaUrl = `https://flow-content.google/${mediaKind}/${mediaId}?fife=1`;

  const page = {
    url: () => `https://flow.google.com/project/${PROJECT_ID}`,
    locator: (selector) => makeLocator({ selector, state }),
    keyboard: { press: async () => {} },
    waitForLoadState: async () => {},
    evaluate: async () => {
      state.evalCalls += 1;
      if (state.evalCalls === 1) {
        // checkFlowReady (inside waitForFlowReady) — MUST stay real/ready
        // even in the "never finds media" tests below, or waitForFlowReady
        // falls into its own separate 45s internal timeout loop before
        // runUiGeneration's poll loop (governed by generationTimeoutMs)
        // is ever reached at all.
        return { url: page.url(), hasProject: true, hasRecaptcha: true };
      }
      if (state.evalCalls === 2) {
        // preExistingMediaUrls snapshot — none yet
        return [];
      }
      // Poll loop: only "discover" the new media once Generate was clicked
      // (and never, for the MissingMediaIdError timeout tests).
      return !neverFindsMedia && state.generateClicked ? [mediaUrl] : [];
    },
    context: () => ({ request: { get: async () => ({ ok: () => true, body: async () => Buffer.from("") }) } }),
  };

  // The polling loop's page.evaluate signature returns a single string or
  // null (see runUiGeneration) — adapt the list-returning stub above.
  const rawEvaluate = page.evaluate;
  page.evaluate = async (...args) => {
    const result = await rawEvaluate(...args);
    if (Array.isArray(result) && state.evalCalls > 2) {
      return result.length ? result[0] : null;
    }
    return result;
  };

  return { page, state, mediaUrl };
}

function tmpOutputDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "flow-ui-test-"));
}

test("generateOneVideoViaUI enters the UI-based path and selects Video mode", async () => {
  const outputDir = tmpOutputDir();
  const { page, state } = makeFakePage({ mediaKind: "video", mediaId: "vid-abc-123" });
  const result = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir }, 0);

  assert.equal(state.modeClicked, "Video");
  assert.equal(state.promptText, PROMPT);
  assert.equal(state.generateClicked, true);
  assert.equal(result.mediaId, "vid-abc-123");
  assert.ok(result.fifeUrl.includes("flow-content.google/video/"));
});

test("generateOneVideoViaUI returns a result shape the existing downstream pipeline can consume", async () => {
  const outputDir = tmpOutputDir();
  const { page } = makeFakePage({ mediaKind: "video", mediaId: "vid-consume-me" });
  const result = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir }, 0);

  // Same {mediaId, fifeUrl, width, height} shape generateOneImageViaUI/the
  // old generateOneVideo both already produced — batch-runner.js's
  // download/retry logic reads exactly these fields.
  assert.ok("mediaId" in result);
  assert.ok("fifeUrl" in result);
  assert.ok("width" in result);
  assert.ok("height" in result);
});

test("generateOneVideoViaUI raises MissingMediaIdError when no media ever appears", async () => {
  const outputDir = tmpOutputDir();
  const { page } = makeFakePage({ mediaKind: "video", mediaId: "never-seen", neverFindsMedia: true });
  // A short generation timeout keeps this test fast.
  await assert.rejects(
    () =>
      generateOneVideoViaUI(
        page, PROJECT_ID, PROMPT,
        { outputDir, generationTimeoutMs: 50 },
        0,
      ),
    /Flow UI generation did not produce a video/,
  );
});

test("generateOneImageViaUI still works (regression) after the video path was added", async () => {
  const outputDir = tmpOutputDir();
  const { page, state } = makeFakePage({ mediaKind: "image", mediaId: "img-xyz-789" });
  const result = await generateOneImageViaUI(page, PROJECT_ID, PROMPT, { outputDir }, 0);

  assert.equal(state.modeClicked, "Image");
  assert.equal(result.mediaId, "img-xyz-789");
  assert.ok(result.fifeUrl.includes("flow-content.google/image/"));
});

// Not re-run here: generateOneImageViaUI (pre-existing, untouched by this
// change) doesn't forward a configurable generationTimeoutMs the way the
// new generateOneVideoViaUI does, so exercising its own timeout path would
// mean actually waiting out its real ~120s default — the identical
// underlying runUiGeneration timeout/MissingMediaIdError logic is already
// proven above for video (same function, mode-parameterized only), and
// image's own success path is proven immediately below.

// Runs the REAL in-page selector function (the one passed to page.evaluate)
// against a fake DOM, instead of stubbing its return value — so the
// element-filtering logic itself is under test.
function makeDomPage({ elementsAfterGenerate }) {
  const { page, state } = makeFakePage({ mediaKind: "video", mediaId: "unused" });
  page.evaluate = async (fn, arg) => {
    state.evalCalls += 1;
    if (state.evalCalls === 1) return { url: page.url(), hasProject: true, hasRecaptcha: true };
    const elements = state.generateClicked ? elementsAfterGenerate : [];
    const prev = globalThis.document;
    globalThis.document = { querySelectorAll: () => elements };
    try {
      return fn(arg);
    } finally {
      globalThis.document = prev;
    }
  };
  return { page, state };
}

test("video mode never returns a poster/thumbnail /image/ URL as the video", async () => {
  const outputDir = tmpOutputDir();
  const { page } = makeDomPage({
    elementsAfterGenerate: [
      { src: "https://flow-content.google/image/poster-123?fife=1" }, // poster appears first
      { src: "https://flow-content.google/video/real-vid-456?fife=1" },
    ],
  });
  const result = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir }, 0);
  assert.equal(result.mediaId, "real-vid-456");
  assert.ok(result.fifeUrl.includes("/video/"));
});

test("video mode with only a poster image fails visibly instead of saving an image as .mp4", async () => {
  const outputDir = tmpOutputDir();
  const { page } = makeDomPage({
    elementsAfterGenerate: [{ src: "https://flow-content.google/image/poster-only?fife=1" }],
  });
  await assert.rejects(
    () => generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir, generationTimeoutMs: 50 }, 0),
    /did not produce a video/,
  );
});

test("image mode still accepts the new /image/ result", async () => {
  const outputDir = tmpOutputDir();
  const { page } = makeDomPage({
    elementsAfterGenerate: [{ src: "https://flow-content.google/image/img-789?fife=1" }],
  });
  const result = await generateOneImageViaUI(page, PROJECT_ID, PROMPT, { outputDir }, 0);
  assert.equal(result.mediaId, "img-789");
});

test("batch-runner.js generates only through the one dispatcher (mode, fallback and billing rules live there)", async () => {
  const src = fs.readFileSync(new URL("../lib/batch-runner.js", import.meta.url), "utf8");
  assert.ok(!/\bgenerateOneVideo\(|\bgenerateOneImage\(|ViaUI\(/.test(src), "batch-runner.js must not call a generation path directly");
  assert.ok(src.includes('from "./generation-dispatch.js"'), "batch-runner.js must generate through generation-dispatch.js");
});

test("video detection waits well past 3 minutes by default (Flow videos finish late under load)", () => {
  const src = fs.readFileSync(new URL("../lib/flow-ui-experiment.js", import.meta.url), "utf8");
  const m = src.match(/mode: "video",[\s\S]*?generationTimeoutMs: settings\?\.generationTimeoutMs \|\| (\d+)/);
  assert.ok(m, "video default generationTimeoutMs not found");
  const ms = Number(m[1]);
  assert.ok(ms > 180000, `video detection window ${ms}ms is no longer than the old 180s cap`);
  assert.ok(ms < 12 * 60 * 1000, "must stay under the app's 12-minute per-scene watchdog");
});

test("a Stop ends the video detection wait promptly without re-clicking Generate", async () => {
  const outputDir = tmpOutputDir();
  const { page, state } = makeFakePage({ mediaKind: "video", mediaId: "never", neverFindsMedia: true });
  let stop = false;
  setTimeout(() => (stop = true), 20);
  const started = Date.now();
  await assert.rejects(
    () =>
      generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir }, 0, { shouldStop: () => stop }),
    (err) => /outcome: stopped/.test(err.message) && err.generateClicked === true,
  );
  assert.ok(Date.now() - started < 5000, "stop must not wait out the full detection window");
  assert.equal(state.generateClicked, true);
});

test("a video that appears after the old 180s cap is detected (one click) and downloaded", async () => {
  const { downloadMedia } = await import("../lib/flow-api.js");
  const outputDir = tmpOutputDir();
  const { page, state } = makeFakePage({ mediaKind: "video", mediaId: "late-vid-1", neverFindsMedia: true });
  let clicks = 0;
  const realLocator = page.locator;
  page.locator = (selector) => {
    const loc = realLocator(selector);
    if (selector !== 'button[aria-label="Start generation"]') return loc;
    return { ...loc, first: () => ({ ...loc, click: async () => { clicks += 1; await loc.click(); } }) };
  };
  // Simulated clock: every poll advances 70s; the video only shows up once
  // 250s have "passed" since Generate was clicked.
  const realNow = Date.now;
  let offset = 0;
  let clickedAt = null;
  const polled = page.evaluate;
  page.evaluate = async (...args) => {
    if (state.generateClicked && clickedAt === null) clickedAt = Date.now();
    if (clickedAt !== null && state.evalCalls >= 2) {
      offset += 70000;
      state.evalCalls += 1;
      return Date.now() - clickedAt >= 250000 ? "https://flow-content.google/video/late-vid-1?fife=1" : null;
    }
    return polled(...args);
  };
  Date.now = () => realNow() + offset;
  let result;
  try {
    result = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir }, 0);
  } finally {
    Date.now = realNow;
  }
  assert.equal(result.mediaId, "late-vid-1");
  assert.ok(offset >= 250000, "detection must have run past the old 180s window");
  assert.equal(clicks, 1, "Start generation must be clicked exactly once");

  const mp4 = Buffer.concat([Buffer.from([0, 0, 0, 0x20]), Buffer.from("ftypisom"), Buffer.alloc(200, 1)]);
  const dlPage = { context: () => ({ request: { get: async () => ({ ok: () => true, status: () => 200, body: async () => mp4 }) } }) };
  const dest = path.join(outputDir, "013.mp4");
  await downloadMedia(dlPage, result.mediaId, dest, result.fifeUrl);
  assert.equal(fs.readFileSync(dest).length, mp4.length);
  assert.ok(!fs.existsSync(`${dest}.part`));
});

test("Agent UI: image requests say 'still image, not a video'; video requests are unchanged", async () => {
  const { agentPromptFor } = await import("../lib/flow-ui-experiment.js");
  const img = agentPromptFor("slow drone glide over sawgrass with visible water flow", "image");
  assert.match(img, /still image/i);
  assert.match(img, /not a video/i);
  assert.ok(img.endsWith("slow drone glide over sawgrass with visible water flow"));
  assert.equal(agentPromptFor("drone flight over the coast", "video"), "drone flight over the coast");
});
