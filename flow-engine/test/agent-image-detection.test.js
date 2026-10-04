/**
 * Flow Agent-view still images ("generated, but never added").
 *
 * Confirmed live (2026-10-03): on accounts whose Flow toolbar is the Agent
 * view, a finished still shows up as <img alt="Option N"> in the chat and
 * <img alt="Tile displaying a user's image"> in the grid, both on
 * flow.google.com/asb/<token>=s1600-rw. The detector only knew
 * flow-content.google/image URLs, so 80 of 81 Agent-view generations timed
 * out while the picture sat on the page. GET on "<token>=s0" returns the
 * original JPEG.
 *
 * Real in-page detector against a fake DOM (one fake page per account) and the
 * real downloadMedia -- no browser, no Flow, no credits. Also covers the
 * "Close instances" crash (closeBrowsers read an undefined `contexts`).
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const experiment = await import("../lib/flow-ui-experiment.js");
const { generateOneImageViaUI } = experiment;
const resolveAsbImage = experiment.resolveAsbImage ?? (() => null);
const { downloadMedia } = await import("../lib/flow-api.js");

const PROJECT_ID = "3fe16e7e-e725-4dc0-852b-80593cffdd9f";
const PROMPT = "a horizontal geological timeline, dark teal background";
const ASB = (token, suffix = "=s1600-rw") => `https://flow.google.com/asb/${token}${suffix}`;
const tmpDir = () => fs.mkdtempSync(path.join(os.tmpdir(), "flow-agent-img-"));
const opts = (extra = {}) => ({ outputDir: tmpDir(), generationTimeoutMs: 8000, ...extra });

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

const option = (token, n = 1) => ({ tagName: "IMG", alt: `Option ${n}`, src: ASB(token) });
const gridTile = (token) => ({ tagName: "IMG", alt: "Tile displaying a user's image", src: ASB(token) });

test("an Agent-view 'Option 1' still is detected and mapped to the original-JPEG URL", async () => {
  const { page } = makeAccountPage({ afterPolls: () => [option("TOKEN-NEW")] });
  const r = await generateOneImageViaUI(page, PROJECT_ID, PROMPT, opts(), 0);
  assert.equal(r.fifeUrl, ASB("TOKEN-NEW", "=s0"));
  assert.match(r.mediaId, /^asb-[0-9a-f]{16}$/);
  assert.ok(!r.mediaId.includes("TOKEN"), "the signed token must not leak into the media id");
});

test("the grid tile alone is enough too", async () => {
  const { page } = makeAccountPage({ afterPolls: () => [gridTile("TOKEN-GRID")] });
  const r = await generateOneImageViaUI(page, PROJECT_ID, PROMPT, opts(), 0);
  assert.equal(r.fifeUrl, ASB("TOKEN-GRID", "=s0"));
});

test("stills already on the page from earlier scenes are never mistaken for the new one", async () => {
  const { page } = makeAccountPage({
    before: [option("TOKEN-OLD-1"), gridTile("TOKEN-OLD-1"), option("TOKEN-OLD-2"), gridTile("TOKEN-OLD-2")],
    afterPolls: (n) => (n < 2 ? [] : [option("TOKEN-NEW"), gridTile("TOKEN-NEW")]),
  });
  const r = await generateOneImageViaUI(page, PROJECT_ID, PROMPT, opts(), 0);
  assert.equal(r.fifeUrl, ASB("TOKEN-NEW", "=s0"));
});

test("a video the Agent made for an image request is never saved as the image", async () => {
  const { page } = makeAccountPage({
    afterPolls: () => [{ tagName: "IMG", alt: "Generated video thumbnail", src: ASB("TOKEN-VIDEO", "") }],
  });
  await assert.rejects(
    () => generateOneImageViaUI(page, PROJECT_ID, PROMPT, opts({ generationTimeoutMs: 50 }), 0),
    /did not produce an image/,
  );
});

test("the classic flow-content.google/image result is still detected as before", async () => {
  const { page } = makeAccountPage({
    afterPolls: () => [{ tagName: "IMG", alt: "x", src: "https://flow-content.google/image/classic-img-1?fife=1" }],
  });
  const r = await generateOneImageViaUI(page, PROJECT_ID, PROMPT, opts(), 0);
  assert.equal(r.mediaId, "classic-img-1");
});

test("three Agent-view accounts finishing at different times each get, download and save their own image", async () => {
  const accounts = [
    { name: "4", page: makeAccountPage({ afterPolls: (n) => (n >= 1 ? [option("TOKEN-A")] : []) }).page },
    { name: "131", page: makeAccountPage({ afterPolls: (n) => (n >= 2 ? [gridTile("TOKEN-B")] : []) }).page },
    { name: "178", page: makeAccountPage({ afterPolls: (n) => (n >= 3 ? [option("TOKEN-C")] : []) }).page },
  ];
  const outDir = tmpDir();
  const results = await Promise.all(
    accounts.map(async ({ name, page }) => {
      const r = await generateOneImageViaUI(page, PROJECT_ID, PROMPT, { outputDir: outDir, generationTimeoutMs: 12000 }, 0);
      const bytes = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.from(`jpeg-for-${r.fifeUrl}`), Buffer.alloc(80, 7)]);
      page.context = () => ({ request: { get: async () => ({ ok: () => true, status: () => 200, body: async () => bytes }) } });
      const dest = path.join(outDir, `${name.padStart(3, "0")}.png`);
      await downloadMedia(page, r.mediaId, dest, r.fifeUrl);
      return { dest, bytes, url: r.fifeUrl };
    }),
  );
  assert.deepEqual(
    results.map((x) => x.url),
    [ASB("TOKEN-A", "=s0"), ASB("TOKEN-B", "=s0"), ASB("TOKEN-C", "=s0")],
    "each scene must get its own picture, not a sibling's",
  );
  for (const x of results) {
    assert.ok(fs.existsSync(x.dest), `${x.dest} was not saved`);
    assert.ok(!fs.existsSync(`${x.dest}.part`), "the atomic .part file must be gone");
    assert.deepEqual(fs.readFileSync(x.dest), x.bytes);
  }
});

test("resolveAsbImage ignores URLs that are not asb tiles", () => {
  assert.equal(resolveAsbImage("https://flow-content.google/image/abc?x=1"), null);
  assert.equal(resolveAsbImage(""), null);
});

test("'Close instances' no longer crashes the engine (closeBrowsers read an undefined variable)", async () => {
  const { closeBrowsers } = await import("../lib/orchestrator.js");
  // Nothing is open in the test process, so this must simply report 0 closed.
  assert.equal(await closeBrowsers(), 0);
});
