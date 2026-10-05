/**
 * Every failed generation call says whether the request may have created something (generation-state.js), so the caller can
 * never resubmit an ambiguous request. Fakes only: no network, no browser, no credits.
 * Run: node --test test/submission-classification.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const api = await import("../lib/flow-api.js");
const { generateOneImage, generateOneVideo, resumeVideo, timing, RateLimitError } = api;
const { Submission, AccountRestrictedError } = await import("../lib/generation-state.js");

const PROJECT_ID = "3fe16e7e-e725-4dc0-852b-80593cffdd9f";
const WORKFLOW_ID = "5b04d221-f639-4495-9fc3-48828edad1dd";
const MEDIA_ID = "eef3f601-ea48-4502-9fef-71639a89e197";
const WIZ = { SNlM0e: "A".repeat(42), cfb2h: "boq_x_20260903.13_p0", FdrFJe: "5839573032030491108" };

timing.videoPollIntervalMs = 1;
timing.videoPollTimeoutMs = 40;

function fakePage({ fetchImpl, evaluateHook = null }) {
  const grecaptcha = { enterprise: { execute: async () => "CAPTCHA_TOKEN_XYZ", ready: (f) => f() } };
  const location = { href: "https://flow.google.com/project/" + PROJECT_ID };
  const window = { WIZ_global_data: WIZ, grecaptcha, location };
  return {
    sends: 0,
    async waitForLoadState() {},
    url: () => location.href,
    async evaluate(fn, arg) {
      if (arg && typeof arg === "object" && "captcha" in arg) this.sends++;
      if (evaluateHook) await evaluateHook(arg, this);
      globalThis.window = window;
      globalThis.grecaptcha = grecaptcha;
      globalThis.location = location;
      globalThis.fetch = fetchImpl;
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

function chunkOf(obj) {
  const json = JSON.stringify(obj);
  return `${Buffer.byteLength(json, "utf8")}\n${json}\n`;
}
function canned(rpcid, value) {
  return ")]}'\n\n" + chunkOf([["wrb.fr", rpcid, JSON.stringify(value), null, null, null, "generic"]]) + chunkOf([["e", 4, null, null, 143]]);
}
function errorInfo(rpcid, reason) {
  const detail = [3, null, [["type.googleapis.com/google.rpc.ErrorInfo", [reason, "aisandbox"]]]];
  return ")]}'\n\n" + chunkOf([["wrb.fr", rpcid, null, null, null, detail, "generic"]]) + chunkOf([["e", 4, null, null, 143]]);
}
const ok = (text) => ({ ok: true, status: 200, text: async () => text });
const http = (status) => ({ ok: false, status, text: async () => "error" });
const otherRpc = (url) => !/rpcids=(ogiZ0b|YhhmEf|jwpduf|as29s)/.test(url);

const START = [null, 48, [[MEDIA_ID, null, null, ["x"], PROJECT_ID]],
  [[WORKFLOW_ID, PROJECT_ID, MEDIA_ID, "CAE", null, [[1, 2], "p", null, null, null, null, null, null, [2], 1]]]];

async function failureOf(p) {
  try {
    await p;
  } catch (err) {
    return err;
  }
  assert.fail("expected the call to fail");
}

// ---- image ---------------------------------------------------------------------------------------------------------------

test("image: a timeout after sending is UNKNOWN, never 'not submitted'", async () => {
  const page = fakePage({ fetchImpl: async (url) => {
    if (otherRpc(url)) return ok(canned("x", []));
    const e = new Error("aborted");
    e.name = "AbortError";
    throw e;
  } });
  const err = await failureOf(generateOneImage(page, PROJECT_ID, "a red apple", {}, 0));
  assert.equal(err.submission, Submission.UNKNOWN);
});

test("image: HTTP 5xx is UNKNOWN, HTTP 429 is REJECTED", async () => {
  for (const [status, want] of [[500, Submission.UNKNOWN], [503, Submission.UNKNOWN], [429, Submission.REJECTED]]) {
    const page = fakePage({ fetchImpl: async (url) => (otherRpc(url) ? ok(canned("x", [])) : http(status)) });
    const err = await failureOf(generateOneImage(page, PROJECT_ID, "a red apple", {}, 0));
    assert.equal(err.submission, want, `HTTP ${status}`);
    if (status === 429) assert.ok(err instanceof RateLimitError);
  }
});

test("image: a 200 with nothing readable is UNKNOWN; a 200 with an ErrorInfo reason is REJECTED", async () => {
  let page = fakePage({ fetchImpl: async (url) => (otherRpc(url) ? ok(canned("x", [])) : ok(canned("ogiZ0b", [null]))) });
  assert.equal((await failureOf(generateOneImage(page, PROJECT_ID, "p", {}, 0))).submission, Submission.UNKNOWN);
  page = fakePage({ fetchImpl: async (url) => (otherRpc(url) ? ok(canned("x", [])) : ok(errorInfo("ogiZ0b", "PUBLIC_ERROR_SOMETHING"))) });
  assert.equal((await failureOf(generateOneImage(page, PROJECT_ID, "p", {}, 0))).submission, Submission.REJECTED);
});

test("image: the page navigating during the send is UNKNOWN and the request is NOT sent again", async () => {
  const page = fakePage({
    fetchImpl: async () => ok(canned("x", [])),
    evaluateHook: async (arg) => {
      if (arg && "captcha" in arg) throw new Error("Execution context was destroyed, most likely because of a navigation");
    },
  });
  const err = await failureOf(generateOneImage(page, PROJECT_ID, "p", {}, 0));
  assert.equal(page.sends, 1, "the generation request must be attempted exactly once");
  assert.equal(err.submission, Submission.UNKNOWN);
});

test("an anti-abuse answer is an account restriction (a stop condition), not a retryable failure", async () => {
  const page = fakePage({ fetchImpl: async (url) => (otherRpc(url) ? ok(canned("x", [])) : ok(errorInfo("ogiZ0b", "PUBLIC_ERROR_UNUSUAL_ACTIVITY"))) });
  const err = await failureOf(generateOneImage(page, PROJECT_ID, "p", {}, 0));
  assert.ok(err instanceof AccountRestrictedError);
  assert.equal(err.submission, Submission.REJECTED);
});

// ---- video ---------------------------------------------------------------------------------------------------------------

test("video: an unreadable YhhmEf answer is UNKNOWN (the shape change that once caused a duplicate)", async () => {
  const page = fakePage({ fetchImpl: async (url) => (otherRpc(url) ? ok(canned("x", [])) : ok(canned("YhhmEf", [null, 48, [], []]))) });
  const err = await failureOf(generateOneVideo(page, PROJECT_ID, "p", { videoModel: "abra" }, 0));
  assert.equal(err.submission, Submission.UNKNOWN);
});

test("video: once accepted, a polling failure is ACCEPTED with the workflow id, reported before polling began", async () => {
  let accepted = null;
  const page = fakePage({ fetchImpl: async (url) => {
    if (url.includes("rpcids=YhhmEf")) return ok(canned("YhhmEf", START));
    if (url.includes("rpcids=jwpduf")) return http(500);
    return ok(canned("x", []));
  } });
  const err = await failureOf(generateOneVideo(page, PROJECT_ID, "p", { videoModel: "abra" }, 0, { onAccepted: (w) => { accepted = w; } }));
  assert.equal(accepted, WORKFLOW_ID);
  assert.equal(err.submission, Submission.ACCEPTED);
  assert.equal(err.workflowId, WORKFLOW_ID);
  assert.equal(page.sends, 1);
});

test("video: a 429 while polling an accepted job is still ACCEPTED (it must never be handed to another account)", async () => {
  const page = fakePage({ fetchImpl: async (url) => {
    if (url.includes("rpcids=YhhmEf")) return ok(canned("YhhmEf", START));
    if (url.includes("rpcids=jwpduf")) return http(429);
    return ok(canned("x", []));
  } });
  const err = await failureOf(generateOneVideo(page, PROJECT_ID, "p", { videoModel: "abra" }, 0));
  assert.equal(err.submission, Submission.ACCEPTED);
  assert.equal(err.workflowId, WORKFLOW_ID);
});

test("resumeVideo never sends a generation request and tags failures ACCEPTED", async () => {
  const page = fakePage({ fetchImpl: async (url) => (url.includes("rpcids=jwpduf") ? http(500) : ok(canned("x", []))) });
  page.locator = () => ({});
  const err = await failureOf(resumeVideo(page, WORKFLOW_ID, PROJECT_ID, {}));
  assert.equal(page.sends, 0);
  assert.equal(err.submission, Submission.ACCEPTED);
  assert.equal(err.workflowId, WORKFLOW_ID);
});
