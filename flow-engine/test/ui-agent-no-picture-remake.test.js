/**
 * Owner's decision (2026-11-04): a still request after which no picture appeared anywhere (whole gallery scanned, page-wide
 * image count has no Flow image) is made again automatically: now on the standard path, and by any later Generate. Live:
 * Account 7, 12 scenes, 0 tiles after 5 min, then all 12 blocked on the next Generate until Retry.
 * Videos, and any request where Flow did show a picture, keep the Retry-only rule (billing-safety.test.js).
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { runAgentSlice, resetUiBatchCaps, noPictureAnywhere } = await import("../lib/agent-runner.js");
const { GenerationLedger, LedgerState } = await import("../lib/generation-ledger.js");

const AVATAR_ONLY = { "img lh3.google.com/u 32x32": 1 };
const CHAT_COPY = { "img lh3.google.com/u 32x32": 1, 'img flow.google.com/asb 1376x768 alt="Option 1"': 1 };

function setup() {
  resetUiBatchCaps();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-no-pic-"));
  const out = path.join(dir, "out");
  fs.mkdirSync(out, { recursive: true });
  return { out, file: path.join(dir, "ledger.json") };
}

async function runUi({ out, ledger, diag }) {
  const standard = [];
  const events = [];
  const prompts = ["a red barn at dawn in the snow", "a blue tram on a hill street", "a green kite over a beach"];
  await runAgentSlice({
    page: {}, prompts, promptIndices: [0, 1, 2], promptKeys: ["1", "2", "3"], totalAbsolute: 3,
    settings: { mediaKind: "image", generationMode: "agent", agentViaUi: true, model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
      outputDir: out, _runId: "run-1", agentBatchGapMs: 0, agentMinScenes: 1 },
    folderLabel: "acct-7", accountId: "acct-7", accountLabel: "Account 7", shouldStop: () => false,
    onProgress: (e) => events.push(e),
    deps: {
      ledger, sleep: async () => {}, openOrCreateProject: async () => "proj-1", waitForFlowReady: async () => {},
      runBatchSlice: async ({ prompts: ps, promptIndices, onProgress }) => {
        standard.push(...promptIndices);
        ps.forEach((p, i) => onProgress({ type: "PROMPT_RESULT", index: promptIndices[i], prompt: p, status: "done", path: "/std" }));
        return { completed: ps.length, failed: 0, reassign: [] };
      },
      generateAgentBatchViaUI: async () => ({ clicked: true, images: [], diag: { outcome: "timeout_no_media", ...diag } }),
    },
  });
  return { standard, results: events.filter((e) => e.type === "PROMPT_RESULT") };
}

test("no picture anywhere after the wait: the scenes go to the standard path in the same run", async () => {
  const { out, file } = setup();
  const { standard, results } = await runUi({ out, ledger: new GenerationLedger(file), diag: { rawTileCount: 0, mediaInventory: AVATAR_ONLY } });
  assert.deepEqual(standard.sort(), [0, 1, 2]);
  assert.ok(results.every((r) => r.status === "done"), JSON.stringify(results));
  const entries = Object.values(JSON.parse(fs.readFileSync(file, "utf8")).entries);
  assert.ok(entries.every((e) => e.state === LedgerState.SUBMITTED_UNKNOWN && e.noMediaSeen === true));
});

test("a later Generate re-makes such a still without Retry; videos and known media stay Retry-only", () => {
  const { file } = setup();
  const l = new GenerationLedger(file);
  l.put("img", { state: LedgerState.SUBMITTED_UNKNOWN, mediaKind: "image", accountId: "A", noMediaSeen: true });
  assert.equal(l.decide("img", { accountId: "B", runId: "r2" }).action, "submit");
  l.put("vid", { state: LedgerState.SUBMITTED_UNKNOWN, mediaKind: "video", accountId: "A", noMediaSeen: true });
  assert.equal(l.decide("vid", { accountId: "A", runId: "r2" }).action, "block");
  l.put("plain", { state: LedgerState.SUBMITTED_UNKNOWN, mediaKind: "image", accountId: "A" });
  assert.equal(l.decide("plain", { accountId: "A", runId: "r2" }).action, "block");
  l.put("stop", { state: LedgerState.SUBMITTING, mediaKind: "image", accountId: "A", noMediaSeen: true });
  assert.equal(l.decide("stop", { accountId: "A", runId: "r2" }).action, "block", "only a finished wait with nothing seen counts");
});

test("any picture on the page (a chat copy too), a refusal, or a missing count keeps the old needs-action rule", async () => {
  assert.equal(noPictureAnywhere({ rawTileCount: 0, mediaInventory: AVATAR_ONLY }), true);
  assert.equal(noPictureAnywhere({ rawTileCount: 0, mediaInventory: CHAT_COPY }), false);
  assert.equal(noPictureAnywhere({ rawTileCount: 0, refused: true, mediaInventory: AVATAR_ONLY }), false);
  assert.equal(noPictureAnywhere({ rawTileCount: 0 }), false);
  assert.equal(noPictureAnywhere({ rawTileCount: 3, mediaInventory: AVATAR_ONLY }), false);

  const { out, file } = setup();
  const { standard, results } = await runUi({ out, ledger: new GenerationLedger(file), diag: { rawTileCount: 0, mediaInventory: CHAT_COPY } });
  assert.deepEqual(standard, []);
  assert.ok(results.every((r) => r.status === "failed" && r.needsAction), JSON.stringify(results));
});
