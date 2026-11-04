/**
 * An agent request Flow never starts (live 2026-11-04: Account 6 sat 195 s, Account 7 5 min, while Account 8 was idle):
 * 1. it is over after NO_ACTIVITY_MS with no sign of life, not after the whole wait; any sign of life keeps the full wait;
 * 2. its scenes go straight to another free account in the same round (once), never back to the stalled one;
 * 3. a screenshot and the page text after our message are saved next to the diagnostic log.
 * (The wait loop itself uses agentLooksDead; driving the whole Flow page here would only test the fake.)
 * Flow is a fake (no network, no credits).
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { agentLooksDead, NO_ACTIVITY_MS, saveStallEvidence } = await import("../lib/flow-ui-agent.js");
const { runAgentPool, sceneStanding } = await import("../lib/agent-pool.js");
const { LedgerState } = await import("../lib/generation-ledger.js");

test("no sign of life for NO_ACTIVITY_MS ends the wait; any sign of life keeps it", () => {
  const base = { sinceClickMs: NO_ACTIVITY_MS, everBusy: false, tiles: 0, replyGrowth: 0 };
  assert.equal(agentLooksDead(base), true);
  assert.equal(agentLooksDead({ ...base, sinceClickMs: NO_ACTIVITY_MS - 1 }), false, "too early");
  assert.equal(agentLooksDead({ ...base, everBusy: true }), false, "busy text seen once");
  assert.equal(agentLooksDead({ ...base, tiles: 1 }), false, "a tile appeared");
  assert.equal(agentLooksDead({ ...base, replyGrowth: 400 }), false, "the agent replied in the chat");
  assert.equal(agentLooksDead({ ...base, replyGrowth: null }), false, "chat unreadable: never taken for dead");
});

test("a stall leaves a screenshot and the page text after our message next to the log", async () => {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), "flow-stall-"));
  const marker = "S01: a red barn at dawn in d";
  const body = `Agent chat\nGenerate exactly 2 still images\n${marker}eep snow\nYou have reached your daily limit.`;
  const page = {
    url: () => "https://flow.google.com/project/p1",
    screenshot: async ({ path: p }) => fs.writeFileSync(p, "png"),
    evaluate: async (fn) => {
      const prev = globalThis.document;
      globalThis.document = { body: { innerText: body }, querySelector: () => ({ innerText: "" }) };
      try { return fn(); } finally { globalThis.document = prev; }
    },
  };
  const ev = await saveStallEvidence(page, out, marker);
  assert.match(ev.screenshot, /^stall-.*\.png$/);
  const txt = fs.readFileSync(path.join(out, "agent", ev.text), "utf8");
  assert.match(txt, /message still in the editor: false/);
  assert.match(txt, /daily limit/);
  assert.equal(await saveStallEvidence(page, null, marker), null, "no folder: nothing written, no error");
});

const items = (n) => Array.from({ length: n }, (_, i) => ({ index: i, prompt: `scene ${i} of a quiet harbour ${i}x`, promptKey: String(i + 1) }));
const accounts = (n) => Array.from({ length: n }, (_, i) => ({ id: `acct-${i + 1}`, label: `Account ${i + 1}` }));

function stallingPool(stallsOn) {
  const log = [];
  const states = [];
  const standard = [];
  const runSlice = async ({ account, items: its }) => {
    log.push({ account: account.id, indices: its.map((x) => x.index) });
    if (stallsOn(account.id, log.length)) {
      return { completed: 0, fallback: its.map((x) => ({ index: x.index, prompt: x.prompt, promptKey: x.promptKey, stalled: true })) };
    }
    return { completed: its.length, fallback: [] };
  };
  return { log, states, standard, args: {
    accounts: accounts(3), prepare: async (a) => ({ page: a.id }), sleep: async () => {}, now: () => 0, batchGapMs: 0, runSlice,
    runStandard: async ({ items: its }) => { standard.push(...its.map((x) => x.index)); return {}; },
    onAccountState: (a, status, message) => states.push([a.id, status, message]),
  } };
}

test("a stalled account's scenes go to another account in the same round, never back to it", async () => {
  const p = stallingPool((acct) => acct === "acct-1");
  const res = await runAgentPool({ items: items(15), maxBatch: 5, minScenes: 5, ...p.args });
  const first = p.log.find((x) => x.account === "acct-1");
  const again = p.log.filter((x) => x.account !== "acct-1" && x.indices.some((i) => first.indices.includes(i)));
  assert.equal(again.length, 1, JSON.stringify(p.log));
  assert.deepEqual(again[0].indices, first.indices);
  assert.equal(p.log.filter((x) => x.account === "acct-1").length, 1, "the stalled account gets none of them back");
  assert.deepEqual(p.standard, []);
  assert.deepEqual(res.unrun, []);
  assert.ok(p.states.some(([id, s, m]) => id === "acct-1" && s === "waiting" && /did not start/.test(m)), "a state the app counts as working");
});

test("stalled again on the second account: handed on only once, then the normal way", async () => {
  const p = stallingPool(() => true);
  const res = await runAgentPool({ items: items(5), maxBatch: 5, minScenes: 5, maxRounds: 1, ...p.args });
  assert.equal(p.log.length, 2, JSON.stringify(p.log));
  assert.notEqual(p.log[0].account, p.log[1].account);
  assert.deepEqual(p.standard.sort((a, b) => a - b), [0, 1, 2, 3, 4], "then the standard path, nothing lost");
  assert.deepEqual(res.unrun, []);
});

test("one account only: the stalled scenes are not handed on (nobody to take them)", async () => {
  const p = stallingPool(() => true);
  p.args.accounts = accounts(1);
  const res = await runAgentPool({ items: items(5), maxBatch: 5, minScenes: 5, maxRounds: 1, ...p.args });
  assert.equal(p.log.length, 1);
  assert.deepEqual(p.standard.sort((a, b) => a - b), [0, 1, 2, 3, 4]);
  assert.deepEqual(res.unrun, []);
});

test("a no-picture still counts as a new image when a job is planned; videos and plain unknowns do not", () => {
  const e = { state: LedgerState.SUBMITTED_UNKNOWN, mediaKind: "image", noMediaSeen: true };
  assert.equal(sceneStanding(e), "new");
  assert.equal(sceneStanding({ ...e, mediaKind: "video" }), "other");
  assert.equal(sceneStanding({ ...e, noMediaSeen: undefined }), "other");
});
