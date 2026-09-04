/**
 * A 100+ scene project starts every worker navigating at once. A single
 * transient failure while preparing an account used to reassign that whole
 * slice as "prepare_failed" and mark the account exhausted — hundreds of
 * scenes lost in one go, which is what a run of images silently falling back
 * to stock actually was.
 * Run: node --test test/prepare-resilience.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../lib/orchestrator.js", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/flow-api.js", import.meta.url), "utf8");

test("preparation is retried instead of failing a whole slice at once", () => {
  assert.match(src, /async function ensurePrepared\(account, attempts = \d+\)/);
  assert.match(src, /for \(let attempt = 1; attempt <= attempts; attempt\+\+\)/);
});

test("retries back off and stay bounded", () => {
  const body = src.slice(src.indexOf("async function ensurePrepared"));
  assert.match(body, /attempt >= attempts/, "must stop after the attempt budget");
  assert.match(body, /3000 \* attempt/, "must back off between attempts");
});

test("a stop request aborts preparation immediately", () => {
  const body = src.slice(src.indexOf("async function ensurePrepared"));
  assert.match(body, /if \(stopAll \|\| attempt >= attempts\) break/);
});

test("a genuinely broken account still throws", () => {
  const body = src.slice(src.indexOf("async function ensurePrepared"));
  assert.match(body, /throw lastErr \|\| new Error\("Could not prepare/);
});

test("the image path waits for the page, like the video path", () => {
  // The asymmetry that let videos succeed while every image failed.
  const img = api.slice(api.indexOf("export async function generateOneImage"));
  const vid = api.slice(api.indexOf("export async function generateOneVideo"));
  const head = (s) => s.slice(0, s.indexOf("const body =") + 1 || 900);
  assert.match(head(img), /await waitForFlowReady\(page\)/, "image path must wait");
  assert.match(head(vid), /await waitForFlowReady\(page\)/, "video path must still wait");
});

test("preparation cannot generate media, so retrying it spends no credit", () => {
  const body = src.slice(
    src.indexOf("async function ensurePrepared"),
    src.indexOf("async function runPass"),
  );
  for (const forbidden of ["generateOneImage", "generateOneVideo", "runBatchSlice"]) {
    assert.ok(!body.includes(forbidden), `prepare must not call ${forbidden}`);
  }
});
