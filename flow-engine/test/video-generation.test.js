/**
 * Video generation — replaces the obsolete batchAsyncGenerateVideoText /
 * batchCheckAsyncVideoGenerationStatus REST path with the confirmed live
 * lifecycle: YhhmEf (start) -> jwpduf (poll, ~5-8s interval) -> as29s
 * (final detail, extracts the signed flow-content.google/video/... URL).
 * See flow-engine investigation notes for how this was established.
 *
 * No live network calls: fetch is mocked with canned responses reproducing
 * the exact captured batchexecute wire format from the one approved live
 * test generation (project 3fe16e7e-e725-4dc0-852b-80593cffdd9f, prompt
 * "a small red ball rolling slowly across a white studio floor", abra
 * tool, 360p, 4s).
 *
 * pollVideoStatus() sleeps the real timing.videoPollIntervalMs (8s,
 * unchanged/production value — deliberately not shortened just for tests,
 * see the task's "do not hammer the endpoint" instruction) before every
 * attempt, including the first. Tests that reach polling are consolidated
 * into as few real generateOneVideo()/pollVideoStatus() calls as possible
 * so the suite stays in the tens-of-seconds range rather than minutes;
 * anything checkable without invoking the real poll loop (extraction
 * helpers, status-marker meaning) is tested separately and fast.
 * Run: node --test test/video-generation.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const {
  generateOneVideo,
  pollVideoStatus,
  extractVideoStartResult,
  extractVideoPollStatus,
  extractAs29sVideoResult,
  RateLimitError,
  AuthExpiredError,
  EndpointRejectedError,
} = await import("../lib/flow-api.js");

const REAL_TOKEN = "A".repeat(42);
const PROJECT_ID = "3fe16e7e-e725-4dc0-852b-80593cffdd9f";
const WORKFLOW_ID = "5b04d221-f639-4495-9fc3-48828edad1dd";
const MEDIA_ID = "eef3f601-ea48-4502-9fef-71639a89e197";
const PROMPT = "a small red ball rolling slowly across a white studio floor";

function fakePage({ wiz = {}, fetchImpl = null } = {}) {
  const grecaptcha = { enterprise: { execute: async () => "CAPTCHA_TOKEN_XYZ" } };
  const location = { href: "https://flow.google.com/project/" + PROJECT_ID };
  const window = { WIZ_global_data: wiz, grecaptcha, location, fetch: fetchImpl };
  return {
    calls: 0,
    async waitForLoadState() {},
    async evaluate(fn, arg) {
      this.calls++;
      globalThis.window = window;
      globalThis.grecaptcha = grecaptcha;
      globalThis.location = location;
      globalThis.fetch = fetchImpl || (async () => { throw new Error("fetch not stubbed"); });
      try {
        return await fn(arg);
      } finally {
        delete globalThis.window;
        delete globalThis.grecaptcha;
        delete globalThis.location;
        delete globalThis.fetch;
      }
    },
  };
}

function fullWiz() {
  return { SNlM0e: REAL_TOKEN, cfb2h: "boq_labs-ai-sandbox-frontend_20260903.13_p0", FdrFJe: "5839573032030491108" };
}

function chunkOf(obj) {
  const json = JSON.stringify(obj);
  return `${Buffer.byteLength(json, "utf8")}\n${json}\n`;
}
function canned(...rpcResults) {
  let out = ")]}'\n\n";
  for (const [rpcid, resultValue] of rpcResults) {
    out += chunkOf([["wrb.fr", rpcid, JSON.stringify(resultValue), null, null, null, "generic"]]);
  }
  out += chunkOf([["e", 4, null, null, 143]]);
  return out;
}

// --- Real captured shapes (see flow-engine investigation notes) ---------

const YHHMEF_START_RESULT = [
  null, 48,
  [[MEDIA_ID, null, null,
    ["Red ball rolling on floor", [1788540716, 26271000], null, null, WORKFLOW_ID, "6A28A09B-C892-4F37-B1EF-5A807BB8B358", [1788540718, 44864000]],
    PROJECT_ID]],
  [[WORKFLOW_ID, PROJECT_ID, MEDIA_ID, "CAE", null,
    [[1788540716, 26271000], PROMPT, null, null, null, null,
      [null, [["abra_t2v_4s_360p", 1, null, null, 2, 4]], [[null, null, [[[PROMPT]]]]], null, 1],
      null, [2], 1],
  ]],
];

function jwpdufResult(status) {
  return [null, status === 3 ? 48 : null,
    [[WORKFLOW_ID, PROJECT_ID, MEDIA_ID, "CAE", null,
      [[1788540716, 26271000], PROMPT, null, null, null, null,
        [null, [["abra_t2v_4s_360p", 1, null, null, 2, 4]], [[null, null, [[[PROMPT]]]]], null, 1],
        null, [status], 1],
    ]],
  ];
}

const AS29S_RESULT = [
  WORKFLOW_ID, PROJECT_ID, MEDIA_ID, "CAE", null,
  [[1788540716, 26271000], PROMPT, null, null, null, null,
    [null, [["abra_t2v_4s_360p", 1, null, null, 2, 4]], [[null, null, [[[PROMPT]]]]], null, 1],
    null, [3], 1, null, null, null, 246798,
  ],
  null,
  [[null, 864328, null, null, null, null, null, PROMPT,
    "https://flow-content.google/video/" + WORKFLOW_ID + "?Expires=1788562341&KeyName=labs-flow-prod-cdn-key&Signature=PAW-Z-38sZUR9w7WksVnbsX6jio",
    null, null, null, "abra_t2v_4s_360p", "", null, false, 2],
   [null, null, [4]], [WORKFLOW_ID]],
];

// ---------------------------------------------------------------------------
// Extraction helpers — real captured shapes, no network/polling involved
// ---------------------------------------------------------------------------

test("extractVideoStartResult pulls workflowId and mediaId from YhhmEf's real shape", () => {
  const { workflowId, mediaId } = extractVideoStartResult(YHHMEF_START_RESULT);
  assert.equal(workflowId, WORKFLOW_ID);
  assert.equal(mediaId, MEDIA_ID);
});

test("extractVideoPollStatus reads the status marker at the confirmed position (2=pending, 3=complete)", () => {
  assert.equal(extractVideoPollStatus(jwpdufResult(2)).status, 2);
  assert.equal(extractVideoPollStatus(jwpdufResult(3)).status, 3);
});

test("extractVideoPollStatus returns ids alongside status", () => {
  const { status, workflowId, mediaId } = extractVideoPollStatus(jwpdufResult(2));
  assert.equal(status, 2);
  assert.equal(workflowId, WORKFLOW_ID);
  assert.equal(mediaId, MEDIA_ID);
});

test("extractAs29sVideoResult pulls the signed /video/ URL, never the /image/ poster", () => {
  const { mediaId, fifeUrl } = extractAs29sVideoResult(AS29S_RESULT);
  assert.equal(mediaId, MEDIA_ID);
  assert.ok(fifeUrl.startsWith("https://flow-content.google/video/"));
  assert.ok(!fifeUrl.includes("/image/"));
});

test("extraction helpers never throw on malformed/empty input", () => {
  for (const bad of [null, undefined, {}, [], [[]], "not an array"]) {
    assert.doesNotThrow(() => extractVideoStartResult(bad));
    assert.doesNotThrow(() => extractVideoPollStatus(bad));
    assert.doesNotThrow(() => extractAs29sVideoResult(bad));
  }
});

// ---------------------------------------------------------------------------
// generateOneVideo — one consolidated full-lifecycle invocation covering
// call sequence, endpoint/query params, payload shape, and final result.
// ---------------------------------------------------------------------------

function makeLifecycleFetch({ pollsUntilComplete = 2 } = {}) {
  const calls = [];
  let polls = 0;
  const fetchImpl = async (url, init) => {
    calls.push({ url, body: init.body });
    if (url.includes("rpcids=YhhmEf")) {
      return { ok: true, status: 200, text: async () => canned(["YhhmEf", YHHMEF_START_RESULT]) };
    }
    if (url.includes("rpcids=jwpduf")) {
      polls++;
      const status = polls >= pollsUntilComplete ? 3 : 2;
      return { ok: true, status: 200, text: async () => canned(["jwpduf", jwpdufResult(status)]) };
    }
    if (url.includes("rpcids=as29s")) {
      return { ok: true, status: 200, text: async () => canned(["as29s", AS29S_RESULT]) };
    }
    throw new Error("unexpected URL: " + url);
  };
  return { fetchImpl, calls };
}

test("generateOneVideo: full lifecycle — call sequence, request shape, and final {mediaId, fifeUrl}", async () => {
  const { fetchImpl, calls } = makeLifecycleFetch({ pollsUntilComplete: 2 });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  const result = await generateOneVideo(page, PROJECT_ID, PROMPT, {}, 0);

  // Final contract: same {mediaId, fifeUrl} shape batch-runner.js destructures.
  assert.equal(result.mediaId, MEDIA_ID);
  assert.ok(result.fifeUrl.startsWith("https://flow-content.google/video/"));
  assert.ok(!result.fifeUrl.includes("/image/"));

  // Call sequence: exactly one start, N polls until complete, one final detail fetch.
  const starts = calls.filter((c) => c.url.includes("rpcids=YhhmEf"));
  const polls = calls.filter((c) => c.url.includes("rpcids=jwpduf"));
  const finals = calls.filter((c) => c.url.includes("rpcids=as29s"));
  assert.equal(starts.length, 1);
  assert.equal(polls.length, 2);
  assert.equal(finals.length, 1);

  // YhhmEf: endpoint, query params, at= token, payload shape.
  const start = starts[0];
  assert.equal(start.url.startsWith("https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?"), true);
  assert.match(start.url, /rpcids=YhhmEf/);
  assert.match(start.url, /source-path=%2Fproject%2F3fe16e7e-e725-4dc0-852b-80593cffdd9f/);
  assert.match(start.url, /bl=boq_labs-ai-sandbox-frontend_20260903\.13_p0/);
  assert.match(start.url, /f\.sid=5839573032030491108/);
  assert.match(start.url, /rt=c/);
  const atMatch = start.body.match(/&at=([^&]+)/);
  assert.equal(decodeURIComponent(atMatch[1]), REAL_TOKEN);

  const startArgs = JSON.parse(JSON.parse(decodeURIComponent(start.body.match(/^f\.req=([^&]+)/)[1]))[0][0][1]);
  const request = startArgs[0][0]; // [[request], context, [uuidC, 2]]
  assert.deepEqual(request[0], [null, null, [[[PROMPT]]]]);
  // No settings.videoModel given -> resolveVideoModelKey()'s own default
  // (config.js's videoModels.default = "veo_3_1_t2v_fast") applies, which
  // maps to tool id "veo_3_1_fast" — "abra" is only the fallback for a
  // model key this file doesn't recognize.
  assert.match(request[1], /^(abra|veo_3_1_fast|veo_3_1_quality|veo_3_1_lite)_t2v_4s_(360p|720p)$/);
  assert.deepEqual(startArgs[1].slice(0, 6), [null, 22, null, null, null, PROJECT_ID]);

  // jwpduf: only the workflowId, no captcha/context.
  const pollArgs = JSON.parse(JSON.parse(decodeURIComponent(polls[0].body.match(/^f\.req=([^&]+)/)[1]))[0][0][1]);
  assert.deepEqual(pollArgs, [null, null, [[WORKFLOW_ID]]]);
  assert.match(polls[0].url, /rpcids=jwpduf/);

  // as29s: only the workflowId.
  const finalArgs = JSON.parse(JSON.parse(decodeURIComponent(finals[0].body.match(/^f\.req=([^&]+)/)[1]))[0][0][1]);
  assert.deepEqual(finalArgs, [WORKFLOW_ID]);
  assert.match(finals[0].url, /rpcids=as29s/);
});

test("generateOneVideo: fixed 4s duration regardless of settings.videoDuration, and a recognized videoModel maps to its real tool id", async () => {
  const { fetchImpl, calls } = makeLifecycleFetch({ pollsUntilComplete: 1 });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await generateOneVideo(page, PROJECT_ID, PROMPT, { videoDuration: 10, videoModel: "veo_3_1_t2v_lite" }, 0);
  const start = calls.find((c) => c.url.includes("rpcids=YhhmEf"));
  const args = JSON.parse(JSON.parse(decodeURIComponent(start.body.match(/^f\.req=([^&]+)/)[1]))[0][0][1]);
  // "4s" (never "10s") and "veo_3_1_lite" (not the raw settings key) —
  // resolveVideoModelKey() already normalizes any *unrecognized* key to
  // config.js's own default before this file's tool-id table ever sees it,
  // so "abra" (the table's fallback) is unreachable through settings.videoModel
  // in practice — this exercises the one path that's actually reachable.
  assert.equal(args[0][0][1], "veo_3_1_lite_t2v_4s_720p");
});

test("missing WIZ session state fails without a network call", async () => {
  const fetchImpl = async () => { throw new Error("must not be called"); };
  const page = fakePage({ wiz: {}, fetchImpl });
  await assert.rejects(() => generateOneVideo(page, PROJECT_ID, PROMPT, {}, 0));
});

// ---------------------------------------------------------------------------
// pollVideoStatus in isolation (one real poll — resolves on the first check)
// ---------------------------------------------------------------------------

test("pollVideoStatus resolves with workflowId/mediaId once status is 3", async () => {
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => canned(["jwpduf", jwpdufResult(3)]) });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  const result = await pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID);
  assert.equal(result.workflowId, WORKFLOW_ID);
  assert.equal(result.mediaId, MEDIA_ID);
});

// ---------------------------------------------------------------------------
// Failure handling (all fail before/at the YhhmEf step — no polling, fast)
// ---------------------------------------------------------------------------

test("HTTP 429 on YhhmEf raises RateLimitError", async () => {
  const fetchImpl = async () => ({ ok: false, status: 429, text: async () => "rate limited" });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(() => generateOneVideo(page, PROJECT_ID, PROMPT, {}, 0), RateLimitError);
});

test("HTTP 401 on YhhmEf while still signed in raises EndpointRejectedError", async () => {
  const fetchImpl = async () => ({ ok: false, status: 401, text: async () => "unauthenticated" });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(() => generateOneVideo(page, PROJECT_ID, PROMPT, {}, 0), EndpointRejectedError);
});

test("HTTP 401 on YhhmEf while genuinely signed out raises AuthExpiredError", async () => {
  const fetchImpl = async () => ({ ok: false, status: 401, text: async () => "unauthenticated" });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  const originalEvaluate = page.evaluate.bind(page);
  let first = true;
  page.evaluate = async (fn, arg) => {
    if (!first) {
      const grecaptcha = { enterprise: { execute: async () => "x" } };
      const location = { href: "https://flow.google.com/" };
      globalThis.window = { WIZ_global_data: {}, grecaptcha, location };
      globalThis.grecaptcha = grecaptcha;
      globalThis.location = location;
      try {
        return await fn(arg);
      } finally {
        delete globalThis.window;
        delete globalThis.grecaptcha;
        delete globalThis.location;
      }
    }
    first = false;
    return originalEvaluate(fn, arg);
  };
  await assert.rejects(() => generateOneVideo(page, PROJECT_ID, PROMPT, {}, 0), AuthExpiredError);
});

test("malformed YhhmEf response fails generation before any polling, not a crash", async () => {
  const fetchImpl = async (url) => {
    if (url.includes("rpcids=YhhmEf")) {
      return { ok: true, status: 200, text: async () => canned(["someOtherRpc", [1]]) };
    }
    throw new Error("must not reach polling");
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(
    () => generateOneVideo(page, PROJECT_ID, PROMPT, {}, 0),
    /Video generation did not start/,
  );
});

test("as29s failure after successful completion surfaces a clear error, not a silent loss", async () => {
  const fetchImpl = async (url) => {
    if (url.includes("rpcids=YhhmEf")) {
      return { ok: true, status: 200, text: async () => canned(["YhhmEf", YHHMEF_START_RESULT]) };
    }
    if (url.includes("rpcids=jwpduf")) {
      return { ok: true, status: 200, text: async () => canned(["jwpduf", jwpdufResult(3)]) };
    }
    if (url.includes("rpcids=as29s")) {
      return { ok: false, status: 500, text: async () => "server error" };
    }
    throw new Error("unexpected URL: " + url);
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(
    () => generateOneVideo(page, PROJECT_ID, PROMPT, {}, 0),
    /final detail fetch \(as29s\) failed/,
  );
});
