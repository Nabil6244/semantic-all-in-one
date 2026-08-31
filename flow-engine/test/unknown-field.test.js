/**
 * Google periodically drops or renames fields in Flow's private API. When
 * `videoLengthSeconds` disappeared from batchAsyncGenerateVideoText, every
 * video job failed with INVALID_ARGUMENT (400) and whole batches were lost.
 * Run: node --test test/unknown-field.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const { parseUnknownField, stripUnknownField } = await import("../lib/flow-api.js");

// Verbatim body Google returned when videoLengthSeconds was removed.
const REAL_400 = JSON.stringify({
  error: {
    code: 400,
    message:
      "Invalid JSON payload received. Unknown name \"videoLengthSeconds\" at 'requests[0]': Cannot find field.",
    status: "INVALID_ARGUMENT",
  },
});

test("parses the field and path out of the real rejection", () => {
  assert.deepEqual(parseUnknownField(REAL_400), {
    field: "videoLengthSeconds",
    path: "requests[0]",
  });
});

test("parses an escaped payload as delivered through the page bridge", () => {
  const escaped =
    'Unknown name \\"videoLengthSeconds\\" at \'requests[0]\': Cannot find field.';
  assert.equal(parseUnknownField(escaped)?.field, "videoLengthSeconds");
});

test("returns null for unrelated 400s so they still surface", () => {
  assert.equal(parseUnknownField("RESOURCE_EXHAUSTED"), null);
  assert.equal(parseUnknownField(""), null);
  assert.equal(parseUnknownField(null), null);
});

test("strips only the named field and keeps the rest of the request", () => {
  const body = {
    requests: [
      { aspectRatio: "A", seed: 7, videoLengthSeconds: 8, videoModelKey: "k" },
    ],
    useV2ModelConfig: true,
  };
  assert.equal(stripUnknownField(body, "videoLengthSeconds", "requests[0]"), true);
  assert.deepEqual(body.requests[0], { aspectRatio: "A", seed: 7, videoModelKey: "k" });
  assert.equal(body.useV2ModelConfig, true);
});

test("strips a nested field", () => {
  const body = { requests: [{ textInput: { structuredPrompt: { bogus: 1, parts: [] } } }] };
  assert.equal(
    stripUnknownField(body, "bogus", "requests[0].textInput.structuredPrompt"),
    true,
  );
  assert.deepEqual(body.requests[0].textInput.structuredPrompt, { parts: [] });
});

test("strips a top-level field", () => {
  const body = { weird: 1, requests: [] };
  assert.equal(stripUnknownField(body, "weird", ""), true);
  assert.deepEqual(body, { requests: [] });
});

test("reports false rather than throwing on paths that do not exist", () => {
  assert.equal(stripUnknownField({ requests: [{}] }, "nope", "requests[0]"), false);
  assert.equal(stripUnknownField({}, "x", "requests[9].deep"), false);
  assert.equal(stripUnknownField(null, "x", ""), false);
  assert.equal(stripUnknownField({ requests: {} }, "x", "requests[0]"), false);
});

test("a second unknown field can still be stripped after the first", () => {
  // Guards the retry loop: each pass removes one field, so a payload with two
  // stale fields converges instead of looping on the first one forever.
  const body = { requests: [{ a: 1, videoLengthSeconds: 8, alsoGone: 2 }] };
  assert.equal(stripUnknownField(body, "videoLengthSeconds", "requests[0]"), true);
  assert.equal(stripUnknownField(body, "alsoGone", "requests[0]"), true);
  assert.deepEqual(body.requests[0], { a: 1 });
  // Re-stripping an already-removed field reports false, which is what stops
  // apiPost from retrying the same field twice.
  assert.equal(stripUnknownField(body, "alsoGone", "requests[0]"), false);
});

const { AuthExpiredError, EndpointRejectedError, FatalError, QuotaError, RateLimitError } =
  await import("../lib/flow-api.js");

test("AuthExpiredError is its own type, not a FatalError", () => {
  // batch-runner branches on it BEFORE the FatalError/recoverable test, so it
  // must not be swallowed by that path.
  const e = new AuthExpiredError("signed out");
  assert.equal(e.name, "AuthExpiredError");
  assert.ok(e instanceof Error);
  assert.ok(!(e instanceof FatalError));
  assert.ok(!(e instanceof QuotaError));
  assert.ok(!(e instanceof RateLimitError));
});

test("the 401 message tells the user what to actually do", () => {
  // The raw Google body ("Expected OAuth 2 access token, login cookie or
  // other valid authentication credential") gave no actionable instruction.
  const e = new AuthExpiredError(
    "Flow account is signed out — open Accounts and sign in again",
  );
  assert.match(e.message, /sign in again/i);
  assert.doesNotMatch(e.message, /OAuth 2 access token/);
});

test("an endpoint rejection is a distinct type from a signed-out account", () => {
  // Flow's IMAGE endpoint is project-scoped and current; VIDEO is the legacy
  // global /v1/video:* one. Google can 401 the video endpoint while the SAME
  // token still generates images, so a bare 401 must not condemn the account.
  const endpoint = new EndpointRejectedError("endpoint moved");
  const signedOut = new AuthExpiredError("signed out");
  assert.ok(!(endpoint instanceof AuthExpiredError));
  assert.ok(!(signedOut instanceof EndpointRejectedError));
  assert.equal(endpoint.name, "EndpointRejectedError");
});

test("the endpoint-rejection message names the endpoint, not the login", () => {
  const e = new EndpointRejectedError(
    "Google rejected this request (401) while the account is still signed in — " +
      "the endpoint https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText " +
      "no longer accepts this credential.",
  );
  assert.match(e.message, /still signed in/);
  assert.match(e.message, /v1\/video:batchAsyncGenerateVideoText/);
  assert.doesNotMatch(e.message, /sign in again/);
});

test("401 backoff escalates and is bounded", async () => {
  // Measured on all nine signed-in profiles: an immediate token check gets
  // 401, the same profile gets 200 once the SPA settles. So a 401 must buy
  // time and refetch rather than condemn the account on the first try —
  // but it must also terminate.
  const src = await import("node:fs").then((fs) =>
    fs.readFileSync(new URL("../lib/flow-api.js", import.meta.url), "utf8"),
  );
  const m = /AUTH_RETRY_DELAYS_MS = \[([^\]]+)\]/.exec(src);
  assert.ok(m, "AUTH_RETRY_DELAYS_MS must exist");
  const delays = m[1].split(",").map((x) => Number(x.trim()));
  assert.ok(delays.length >= 2 && delays.length <= 5, "bounded retry count");
  for (let i = 1; i < delays.length; i++) {
    assert.ok(delays[i] > delays[i - 1], "delays must increase");
  }
  assert.ok(delays[0] >= 1000, "first wait must actually let the SPA settle");
});

test("the retry is threaded through the unknown-field retry too", async () => {
  // Otherwise stripping a stale field would silently reset the auth counter
  // and the two recoveries could ping-pong.
  const src = await import("node:fs").then((fs) =>
    fs.readFileSync(new URL("../lib/flow-api.js", import.meta.url), "utf8"),
  );
  assert.match(src, /return apiPost\(page, url, bodyObj, recaptchaAction, tried, _authAttempt\)/);
});
