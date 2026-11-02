/**
 * Live 2026-11-02 (project #054): on Accounts 6 and 7 Flow's page showed no settings control, so single pictures failed, the
 * account reloaded and tried the same scene again and again (and stepped through image models) for 20+ minutes while other
 * accounts sat idle. Now: one reload, then the scene goes to another account (or that account's agent panel); a scene never
 * retries forever; the model is never switched for a page problem. Flow is faked (no network, no credits).
 * Run: node --test test/layout-handoff.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { runBatchSlice, MAX_RETRY_ATTEMPTS } = await import("../lib/batch-runner.js");
const { GenerationLedger } = await import("../lib/generation-ledger.js");
const { Submission, tagSubmission } = await import("../lib/generation-state.js");
const { MissingMediaIdError } = await import("../lib/flow-api.js");
const { runAgentPool } = await import("../lib/agent-pool.js");

const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47]), Buffer.alloc(200, 1)]);
const noSettings = () => {
  const e = new MissingMediaIdError("Flow UI generation did not produce an image (outcome: no_visible_settings_control)");
  e.layoutUnsupported = true;
  return tagSubmission(e, Submission.NOT_SUBMITTED);
};
const notSent = () => tagSubmission(new MissingMediaIdError("No mediaId — page not ready"), Submission.NOT_SUBMITTED);

async function run(outcomes, prompts = ["scene one", "scene two"]) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-layout-"));
  const out = path.join(dir, "flow", "runs", "run-1"); fs.mkdirSync(out, { recursive: true });
  const calls = { submit: 0, models: [], reloads: 0 };
  const deps = {
    sleep: async () => {}, openOrCreateProject: async () => "proj-1", createFlowProject: async () => "proj-2", flowGoto: async () => {},
    waitForFlowReady: async () => {}, checkFlowReady: async () => ({ hasProject: true, hasRecaptcha: true }), flowReload: async () => { calls.reloads++; },
    generateOneMedia: async (_p, _pid, _prompt, s) => {
      calls.submit++; calls.models.push(s?.model);
      const o = outcomes.length ? outcomes.shift() : "ok";
      if (o === "ok") return { mediaId: `m-${calls.submit}`, fifeUrl: null, via: "ui" };
      throw o();
    },
    downloadMedia: async (_p, _id, dest) => { fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, PNG); },
    ledger: new GenerationLedger(path.join(dir, "ledger.json")),
  };
  const events = [];
  const result = await runBatchSlice({
    page: {}, prompts, promptIndices: prompts.map((_, i) => i), promptKeys: prompts.map((_, i) => `scene-${i + 1}`), totalAbsolute: prompts.length,
    settings: { mediaKind: "image", outputDir: out, delayMin: 0, delayMax: 0, refreshFrequency: 1000, _runId: "run-1", model: "GEM_PIX_2" },
    folderLabel: "acct-6", accountId: "acct-6", accountLabel: "acct-6", shouldStop: () => false, onProgress: (e) => events.push(e), deps,
  });
  return { result, calls, results: events.filter((e) => e.type === "PROMPT_RESULT") };
}

test("no settings control: one reload, then this scene and the rest are handed on — no model switch, no endless loop", async () => {
  const { result, calls } = await run([noSettings, noSettings]);
  assert.equal(calls.submit, 2, "the first try and one try after a reload");
  assert.ok(calls.models.every((m) => m === "GEM_PIX_2"), "the image model never changes for a page problem");
  assert.deepEqual(result.reassign.map((r) => [r.index, r.reason]), [[0, "layout"], [1, "layout"]]);
  assert.equal(result.failed, 0);
});

test("no settings control once, fine after the reload: the scene is made on this account", async () => {
  const { result } = await run([noSettings, "ok", "ok"]);
  assert.equal(result.completed, 2);
  assert.deepEqual(result.reassign, []);
});

test(`a scene that keeps failing stops after ${MAX_RETRY_ATTEMPTS} tries with its reason, instead of retrying forever`, async () => {
  const { result, results, calls } = await run(Array(50).fill(notSent), ["scene one"]);
  assert.ok(calls.submit <= MAX_RETRY_ATTEMPTS + 1, `tried ${calls.submit} times`);
  assert.equal(result.failed, 1);
  assert.match(results.at(-1).error || "", /Gave up after|No mediaId/);
});

test("pool: scenes an account hands back are made — layout on its own agent panel, others on another account", async () => {
  const log = [];
  const accounts = [{ id: "acct-1" }, { id: "acct-6" }];
  const res = await runAgentPool({
    items: [0, 1, 2].map((i) => ({ index: i, prompt: `scene ${i} words ${i}x`, promptKey: String(i + 1) })), accounts, minScenes: 5,
    prepare: async (a) => ({ page: a.id }), sleep: async () => {}, now: () => 0, batchGapMs: 0,
    runSlice: async ({ account, items }) => {
      log.push(["agent", account.id, items.map((x) => x.index)]);
      const first = log.filter((x) => x[0] === "agent").length === 1;      // the first agent request makes nothing: its scenes go one by one
      return first ? { completed: 0, fallback: items.map((x) => ({ index: x.index, prompt: x.prompt, promptKey: x.promptKey })) } : { completed: items.length, fallback: [] };
    },
    runStandard: async ({ account, items }) => {
      log.push(["standard", account.id, items.map((x) => x.index)]);
      if (account.id === "acct-6" && log.filter((x) => x[1] === "acct-6").length === 1) return { reassign: items.map((x) => ({ index: x.index, prompt: x.prompt, promptKey: x.promptKey, reason: "layout" })) };
      return { reassign: [] };
    },
  });
  const sixAgent = log.find((x) => x[0] === "agent" && x[1] === "acct-6");
  assert.ok(sixAgent, "the scenes Account 6 could not make one by one went through its agent panel");
  assert.deepEqual(res.unrun, []);
});

test("an account that handed a scene back for its page layout takes no more single scenes in this job", async () => {
  const { exhaustsAccount, failMessageForPending } = await import("../lib/orchestrator.js");
  assert.equal(exhaustsAccount("layout"), true);
  assert.equal(exhaustsAccount("quota"), true);
  assert.equal(exhaustsAccount("auth_expired"), false, "a signed-out account is handled by its own path");
  assert.match(failMessageForPending({ reason: "layout" }), /settings control/);
});
