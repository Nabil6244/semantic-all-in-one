/**
 * Billing safety of the batch runner: no path may submit the same paid generation twice. The Flow calls are replaced with
 * fakes (runBatchSlice's `deps`) and the ledger lives in a temp file, so these runs spend nothing.
 * Run: node --test test/billing-safety.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { runBatchSlice } = await import("../lib/batch-runner.js");
const { GenerationLedger, LedgerState } = await import("../lib/generation-ledger.js");
const { Submission, tagSubmission, AccountRestrictedError } = await import("../lib/generation-state.js");
const { routeToOwners } = await import("../lib/orchestrator.js");
const { mayFallBackToUi, generateOneMedia } = await import("../lib/generation-dispatch.js");
const { RateLimitError, MissingMediaIdError } = await import("../lib/flow-api.js");

const VIDEO_BYTES = Buffer.concat([Buffer.from([0, 0, 0, 0x20]), Buffer.from("ftypisom"), Buffer.alloc(200, 1)]);
const PNG_BYTES = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47]), Buffer.alloc(200, 1)]);

function tmp() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "flow-billing-"));
}

/** A run folder laid out like the app's: <project>/flow/runs/<run id>. */
function runDir(project, id) {
  const d = path.join(project, "flow", "runs", id);
  fs.mkdirSync(d, { recursive: true });
  return d;
}

/** A fake Flow: counts submissions, scripts each one's outcome, writes downloads. */
function fakeFlow({ outcomes = [], downloads = [], resumes = [] } = {}) {
  const calls = { submit: 0, resume: 0, download: 0, prompts: [] };
  const deps = {
    sleep: async () => {},
    openOrCreateProject: async () => "proj-0001-aaaa",
    createFlowProject: async () => "proj-0002-bbbb",
    flowGoto: async () => {},
    waitForFlowReady: async () => {},
    checkFlowReady: async () => ({ hasProject: true, hasRecaptcha: true }),
    flowReload: async () => {},
    generateOneMedia: async (_page, _pid, prompt, _s, _i, kind, opts) => {
      calls.submit++;
      calls.prompts.push(prompt);
      const o = outcomes.length ? outcomes.shift() : "ok";
      if (typeof o === "function") return o(opts);
      if (o === "ok") return { mediaId: `m-${calls.submit}`, fifeUrl: null, via: "rpc" };
      throw o;
    },
    resumeVideo: async () => {
      calls.resume++;
      const o = resumes.length ? resumes.shift() : "ok";
      if (o === "ok") return { mediaId: `resumed-${calls.resume}`, fifeUrl: null };
      throw o;
    },
    downloadMedia: async (_page, _id, dest) => {
      calls.download++;
      const o = downloads.length ? downloads.shift() : "ok";
      if (o !== "ok") throw o;
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, dest.endsWith(".mp4") ? VIDEO_BYTES : PNG_BYTES);
    },
  };
  return { deps, calls };
}

async function run({ flow, ledger, prompts = ["a ship at dawn"], kind = "video", account = "acct-A", out, runId = "run-1", confirm = false, extra = {} }) {
  const events = [];
  const result = await runBatchSlice({
    page: {},
    prompts,
    promptIndices: prompts.map((_, i) => i),
    promptKeys: prompts.map((_, i) => `scene-${i + 1}`),
    totalAbsolute: prompts.length,
    settings: {
      mediaKind: kind, outputDir: out, delayMin: 0, delayMax: 0, refreshFrequency: 1000, _runId: runId,
      ...(confirm ? { confirmResubmitKeys: prompts.map((_, i) => `scene-${i + 1}`) } : {}), ...extra,
    },
    folderLabel: account,
    accountId: account,
    accountLabel: account,
    shouldStop: () => false,
    onProgress: (e) => events.push(e),
    deps: { ...flow.deps, ledger },
  });
  const results = events.filter((e) => e.type === "PROMPT_RESULT");
  return { result, results, events };
}

const unknown = (msg = "Request timed out") => tagSubmission(new Error(msg), Submission.UNKNOWN);
const accepted = (workflowId, msg = "Video polling failed repeatedly") => tagSubmission(new Error(msg), Submission.ACCEPTED, { workflowId });
const notSent = () => tagSubmission(new MissingMediaIdError("No mediaId — page not ready"), Submission.NOT_SUBMITTED);

test("success: submit -> media id -> download -> completed, exactly one submission", async () => {
  const dir = tmp();
  const ledger = new GenerationLedger(path.join(dir, "ledger.json"));
  const flow = fakeFlow();
  const { results } = await run({ flow, ledger, out: dir });
  assert.equal(flow.calls.submit, 1);
  assert.equal(results[0].status, "done");
  assert.ok(fs.existsSync(results[0].path));
});

test("download failure: the download is retried, the generation is not", async () => {
  const dir = tmp();
  const ledger = new GenerationLedger(path.join(dir, "ledger.json"));
  const flow = fakeFlow({ downloads: [new Error("HTTP 503")] });
  const { results } = await run({ flow, ledger, out: dir });
  assert.equal(flow.calls.submit, 1);
  assert.equal(flow.calls.download, 2);
  assert.equal(results[0].status, "done");
});

test("download failing all run long: kept resumable, and the next run downloads it without generating", async () => {
  const dir = tmp();
  const file = path.join(dir, "ledger.json");
  const flow = fakeFlow({ downloads: [new Error("HTTP 503"), new Error("HTTP 503")] });
  const first = await run({ flow, ledger: new GenerationLedger(file), out: dir });
  assert.equal(first.results[0].status, "failed");
  assert.equal(first.results[0].resumable, true);
  assert.equal(flow.calls.submit, 1);
  const flow2 = fakeFlow();
  const second = await run({ flow: flow2, ledger: new GenerationLedger(file), out: dir, runId: "run-2" });
  assert.equal(flow2.calls.submit, 0, "a known media id is downloaded, never generated again");
  assert.equal(second.results[0].status, "done");
});

test("image DOWNLOAD_FAILED with known mediaId: resume downloads only — generateOneMedia never called", async () => {
  const project = tmp();
  const out = runDir(project, "run-seed");
  const file = path.join(project, "ledger.json");
  const ledger = new GenerationLedger(file);
  const { generationKey, scopeOf } = await import("../lib/generation-ledger.js");
  const settings = { mediaKind: "image", outputDir: out, delayMin: 0, delayMax: 0, refreshFrequency: 1000, _runId: "run-seed" };
  const key = generationKey({
    mediaKind: "image",
    prompt: "scene-1\u0000a red balloon",
    settings,
    slot: 0,
    scope: scopeOf(out),
  });
  ledger.put(key, {
    state: LedgerState.DOWNLOAD_FAILED,
    accountId: "acct-A",
    accountLabel: "acct-A",
    mediaKind: "image",
    mediaId: "media-already-on-flow",
    fifeUrl: null,
    workflowId: null,
    runId: "run-seed",
  });
  let generateCalls = 0;
  const flow = fakeFlow();
  flow.deps.generateOneMedia = async () => {
    generateCalls++;
    throw new Error("generateOneMedia must not be called on DOWNLOAD_FAILED resume");
  };
  const { results } = await run({
    flow,
    ledger: new GenerationLedger(file),
    out,
    kind: "image",
    prompts: ["a red balloon"],
    runId: "run-resume",
  });
  assert.equal(generateCalls, 0);
  assert.equal(flow.calls.submit, 0);
  assert.ok(flow.calls.download >= 1, "must download the known media id");
  assert.equal(results[0].status, "done");
  assert.ok(fs.existsSync(results[0].path));
});

test("ambiguous submission: never generated again automatically, in this run or any later one; only an explicit Retry may", async () => {
  const dir = tmp();
  const file = path.join(dir, "ledger.json");
  const flow = fakeFlow({ outcomes: [unknown()] });
  const first = await run({ flow, ledger: new GenerationLedger(file), out: dir });
  assert.equal(flow.calls.submit, 1);
  assert.equal(first.results[0].status, "failed");
  assert.equal(first.results[0].needsAction, true);
  assert.equal(Object.values(JSON.parse(fs.readFileSync(file, "utf8")).entries)[0].state, LedgerState.SUBMITTED_UNKNOWN);
  for (const runId of ["run-2", "run-3", "run-4"]) {        // automatic reruns (a new Generate, a restart): still blocked
    const again = fakeFlow();
    const r = await run({ flow: again, ledger: new GenerationLedger(file), out: dir, runId });
    assert.equal(again.calls.submit, 0, runId);
    assert.equal(r.results[0].needsAction, true);
  }
  const retry = fakeFlow();                                    // the user clicked Retry on this scene
  const confirmed = await run({ flow: retry, ledger: new GenerationLedger(file), out: dir, runId: "run-5", confirm: true });
  assert.equal(retry.calls.submit, 1);
  assert.equal(confirmed.results[0].status, "done");
});

test("ambiguous image submission (image count 1) is treated the same way", async () => {
  const dir = tmp();
  const flow = fakeFlow({ outcomes: [unknown("HTTP 500")] });
  const { results } = await run({ flow, ledger: new GenerationLedger(path.join(dir, "l.json")), out: dir, kind: "image" });
  assert.equal(flow.calls.submit, 1);
  assert.equal(results[0].needsAction, true);
});

test("poll failure after acceptance: the workflow is resumed, never resubmitted", async () => {
  const dir = tmp();
  const flow = fakeFlow({ outcomes: [accepted("wf-1")], resumes: [new Error("HTTP 500"), "ok"] });
  const { results } = await run({ flow, ledger: new GenerationLedger(path.join(dir, "l.json")), out: dir });
  assert.equal(flow.calls.submit, 1);
  assert.equal(flow.calls.resume, 2);
  assert.equal(results[0].status, "done");
});

test("a rate limit while polling an accepted job is never handed to another account", async () => {
  const dir = tmp();
  const rl = tagSubmission(new RateLimitError("Rate limited by Google"), Submission.ACCEPTED, { workflowId: "wf-9" });
  const flow = fakeFlow({ outcomes: [rl], resumes: ["ok"] });
  const { result, results } = await run({ flow, ledger: new GenerationLedger(path.join(dir, "l.json")), out: dir });
  assert.equal(result.reassign.length, 0);
  assert.equal(flow.calls.submit, 1);
  assert.equal(results[0].status, "done");
});

test("UI false negative (Generate clicked, result not seen): no second click, the page moves to a fresh project", async () => {
  const dir = tmp();
  const ui = tagSubmission(new MissingMediaIdError("Flow UI generation did not produce a video (outcome: timeout_no_media_detected)"), Submission.UNKNOWN);
  ui.pageMayShowLateResult = true;
  let fresh = 0;
  const flow = fakeFlow({ outcomes: [ui, "ok"] });
  flow.deps.createFlowProject = async () => { fresh++; return "proj-fresh-0001"; };
  const { results } = await run({ flow, ledger: new GenerationLedger(path.join(dir, "l.json")), out: dir, prompts: ["first", "second"], extra: { generationMode: "ui" } });
  assert.equal(flow.calls.submit, 2, "one click per prompt, never two for the same prompt");
  assert.deepEqual(flow.calls.prompts, ["first", "second"]);
  assert.equal(results[0].needsAction, true);
  assert.equal(results[1].status, "done");
  assert.equal(fresh, 1, "the next UI generation starts where the late result cannot be mistaken for it");
});

test("image count 3: slot 2's download fails, slots 1 and 3 are not regenerated", async () => {
  const dir = tmp();
  const flow = fakeFlow({ downloads: ["ok", new Error("HTTP 404"), "ok", "ok"] });
  const { results } = await run({ flow, ledger: new GenerationLedger(path.join(dir, "l.json")), out: dir, kind: "image", extra: { imageCount: 3 } });
  assert.equal(flow.calls.submit, 3, "one submission per slot");
  assert.equal(results[0].status, "done");
  const files = fs.readdirSync(path.join(dir, fs.readdirSync(dir).find((n) => fs.statSync(path.join(dir, n)).isDirectory())));
  assert.deepEqual(files.filter((f) => f.endsWith(".png")).sort(), ["001-1.png", "001-2.png", "001-3.png"]);
});

test("a failure proven to have sent nothing is still retried (no lost throughput)", async () => {
  const dir = tmp();
  const flow = fakeFlow({ outcomes: [notSent(), "ok"] });
  const { results } = await run({ flow, ledger: new GenerationLedger(path.join(dir, "l.json")), out: dir });
  assert.equal(flow.calls.submit, 2);
  assert.equal(results[0].status, "done");
});

test("two accounts at once: separate folders, separate ledger owners, no shared state", async () => {
  const dir = tmp();
  const ledger = new GenerationLedger(path.join(dir, "l.json"));
  const a = fakeFlow();
  const b = fakeFlow();
  const [ra, rb] = await Promise.all([
    run({ flow: a, ledger, out: dir, account: "acct-A", prompts: ["alpha"] }),
    run({ flow: b, ledger, out: dir, account: "acct-B", prompts: ["beta"] }),
  ]);
  assert.notEqual(path.dirname(ra.results[0].path), path.dirname(rb.results[0].path));
  const owners = Object.values(JSON.parse(fs.readFileSync(path.join(dir, "l.json"), "utf8")).entries).map((e) => e.accountId).sort();
  assert.deepEqual(owners, ["acct-A", "acct-B"]);
});

test("another account never resumes or resubmits a job owned by account A", async () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  await run({ flow: fakeFlow({ outcomes: [accepted("wf-A")], resumes: [new Error("x"), new Error("x"), new Error("x")] }), ledger: new GenerationLedger(file), out: dir, account: "acct-A" });
  const b = fakeFlow();
  const { results } = await run({ flow: b, ledger: new GenerationLedger(file), out: dir, account: "acct-B", runId: "run-2" });
  assert.equal(b.calls.submit, 0);
  assert.equal(b.calls.resume, 0);
  assert.equal(results[0].needsAction, true);
});

test("process interruption after acceptance: the next run resumes the job, it does not generate again", async () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  // Flow accepts the job, then the call dies with an unclassified error (as a killed process leaves it): the ledger,
  // written before polling, keeps the workflow id.
  const dying = fakeFlow({
    outcomes: [(opts) => { opts.onAccepted("wf-crash"); throw new Error("Target page, context or browser has been closed"); }],
    resumes: [new Error("browser gone"), new Error("browser gone"), new Error("browser gone")],
  });
  const first = await run({ flow: dying, ledger: new GenerationLedger(file), out: dir });
  assert.equal(first.results[0].resumable, true, "an accepted job is kept resumable, not 'unknown'");
  const entry = Object.values(JSON.parse(fs.readFileSync(file, "utf8")).entries)[0];
  assert.equal(entry.workflowId, "wf-crash");
  const after = fakeFlow();
  const { results } = await run({ flow: after, ledger: new GenerationLedger(file), out: dir, runId: "run-2" });
  assert.equal(after.calls.submit, 0);
  assert.equal(after.calls.resume, 1);
  assert.equal(results[0].status, "done");
});

test("process interruption mid-submit (SUBMITTING on disk): blocked on every automatic run, generated only on an explicit Retry", async () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  const ledger = new GenerationLedger(file);
  await run({ flow: fakeFlow(), ledger, out: dir });   // learn the key
  const key = Object.keys(JSON.parse(fs.readFileSync(file, "utf8")).entries)[0];
  ledger.put(key, { state: LedgerState.SUBMITTING });
  for (const runId of ["run-2", "run-3"]) {
    const f = fakeFlow();
    const r = await run({ flow: f, ledger: new GenerationLedger(file), out: dir, runId });
    assert.equal(f.calls.submit, 0);
    assert.equal(r.results[0].needsAction, true);
  }
  const f2 = fakeFlow();
  const r2 = await run({ flow: f2, ledger: new GenerationLedger(file), out: dir, runId: "run-4", confirm: true });
  assert.equal(f2.calls.submit, 1);
  assert.equal(r2.results[0].status, "done");
});

test("crash after the file was saved but before COMPLETED_LOCAL: the next run reuses the file, generates and downloads nothing", async () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  const first = await run({ flow: fakeFlow(), ledger: new GenerationLedger(file), out: runDir(dir, "r1") });
  const saved = first.results[0].path;
  const key = Object.keys(JSON.parse(fs.readFileSync(file, "utf8")).entries)[0];
  // What a crash between the rename into place and the ledger write leaves: media id + destination, not "completed".
  new GenerationLedger(file).put(key, { state: LedgerState.MEDIA_ID_KNOWN, savedPath: null });
  const out2 = runDir(dir, "r2");
  const after = fakeFlow();
  const { results } = await run({ flow: after, ledger: new GenerationLedger(file), out: out2, runId: "run-2" });
  assert.equal(after.calls.submit, 0);
  assert.equal(after.calls.download, 0);
  assert.equal(results[0].status, "done");
  assert.ok(results[0].path.startsWith(out2), "the recovered file is handed over in the new run's folder");
  assert.deepEqual(fs.readFileSync(results[0].path), fs.readFileSync(saved));
});

test("a broken or wrong-kind file at the recorded destination is not reused: it is downloaded again (still no generation)", async () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  const first = await run({ flow: fakeFlow(), ledger: new GenerationLedger(file), out: runDir(dir, "r1") });
  fs.writeFileSync(first.results[0].path, PNG_BYTES);   // an image where a video should be
  const key = Object.keys(JSON.parse(fs.readFileSync(file, "utf8")).entries)[0];
  new GenerationLedger(file).put(key, { state: LedgerState.MEDIA_ID_KNOWN, savedPath: null });
  const after = fakeFlow();
  const { results } = await run({ flow: after, ledger: new GenerationLedger(file), out: runDir(dir, "r2"), runId: "run-2" });
  assert.equal(after.calls.submit, 0);
  assert.equal(after.calls.download, 1);
  assert.equal(results[0].status, "done");
});

test("completed and saved, but the app never recorded it: an automatic rerun reuses the file; a Regenerate makes a new one", async () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  await run({ flow: fakeFlow(), ledger: new GenerationLedger(file), out: runDir(dir, "r1") });
  const auto = fakeFlow();
  const r = await run({ flow: auto, ledger: new GenerationLedger(file), out: runDir(dir, "r2"), runId: "run-2" });
  assert.equal(auto.calls.submit, 0);
  assert.equal(r.results[0].status, "done");
  const regen = fakeFlow();
  await run({ flow: regen, ledger: new GenerationLedger(file), out: runDir(dir, "r3"), runId: "run-3", confirm: true });
  assert.equal(regen.calls.submit, 1);
});

test("completed earlier but the file was deleted: an automatic run downloads the same media again, it does not generate", async () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  const first = await run({ flow: fakeFlow(), ledger: new GenerationLedger(file), out: runDir(dir, "r1") });
  fs.rmSync(first.results[0].path);
  const auto = fakeFlow();
  const r = await run({ flow: auto, ledger: new GenerationLedger(file), out: runDir(dir, "r2"), runId: "run-2" });
  assert.equal(auto.calls.submit, 0);
  assert.equal(auto.calls.download, 1);
  assert.equal(r.results[0].status, "done");
  const other = fakeFlow();
  fs.rmSync(r.results[0].path);
  const r2 = await run({ flow: other, ledger: new GenerationLedger(file), out: runDir(dir, "r3"), runId: "run-3", account: "acct-B" });
  assert.equal(other.calls.submit, 0, "another account cannot fetch it and must not generate it either");
  assert.equal(r2.results[0].needsAction, true);
});

test("one account never submits two generations at once through its page; different accounts run in parallel", async () => {
  const dir = tmp();
  const ledger = new GenerationLedger(path.join(dir, "l.json"));
  let inFlight = 0;
  let maxSame = 0;
  const perAccount = new Map();
  const slowFlow = (account) => {
    const f = fakeFlow();
    f.deps.generateOneMedia = async () => {
      const n = (perAccount.get(account) || 0) + 1;
      perAccount.set(account, n);
      maxSame = Math.max(maxSame, n);
      inFlight++;
      const peak = inFlight;
      await new Promise((r) => setTimeout(r, 30));
      inFlight--;
      perAccount.set(account, perAccount.get(account) - 1);
      f.calls.submit++;
      return { mediaId: `m-${account}-${f.calls.submit}-${peak}`, fifeUrl: null };
    };
    return f;
  };
  // Two slices for the SAME account at once (what two overlapping runs would do).
  await Promise.all([
    run({ flow: slowFlow("A"), ledger, out: dir, account: "acct-A", prompts: ["one", "two"], kind: "image" }),
    run({ flow: slowFlow("A"), ledger, out: dir, account: "acct-A", prompts: ["three", "four"], kind: "image", runId: "run-x" }),
  ]);
  assert.equal(maxSame, 1, "the same account's page never runs two generations at once");
  // Different accounts: they overlap.
  inFlight = 0;
  let overlap = 0;
  const watch = setInterval(() => { overlap = Math.max(overlap, inFlight); }, 2);
  await Promise.all([
    run({ flow: slowFlow("B"), ledger, out: dir, account: "acct-B", prompts: ["b1", "b2"], kind: "image" }),
    run({ flow: slowFlow("C"), ledger, out: dir, account: "acct-C", prompts: ["c1", "c2"], kind: "image" }),
  ]);
  clearInterval(watch);
  assert.equal(overlap, 2, "two accounts generate at the same time");
});

test("an account restriction stops the account: no retry, no other mechanism, no hand-off", async () => {
  const dir = tmp();
  const flow = fakeFlow({ outcomes: [new AccountRestrictedError("PUBLIC_ERROR_UNUSUAL_ACTIVITY")] });
  const { result, results } = await run({ flow, ledger: new GenerationLedger(path.join(dir, "l.json")), out: dir, prompts: ["one", "two", "three"] });
  assert.equal(flow.calls.submit, 1);
  assert.equal(result.reassign.length, 0);
  assert.equal(result.restricted, "PUBLIC_ERROR_UNUSUAL_ACTIVITY");
  assert.deepEqual(results.map((r) => r.status), ["failed", "failed", "failed"]);
});

test("an empty prompt fails its own scene and does not shift the others", async () => {
  const dir = tmp();
  const flow = fakeFlow();
  const { results } = await run({ flow, ledger: new GenerationLedger(path.join(dir, "l.json")), out: dir, prompts: ["first", "", "third"], kind: "image" });
  assert.deepEqual(results.map((r) => [r.index, r.status]), [[0, "done"], [1, "failed"], [2, "done"]]);
  assert.equal(flow.calls.submit, 2);
});

// ---- ledger, routing, dispatch ------------------------------------------------------------------------------------------

test("ledger: a possibly-existing generation never expires on its own — only an explicit request overrides it", () => {
  let now = 1_000_000;
  const l = new GenerationLedger(null, { now: () => now });
  for (const state of [LedgerState.SUBMITTING, LedgerState.SUBMITTED_UNKNOWN, LedgerState.FAILED_ON_FLOW]) {
    l.put("k", { state, accountId: "A" });
    now += 365 * 24 * 60 * 60 * 1000;
    assert.equal(l.decide("k", { accountId: "A", runId: "r9" }).action, "block", state);
    assert.equal(l.decide("k", { accountId: "A", runId: "r9", confirmed: true }).action, "submit", state);
  }
  for (const state of [LedgerState.ACCEPTED, LedgerState.MEDIA_ID_KNOWN, LedgerState.DOWNLOAD_FAILED]) {
    l.put("r", { state, accountId: "A", workflowId: "wf" });
    now += 365 * 24 * 60 * 60 * 1000;
    assert.equal(l.decide("r", { accountId: "A", runId: "r9" }).action, "resume", state);
    assert.equal(l.decide("r", { accountId: "B", runId: "r9" }).action, "block", state);
  }
  // Only proven-nothing-created states submit without asking.
  for (const state of [LedgerState.FAILED_BEFORE_SUBMISSION, LedgerState.REJECTED]) {
    l.put("n", { state });
    assert.equal(l.decide("n", { accountId: "A", runId: "r9" }).action, "submit", state);
  }
});

test("ledger: entries that may still exist on Flow are never pruned from disk", () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  let now = 1_000_000;
  const l = new GenerationLedger(file, { now: () => now });
  l.put("unknown", { state: LedgerState.SUBMITTED_UNKNOWN });
  l.put("done", { state: LedgerState.COMPLETED_LOCAL });
  now += 400 * 24 * 60 * 60 * 1000;
  const reloaded = new GenerationLedger(file, { now: () => now });
  assert.ok(reloaded.get("unknown"));
  assert.equal(reloaded.get("done"), null);
});

test("accepted video stays with its account: after repeated resume failures a later automatic run still only resumes", async () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  const failing = () => fakeFlow({ resumes: [new Error("x"), new Error("x"), new Error("x")] });
  const first = failing();
  first.deps.generateOneMedia = async (...a) => { first.calls.submit++; throw accepted("wf-keep"); };
  await run({ flow: first, ledger: new GenerationLedger(file), out: dir });
  for (const runId of ["run-2", "run-3", "run-4"]) {
    const f = failing();
    const r = await run({ flow: f, ledger: new GenerationLedger(file), out: dir, runId });
    assert.equal(f.calls.submit, 0, runId);
    assert.equal(f.calls.resume, 3, runId);
    assert.equal(r.results[0].resumable, true);
  }
  // Explicit Retry: resume is tried first; a new generation needs a second explicit Retry after that fails too.
  const c1 = failing();
  await run({ flow: c1, ledger: new GenerationLedger(file), out: dir, runId: "run-5", confirm: true });
  assert.equal(c1.calls.submit, 0);
  const c2 = fakeFlow();
  const r2 = await run({ flow: c2, ledger: new GenerationLedger(file), out: dir, runId: "run-6", confirm: true });
  assert.equal(c2.calls.submit, 1);
  assert.equal(r2.results[0].status, "done");
});

test("ledger: a corrupt file is set aside, not silently overwritten", () => {
  const dir = tmp();
  const file = path.join(dir, "l.json");
  fs.writeFileSync(file, "{ not json");
  const l = new GenerationLedger(file);
  assert.equal(l.get("x"), null);
  assert.ok(fs.readdirSync(dir).some((n) => n.startsWith("l.json.corrupt-")));
});

test("orchestrator routes an accepted job back to the account that owns it (a standby owner joins as a worker)", () => {
  const A = { id: "A" }, B = { id: "B" }, C = { id: "C" };
  const slices = [{ prompts: ["p0", "p1"], indices: [0, 1], keys: ["s1", "s2"] }];
  const { workers, slices: out } = routeToOwners([A], slices, [A, B, C], (i) => (i === 1 ? "C" : null));
  assert.deepEqual(workers.map((w) => w.id), ["A", "C"]);
  assert.deepEqual(out[0].indices, [0]);
  assert.deepEqual(out[1].indices, [1]);
  assert.deepEqual(out[1].keys, ["s2"]);
});

test("UI fallback only when the RPC certainly sent nothing — never after an unknown outcome or a restriction", async () => {
  assert.equal(mayFallBackToUi(tagSubmission(new Error("x"), Submission.NOT_SUBMITTED)), true);
  assert.equal(mayFallBackToUi(tagSubmission(new Error("x"), Submission.UNKNOWN)), false);
  assert.equal(mayFallBackToUi(tagSubmission(new Error("Flow RPC rejected: X"), Submission.REJECTED)), false);
  assert.equal(mayFallBackToUi(new AccountRestrictedError("PUBLIC_ERROR_UNUSUAL_ACTIVITY")), false);

  let ui = 0;
  const impl = {
    generateOneVideo: async () => { throw tagSubmission(new Error("Request timed out"), Submission.UNKNOWN); },
    generateOneVideoViaUI: async () => { ui++; return { mediaId: "u" }; },
  };
  await assert.rejects(() => generateOneMedia({}, "p", "prompt", { generationMode: "rpc_then_ui" }, 0, "video", { impl }));
  assert.equal(ui, 0, "an ambiguous RPC video must never become a UI video");
});
