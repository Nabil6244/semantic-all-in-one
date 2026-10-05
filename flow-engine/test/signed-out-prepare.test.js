/**
 * Signed-out Flow profiles must fail preparation once and leave the registry
 * honest — otherwise a 1-prompt batch burns the Python idle timeout rotating
 * through dead accounts that still say authenticated:true.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {
  isSignedOutPrepareError,
  failMessageForPending,
} from "../lib/orchestrator.js";

test("isSignedOutPrepareError matches both prepare and openOrCreate messages", () => {
  assert.equal(isSignedOutPrepareError(new Error('Account "Account 2" is not signed in')), true);
  assert.equal(isSignedOutPrepareError(new Error("Not signed in to Flow — open this account and sign in once")), true);
  assert.equal(isSignedOutPrepareError(new Error("Rate limited by Google")), false);
  assert.equal(isSignedOutPrepareError(new Error("Execution context was destroyed")), false);
});

test("failMessageForPending does not blame rate limit when prepare failed", () => {
  const msg = failMessageForPending({ reason: "prepare_failed", prompt: "x", index: 0 });
  assert.match(msg, /signed-in/i);
  assert.doesNotMatch(msg, /Rate limit/i);
});

test("ensurePrepared stops retrying on signed-out errors", () => {
  const src = fs.readFileSync(new URL("../lib/orchestrator.js", import.meta.url), "utf8");
  const body = src.slice(src.indexOf("async function ensurePrepared"));
  assert.match(body, /isSignedOutPrepareError/);
  assert.match(body, /authenticated: false/);
  assert.match(body, /closeAccountBrowser\(account\.id\)/);
});
