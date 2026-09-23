/**
 * _reqid and hl protocol-fidelity tests.
 *
 * Confirmed live from the CURRENT production AiSandboxAngularFrontend
 * bundle (see project notes — fetched and read directly, read-only, no
 * account/generation/reCAPTCHA involved): the real frontend computes
 *   _reqid = 1 + hq + Kb*100000
 * where hq is seconds-since-local-midnight computed once per page session
 * and Kb is a counter incremented once per request object, SHARED across
 * every RPC type that page makes — not a fresh random draw per call, and
 * not a process-wide global. hl is read from the page's own current URL
 * (`?hl=...`), falling back to "en-US", not a fixed hardcoded locale.
 *
 * nextReqId()/currentHl() in flow-api.js replicate both at the narrowest
 * scope this codebase actually has a "page session": the Playwright `page`
 * object itself, which already persists across every RPC call for one Flow
 * browser session.
 *
 * Run: node --test test/reqid-hl.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const { generateOneImage, generateOneVideo, nextReqId, currentHl } = await import("../lib/flow-api.js");

const REAL_TOKEN = "A".repeat(42);
const PROJECT_ID = "3fe16e7e-e725-4dc0-852b-80593cffdd9f";
const WORKFLOW_ID = "5b04d221-f639-4495-9fc3-48828edad1dd";
const MEDIA_ID = "eef3f601-ea48-4502-9fef-71639a89e197";
const PROMPT = "a small red ball rolling slowly across a white studio floor";

function fakePage({ wiz = {}, fetchImpl = null, url } = {}) {
  const grecaptcha = { enterprise: { execute: async () => "CAPTCHA_TOKEN_XYZ" } };
  let currentUrl = url || "https://flow.google.com/project/" + PROJECT_ID;
  const location = { href: currentUrl };
  const window = { WIZ_global_data: wiz, grecaptcha, location, fetch: fetchImpl };
  return {
    url: () => currentUrl,
    setUrl(u) {
      currentUrl = u;
      location.href = u;
    },
    async waitForLoadState() {},
    async evaluate(fn, arg) {
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
  return { SNlM0e: REAL_TOKEN, cfb2h: "boq_labs-ai-sandbox-frontend_20260922.00_p0", FdrFJe: "5839573032030491108" };
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

const REAL_IMAGE_RESULT = [
  [[
    "e7205d39-9526-468f-bf3f-01ef99d476d0", null, "3677f65e-ffe3-4a38-92b8-de54727e2fb7", null, null, null,
    [[null, 1757688819, null, null, null, null, 1, "a single red apple", 25, null, null,
      "3677f65e-ffe3-4a38-92b8-de54727e2fb7", null,
      "https://flow-content.google/image/e7205d39-9526-468f-bf3f-01ef99d476d0?Expires=1&Signature=x",
      3, [null, null, [["a single red apple", null, [[["a single red apple"]]]]], []], null,
      "e7205d39-9526-468f-bf3f-01ef99d476d0"],
    ], null, [1376, 768],
  ]],
  [["3677f65e-ffe3-4a38-92b8-de54727e2fb7", null, null,
    ["Red apple", [1788536134, 770111000], null, null, "e7205d39-9526-468f-bf3f-01ef99d476d0", "id", [1788536151, 610572000]],
    PROJECT_ID]],
];

const YHHMEF_START_RESULT = [
  null, 48,
  [[MEDIA_ID, null, null,
    ["Red ball rolling on floor", [1788540716, 26271000], null, null, WORKFLOW_ID, "id", [1788540718, 44864000]],
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
    null, [3], 1, null, null, null, 246798],
  null,
  [[null, 864328, null, null, null, null, null, PROMPT,
    "https://flow-content.google/video/" + WORKFLOW_ID + "?Expires=1&Signature=x",
    null, null, null, "abra_t2v_4s_360p", "", null, false, 2],
   [null, null, [4]], [WORKFLOW_ID]],
];

function makeVideoLifecycleFetch({ pollsUntilComplete = 1 } = {}) {
  const calls = [];
  let polls = 0;
  const fetchImpl = async (url, init) => {
    calls.push({ url, body: init.body });
    if (url.includes("rpcids=YhhmEf")) return { ok: true, status: 200, text: async () => canned(["YhhmEf", YHHMEF_START_RESULT]) };
    if (url.includes("rpcids=jwpduf")) {
      polls++;
      const status = polls >= pollsUntilComplete ? 3 : 2;
      return { ok: true, status: 200, text: async () => canned(["jwpduf", jwpdufResult(status)]) };
    }
    if (url.includes("rpcids=as29s")) return { ok: true, status: 200, text: async () => canned(["as29s", AS29S_RESULT]) };
    throw new Error("unexpected URL: " + url);
  };
  return { fetchImpl, calls };
}

function reqIdFromUrl(url) {
  const m = url.match(/[?&]_reqid=(\d+)/);
  return m ? Number(m[1]) : null;
}
function hlFromUrl(url) {
  const m = url.match(/[?&]hl=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

// ---------------------------------------------------------------------------
// nextReqId() — direct unit tests
// ---------------------------------------------------------------------------

test("nextReqId: consecutive calls on the same page differ by exactly 100000", () => {
  const page = fakePage({});
  const a = nextReqId(page);
  const b = nextReqId(page);
  const c = nextReqId(page);
  assert.equal(b - a, 100000);
  assert.equal(c - b, 100000);
});

test("nextReqId: the same page reuses the same hq base across calls", () => {
  const page = fakePage({});
  const a = nextReqId(page);
  const b = nextReqId(page);
  // a = 1+hq+0*100000, b = 1+hq+1*100000 -> both share the same value mod 100000.
  assert.equal(a % 100000, b % 100000);
});

test("nextReqId: a new page/session gets its own independent counter, not a continuation of another page's", () => {
  const pageA = fakePage({});
  const firstA = nextReqId(pageA);
  const secondA = nextReqId(pageA); // pageA's Kb=1 -> firstA+100000

  const pageB = fakePage({});
  const firstB = nextReqId(pageB); // pageB's own Kb=0, independent hq

  // If the counter were global/shared across pages, firstB would equal
  // secondA (continuing pageA's sequence at Kb=2->3). It must not.
  assert.notEqual(firstB, secondA);
  // pageB's first call should be close to pageA's first call (both Kb=0,
  // same second in practice), not offset by pageA's own progress.
  assert.ok(Math.abs(firstB - firstA) <= 1, `expected pageB's fresh Kb=0 value near pageA's, got firstA=${firstA} firstB=${firstB}`);
});

test("nextReqId: the counter is shared across RPC types on the same page (image then video)", async () => {
  const { fetchImpl: videoFetch, calls: videoCalls } = makeVideoLifecycleFetch({ pollsUntilComplete: 1 });
  const imageCalls = [];
  const fetchImpl = async (url, init) => {
    if (url.includes("rpcids=ogiZ0b")) {
      imageCalls.push({ url });
      return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_IMAGE_RESULT]) };
    }
    return videoFetch(url, init);
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });

  await generateOneImage(page, PROJECT_ID, "a single red apple", {}, 0);
  await generateOneVideo(page, PROJECT_ID, PROMPT, {}, 0);

  const imageReqId = reqIdFromUrl(imageCalls[0].url);
  const yhhmEfCall = videoCalls.find((c) => c.url.includes("rpcids=YhhmEf"));
  const videoReqId = reqIdFromUrl(yhhmEfCall.url);

  assert.equal(videoReqId - imageReqId, 100000, "the video call's _reqid must continue the SAME page's counter, not restart");
});

// ---------------------------------------------------------------------------
// currentHl() — direct unit tests
// ---------------------------------------------------------------------------

test("currentHl: reads hl from the page's current URL when present", () => {
  const page = fakePage({ url: "https://flow.google.com/project/" + PROJECT_ID + "?hl=fr-FR" });
  assert.equal(currentHl(page), "fr-FR");
});

test("currentHl: falls back to en-US when the URL has no hl param", () => {
  const page = fakePage({ url: "https://flow.google.com/project/" + PROJECT_ID });
  assert.equal(currentHl(page), "en-US");
});

test("currentHl: never throws on a malformed page URL, falls back to en-US", () => {
  const page = { url: () => "not a valid url at all" };
  assert.doesNotThrow(() => currentHl(page));
  assert.equal(currentHl(page), "en-US");
});

// ---------------------------------------------------------------------------
// End-to-end: the actual request URL generateOneImage/generateOneVideo send
// ---------------------------------------------------------------------------

test("generateOneImage sends hl=en-GB when the page URL carries hl=en-GB", async () => {
  let captured = null;
  const fetchImpl = async (url) => {
    captured = url;
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_IMAGE_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl, url: "https://flow.google.com/project/" + PROJECT_ID + "?hl=en-GB" });
  await generateOneImage(page, PROJECT_ID, "a single red apple", {}, 0);
  assert.equal(hlFromUrl(captured), "en-GB");
});

test("generateOneImage sends hl=en-US (the frontend's own default) when the page URL has no hl param", async () => {
  let captured = null;
  const fetchImpl = async (url) => {
    captured = url;
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_IMAGE_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl, url: "https://flow.google.com/project/" + PROJECT_ID });
  await generateOneImage(page, PROJECT_ID, "a single red apple", {}, 0);
  assert.equal(hlFromUrl(captured), "en-US");
});

test("generateOneImage's _reqid is a deterministic counter value, not a random 6-digit draw", async () => {
  let captured = null;
  const fetchImpl = async (url) => {
    captured = url;
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_IMAGE_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  // generateOneImage now calls getFlowProject (AiSandbox.GetProject) once
  // before ogiZ0b itself — same shared per-page counter, so it consumes one
  // Kb step first. Independent page, same instant -> same hq; two calls to
  // reach Kb=1 for the second (ogiZ0b's own) request.
  const refPage = fakePage({});
  nextReqId(refPage);
  const expected = nextReqId(refPage);
  await generateOneImage(page, PROJECT_ID, "a single red apple", {}, 0);
  const actual = reqIdFromUrl(captured);
  assert.ok(Math.abs(actual - expected) <= 1, `expected reqid near ${expected}, got ${actual}`);
});
