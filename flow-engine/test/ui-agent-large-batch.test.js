/**
 * UI Agent with real-length prompts (2026-10-20): ~1,900-char prompts with a shared character/style block in the middle.
 * 20-24 scenes per paste, long tile prompts kept, reworded tiles matched only on a clear winner, a cut paste split in two,
 * an unmatched scene made again (never guessed), and leftover standard-path scenes shared across accounts.
 * Flow is a fake (no network, no credits). Run: node --test test/ui-agent-large-batch.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { splitSharedForUiAgent, mapUiTilesToScenes, buildUiAgentMessage } = await import("../lib/agent-api.js");
const { runAgentSlice, resetUiBatchCaps, uiBatchCapFor, noteUiBatchResult } = await import("../lib/agent-runner.js");
const { planPoolBatches, runAgentPool } = await import("../lib/agent-pool.js");
const { isBulkAgentMessage } = await import("../lib/flow-ui-agent.js");
const { GenerationLedger } = await import("../lib/generation-ledger.js");
const { Submission, tagSubmission } = await import("../lib/generation-state.js");
const { agent: agentConfig } = await import("../config.js");

const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(200, 1)]);

// Deterministic words so every scene has its own vocabulary, like real scene descriptions.
const VOCAB = ("kitchen grill tray nuggets flames tile counter booth manager cashier window parking lot rain neon sign " +
  "uniform collar sleeve paper hat fryer basket oil smoke alarm ceiling light pendant amber navy shadow mop bucket floor " +
  "customer receipt register drawer coin straw cup lid soda fountain ice machine freezer door handle shelf box sauce " +
  "packet napkin dispenser trash bin bag alley dumpster cat bicycle van delivery driver clipboard schedule poster wall " +
  "clock noon midnight dawn dusk storm thunder window glass reflection puddle sidewalk crosswalk truck bus stop bench")
  .split(" ");
function sceneWords(i, n = 170) {
  let x = (i + 1) * 2654435761 >>> 0;
  const out = [];
  for (let k = 0; k < n; k++) {
    x = (x * 1103515245 + 12345) >>> 0;
    out.push(VOCAB[x % VOCAB.length]);
  }
  return `Scene ${i + 1} shot: ${out.join(" ")}.`;
}
const SHARED = [
  "EDDIE IDENTITY LOCK: the same 27-year-old stick-figure cartoon protagonist from the reference screenshots.",
  "Oversized smooth circular white head, enormous circular white eyes with small black pupils, thick black eyebrows, messy brown spiky hair.",
  "Preserve the same facial structure, hair silhouette, anatomy, and overall character identity.",
  "Never generate a fully anatomical cartoon human.",
  "Premium hand-drawn cinematic American 2D cartoon with warm amber pendant lights and deep navy shadows.",
];
const longPrompt = (i) => `${sceneWords(i)} ${SHARED.join(" ")} Single 16:9 still frame, scene ${i + 1}.`;
const PROMPTS = (n) => Array.from({ length: n }, (_, i) => longPrompt(i));

function setup() {
  resetUiBatchCaps();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-ui-large-"));
  const out = path.join(dir, "flow", "runs", "run-1");
  fs.mkdirSync(out, { recursive: true });
  return { out, ledger: new GenerationLedger(path.join(dir, "ledger.json")) };
}

function fakeFlow(ui) {
  const calls = { ui: [], standard: [] };
  const deps = {
    sleep: async () => {},
    openOrCreateProject: async () => "proj-1",
    waitForFlowReady: async () => {},
    fetchImageUrl: async (_p, id) => `https://flow-content.google/image/${id}`,
    downloadMedia: async (_p, _id, dest) => { fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, PNG); },
    sendAgentMessage: async () => { throw new Error("RPC agent must not run"); },
    createAgentChat: async () => { throw new Error("RPC agent must not run"); },
    runBatchSlice: async ({ prompts, promptIndices, onProgress }) => {
      calls.standard.push(...promptIndices);
      prompts.forEach((p, i) => onProgress({ type: "PROMPT_RESULT", index: promptIndices[i], prompt: p, status: "done", path: "/std" }));
      return { completed: prompts.length, failed: 0, reassign: [] };
    },
    generateAgentBatchViaUI: async (page, args) => { calls.ui.push(args); return ui(args, calls.ui.length); },
  };
  return { deps, calls };
}

/** The scene lines of a pasted message, as the agent would make them into prompts (scene text + shared details). */
function scenesIn(message) {
  const shared = (/^Shared details[^:]*: (.*)$/m.exec(message) || [])[1] || "";
  return [...message.matchAll(/^S(\d{2,3}): (.*)$/gm)].map((m) => ({ id: Number(m[1]), text: m[2], prompt: `${m[2]} ${shared}`.trim() }));
}
const tile = (prompt, k) => ({ mediaId: `asb-${k}`, fifeUrl: `https://flow.google.com/asb/t${k}=s0`, prompt, ariaLabel: "" });

async function run({ flow, ledger, out, prompts }) {
  const events = [];
  await runAgentSlice({
    page: {}, prompts, promptIndices: prompts.map((_, i) => i), promptKeys: prompts.map((_, i) => String(i + 1)), totalAbsolute: prompts.length,
    settings: { mediaKind: "image", generationMode: "agent", agentViaUi: true, model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
      outputDir: out, _runId: "run-1", agentBatchGapMs: 0, agentMinScenes: 1 },
    folderLabel: "acct-A", accountId: "acct-A", accountLabel: "acct-A", shouldStop: () => false,
    onProgress: (e) => events.push(e), deps: { ...flow.deps, ledger },
  });
  return events.filter((e) => e.type === "PROMPT_RESULT");
}

test("shared sentences in the middle of every prompt are lifted out once; each scene keeps its own words", () => {
  const ps = PROMPTS(24);
  const s = splitSharedForUiAgent(ps);
  assert.ok(s.shared.includes("EDDIE IDENTITY LOCK"));
  assert.ok(s.shared.includes("Never generate a fully anatomical cartoon human."));
  s.texts.forEach((t, i) => {
    assert.ok(!t.includes("EDDIE IDENTITY LOCK"));
    assert.ok(t.startsWith(`Scene ${i + 1} shot:`));
  });
});

test("24 real-length scenes fit one UI Agent request (they took 4+ under the old 12k limit)", () => {
  const its = PROMPTS(24).map((prompt, index) => ({ index, prompt, promptKey: String(index + 1) }));
  const ui = planPoolBatches(its, { ui: true, maxChars: agentConfig.uiMaxMessageChars });
  assert.deepEqual(ui.map((b) => b.length), [24]);
  assert.ok(planPoolBatches(its, { maxChars: 12000 }).length >= 3);
  const msg = buildUiAgentMessage(splitSharedForUiAgent(PROMPTS(24)).texts, { shared: splitSharedForUiAgent(PROMPTS(24)).shared });
  assert.ok(msg.length <= agentConfig.uiMaxMessageChars, `message ${msg.length} chars`);
  assert.equal(msg.split("EDDIE IDENTITY LOCK").length - 1, 1, "the shared block is carried once");
});

test("a long tile prompt is a real prompt; only the pasted scene list is rejected", () => {
  assert.equal(isBulkAgentMessage(longPrompt(0)), false);
  assert.ok(longPrompt(0).length > 1000);
  assert.equal(isBulkAgentMessage(buildUiAgentMessage(["a", "b"])), true);
  assert.equal(isBulkAgentMessage("S01: one scene\nS02: another"), true);
});

test("a tile the agent trimmed is matched by its words only when one scene clearly wins", () => {
  const texts = splitSharedForUiAgent(PROMPTS(6)).texts;
  // Tile 0: scene 3 with its last 25 words dropped and a few added (agent tidy-up). Tile 1: half scene 1, half scene 2.
  const trimmed = texts[3].split(" ").slice(0, -25).join(" ") + " cinematic lighting";
  const w1 = texts[1].split(" ");
  const w2 = texts[2].split(" ");
  const blend = [...w1.slice(0, w1.length / 2), ...w2.slice(w2.length / 2)].join(" ");
  const m = mapUiTilesToScenes(texts, [tile(trimmed, 0), tile(blend, 1)]);
  assert.equal(m.mapping.get(3).tile.mediaId, "asb-0");
  assert.equal(m.mapping.get(3).method, "words");
  assert.equal(m.mapping.has(1), false, "an unclear tile never goes to a scene");
  assert.equal(m.mapping.has(2), false);
  assert.equal(m.extraTiles.length, 1);
});

test("24 long scenes: one paste, every image tied to its own scene whatever the gallery order", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow(({ message, expectedCount }) => {
    const sc = scenesIn(message);
    assert.equal(expectedCount, 24);
    const order = sc.map((_, k) => k).reverse();
    return { clicked: true, images: order.map((k) => tile(sc[k].prompt, sc[k].id)), diag: { outcome: "success" } };
  });
  const results = await run({ flow, ledger, out, prompts: PROMPTS(24) });
  assert.equal(flow.calls.ui.length, 1);
  assert.equal(results.filter((r) => r.status === "done").length, 24);
  for (const r of results) assert.equal(r.mediaIds[0], `asb-${r.index + 1}`, `scene ${r.index} got its own image`);
  assert.equal(uiBatchCapFor("acct-A"), 24);
});

test("a paste Flow cut is never sent: the batch goes again as two halves", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow(({ message, expectedCount }, n) => {
    if (n === 1) {
      const e = new Error("Flow kept 20000 of 38000 characters of the scene list");
      e.pasteTruncated = true;
      throw tagSubmission(e, Submission.NOT_SUBMITTED);
    }
    const sc = scenesIn(message);
    assert.equal(sc.length, expectedCount);
    return { clicked: true, images: sc.map((x) => tile(x.prompt, x.id + n * 100)), diag: { outcome: "success" } };
  });
  const results = await run({ flow, ledger, out, prompts: PROMPTS(24) });
  assert.deepEqual(flow.calls.ui.map((c) => c.expectedCount), [24, 12, 12]);
  assert.equal(results.filter((r) => r.status === "done").length, 24);
  assert.equal(flow.calls.standard.length, 0);
});

test("a scene with no certain image is made again, not left for Retry, and the next request is smaller", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow(({ message }) => {
    const sc = scenesIn(message);
    // 6 of 24 tiles come back with an unreadable/unrelated prompt.
    const images = sc.map((x, k) => tile(k < 6 ? `mystery picture number ${k}` : x.prompt, x.id));
    return { clicked: true, images, diag: { outcome: "partial" } };
  });
  const results = await run({ flow, ledger, out, prompts: PROMPTS(24) });
  const done = results.filter((r) => r.status === "done");
  assert.equal(done.length, 24);
  assert.equal(results.filter((r) => r.needsAction).length, 0);
  assert.deepEqual(flow.calls.standard.sort((a, b) => a - b), [0, 1, 2, 3, 4, 5], "the 6 unmatched scenes were made again");
  for (const r of done.filter((x) => x.via === "agent")) assert.equal(r.mediaIds[0], `asb-${r.index + 1}`);
  assert.equal(uiBatchCapFor("acct-A"), 16);
});

test("the request size steps down on poor matches and back up on clean ones", () => {
  resetUiBatchCaps();
  assert.equal(noteUiBatchResult("x", { size: 24, matched: 10 }), 16);
  assert.equal(noteUiBatchResult("x", { size: 16, matched: 5 }), 12);
  assert.equal(noteUiBatchResult("x", { size: 12, matched: 1 }), 8);
  assert.equal(noteUiBatchResult("x", { size: 8, matched: 0 }), 8);
  assert.equal(noteUiBatchResult("x", { size: 8, matched: 8 }), 12);
  assert.equal(noteUiBatchResult("x", { size: 12, matched: 12 }), 16);
  assert.equal(noteUiBatchResult("x", { size: 16, matched: 16 }), 24);
});

test("leftover standard-path scenes are shared across every healthy account, not one", async () => {
  const items = Array.from({ length: 30 }, (_, i) => ({ index: i, prompt: `scene ${i} with its own subject ${i}x`, promptKey: String(i + 1) }));
  const standard = [];
  const res = await runAgentPool({
    items, accounts: [1, 2, 3, 4].map((i) => ({ id: `a${i}`, label: `A${i}` })),
    prepare: async (a) => ({ page: a.id }),
    // The agent makes nothing: every scene comes back for the standard path (after the extra round).
    runSlice: async ({ items: its }) => ({ completed: 0, failed: 0, reassign: [], fallback: its.map((x) => ({ index: x.index, prompt: x.prompt, promptKey: x.promptKey })) }),
    runStandard: async ({ account, items: its }) => { standard.push({ account: account.id, n: its.length }); return {}; },
    sleep: async () => {}, now: () => 0, batchGapMs: 0, maxRounds: 1,
  });
  assert.equal(res.unrun.length, 0);
  assert.equal(standard.length, 4);
  assert.equal(standard.reduce((n, s) => n + s.n, 0), 30);
});

test("agent images are downloaded several at once, each to its own scene file", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow(({ message }) => {
    const sc = scenesIn(message);
    return { clicked: true, images: sc.map((x) => tile(x.prompt, x.id)), diag: { outcome: "success" } };
  });
  let active = 0;
  let peak = 0;
  const write = flow.deps.downloadMedia;
  flow.deps.downloadMedia = async (...a) => {
    active++;
    peak = Math.max(peak, active);
    await new Promise((r) => setTimeout(r, 20));
    await write(...a);
    active--;
  };
  const results = await run({ flow, ledger, out, prompts: PROMPTS(12) });
  assert.equal(results.filter((r) => r.status === "done").length, 12);
  assert.equal(peak, agentConfig.downloadParallel);
  for (const r of results) assert.equal(path.basename(r.path), `${String(r.index + 1).padStart(3, "0")}.png`);
});
