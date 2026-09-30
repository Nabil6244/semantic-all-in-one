/**
 * Flow video results that live on flow.google.com/asb/<token>.
 *
 * Confirmed live (2026-09-30, read-only look at a real finished project): a
 * finished video tile is an <img alt="Generated video thumbnail"> on
 * flow.google.com/asb/<token> while idle and a <video> on
 * flow.google.com/asb/<token>=mm,22,15 once hovered; GET on the "=mm,22,15"
 * URL returns the full video/mp4. Neither is on flow-content.google or has
 * "/video/" in it, so the old detector waited out the whole window while the
 * video sat finished on Flow ("generated, but never downloaded").
 *
 * These run the REAL in-page detection function against a fake DOM, one fake
 * page per account, and then the REAL downloadMedia. No browser, no Flow, no
 * credits.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const experiment = await import("../lib/flow-ui-experiment.js");
const { generateOneVideoViaUI } = experiment;
const resolveAsbVideo = experiment.resolveAsbVideo ?? (() => null);
const { downloadMedia } = await import("../lib/flow-api.js");

const PROJECT_ID = "3fe16e7e-e725-4dc0-852b-80593cffdd9f";
const PROMPT = "a drone glides over a dam at sunset";
const ASB = (token, suffix = "") => `https://flow.google.com/asb/${token}${suffix}`;

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "flow-asb-test-"));
}

function makeLocator(selector, state) {
  const self = {
    filter: () => self,
    first: () => self,
    count: async () => (selector === 'button[role="radio"]' ? 1 : 0),
    isVisible: async () => selector === 'button[role="radio"]',
    waitFor: async () => {},
    click: async () => {
      if (selector === 'button[aria-label="Start generation"]') state.generateClicked = true;
    },
    getAttribute: async () => "false",
    pressSequentially: async () => {},
  };
  return self;
}

/**
 * A fake Flow page for one account. `before` is what its grid already shows;
 * `afterPolls(n)` is what it shows on the n-th poll after Generate was clicked.
 */
function makeAccountPage({ before = [], afterPolls }) {
  const state = { evalCalls: 0, generateClicked: false, polls: 0 };
  const page = {
    url: () => `https://flow.google.com/project/${PROJECT_ID}`,
    locator: (selector) => makeLocator(selector, state),
    keyboard: { press: async () => {} },
    waitForLoadState: async () => {},
    evaluate: async (fn, arg) => {
      state.evalCalls += 1;
      if (state.evalCalls === 1) return { url: page.url(), hasProject: true, hasRecaptcha: true };
      let elements;
      if (!state.generateClicked) elements = before;
      else {
        state.polls += 1;
        elements = [...before, ...afterPolls(state.polls)];
      }
      const prev = globalThis.document;
      globalThis.document = { querySelectorAll: () => elements };
      try {
        return fn(arg);
      } finally {
        globalThis.document = prev;
      }
    },
    context: () => ({ request: { get: async () => ({ ok: () => true, body: async () => Buffer.from("") }) } }),
  };
  return { page, state };
}

const thumb = (token) => ({ tagName: "IMG", alt: "Generated video thumbnail", src: ASB(token) });
const hoveredVideo = (token) => ({ tagName: "VIDEO", alt: undefined, src: ASB(token, "=mm,22,15") });

test("a finished asb thumbnail tile is detected and turned into a downloadable video URL", async () => {
  const { page } = makeAccountPage({ afterPolls: () => [thumb("TOKEN-NEW")] });
  const r = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir: tmpDir(), generationTimeoutMs: 8000 }, 0);
  assert.equal(r.fifeUrl, ASB("TOKEN-NEW", "=mm,22,15"));
  assert.match(r.mediaId, /^asb-[0-9a-f]{16}$/);
  assert.ok(!r.mediaId.includes("TOKEN"), "the signed token must not leak into the media id");
});

test("a hovered asb <video> tile is detected too (same token, suffix normalised)", async () => {
  const { page } = makeAccountPage({ afterPolls: () => [hoveredVideo("TOKEN-HOVER")] });
  const r = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir: tmpDir(), generationTimeoutMs: 8000 }, 0);
  assert.equal(r.fifeUrl, ASB("TOKEN-HOVER", "=mm,22,15"));
});

test("an earlier video tile already in the grid is never mistaken for the new one", async () => {
  // Old tile is a thumbnail before Generate and turns into a hovered <video>
  // (different URL, same token) afterwards: must still be ignored.
  const { page } = makeAccountPage({
    before: [thumb("TOKEN-OLD")],
    afterPolls: (n) => (n < 2 ? [hoveredVideo("TOKEN-OLD")] : [hoveredVideo("TOKEN-OLD"), thumb("TOKEN-NEW")]),
  });
  const r = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir: tmpDir(), generationTimeoutMs: 8000 }, 0);
  assert.equal(r.fifeUrl, ASB("TOKEN-NEW", "=mm,22,15"));
});

test("an asb still-image tile is not accepted as a video", async () => {
  const { page } = makeAccountPage({
    afterPolls: () => [{ tagName: "IMG", alt: "Generated image", src: ASB("TOKEN-IMAGE") }],
  });
  await assert.rejects(
    () => generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir: tmpDir(), generationTimeoutMs: 50 }, 0),
    /did not produce a video/,
  );
});

test("the classic flow-content.google/video result is still detected first", async () => {
  const { page } = makeAccountPage({
    afterPolls: () => [
      thumb("TOKEN-ASB"),
      { tagName: "VIDEO", src: "https://flow-content.google/video/classic-vid-1?fife=1" },
    ],
  });
  const r = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir: tmpDir(), generationTimeoutMs: 8000 }, 0);
  assert.equal(r.mediaId, "classic-vid-1");
});

test("a detection timeout records what the page showed, without any token", async () => {
  const outputDir = tmpDir();
  const { page } = makeAccountPage({
    afterPolls: () => [{ tagName: "IMG", alt: "Something else", src: ASB("SECRET-TOKEN-XYZ") }],
  });
  await assert.rejects(
    () => generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir, generationTimeoutMs: 50 }, 0),
    /timeout_no_media_detected/,
  );
  const log = fs.readFileSync(path.join(outputDir, "flow-ui-generation.log"), "utf8");
  const entry = JSON.parse(log.trim().split("\n").pop());
  assert.equal(entry.outcome, "timeout_no_media_detected");
  assert.ok(entry.mediaInventory && Object.keys(entry.mediaInventory).length > 0);
  assert.ok(!log.includes("SECRET-TOKEN-XYZ"), "the log must never contain a media token");
});

test("resolveAsbVideo ignores URLs that are not asb tiles", () => {
  assert.equal(resolveAsbVideo("https://flow-content.google/video/abc?x=1"), null);
  assert.equal(resolveAsbVideo(""), null);
});

test("three accounts finishing at different times are each detected, downloaded and saved on their own", async () => {
  // Account A finishes on the 1st poll, B on the 2nd, C on the 3rd (and C
  // renders as a hovered <video>, A/B as thumbnails) -- the shape of the real
  // report where only the first finished video was ever picked up.
  const accounts = [
    { name: "1", page: makeAccountPage({ afterPolls: (n) => (n >= 1 ? [thumb("TOKEN-A")] : []) }).page },
    { name: "13", page: makeAccountPage({ afterPolls: (n) => (n >= 2 ? [thumb("TOKEN-B")] : []) }).page },
    { name: "27", page: makeAccountPage({ afterPolls: (n) => (n >= 3 ? [hoveredVideo("TOKEN-C")] : []) }).page },
  ];
  const outDir = tmpDir();

  const results = await Promise.all(
    accounts.map(async ({ name, page }) => {
      const r = await generateOneVideoViaUI(page, PROJECT_ID, PROMPT, { outputDir: outDir, generationTimeoutMs: 12000 }, 0);
      // Each account's browser context serves ITS OWN mp4 bytes for its own URL.
      const bytes = Buffer.concat([Buffer.from([0, 0, 0, 24]), Buffer.from("ftypmp42"), Buffer.from(`clip-for-${r.fifeUrl}`)]);
      page.context = () => ({ request: { get: async () => ({ ok: () => true, status: () => 200, body: async () => bytes }) } });
      const dest = path.join(outDir, `${name.padStart(3, "0")}.mp4`);
      await downloadMedia(page, r.mediaId, dest, r.fifeUrl);
      return { name, r, dest, bytes };
    }),
  );

  assert.deepEqual(
    results.map((x) => x.r.fifeUrl),
    [ASB("TOKEN-A", "=mm,22,15"), ASB("TOKEN-B", "=mm,22,15"), ASB("TOKEN-C", "=mm,22,15")],
    "each scene must get its own video, not a sibling's",
  );
  for (const x of results) {
    assert.ok(fs.existsSync(x.dest), `${x.dest} was not saved`);
    assert.ok(!fs.existsSync(`${x.dest}.part`), "the atomic .part file must be gone");
    assert.deepEqual(fs.readFileSync(x.dest), x.bytes);
  }
  assert.equal(new Set(results.map((x) => fs.readFileSync(x.dest).toString("latin1"))).size, 3);
});
