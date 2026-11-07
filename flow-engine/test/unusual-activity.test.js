/**
 * "Unusual activity" on 2 of 4-5 Flow windows at the start (owner, 2026-11-07). The ledger showed Google refusing accounts 5-8
 * on their FIRST request of a run, with plain prompts, after several accounts fired within 3 s from one machine. So:
 * 1. accounts start one after another (agent.startGapMs apart), never all in the same second;
 * 2. "unusual activity" shown on the page (UI and agent modes) is recognised: only below our own message or in a banner/dialog,
 *    never an old message higher up the chat;
 * 3. such an account rests (cool-down) and its scenes go to the other accounts at once, marked as not made (safe to send again),
 *    instead of the request waiting out its whole reply time.
 * Flow is a fake (no network, no credits). Run: node --test test/unusual-activity.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { unusualIn, pasteMarker } = await import("../lib/flow-ui-agent.js");
const { runAgentPool } = await import("../lib/agent-pool.js");
const { runAgentSlice, resetUiBatchCaps, UNUSUAL_ON_PAGE } = await import("../lib/agent-runner.js");
const { GenerationLedger, LedgerState } = await import("../lib/generation-ledger.js");
const { tagSubmission, Submission } = await import("../lib/generation-state.js");
const { agent: agentConfig } = await import("../config.js");

test("unusual activity is read below our message or in a banner, never from older chat", () => {
  const msg = "Make these images:\nS01: a red barn at dawn in the snow\nS02: a blue tram on a hill street";
  const marker = pasteMarker(msg);
  assert.equal(unusualIn({ body: `${msg}\nWe noticed unusual activity. Please try again later.`, marker }), true);
  assert.equal(unusualIn({ body: `Earlier: unusual activity detected.\n${msg}\nGenerating 2 images...`, marker }), false, "old message above ours");
  assert.equal(unusualIn({ body: "unusual activity", marker }), false, "our message not on the page: not assumed");
  assert.equal(unusualIn({ alerts: "Our systems have detected unusual traffic from your computer network" }), true, "banner or dialog");
  assert.equal(unusualIn({ body: `${msg}\nGenerating 2 images...`, marker, alerts: "" }), false);
});

test("accounts start one after another, startGapMs apart (default 20 s)", async () => {
  assert.ok(agentConfig.startGapMs >= 15000, "a real gap by default");
  let t = 0;
  const firstAt = new Map();
  const notes = [];
  const accounts = [1, 2, 3, 4].map((i) => ({ id: `a${i}`, label: `Account ${i}` }));
  const sleep = async (d) => { t += Math.max(1, d); await new Promise((r) => setImmediate(r)); };
  const items = Array.from({ length: 40 }, (_, i) => ({ index: i, prompt: `scene ${i}: a distinct subject number ${i} in a field` }));
  await runAgentPool({
    items, accounts, prepare: async (a) => ({ page: a.id }), runStandard: async () => ({}),
    runSlice: async ({ account, items: its }) => {
      if (!firstAt.has(account.id)) firstAt.set(account.id, t);
      await sleep(90000);                    // a real agent request takes minutes, so the later accounts still find work
      return { completed: its.length, failed: 0, reassign: [] };
    },
    sleep, now: () => t,
    onAccountState: (a, st, msg) => notes.push(`${a.label} ${st} ${msg}`), batchGapMs: 0, startGapMs: 20000, maxBatch: 10,
  });
  const order = accounts.map((a) => firstAt.get(a.id));
  assert.ok(order.every((x) => x != null), "every account still takes part");
  for (let k = 1; k < order.length; k++) assert.ok(order[k] - order[k - 1] >= 20000 - 1, `account ${k + 1} waited its turn: ${order}`);
  assert.ok(notes.some((n) => /Account 2 waiting starting in 20 s/.test(n)), notes.join("\n"));
});

function setup() {
  resetUiBatchCaps();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-unusual-"));
  const out = path.join(dir, "out");
  fs.mkdirSync(out, { recursive: true });
  return { out, file: path.join(dir, "ledger.json") };
}

async function runUi({ out, ledger, ui }) {
  const events = [];
  const prompts = ["a red barn at dawn in the snow", "a blue tram on a hill street", "a green kite over a beach"];
  const res = await runAgentSlice({
    page: {}, prompts, promptIndices: [0, 1, 2], promptKeys: ["1", "2", "3"], totalAbsolute: 3,
    settings: { mediaKind: "image", generationMode: "agent", agentViaUi: true, model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
      outputDir: out, _runId: "run-1", agentBatchGapMs: 0, agentMinScenes: 1 },
    folderLabel: "acct-7", accountId: "acct-7", accountLabel: "Account 7", shouldStop: () => false,
    onProgress: (e) => events.push(e),
    deps: {
      ledger, sleep: async () => {}, openOrCreateProject: async () => "proj-1", waitForFlowReady: async () => {},
      runBatchSlice: async () => { throw new Error("the standard path must not run on a refused account"); },
      generateAgentBatchViaUI: ui,
    },
  });
  return { res, events };
}

for (const [when, ui] of [
  ["shown after our paste", async () => ({ clicked: true, images: [], diag: { outcome: "unusual_activity", rawTileCount: 0 } })],
  ["already on the page before anything was pasted", async () => {
    const err = new Error("Flow shows 'unusual activity' on this account (before anything was sent)");
    err.unusual = true;
    throw tagSubmission(err, Submission.NOT_SUBMITTED);
  }],
]) {
  test(`unusual activity ${when}: the account rests and every scene goes to the other accounts, marked not made`, async () => {
    const { out, file } = setup();
    const { res, events } = await runUi({ out, ledger: new GenerationLedger(file), ui });
    assert.equal(res.coolDown, UNUSUAL_ON_PAGE);
    assert.deepEqual(res.reassign.map((r) => r.index).sort(), [0, 1, 2]);
    const entries = Object.values(JSON.parse(fs.readFileSync(file, "utf8")).entries);
    assert.ok(entries.every((e) => e.state === LedgerState.REJECTED), "nothing was made: safe to send again");
    assert.ok(events.some((e) => e.type === "status" && /unusual activity.*go to other accounts/.test(e.message)), "a clear line in the log");
  });
}
