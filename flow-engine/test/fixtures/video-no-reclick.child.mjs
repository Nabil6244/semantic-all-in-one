// Run by test/video-no-reclick.test.js with --experimental-test-module-mocks.
// Drives the REAL runBatchSlice retry loop; only the browser-touching
// modules are stubbed, so we can count paid "Start generation" clicks.
import test, { mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const realApi = await import("../../lib/flow-api.js");
const { MissingMediaIdError } = realApi;

const ctl = { calls: 0, behavior: null, downloadFails: false };

mock.module("../../lib/flow-api.js", {
  namedExports: {
    ...realApi,
    timing: { ...realApi.timing, sessionRetrySeconds: [0, 0, 0], rateLimitRetrySeconds: [0, 0], quotaRetrySeconds: [0, 0] },
    openOrCreateProject: async () => "test-project-id",
    waitForFlowReady: async () => {},
    checkFlowReady: async () => ({ hasProject: true, hasRecaptcha: true }),
    flowReload: async () => {},
    downloadMedia: async (_page, _id, dest) => {
      if (ctl.downloadFails) throw new Error("download failed: network reset");
      fs.writeFileSync(dest, Buffer.alloc(256, 1));
    },
  },
});

const fakeGenerate = async () => {
  ctl.calls += 1;
  return ctl.behavior(ctl.calls);
};
mock.module("../../lib/flow-ui-experiment.js", {
  namedExports: { generateOneVideoViaUI: fakeGenerate, generateOneImageViaUI: fakeGenerate },
});

const { runBatchSlice } = await import("../../lib/batch-runner.js");

function missing(generateClicked) {
  const err = new MissingMediaIdError("Flow UI generation did not produce media (outcome: timeout_no_media_detected)");
  err.generateClicked = generateClicked;
  return err;
}

async function runOne(mediaKind) {
  const events = [];
  await runBatchSlice({
    page: { __flowAccountId: "acct-test" },
    prompts: ["a plane taking off"],
    promptIndices: [0],
    totalAbsolute: 1,
    settings: { mediaKind, outputDir: fs.mkdtempSync(path.join(os.tmpdir(), "no-reclick-")) },
    folderLabel: "acct-test",
    shouldStop: () => false,
    onProgress: (e) => events.push(e),
    accountId: "acct-test",
    accountLabel: "Test",
    workerIndex: 0,
  });
  const result = events.find((e) => e.type === "PROMPT_RESULT");
  return { result };
}

function reset(behavior, { downloadFails = false } = {}) {
  ctl.calls = 0;
  ctl.behavior = behavior;
  ctl.downloadFails = downloadFails;
}

test("video: a detection timeout AFTER the paid click is never re-clicked", async () => {
  reset(() => { throw missing(true); });
  const { result } = await runOne("video");
  assert.equal(ctl.calls, 1, "Start generation was clicked more than once for one video prompt");
  assert.equal(result.status, "failed");
  assert.match(result.error, /not resubmitted/);
});

test("video: a download failure after a successful generation is never re-clicked", async () => {
  reset(() => ({ mediaId: "m1", fifeUrl: null }), { downloadFails: true });
  const { result } = await runOne("video");
  assert.equal(ctl.calls, 1, "a finished video was generated again because its download failed");
  assert.equal(result.status, "failed");
  assert.match(result.error, /not resubmitted/);
});

test("video: a failure BEFORE the paid click is still retried (safe, no credit spent)", async () => {
  reset((n) => {
    if (n === 1) throw missing(false);
    return { mediaId: "m1", fifeUrl: null };
  });
  const { result } = await runOne("video");
  assert.equal(ctl.calls, 2);
  assert.equal(result.status, "done");
});

test("image: existing retry behavior is unchanged (free, may re-click)", async () => {
  reset((n) => {
    if (n === 1) throw missing(true);
    return { mediaId: "i1", fifeUrl: null };
  });
  const { result } = await runOne("image");
  assert.equal(ctl.calls, 2, "image retry behavior must stay as before");
  assert.equal(result.status, "done");
});
