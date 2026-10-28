/**
 * Reference images for Flow image generation (2026-10-28). Flow is a fake (no network, no credits).
 * Run: node --test test/flow-references.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const {
  validateReferenceImages, referenceKeyOf, withReferenceSettings, attachReferenceImages, MAX_REFERENCES, MAX_REFERENCE_BYTES,
} = await import("../lib/flow-references.js");
const { generationKey } = await import("../lib/generation-ledger.js");
const { runAgentSlice, resetUiBatchCaps } = await import("../lib/agent-runner.js");
const { GenerationLedger } = await import("../lib/generation-ledger.js");
const { Submission, tagSubmission } = await import("../lib/generation-state.js");

function tmp() { return fs.mkdtempSync(path.join(os.tmpdir(), "flow-refs-")); }
function pic(dir, name, bytes = 64) { const f = path.join(dir, name); fs.writeFileSync(f, Buffer.alloc(bytes, 7)); return f; }

test("validation: absolute existing pictures, at most three, supported types, size limits", () => {
  const d = tmp();
  const a = pic(d, "a.jpg"), b = pic(d, "b.png");
  assert.deepEqual(validateReferenceImages([a, b]), [a, b]);
  assert.deepEqual(validateReferenceImages(null), []);
  assert.deepEqual(validateReferenceImages([]), []);
  assert.throws(() => validateReferenceImages([a, a]), /listed twice/);
  assert.throws(() => validateReferenceImages([path.join(d, "missing.jpg")]), /not found/);
  assert.throws(() => validateReferenceImages([pic(d, "c.gif")]), /PNG, JPEG or WebP/);
  assert.throws(() => validateReferenceImages([pic(d, "e.jpg", 0)]), /empty/);
  const many = [1, 2, 3, 4].map((i) => pic(d, `m${i}.jpg`));
  assert.equal(MAX_REFERENCES, 3);
  assert.throws(() => validateReferenceImages(many), /at most 3/);
  const big = path.join(d, "big.jpg"); fs.writeFileSync(big, Buffer.alloc(MAX_REFERENCE_BYTES + 1));
  assert.throws(() => validateReferenceImages([big]), /limit is 10 MB/);
  assert.throws(() => validateReferenceImages("a.jpg"), /list of file paths/);
});

test("reference key: order-independent, changes with a different picture, null without references", () => {
  const d = tmp();
  const a = pic(d, "a.jpg", 10), b = pic(d, "b.jpg", 20);
  assert.equal(referenceKeyOf([a, b]), referenceKeyOf([b, a]));
  assert.notEqual(referenceKeyOf([a]), referenceKeyOf([a, b]));
  const a2 = pic(tmp(), "a.jpg", 11);
  assert.notEqual(referenceKeyOf([a]), referenceKeyOf([a2]), "the same name with other content is another reference");
  assert.equal(referenceKeyOf([]), null);
});

test("ledger key: unchanged without references, different with them (same prompt, other pictures = another image)", () => {
  const base = { mediaKind: "image", prompt: "a phone", settings: { model: "M", aspectRatio: "L" }, scope: "s" };
  assert.equal(generationKey(base), generationKey({ ...base, settings: { ...base.settings, referenceKey: null } }));
  assert.equal(generationKey(base), generationKey({ ...base, settings: { ...base.settings, referenceKey: "" } }));
  const k1 = generationKey({ ...base, settings: { ...base.settings, referenceKey: "aaaa" } });
  const k2 = generationKey({ ...base, settings: { ...base.settings, referenceKey: "bbbb" } });
  assert.notEqual(k1, generationKey(base));
  assert.notEqual(k1, k2);
  assert.equal(k1, generationKey({ ...base, settings: { ...base.settings, referenceKey: "aaaa" } }), "identical references stay deduplicated");
  // the exact key a run without references got before this change (a recorded value): it must not move
  assert.equal(generationKey({ mediaKind: "image", prompt: "x", settings: {}, scope: "" }),
    generationKey({ mediaKind: "image", prompt: "x", settings: { referenceImages: ["z.jpg"] }, scope: "" }), "paths alone are not identity; the key is");
});

test("settings with references go the UI agent route, even for one scene, with no standard-path fallback", () => {
  const d = tmp();
  const a = pic(d, "a.jpg");
  const s = withReferenceSettings({ mediaKind: "image", generationMode: "standard", agentFallback: true }, {});
  assert.equal(s.generationMode, "standard", "no references: untouched");
  const r = withReferenceSettings({ mediaKind: "image", generationMode: "standard", referenceImages: [a] });
  assert.equal(r.generationMode, "agent");
  assert.equal(r.agentViaUi, true);
  assert.equal(r.agentFallback, false);
  assert.equal(r.agentMinScenes, 1);
  assert.ok(r.referenceKey && r.referenceKey.length === 16);
  assert.deepEqual(r.referenceImages, [a]);
  assert.throws(() => withReferenceSettings({ referenceImages: [path.join(d, "none.jpg")] }), /not found/);
});

// ---- a fake Flow composer: the picker, the upload chooser and "Add to prompt" -----------------------------------------------------
function fakePage({ assets = [], failUpload = false, noAddButton = false } = {}) {
  const log = [];
  const state = { picker: false, assets: [...assets], attached: [], selected: null, chooserFiles: null };
  const names = (files) => files.map((f) => path.basename(f));
  const loc = (kind, key) => ({
    first() { return this; },
    async waitFor({ timeout } = {}) {
      if (kind === "add" && noAddButton) throw new Error("timeout");
      if (kind === "button" && /upload/i.test(key) && !state.picker) throw new Error("timeout");
      if (kind === "button" && /add to prompt/i.test(key) && !state.selected) throw new Error("timeout");
      if (kind === "text") {
        const hit = state.assets.find((n) => n.includes(key)) && state.picker && !state.attached.includes(key);
        if (!hit) throw new Error("timeout");
      }
    },
    async click() {
      log.push(`click:${kind}:${key}`);
      if (kind === "add") state.picker = true;
      if (kind === "text") state.selected = key;
      if (kind === "button" && /add to prompt/i.test(key)) { state.attached.push(state.selected); state.selected = null; state.picker = false; }
      if (kind === "button" && /upload/i.test(key)) state._uploadClicked = true;
    },
  });
  const page = {
    locator: (sel) => loc(sel.includes("Add ingredients") ? "add" : "other", sel),
    getByRole: (_role, { name }) => loc("button", String(name)),
    getByText: (text) => loc("text", text),
    waitForEvent: async (ev) => {
      assert.equal(ev, "filechooser");
      return new Promise((resolve, reject) => {
        state._resolveChooser = () => resolve({ setFiles: async (files) => {
          if (failUpload) return;                       // Flow ignored the files
          state.chooserFiles = names(files); state.assets.push(...names(files));
          log.push(`upload:${names(files).join(",")}`);
        } });
        setTimeout(() => (state._uploadClicked ? state._resolveChooser() : null), 0);
        setTimeout(() => state._resolveChooser(), 5);
        void reject;
      });
    },
  };
  return { page, log, state };
}

test("attach: uploads only what the project lacks, then attaches each picture one by one", async () => {
  const d = tmp();
  const a = pic(d, "ref1_fan_backs.jpg"), b = pic(d, "ref4_blue.jpg");
  const { page, log, state } = fakePage({ assets: ["ref1_fan_backs.jpg"] });          // ref1 already in the project
  const r = await attachReferenceImages(page, [a, b], { timeoutMs: 200, probeMs: 20, settleMs: 0 });
  assert.deepEqual(r.uploaded, ["ref4_blue.jpg"], "ref1 was already there: not uploaded twice");
  assert.deepEqual(r.attached, ["ref1_fan_backs.jpg", "ref4_blue.jpg"]);
  assert.deepEqual(state.attached, ["ref1_fan_backs.jpg", "ref4_blue.jpg"]);
  assert.equal(log.filter((l) => l.startsWith("upload:")).length, 1);
});

test("attach: nothing asked, nothing touched", async () => {
  const { page, log } = fakePage();
  const r = await attachReferenceImages(page, [], { timeoutMs: 50, settleMs: 0 });
  assert.deepEqual(r, { attached: [], uploaded: [] });
  assert.equal(log.length, 0);
});

test("attach: a picture Flow does not list after the upload is an error (nothing sent)", async () => {
  const d = tmp();
  const a = pic(d, "ref9.jpg");
  const { page } = fakePage({ failUpload: true });
  await assert.rejects(() => attachReferenceImages(page, [a], { timeoutMs: 60, probeMs: 10, settleMs: 0 }), /did not list the uploaded reference image ref9.jpg/);
});

test("attach: a missing Add-ingredients button is an error, not a silent skip", async () => {
  const d = tmp();
  const a = pic(d, "ref1.jpg");
  const { page } = fakePage({ noAddButton: true });
  await assert.rejects(() => attachReferenceImages(page, [a], { timeoutMs: 40, probeMs: 10, settleMs: 0 }));
});

// ---- the runner hands the pictures to the UI agent and never falls back without them -----------------------------------------------
function runnerDeps(calls) {
  return {
    sleep: async () => {},
    openOrCreateProject: async () => "proj-1",
    waitForFlowReady: async () => {},
    fetchImageUrl: async () => "https://flow-content.google/image/x",
    downloadMedia: async () => {},
    sendAgentMessage: async () => { throw new Error("RPC agent must not run"); },
    createAgentChat: async () => { throw new Error("RPC agent must not run"); },
    runBatchSlice: async ({ prompts, promptIndices }) => { calls.standard.push(...promptIndices); return { completed: prompts.length, failed: 0, reassign: [] }; },
    generateAgentBatchViaUI: async (_page, args) => { calls.ui.push(args); throw tagSubmission(new Error("Reference images were not attached, nothing was sent: test"), Submission.NOT_SUBMITTED); },
  };
}

test("runner: references reach the UI agent call; a failed attach does not fall back to the standard path", async () => {
  resetUiBatchCaps();
  const dir = tmp();
  const out = path.join(dir, "flow", "runs", "run-1");
  fs.mkdirSync(out, { recursive: true });
  const a = pic(dir, "ref1.jpg");
  const settings = withReferenceSettings({ mediaKind: "image", model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE", outputDir: out, _runId: "run-1", agentBatchGapMs: 0, referenceImages: [a] });
  const calls = { ui: [], standard: [] };
  const events = [];
  await runAgentSlice({
    page: {}, prompts: ["one scene only"], promptIndices: [0], promptKeys: ["1"], totalAbsolute: 1, settings,
    folderLabel: "acct-A", accountId: "acct-A", accountLabel: "acct-A", shouldStop: () => false, onProgress: (e) => events.push(e),
    deps: { ...runnerDeps(calls), ledger: new GenerationLedger(path.join(dir, "ledger.json")) },
  });
  assert.equal(calls.ui.length, 1, "a single scene still goes through the UI agent");
  assert.deepEqual(calls.ui[0].referenceImages, [a]);
  assert.deepEqual(calls.standard, [], "no standard-path generation without the references");
  const failed = events.filter((e) => e.type === "PROMPT_RESULT" && e.status === "failed");
  assert.equal(failed.length, 1);
});
