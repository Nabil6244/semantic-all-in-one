/**
 * The agent worker pool (lib/agent-pool.js): batch counts by job size, one request per account at a time, every healthy
 * account used, cool-down and rejoin, hand-off, fallback rounds, owner downloads and Stop. Flow is a fake.
 * Run: node --test test/agent-pool.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const { planPoolBatches, runAgentPool, sceneStanding } = await import("../lib/agent-pool.js");

const items = (n, start = 0) => Array.from({ length: n }, (_, i) => ({
  index: start + i, prompt: `documentary scene ${start + i} showing subject ${start + i}x`, promptKey: String(start + i + 1),
}));
const accounts = (n) => Array.from({ length: n }, (_, i) => ({ id: `acct-${i + 1}`, label: `Account ${i + 1}` }));

/** A fake clock the pool's sleeps advance, and a fake runSlice that takes `ms` per request. */
function harness({ ms = 1000, plan = () => ({}) } = {}) {
  let t = 0;
  const active = new Map();
  const log = [];
  let maxPerAccount = 0;
  const sleep = async (d) => { t += Math.max(1, d); await new Promise((r) => setImmediate(r)); };
  const runSlice = async ({ account, items: its }) => {
    const n = (active.get(account.id) || 0) + 1;
    active.set(account.id, n);
    maxPerAccount = Math.max(maxPerAccount, n);
    const start = t;
    const call = log.push({ account: account.id, size: its.length, start, indices: its.map((x) => x.index) });
    await sleep(ms);
    active.set(account.id, active.get(account.id) - 1);
    return { completed: its.length, failed: 0, reassign: [], ...plan({ account, items: its, start, call }) };
  };
  return {
    log, runSlice, sleep, now: () => t,
    get maxPerAccount() { return maxPerAccount; },
    prepare: async (a) => ({ page: a.id }),
    runStandard: async ({ items: its }) => { log.push({ standard: true, size: its.length }); return {}; },
  };
}

for (const [n, batches] of [[5, 1], [24, 1], [25, 2], [58, 3], [100, 5], [300, 13], [500, 21]]) {
  test(`${n} scenes -> ${batches} agent request(s) of at most 24, no job-size ceiling`, () => {
    const b = planPoolBatches(items(n));
    assert.equal(b.length, batches);
    assert.ok(b.every((x) => x.length <= 24));
    assert.equal(b.flat().length, n);
  });
}

for (const n of [3, 4, 5, 6, 7, 8]) {
  test(`${n} healthy accounts: all take part, never two requests on one account`, async () => {
    const h = harness();
    const res = await runAgentPool({ items: items(300), accounts: accounts(n), prepare: h.prepare, runSlice: h.runSlice,
      runStandard: h.runStandard, sleep: h.sleep, now: h.now, batchGapMs: 0 });
    assert.equal(res.batchesRun, 13);
    assert.equal(res.accountsUsed.size, Math.min(n, 13));
    assert.equal(res.maxConcurrent, Math.min(n, 13), "every healthy account works at the same time");
    assert.equal(h.maxPerAccount, 1, "one agent request per account at a time");
    assert.equal(h.log.reduce((s, x) => s + x.size, 0), 300, "every scene sent exactly once");
    assert.deepEqual(res.unrun, []);
  });
}

test("a free account takes the next batch only after its previous one finished", async () => {
  const h = harness({ ms: 1000 });
  await runAgentPool({ items: items(100), accounts: accounts(2), prepare: h.prepare, runSlice: h.runSlice,
    runStandard: h.runStandard, sleep: h.sleep, now: h.now, batchGapMs: 0 });
  const byAcct = {};
  for (const x of h.log) (byAcct[x.account] ||= []).push(x.start);
  for (const starts of Object.values(byAcct)) {
    for (let i = 1; i < starts.length; i++) assert.ok(starts[i] - starts[i - 1] >= 1000);
  }
});

test("an account asked to slow down rests: its scenes go to other accounts, it rejoins after the cool-down", async () => {
  const h = harness({
    ms: 1000,
    plan: ({ account, items: its, call }) => (account.id === "acct-1" && call === 1
      ? { coolDown: "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC", completed: 0, reassign: its.map((x) => ({ index: x.index, prompt: x.prompt, promptKey: x.promptKey })) }
      : {}),
  });
  const res = await runAgentPool({ items: items(24 * 6), accounts: accounts(2), prepare: h.prepare, runSlice: h.runSlice,
    runStandard: h.runStandard, sleep: h.sleep, now: h.now, batchGapMs: 0, coolDownMs: 3000 });
  const firstCooled = h.log[0];
  assert.equal(firstCooled.account, "acct-1");
  const resent = h.log.filter((x) => x.indices.includes(firstCooled.indices[0]));
  assert.equal(resent.length, 2, "the cooled batch is sent once more, elsewhere or after the rest");
  assert.notEqual(resent[1].start, firstCooled.start);
  const acct1Later = h.log.filter((x) => x.account === "acct-1" && x.start > firstCooled.start);
  assert.ok(acct1Later.every((x) => x.start >= firstCooled.start + 1000 + 3000), "no batch during the cool-down");
  assert.ok(acct1Later.length >= 1, "it rejoins after the cool-down");
  assert.deepEqual(res.unrun, []);
});

test("an account that breaks mid-request hands its batch on without the Retry permission", async () => {
  let calls = 0;
  const h = harness();
  const seen = [];
  const runSlice = async (args) => {
    calls++;
    seen.push(args);
    if (calls === 1) throw new Error("Target page, context or browser has been closed");
    return h.runSlice(args);
  };
  const res = await runAgentPool({ items: items(10), accounts: accounts(2), prepare: h.prepare, runSlice,
    runStandard: h.runStandard, sleep: h.sleep, now: h.now, batchGapMs: 0 });
  assert.equal(seen.length, 2);
  assert.notEqual(seen[1].account.id, seen[0].account.id);
  assert.ok(seen[1].items.every((x) => x.noConfirm), "the handed-on batch may not use the Retry permission");
  assert.deepEqual(res.unrun, []);
});

test("five or more the agent did not make: one more agent round; fewer: the standard path", async () => {
  const h1 = harness({ plan: ({ call, items: its }) => (call === 1 ? { fallback: its.slice(0, 6).map((x) => ({ index: x.index, prompt: x.prompt, promptKey: x.promptKey })) } : {}) });
  await runAgentPool({ items: items(10), accounts: accounts(1), prepare: h1.prepare, runSlice: h1.runSlice,
    runStandard: h1.runStandard, sleep: h1.sleep, now: h1.now, batchGapMs: 0 });
  assert.deepEqual(h1.log.map((x) => (x.standard ? "standard" : x.size)), [10, 6]);

  const h2 = harness({ plan: ({ call, items: its }) => (call === 1 ? { fallback: its.slice(0, 3).map((x) => ({ index: x.index, prompt: x.prompt, promptKey: x.promptKey })) } : {}) });
  await runAgentPool({ items: items(10), accounts: accounts(1), prepare: h2.prepare, runSlice: h2.runSlice,
    runStandard: h2.runStandard, sleep: h2.sleep, now: h2.now, batchGapMs: 0 });
  assert.deepEqual(h2.log.map((x) => (x.standard ? "standard" : x.size)), [10, "standard"]);
  assert.equal(h2.log[1].size, 3);
});

test("download-only scenes go to the account that made them and are not mixed into new batches", async () => {
  const h = harness();
  const its = items(30);
  its[0].owner = "acct-2";
  its[1].owner = "acct-2";
  await runAgentPool({ items: its, accounts: accounts(3), prepare: h.prepare, runSlice: h.runSlice,
    runStandard: h.runStandard, sleep: h.sleep, now: h.now, batchGapMs: 0 });
  const owned = h.log.find((x) => x.indices.includes(0));
  assert.equal(owned.account, "acct-2");
  assert.deepEqual(owned.indices.sort(), [0, 1]);
});

test("Stop: no new batch starts; the rest is reported as not sent", async () => {
  let stopped = false;
  const h = harness({ plan: () => { stopped = true; return {}; } });
  const res = await runAgentPool({ items: items(100), accounts: accounts(2), isStopped: () => stopped, prepare: h.prepare,
    runSlice: h.runSlice, runStandard: h.runStandard, sleep: h.sleep, now: h.now, batchGapMs: 0 });
  assert.equal(h.log.length, 2, "only the requests already out finish");
  assert.equal(res.unrun.length, 100 - h.log.reduce((s, x) => s + x.size, 0));
  assert.ok(res.unrun.every((u) => u.reason === "stopped"));
});

test("an account that cannot be prepared drops out; others take its work", async () => {
  const h = harness();
  const prepare = async (a) => { if (a.id === "acct-1") throw new Error("Signed out"); return {}; };
  const res = await runAgentPool({ items: items(50), accounts: accounts(3), prepare, runSlice: h.runSlice,
    runStandard: h.runStandard, sleep: h.sleep, now: h.now, batchGapMs: 0 });
  assert.ok(h.log.every((x) => x.account !== "acct-1"));
  assert.equal(h.log.reduce((s, x) => s + x.size, 0), 50);
  assert.deepEqual(res.unrun, []);
});

test("which scenes count as new images", () => {
  assert.equal(sceneStanding(null), "new");
  assert.equal(sceneStanding({ state: "REJECTED" }), "new");
  assert.equal(sceneStanding({ state: "MEDIA_ID_KNOWN" }), "download");
  assert.equal(sceneStanding({ state: "COMPLETED_LOCAL" }), "other");
  assert.equal(sceneStanding({ state: "SUBMITTED_UNKNOWN" }), "other");
  assert.equal(sceneStanding({ state: "SUBMITTED_UNKNOWN" }, { confirmed: true }), "new");
});

// ---------------------------------------------------------------- routing (decided before any account split)
const { planImageJob } = await import("../lib/agent-pool.js");
const keyOf = ({ promptKey, index }) => `k${promptKey ?? index}`;
const ledgerOf = (entries = {}) => ({ get: (k) => entries[k] || null });
const route = (n, extra = {}) => planImageJob({ prompts: items(n).map((x) => x.prompt), promptKeys: items(n).map((x) => x.promptKey),
  ledger: ledgerOf(extra.entries), active: extra.active || new Map(), keyOf, agentRequested: true, settings: extra.settings || {} });

for (const [n, agent] of [[1, false], [4, false], [5, true], [24, true], [25, true], [58, true], [100, true], [300, true], [500, true]]) {
  test(`${n} new image(s) -> ${agent ? "agent" : "normal path"}`, () => {
    const r = route(n);
    assert.equal(r.agentPool, agent);
    assert.equal(r.fresh, n);
  });
}

test("download-only and already-saved scenes do not count as new images", () => {
  const entries = { k1: { state: "MEDIA_ID_KNOWN", accountId: "acct-3" }, k2: { state: "COMPLETED_LOCAL" }, k3: { state: "DOWNLOAD_FAILED", accountId: "acct-3" } };
  const r = route(6, { entries });   // 6 scenes, 3 of them not new
  assert.equal(r.fresh, 3);
  assert.equal(r.agentPool, false);
  assert.equal(r.poolItems.find((x) => x.promptKey === "1").owner, "acct-3");
});

test("a confirmed Retry of uncertain scenes counts them as new", () => {
  const entries = Object.fromEntries(["1", "2", "3", "4", "5"].map((k) => [`k${k}`, { state: "SUBMITTED_UNKNOWN" }]));
  assert.equal(route(5, { entries }).agentPool, false, "an automatic run never counts uncertain scenes as new");
  assert.equal(route(5, { entries, settings: { confirmResubmitKeys: ["1", "2", "3", "4", "5"] } }).agentPool, true);
});

test("scenes still inside an agent request are held back, whatever the path", () => {
  const active = new Map([["k2", { accountLabel: "Account 4" }]]);
  const r = route(6, { active });
  assert.deepEqual(r.busy.map((b) => b.index), [1]);
  assert.equal(r.busy[0].by.accountLabel, "Account 4");
  assert.equal(r.poolItems.length, 5);
  assert.equal(r.fresh, 5);
});
