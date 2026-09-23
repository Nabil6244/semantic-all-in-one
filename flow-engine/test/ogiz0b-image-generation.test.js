/**
 * ogiZ0b image generation — replaces the obsolete /fx/api/trpc + aisandbox
 * REST path (api.batchGenerateImages) with the confirmed live batchexecute
 * call. See flow-engine investigation notes for how the request shape,
 * `at=`/`bl`/`f.sid` sources, and the seed field (protobuf field #4,
 * args[1][0][3]) were established.
 *
 * No live network calls: fetch is mocked with canned responses reproducing
 * the exact captured batchexecute wire format.
 * Run: node --test test/ogiz0b-image-generation.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const {
  generateOneImage,
  parseBatchExecuteResponse,
  extractOgiZ0bImageResult,
  extractRpcErrorInfoReason,
  RateLimitError,
  AuthExpiredError,
  EndpointRejectedError,
} = await import("../lib/flow-api.js");

const REAL_TOKEN = "A".repeat(42);
const PROJECT_ID = "3fe16e7e-e725-4dc0-852b-80593cffdd9f";

/**
 * Minimal page stub matching what safeEvaluate()/waitForFlowReady() need.
 * A real Playwright page.evaluate() runs the function in a browser, where
 * bare `location`/`grecaptcha` resolve through the global `window` object
 * automatically (waitForFlowReady's own probe reads bare `grecaptcha`/
 * `location`, not `window.grecaptcha`/`window.location`) — Node has no such
 * implicit link, so both the `window.*` properties AND the matching bare
 * globals are set here for every evaluate() call.
 */
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
  return { SNlM0e: REAL_TOKEN, cfb2h: "boq_labs-ai-sandbox-frontend_20260903.13_p0", FdrFJe: "5154174394542838292" };
}

/**
 * Builds a canned )]}'-prefixed, length-chunked batchexecute body, matching
 * the real observed shape: one "wrb.fr" data chunk per rpcid, followed by a
 * trailing small ["e",4,null,null,n] event chunk that every real captured
 * response also carried.
 */
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

const REAL_RESULT = [
  [[
    "e7205d39-9526-468f-bf3f-01ef99d476d0", null, "3677f65e-ffe3-4a38-92b8-de54727e2fb7", null, null, null,
    [[null, 1757688819, null, null, null, null, 1,
      "a single red apple on a white background, studio lighting", 25, null, null,
      "3677f65e-ffe3-4a38-92b8-de54727e2fb7", null,
      "https://flow-content.google/image/e7205d39-9526-468f-bf3f-01ef99d476d0?Expires=1788557733&KeyName=labs-flow-prod-cdn-key&Signature=AKgys5ntvOUk45ZTXjJZSSVH6Mw",
      3, [null, null, [["a single red apple", null, [[["a single red apple"]]]]], []], null,
      "e7205d39-9526-468f-bf3f-01ef99d476d0"],
    ], null, [1376, 768],
  ]],
  [["3677f65e-ffe3-4a38-92b8-de54727e2fb7", null, null,
    ["Red apple on white background", [1788536134, 770111000], null, null,
      "e7205d39-9526-468f-bf3f-01ef99d476d0", "711F504B-E46D-45BC-A45F-9FDA422DF454", [1788536151, 610572000]],
    PROJECT_ID]],
];

// ---------------------------------------------------------------------------
// 1-6. Request construction, seed insertion, endpoint/query params, at= token
// ---------------------------------------------------------------------------

test("request is sent to the confirmed batchexecute endpoint with the expected query params", async () => {
  let captured = null;
  const fetchImpl = async (url, init) => {
    captured = { url, init };
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await generateOneImage(page, PROJECT_ID, "a single red apple", { model: "GEM_PIX_2" }, 0);

  assert.equal(captured.url.startsWith("https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?"), true);
  assert.match(captured.url, /rpcids=ogiZ0b/);
  assert.match(captured.url, /source-path=%2Fproject%2F3fe16e7e-e725-4dc0-852b-80593cffdd9f/);
  assert.match(captured.url, /bl=boq_labs-ai-sandbox-frontend_20260903\.13_p0/);
  assert.match(captured.url, /f\.sid=5154174394542838292/);
  // hl is read from the page's own current URL now (confirmed live from the
  // real Flow frontend bundle — see project notes), falling back to the
  // frontend's own default "en-US" when the URL carries no ?hl= param, as
  // this fakePage's URL does not. No longer the old hardcoded "en-GB".
  assert.match(captured.url, /hl=en-US/);
  assert.match(captured.url, /_reqid=\d+/);
  assert.match(captured.url, /rt=c/);
});

test("at= is exactly window.WIZ_global_data.SNlM0e, url-encoded in the body", async () => {
  let captured = null;
  const fetchImpl = async (url, init) => {
    captured = init;
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await generateOneImage(page, PROJECT_ID, "prompt", {}, 0);

  const atMatch = captured.body.match(/&at=([^&]+)/);
  assert.equal(decodeURIComponent(atMatch[1]), REAL_TOKEN);
});

test("f.req envelope matches the confirmed generic wrapper shape", async () => {
  let captured = null;
  const fetchImpl = async (url, init) => {
    captured = init;
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await generateOneImage(page, PROJECT_ID, "a prompt", { model: "GEM_PIX_2" }, 0);

  const freqMatch = captured.body.match(/^f\.req=([^&]+)/);
  const envelope = JSON.parse(decodeURIComponent(freqMatch[1]));
  assert.equal(envelope[0][0][0], "ogiZ0b");
  assert.equal(envelope[0][0][2], null);
  assert.equal(envelope[0][0][3], "generic");

  const args = JSON.parse(envelope[0][0][1]);
  assert.equal(args[0], null);
  assert.equal(args[2], 1); // count
  assert.deepEqual(args[3].slice(0, 6), [null, 22, null, null, null, PROJECT_ID]); // batch-level context
});

test("seed lands at the confirmed position args[1][0][3] (protobuf field #4)", async () => {
  let captured = null;
  const fetchImpl = async (url, init) => {
    captured = init;
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await generateOneImage(page, PROJECT_ID, "prompt", { seedMode: "fixed", seedValue: 42424242 }, 0);

  const freq = decodeURIComponent(captured.body.match(/^f\.req=([^&]+)/)[1]);
  const args = JSON.parse(JSON.parse(freq)[0][0][1]);
  assert.equal(args[1][0][3], 42424242);
});

test("fixed seed mode uses the configured seed exactly", async () => {
  let seenSeed = null;
  const fetchImpl = async (url, init) => {
    const args = JSON.parse(JSON.parse(decodeURIComponent(init.body.match(/^f\.req=([^&]+)/)[1]))[0][0][1]);
    seenSeed = args[1][0][3];
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await generateOneImage(page, PROJECT_ID, "prompt", { seedMode: "fixed", seedValue: 777 }, 0);
  assert.equal(seenSeed, 777);
});

test("non-fixed seed mode generates a fresh, positive, 32-bit-safe integer each call", async () => {
  const seeds = [];
  const fetchImpl = async (url, init) => {
    const args = JSON.parse(JSON.parse(decodeURIComponent(init.body.match(/^f\.req=([^&]+)/)[1]))[0][0][1]);
    seeds.push(args[1][0][3]);
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) };
  };
  for (let i = 0; i < 5; i++) {
    const page = fakePage({ wiz: fullWiz(), fetchImpl });
    await generateOneImage(page, PROJECT_ID, "prompt", {}, i);
  }
  for (const s of seeds) {
    assert.equal(Number.isInteger(s), true);
    assert.ok(s >= 0 && s <= 0x7fffffff, `seed ${s} out of expected range`);
  }
  assert.ok(new Set(seeds).size > 1, "seeds should differ across calls");
});

test("model name is threaded through to the request position", async () => {
  let captured = null;
  const fetchImpl = async (url, init) => {
    captured = init;
    return { ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) };
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await generateOneImage(page, PROJECT_ID, "prompt", { model: "GEM_PIX_2" }, 0);
  const args = JSON.parse(JSON.parse(decodeURIComponent(captured.body.match(/^f\.req=([^&]+)/)[1]))[0][0][1]);
  assert.equal(args[1][0][5], "GEM_PIX_2");
  assert.deepEqual(args[1][0][8], [[["prompt"]]]);
});

test("missing WIZ session state fails without a network call", async () => {
  const fetchImpl = async () => {
    throw new Error("must not be called");
  };
  const page = fakePage({ wiz: {}, fetchImpl });
  await assert.rejects(() => generateOneImage(page, PROJECT_ID, "prompt", {}, 0));
});

// ---------------------------------------------------------------------------
// 7-8. batchexecute response parsing + extraction
// ---------------------------------------------------------------------------

test("parseBatchExecuteResponse strips )]}' and decodes the length-prefixed chunk", () => {
  const text = canned(["ogiZ0b", REAL_RESULT]);
  const parsed = parseBatchExecuteResponse(text, "ogiZ0b");
  assert.deepEqual(parsed, REAL_RESULT);
});

test("parseBatchExecuteResponse finds the right rpcid among multiple chunks", () => {
  const text = canned(["otherRpc", [1, 2, 3]], ["ogiZ0b", REAL_RESULT]);
  const parsed = parseBatchExecuteResponse(text, "ogiZ0b");
  assert.deepEqual(parsed, REAL_RESULT);
});

test("parseBatchExecuteResponse returns null for an rpcid that never arrives", () => {
  const text = canned(["otherRpc", [1, 2, 3]]);
  assert.equal(parseBatchExecuteResponse(text, "ogiZ0b"), null);
});

test("parseBatchExecuteResponse handles malformed/truncated input without throwing", () => {
  for (const bad of ["", "not the right prefix at all", ")]}'\nnotanumber\n{}", ")]}'\n5\n{broken", "))]}'"]) {
    assert.doesNotThrow(() => parseBatchExecuteResponse(bad, "ogiZ0b"));
    assert.equal(parseBatchExecuteResponse(bad, "ogiZ0b"), null);
  }
});

test("extractOgiZ0bImageResult pulls mediaId, CDN URL, and dimensions from the real captured shape", () => {
  const { mediaId, fifeUrl, width, height } = extractOgiZ0bImageResult(REAL_RESULT);
  assert.equal(mediaId, "e7205d39-9526-468f-bf3f-01ef99d476d0");
  assert.equal(fifeUrl, "https://flow-content.google/image/e7205d39-9526-468f-bf3f-01ef99d476d0?Expires=1788557733&KeyName=labs-flow-prod-cdn-key&Signature=AKgys5ntvOUk45ZTXjJZSSVH6Mw");
  assert.equal(width, 1376);
  assert.equal(height, 768);
});

test("extractOgiZ0bImageResult never returns the obsolete labs.google host", () => {
  const { fifeUrl } = extractOgiZ0bImageResult(REAL_RESULT);
  assert.ok(!fifeUrl.includes("labs.google"));
  assert.ok(fifeUrl.startsWith("https://flow-content.google/"));
});

test("extractOgiZ0bImageResult falls back to a deep scan when the shape drifts", () => {
  const drifted = { unexpected: { nesting: ["https://flow-content.google/image/abc123?Expires=1&Signature=x"] } };
  const { fifeUrl, mediaId } = extractOgiZ0bImageResult(drifted);
  assert.equal(fifeUrl, "https://flow-content.google/image/abc123?Expires=1&Signature=x");
  assert.equal(mediaId, "abc123");
});

test("extractOgiZ0bImageResult on empty/malformed input returns all-null, never throws", () => {
  for (const bad of [null, undefined, {}, [], [[]], [[[]]]]) {
    assert.doesNotThrow(() => extractOgiZ0bImageResult(bad));
    const r = extractOgiZ0bImageResult(bad);
    assert.equal(r.mediaId, null);
    assert.equal(r.fifeUrl, null);
  }
});

// ---------------------------------------------------------------------------
// Existing contract: { mediaId, fifeUrl } — batch-runner.js destructures
// exactly these two, plus extra fields are additive/safe.
// ---------------------------------------------------------------------------

test("generateOneImage returns the existing {mediaId, fifeUrl} contract, plus dimensions", async () => {
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  const result = await generateOneImage(page, PROJECT_ID, "a single red apple", {}, 0);
  assert.equal(result.mediaId, "e7205d39-9526-468f-bf3f-01ef99d476d0");
  assert.equal(result.fifeUrl.startsWith("https://flow-content.google/"), true);
  assert.equal(result.width, 1376);
  assert.equal(result.height, 768);
});

// ---------------------------------------------------------------------------
// Generation / HTTP failure handling
// ---------------------------------------------------------------------------

test("malformed batchexecute response (no wrb.fr for ogiZ0b) fails generation, not a crash", async () => {
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => canned(["someOtherRpc", [1]]) });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(
    () => generateOneImage(page, PROJECT_ID, "prompt", {}, 0),
    /No mediaId in generation response/,
  );
});

test("garbage response body fails generation cleanly", async () => {
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => "<!doctype html>not batchexecute at all" });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(() => generateOneImage(page, PROJECT_ID, "prompt", {}, 0));
});

test("HTTP 429 raises RateLimitError", async () => {
  const fetchImpl = async () => ({ ok: false, status: 429, text: async () => "rate limited" });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(() => generateOneImage(page, PROJECT_ID, "prompt", {}, 0), RateLimitError);
});

test("HTTP 401 while still signed in raises EndpointRejectedError, not AuthExpiredError", async () => {
  let calls = 0;
  const fetchImpl = async () => {
    calls++;
    return { ok: false, status: 401, text: async () => "unauthenticated" };
  };
  // WIZ still has a valid SNlM0e -> getSessionToken() inside the fallback check reports "still signed in".
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(() => generateOneImage(page, PROJECT_ID, "prompt", {}, 0), EndpointRejectedError);
});

test("HTTP 401 while genuinely signed out raises AuthExpiredError", async () => {
  const fetchImpl = async () => ({ ok: false, status: 401, text: async () => "unauthenticated" });
  // SNlM0e present for the FIRST request (so the request itself is attempted)
  // but the fallback getSessionToken() re-check must see it's actually gone.
  const wiz = fullWiz();
  const page = fakePage({ wiz, fetchImpl });
  // Simulate the session dying between the request and the recheck.
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
  await assert.rejects(() => generateOneImage(page, PROJECT_ID, "prompt", {}, 0), AuthExpiredError);
});

test("generic HTTP error surfaces as a plain Error with the status", async () => {
  const fetchImpl = async () => ({ ok: false, status: 500, text: async () => "server error" });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(() => generateOneImage(page, PROJECT_ID, "prompt", {}, 0), /HTTP 500/);
});

test("network/timeout failure surfaces cleanly", async () => {
  const fetchImpl = async () => {
    const e = new Error("aborted");
    e.name = "AbortError";
    throw e;
  };
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(() => generateOneImage(page, PROJECT_ID, "prompt", {}, 0), /Request timed out/);
});

// ---------------------------------------------------------------------------
// extractRpcErrorInfoReason — shared google.rpc.ErrorInfo extractor. Used at
// all three RPC sites (ogiZ0b here, YhhmEf and as29s in generateOneVideo) so
// a real application-level rejection is named instead of collapsing into a
// generic "no mediaId" message. Real captured envelope shapes (see project
// notes): gRPC 7/PERMISSION_DENIED for PUBLIC_ERROR_UNUSUAL_ACTIVITY, gRPC
// 8/RESOURCE_EXHAUSTED for PUBLIC_ERROR_USER_QUOTA_REACHED.
// ---------------------------------------------------------------------------

function errorEnvelope(rpcid, grpcCode, reason) {
  return (
    ")]}'\n\n" +
    chunkOf([
      [
        "wrb.fr",
        rpcid,
        null,
        null,
        null,
        [grpcCode, null, [["type.googleapis.com/google.rpc.ErrorInfo", [reason]]]],
        "generic",
      ],
    ]) +
    chunkOf([["e", 4, null, null, 228]])
  );
}

test("extractRpcErrorInfoReason finds PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7)", () => {
  const text = errorEnvelope("ogiZ0b", 7, "PUBLIC_ERROR_UNUSUAL_ACTIVITY");
  assert.equal(extractRpcErrorInfoReason(text, "ogiZ0b"), "PUBLIC_ERROR_UNUSUAL_ACTIVITY");
});

test("extractRpcErrorInfoReason finds PUBLIC_ERROR_USER_QUOTA_REACHED (gRPC 8)", () => {
  const text = errorEnvelope("ogiZ0b", 8, "PUBLIC_ERROR_USER_QUOTA_REACHED");
  assert.equal(extractRpcErrorInfoReason(text, "ogiZ0b"), "PUBLIC_ERROR_USER_QUOTA_REACHED");
});

test("extractRpcErrorInfoReason is not hardcoded to known reasons — surfaces an arbitrary one", () => {
  const text = errorEnvelope("ogiZ0b", 9, "SOME_FUTURE_REASON_NEVER_SEEN_BEFORE");
  assert.equal(extractRpcErrorInfoReason(text, "ogiZ0b"), "SOME_FUTURE_REASON_NEVER_SEEN_BEFORE");
});

test("extractRpcErrorInfoReason returns null for a normal successful workflow response", () => {
  const text = canned(["ogiZ0b", REAL_RESULT]);
  assert.equal(extractRpcErrorInfoReason(text, "ogiZ0b"), null);
});

test("extractRpcErrorInfoReason returns null for malformed/unexpected response, never throws", () => {
  for (const bad of ["", "not batchexecute at all", ")]}'\nnotanumber\n{}", ")]}'\n5\n{broken"]) {
    assert.doesNotThrow(() => extractRpcErrorInfoReason(bad, "ogiZ0b"));
    assert.equal(extractRpcErrorInfoReason(bad, "ogiZ0b"), null);
  }
});

test("extractRpcErrorInfoReason returns null when the rpcid never arrives", () => {
  const text = errorEnvelope("someOtherRpc", 7, "PUBLIC_ERROR_UNUSUAL_ACTIVITY");
  assert.equal(extractRpcErrorInfoReason(text, "ogiZ0b"), null);
});

// ---------------------------------------------------------------------------
// generateOneImage surfaces the ErrorInfo reason instead of the generic
// "No mediaId in generation response" message, and writes the same style of
// passive diagnostic capture generateOneVideo already has for YhhmEf.
// ---------------------------------------------------------------------------

test("generateOneImage surfaces the ErrorInfo reason instead of a generic message", async () => {
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    text: async () => errorEnvelope("ogiZ0b", 8, "PUBLIC_ERROR_USER_QUOTA_REACHED"),
  });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(
    () => generateOneImage(page, PROJECT_ID, "prompt", {}, 0),
    /Flow RPC rejected: PUBLIC_ERROR_USER_QUOTA_REACHED/,
  );
});

test("generateOneImage without any ErrorInfo still falls back to the original generic message", async () => {
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => canned(["someOtherRpc", [1]]) });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });
  await assert.rejects(
    () => generateOneImage(page, PROJECT_ID, "prompt", {}, 0),
    /No mediaId in generation response/,
  );
});

test("a missing mediaId writes a passive ogiz0b diagnostic record without changing the thrown error", async () => {
  const { mkdtempSync, readFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");

  const runDir = mkdtempSync(join(tmpdir(), "ogiz0b-diag-test-"));
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    text: async () => errorEnvelope("ogiZ0b", 8, "PUBLIC_ERROR_USER_QUOTA_REACHED"),
  });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });

  try {
    await assert.rejects(
      () => generateOneImage(page, PROJECT_ID, "prompt", { outputDir: runDir }, 0),
      /Flow RPC rejected: PUBLIC_ERROR_USER_QUOTA_REACHED/,
    );
    const diagPath = join(runDir, "ogiz0b-diagnostic.log");
    const lines = readFileSync(diagPath, "utf8").trim().split("\n");
    assert.equal(lines.length, 1);
    const entry = JSON.parse(lines[0]);
    assert.equal(entry.rpc, "ogiZ0b");
    assert.equal(entry.promptIndex, 0);
    assert.equal(entry.prompt, "prompt");
    assert.equal(entry.httpStatus, 200);
    assert.equal(entry.errorInfoReason, "PUBLIC_ERROR_USER_QUOTA_REACHED");
    assert.ok(entry.ts);
    assert.ok(entry.host);
    assert.ok(Number.isInteger(entry.responseLength) && entry.responseLength > 0);
    assert.ok(entry.rawResponse.includes("PUBLIC_ERROR_USER_QUOTA_REACHED"));
    // Never log cookies/tokens/credentials/session secrets.
    assert.ok(!JSON.stringify(entry).includes(REAL_TOKEN));
  } finally {
    rmSync(runDir, { recursive: true, force: true });
  }
});

test("a successful image generation writes no ogiz0b diagnostic record", async () => {
  const { mkdtempSync, existsSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");

  const runDir = mkdtempSync(join(tmpdir(), "ogiz0b-diag-test-success-"));
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });

  try {
    await generateOneImage(page, PROJECT_ID, "a single red apple", { outputDir: runDir }, 0);
    assert.equal(existsSync(join(runDir, "ogiz0b-diagnostic.log")), false);
  } finally {
    rmSync(runDir, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// Symmetric generation-diagnostic.log — fires on BOTH success and failure,
// with the same field shape, so a future incident can compare a successful
// attempt's timings against a failing one (the exact gap that blocked the
// 2026-09-23 investigation: a real success and a real failure on the same
// account/project/code had nothing captured to compare).
// ---------------------------------------------------------------------------

test("a successful image generation writes a symmetric generation-diagnostic.log entry", async () => {
  const { mkdtempSync, readFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");

  const runDir = mkdtempSync(join(tmpdir(), "gen-diag-test-success-"));
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });

  try {
    await generateOneImage(page, PROJECT_ID, "a single red apple", { outputDir: runDir }, 0);
    const lines = readFileSync(join(runDir, "generation-diagnostic.log"), "utf8").trim().split("\n");
    assert.equal(lines.length, 1);
    const entry = JSON.parse(lines[0]);
    assert.equal(entry.rpc, "ogiZ0b");
    assert.equal(entry.outcome, "success");
    assert.equal(entry.mediaId, "e7205d39-9526-468f-bf3f-01ef99d476d0");
    assert.equal(entry.httpStatus, 200);
    assert.ok(entry.responseLength > 0);
    assert.equal(entry.hasWizState, true);
    assert.equal(entry.errorInfoReason, null);
    assert.equal(entry.grpcCode, null);
    assert.ok(entry.ts);
    assert.ok(entry.flowReadyAt);
    assert.ok(entry.recaptchaExecuteStartedAt);
    assert.ok(entry.recaptchaExecuteEndedAt);
    assert.ok(entry.recaptchaExecuteDurationMs >= 0);
    assert.ok(entry.rpcSentAt);
    assert.ok(entry.rpcRespondedAt);
    assert.ok(entry.totalElapsedMs >= 0);
    assert.equal(entry.pageReused, false);
  } finally {
    rmSync(runDir, { recursive: true, force: true });
  }
});

test("a failing image generation (with ErrorInfo) writes the same shape entry, with grpcCode/reason populated", async () => {
  const { mkdtempSync, readFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");

  const runDir = mkdtempSync(join(tmpdir(), "gen-diag-test-failure-"));
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    text: async () => errorEnvelope("ogiZ0b", 7, "PUBLIC_ERROR_UNUSUAL_ACTIVITY"),
  });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });

  try {
    await assert.rejects(() => generateOneImage(page, PROJECT_ID, "prompt", { outputDir: runDir }, 0));
    const lines = readFileSync(join(runDir, "generation-diagnostic.log"), "utf8").trim().split("\n");
    assert.equal(lines.length, 1);
    const entry = JSON.parse(lines[0]);
    assert.equal(entry.outcome, "no_media_id");
    assert.equal(entry.mediaId, null);
    assert.equal(entry.grpcCode, 7);
    assert.equal(entry.errorInfoReason, "PUBLIC_ERROR_UNUSUAL_ACTIVITY");
    assert.equal(entry.httpStatus, 200);
    assert.equal(entry.hasWizState, true);
    // Same fields present as the success case — symmetric shape.
    assert.ok(entry.flowReadyAt);
    assert.ok(entry.recaptchaExecuteStartedAt);
    assert.ok(entry.rpcSentAt);
    assert.ok(entry.rpcRespondedAt);
  } finally {
    rmSync(runDir, { recursive: true, force: true });
  }
});

test("generation-diagnostic.log never contains the reCAPTCHA token, the WIZ at/bl/f.sid values, or the request URL's session query params", async () => {
  const { mkdtempSync, readFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");

  const runDir = mkdtempSync(join(tmpdir(), "gen-diag-test-secrets-"));
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) });
  const wiz = fullWiz();
  const page = fakePage({ wiz, fetchImpl });

  try {
    await generateOneImage(page, PROJECT_ID, "a single red apple", { outputDir: runDir }, 0);
    const raw = readFileSync(join(runDir, "generation-diagnostic.log"), "utf8");
    assert.ok(!raw.includes(REAL_TOKEN), "must not log the WIZ 'at' token");
    assert.ok(!raw.includes(wiz.cfb2h), "must not log 'bl'");
    assert.ok(!raw.includes(wiz.FdrFJe), "must not log 'f.sid'");
    assert.ok(!raw.includes("CAPTCHA_TOKEN"), "must not log the reCAPTCHA token");
    assert.ok(!raw.includes("cookie"), "must not log cookies");
    const entry = JSON.parse(raw.trim());
    assert.equal(entry.url, "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=ogiZ0b");
  } finally {
    rmSync(runDir, { recursive: true, force: true });
  }
});

test("pageReused is false on a page's first generation and true on its second", async () => {
  const { mkdtempSync, readFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");

  const runDir = mkdtempSync(join(tmpdir(), "gen-diag-test-reuse-"));
  const fetchImpl = async () => ({ ok: true, status: 200, text: async () => canned(["ogiZ0b", REAL_RESULT]) });
  const page = fakePage({ wiz: fullWiz(), fetchImpl });

  try {
    await generateOneImage(page, PROJECT_ID, "first", { outputDir: runDir }, 0);
    await generateOneImage(page, PROJECT_ID, "second", { outputDir: runDir }, 1);
    const lines = readFileSync(join(runDir, "generation-diagnostic.log"), "utf8").trim().split("\n");
    assert.equal(lines.length, 2);
    assert.equal(JSON.parse(lines[0]).pageReused, false);
    assert.equal(JSON.parse(lines[1]).pageReused, true);
  } finally {
    rmSync(runDir, { recursive: true, force: true });
  }
});
