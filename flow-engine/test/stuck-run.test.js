/**
 * A run stuck on a step that never returns (a frozen Flow tab) must not hold Stop or later Generates.
 * Live 2026-10-20 (Saad's Mac): 69 of 71 images saved, the last 2 stayed "processing", Stop did nothing, and a
 * Generate for just those 2 waited behind the stuck run forever.
 */
import test from "node:test";
import assert from "node:assert/strict";

const orch = await import("../lib/orchestrator.js");
const { withAccountLock } = await import("../lib/batch-runner.js");
const { activeAgentScenes } = await import("../lib/agent-runner.js");
const { LedgerState } = await import("../lib/generation-ledger.js");
const { bounded, boundedOrThrow, collectStillUrls } = await import("../lib/flow-ui-agent.js");

const never = () => new Promise(() => {});
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const noBrowsers = { closeAllBrowsers: async () => {} };

function captureBroadcasts() {
  const seen = [];
  const off = orch.__onBroadcastForTest((m) => seen.push(m));
  return { seen, off };
}

test("bounded: a page call that never answers gives the fallback", async () => {
  const t0 = Date.now();
  assert.deepEqual(await bounded(never(), 50, []), []);
  assert.ok(Date.now() - t0 < 1000);
  assert.equal(await bounded(Promise.resolve(7), 50, 0), 7);
  assert.equal(await bounded(Promise.reject(new Error("x")), 50, "fb"), "fb");
});

test("boundedOrThrow: a page call that never answers throws", async () => {
  await assert.rejects(boundedOrThrow(never(), 50, "paste"), /did not answer \(paste\)/);
  assert.equal(await boundedOrThrow(Promise.resolve(1), 50, "x"), 1);
});

test("collectStillUrls on a frozen page returns (empty) instead of hanging", { timeout: 20000 }, async () => {
  const frozenPage = { evaluate: never };
  assert.deepEqual(await collectStillUrls(frozenPage), []);
});

test("Stop cuts off a run that does not end by itself", async () => {
  const { seen, off } = captureBroadcasts();
  let closed = 0;
  const run = orch.__startFakeRunForTest({ type: "GENERATE_DONE", outputDir: "/out" });
  orch.stopGenerate({ forceAfterMs: 50, deps: { closeAllBrowsers: async () => { closed++; } } });
  assert.equal(run.stopped(), true);
  assert.equal(orch.getState().running, true, "it first gets a moment to end by itself");
  await wait(150);
  off();
  assert.equal(orch.getState().running, false);
  assert.equal(closed, 1, "its Flow tabs are closed so a stuck page call fails");
  const done = seen.filter((m) => m.type === "GENERATE_DONE");
  assert.equal(done.length, 1);
  assert.equal(done[0].forced, true);
  assert.equal(done[0].outputDir, "/out");
});

test("forced Stop ends the run at once", async () => {
  const { seen, off } = captureBroadcasts();
  orch.__startFakeRunForTest();
  orch.stopGenerate({ force: true, deps: noBrowsers });
  await wait(10);
  off();
  assert.equal(orch.getState().running, false);
  assert.equal(seen.filter((m) => m.type === "GENERATE_DONE").length, 1);
});

test("a cut-off run stays stopped after a new run starts", async () => {
  const a = orch.__startFakeRunForTest();
  await orch.forceEndRun("test", noBrowsers);
  const b = orch.__startFakeRunForTest();
  assert.equal(a.stopped(), true, "the old run's shouldStop stays true although stopAll was cleared");
  assert.equal(a.isCurrent(), false);
  assert.equal(b.stopped(), false);
  await orch.forceEndRun("cleanup", noBrowsers);
});

test("a new Generate does not wait forever behind a stuck run", async () => {
  orch.__startFakeRunForTest();
  const cut = await orch.endPreviousRun(never(), 50, noBrowsers);
  assert.equal(cut, true);
  assert.equal(orch.getState().running, false);
});

test("a previous run that ends normally is never cut off", async () => {
  orch.__startFakeRunForTest();
  const cut = await orch.endPreviousRun(wait(20), 1000, noBrowsers);
  assert.equal(cut, false);
  await orch.forceEndRun("cleanup", noBrowsers);
});

test("cut-off agent scenes become Retry-able (never resent automatically)", async () => {
  const entries = new Map([["k1", { state: LedgerState.SUBMITTING }], ["k2", { state: LedgerState.MEDIA_ID_KNOWN }]]);
  const ledger = { get: (k) => entries.get(k), put: (k, v) => entries.set(k, { ...entries.get(k), ...v }) };
  activeAgentScenes.set("k1", { runId: "r" });
  activeAgentScenes.set("k2", { runId: "r" });
  orch.__startFakeRunForTest();
  await orch.forceEndRun("test", { ...noBrowsers, ledger });
  assert.equal(activeAgentScenes.size, 0, "no longer reported as 'still being made by the agent'");
  assert.equal(entries.get("k1").state, LedgerState.SUBMITTED_UNKNOWN);
  assert.equal(entries.get("k2").state, LedgerState.MEDIA_ID_KNOWN, "an image Flow already made stays downloadable");
});

test("a cut-off run's account lock does not block the next run", async () => {
  withAccountLock("acct-stuck", never);
  orch.__startFakeRunForTest();
  await orch.forceEndRun("test", noBrowsers);
  const ran = await Promise.race([withAccountLock("acct-stuck", async () => "ran"), wait(200).then(() => "blocked")]);
  assert.equal(ran, "ran");
});
