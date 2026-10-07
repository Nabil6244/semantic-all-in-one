/**
 * Flow agent mode for images: the reply parser, scene matching, batch planning, and the runner's safety rules. Flow is
 * replaced by fakes (no network, no credits); the reply streams below have the shape captured live on 2026-10-06.
 * Run: node --test test/agent-mode.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { parseAgentStream, mapCallsToScenes, buildAgentMessage, splitSharedStyle, coolDownReason, AGENT_RECAPTCHA_ACTION, imageUrlFromAs29s } = await import("../lib/agent-api.js");
const { planAgentBatches, runAgentSlice, textsClash } = await import("../lib/agent-runner.js");
const { GenerationLedger, LedgerState } = await import("../lib/generation-ledger.js");
const { Submission, tagSubmission } = await import("../lib/generation-state.js");

const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(200, 1)]);
const kv = (k, v) => [k, [null, null, v]];

/** One reply stream line holding one frame, like the agent's batchexecute stream. */
function frame(payload) {
  const line = JSON.stringify([["wrb.fr", null, JSON.stringify(payload)]]);
  return `${line.length}\n${line}\n`;
}

/**
 * A reply in which the agent plans one call per scene and reports each result. Like the live agent it copies the scene
 * text into its prompt and adds a few words; `named` names each image with its scene ID (S01…). `order` reorders the calls.
 */
function agentReply(texts, { aspect = "16:9", status = {}, missing = new Set(), extraPrompts = [], named = true, order = null, names = {} } = {}) {
  const all = [...texts.map((t, i) => ({ t, i })), ...extraPrompts.map((t, k) => ({ t, i: texts.length + k, extra: true }))];
  const seq = order ? order.map((i) => all[i]) : all;
  const id = (i) => `S${String(i + 1).padStart(2, "0")}`;
  const calls = seq.map(({ t, i }) => [`call-${i}`, null, null, ["generate_image", "generate_image",
    [[kv("prompt", `Documentary style image of ${t}, natural light`), kv("aspect_ratio", aspect), kv("model_usage_key", "HARBOR_SEAL"),
      kv("model_display_name", "🍌 Nano Banana 2"), kv("placeholder_frontend_id", `ph-${i}`)]], `call-${i}`]]);
  const results = seq.filter(({ i }) => !missing.has(i)).map(({ t, i, extra }) => [`call-${i}`, null, null, null, ["generate_image", "generate_image",
    [[kv("placeholder_frontend_id", `ph-${i}`), kv("batch_id", "batch-1"), kv("project_id", "proj-1"), kv("status", status[i] || "success"),
      kv("workflow_id", `wf-${i}`), kv("display_name", names[i] ?? (named && !extra ? id(i) : t.slice(0, 30))), kv("media_id", `media-${i}`)]], `call-${i}`]]);
  return ")]}'\n\n" + frame([[null, [["chat", null, null, null, null, null, null, ["Title"]]], "chat"]]) +
    frame([[[[["text", [null, null, "Planning…"]]]], calls]]) + frame([[null, results]]) + frame([[[[["text", [null, null, "Done."]]]], null, "x"]]);
}

function fakeFlow({ replies = [], sendErrors = [] } = {}) {
  const calls = { chats: 0, sends: 0, messages: [], downloads: 0, standard: [] };
  const deps = {
    sleep: async () => {},
    openOrCreateProject: async () => "proj-1",
    waitForFlowReady: async () => {},
    createAgentChat: async () => { calls.chats++; return `chat-${calls.chats}`; },
    sendAgentMessage: async (_page, { message }) => {
      calls.sends++;
      calls.messages.push(message);
      const err = sendErrors.shift();
      if (err) throw err;
      return { text: replies.shift(), durationMs: 1000 };
    },
    fetchImageUrl: async (_page, mediaId) => `https://flow-content.google/image/${mediaId}`,
    downloadMedia: async (_page, _id, dest) => {
      calls.downloads++;
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, PNG);
    },
    runBatchSlice: async ({ prompts, promptIndices, onProgress }) => {
      calls.standard.push(...prompts);
      prompts.forEach((p, i) => onProgress({ type: "PROMPT_RESULT", index: promptIndices[i], prompt: p, status: "done", path: "/std" }));
      return { completed: prompts.length, failed: 0, reassign: [] };
    },
  };
  return { deps, calls };
}

async function run({ flow, ledger, prompts, out, runId = "run-1", extra = {} }) {
  const events = [];
  const result = await runAgentSlice({
    page: {}, prompts, promptIndices: prompts.map((_, i) => i), promptKeys: prompts.map((_, i) => String(i + 1)),
    totalAbsolute: prompts.length,
    settings: { mediaKind: "image", generationMode: "agent", model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
      outputDir: out, _runId: runId, agentBatchGapMs: 0, agentMinScenes: 1, ...extra },
    folderLabel: "acct-A", accountId: "acct-A", accountLabel: "acct-A", shouldStop: () => false,
    onProgress: (e) => events.push(e), deps: { ...flow.deps, ledger },
  });
  const results = events.filter((e) => e.type === "PROMPT_RESULT");
  return { result, results, events };
}

function setup() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-agent-"));
  const out = path.join(dir, "flow", "runs", "run-1");
  fs.mkdirSync(out, { recursive: true });
  return { dir, out, ledger: new GenerationLedger(path.join(dir, "ledger.json")) };
}

const SCENES = ["a coal power plant at dawn", "engineers inspecting a turbine", "a river polluted by industrial runoff"];

// ---------------------------------------------------------------- parser / matching / planning
test("the reply parser reads every planned call and its result, in order", () => {
  const p = parseAgentStream(agentReply(SCENES));
  assert.equal(p.calls.length, 3);
  assert.deepEqual(p.calls.map((c) => c.modelKey), ["HARBOR_SEAL", "HARBOR_SEAL", "HARBOR_SEAL"]);
  assert.equal(p.calls[0].aspect, "16:9");
  assert.equal(p.results["ph-2"].mediaId, "media-2");
  assert.equal(p.results["ph-2"].title, "S03");
  assert.equal(p.error, null);
});

test("a stream with an error frame is read as a refusal", () => {
  const line = JSON.stringify([["wrb.fr", null, null, null, null, [5], "generic"]]);
  const p = parseAgentStream(`)]}'\n\n${line.length}\n${line}\n`);
  assert.equal(p.calls.length, 0);
  assert.deepEqual(p.error, { grpcCode: 5, reason: null });
  assert.equal(p.refused, true);
});

test("images are tied to scenes by the scene ID they are named with, whatever order the agent used", () => {
  const p = parseAgentStream(agentReply(SCENES, { order: [2, 0, 1] }));
  const m = mapCallsToScenes(SCENES, p.calls, p.results);
  assert.deepEqual([0, 1, 2].map((i) => [m.mapping.get(i).call.placeholderId, m.mapping.get(i).method]),
    [["ph-0", "id"], ["ph-1", "id"], ["ph-2", "id"]]);
});

test("without names, an image is tied to the one scene whose exact text its prompt contains", () => {
  const p = parseAgentStream(agentReply(SCENES, { named: false, order: [1, 2, 0] }));
  const m = mapCallsToScenes(SCENES, p.calls, p.results);
  assert.deepEqual([0, 1, 2].map((i) => [m.mapping.get(i).call.placeholderId, m.mapping.get(i).method]),
    [["ph-0", "text"], ["ph-1", "text"], ["ph-2", "text"]]);
});

test("word overlap is never enough: a reworded prompt with no name stays unmatched", () => {
  const calls = [{ placeholderId: "a", prompt: "Aerial dawn view of a coal power plant", fields: {} }];
  const m = mapCallsToScenes(SCENES, calls, {});
  assert.equal(m.mapping.size, 0);
  assert.equal(m.extraCalls.length, 1);
});

test("two images claiming the same scene ID are not used by ID", () => {
  const p = parseAgentStream(agentReply(SCENES, { names: { 0: "S01", 1: "S01" } }));
  const m = mapCallsToScenes(SCENES, p.calls, p.results);
  assert.equal(m.mapping.get(2).method, "id");
  // The two conflicting images fall back to exact text, which still tells them apart.
  assert.equal(m.mapping.get(0).call.placeholderId, "ph-0");
  assert.equal(m.mapping.get(1).call.placeholderId, "ph-1");
  assert.equal(m.mapping.get(0).method, "text");
});

test("scenes sharing a long style text: the style is found once and the scene texts still differ", () => {
  const style = "Realistic, painterly digital illustration with cinematic, semi-photoreal rendering, moody dramatic light, muted navy and amber grading, clean motion-graphic overlays.";
  const prompts = SCENES.map((t) => `${style} ${t}`);
  const s = splitSharedStyle(prompts);
  assert.equal(s.opening, style);
  assert.deepEqual(s.texts, SCENES);
  assert.equal(splitSharedStyle(["a short one", "a short two"]).opening, "", "short shared words are not a style");
});

test("the message carries scene IDs, the shared style once, and the rules", () => {
  const m = buildAgentMessage(["a b", "c   d"], { aspect: "16:9", opening: "Shared look." });
  assert.match(m, /exactly one image for each of the 2 scenes/);
  assert.match(m, /Name the image with its scene ID only/);
  assert.match(m, /copied exactly/);
  assert.doesNotMatch(m, /documentary/i);
  assert.equal(m.split("Shared look.").length, 2, "the style appears once");
  assert.match(m, /\nS01: a b\nS02: c d$/);
});

test("batches hold at most 24 scenes, stay under the message size, and are balanced", () => {
  const items = Array.from({ length: 50 }, (_, i) => ({ prompt: `scene ${i} end` }));
  assert.deepEqual(planAgentBatches(items).map((b) => b.length), [17, 17, 16]);
  assert.deepEqual(planAgentBatches(items.slice(0, 26)).map((b) => b.length), [13, 13]);
  const long = Array.from({ length: 10 }, () => ({ prompt: "x".repeat(3000) }));
  assert.ok(planAgentBatches(long).every((b) => b.length <= 3));
});

test("cool-down answers are recognised", () => {
  const line = JSON.stringify([["wrb.fr", null, null, null, null, [8, null, [["type.googleapis.com/google.rpc.ErrorInfo", ["PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC"]]]], "generic"]]);
  const raw = `)]}'\n\n${line.length}\n${line}\n`;
  assert.equal(coolDownReason(parseAgentStream(raw), raw), "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC");
  assert.equal(coolDownReason({ error: null }, "… AGENT_CAPACITY_EXCEEDED …"), "AGENT_CAPACITY_EXCEEDED");
  assert.equal(coolDownReason({ error: null }, "fine"), null);
});

test("agent requests carry a reCAPTCHA token for Flow's chat action, not the image one", () => {
  assert.equal(AGENT_RECAPTCHA_ACTION, "CHAT_GENERATION");
  const src = fs.readFileSync(new URL("../lib/agent-api.js", import.meta.url), "utf8");
  assert.match(src, /mintCaptchaWithFallback\(page, AGENT_RECAPTCHA_ACTION\)/);
});

test("the image URL comes out of the as29s answer whole, signature included", () => {
  const signed = "https://flow-content.google/image/abc-123?sig=AbC_d-9&exp=1791290000&w=1376";
  const inner = JSON.stringify([[["wf-1", null, "media-1", [null, null, null, null, null, [[signed, 1376, 768]]]]]]);
  const line = JSON.stringify([["wrb.fr", "as29s", inner, null, null, null, "generic"]]);
  assert.equal(imageUrlFromAs29s(`)]}'\n\n${line.length}\n${line}\n`), signed);
  assert.equal(imageUrlFromAs29s("garbage"), null);
});

// ---------------------------------------------------------------- runner
test("success: one agent request for the whole batch, one saved image per scene", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ replies: [agentReply(SCENES)] });
  const { results, result } = await run({ flow, ledger, prompts: SCENES, out });
  assert.equal(flow.calls.sends, 1);
  assert.equal(flow.calls.downloads, 3);
  assert.deepEqual(results.map((r) => [r.index, r.status, r.mediaIds[0], r.agentModel]),
    [[0, "done", "media-0", "HARBOR_SEAL"], [1, "done", "media-1", "HARBOR_SEAL"], [2, "done", "media-2", "HARBOR_SEAL"]]);
  assert.ok(results.every((r) => fs.existsSync(r.path) && r.path.endsWith(".png")));
  assert.deepEqual(flow.calls.standard, []);
  assert.equal(result.completed, 3);
});

test("a second run reuses the saved images and sends nothing", async () => {
  const { out, ledger } = setup();
  await run({ flow: fakeFlow({ replies: [agentReply(SCENES)] }), ledger, prompts: SCENES, out });
  const again = fakeFlow();
  const { results } = await run({ flow: again, ledger, prompts: SCENES, out, runId: "run-2" });
  assert.equal(again.calls.sends, 0);
  assert.ok(results.every((r) => r.status === "done"));
});

test("an image Flow reports as failed goes to the standard path; the rest are kept", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ replies: [agentReply(SCENES, { status: { 1: "failed" } })] });
  const { results } = await run({ flow, ledger, prompts: SCENES, out });
  assert.deepEqual(flow.calls.standard, [SCENES[1]]);
  assert.equal(results.filter((r) => r.status === "done").length, 3);
});

test("a request that never left goes entirely to the standard path", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ sendErrors: [tagSubmission(new Error("Missing WIZ session state"), Submission.NOT_SUBMITTED)] });
  await run({ flow, ledger, prompts: SCENES, out });
  assert.deepEqual(flow.calls.standard, SCENES);
});

test("a refused request (4xx) goes entirely to the standard path", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ sendErrors: [tagSubmission(new Error("HTTP 400"), Submission.REJECTED)] });
  await run({ flow, ledger, prompts: SCENES, out });
  assert.deepEqual(flow.calls.standard, SCENES);
});

test("no answer after sending: Needs action, never sent again by either path", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ sendErrors: [tagSubmission(new Error("The agent did not finish in time"), Submission.UNKNOWN)] });
  const { results } = await run({ flow, ledger, prompts: SCENES, out });
  assert.equal(flow.calls.sends, 1);
  assert.deepEqual(flow.calls.standard, []);
  assert.ok(results.every((r) => r.status === "failed" && r.needsAction));
  const again = fakeFlow({ replies: [agentReply(SCENES)] });
  const second = await run({ flow: again, ledger, prompts: SCENES, out, runId: "run-2" });
  assert.equal(again.calls.sends, 0, "an automatic run never resends a batch whose outcome is unknown");
  assert.ok(second.results.every((r) => r.needsAction));
});

test("Retry (confirmed) may send a scene whose earlier outcome was unknown", async () => {
  const { out, ledger } = setup();
  await run({ flow: fakeFlow({ sendErrors: [tagSubmission(new Error("timeout"), Submission.UNKNOWN)] }), ledger, prompts: SCENES, out });
  const retry = fakeFlow({ replies: [agentReply(SCENES)] });
  const { results } = await run({ flow: retry, ledger, prompts: SCENES, out, runId: "run-2", extra: { confirmResubmitKeys: ["1", "2", "3"] } });
  assert.equal(retry.calls.sends, 1);
  assert.ok(results.every((r) => r.status === "done"));
});

test("the agent answering without images (e.g. a question) sends the scenes to the standard path", async () => {
  const { out, ledger } = setup();
  const reply = ")]}'\n\n" + frame([[[[["text", [null, null, "Which style would you like?"]]]], null, "x"]]);
  const flow = fakeFlow({ replies: [reply] });
  await run({ flow, ledger, prompts: SCENES, out });
  assert.deepEqual(flow.calls.standard, SCENES);
});

test("an image in the wrong aspect ratio is not used: that scene goes to the standard path", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ replies: [agentReply(SCENES, { aspect: "1:1" })] });
  await run({ flow, ledger, prompts: SCENES, out });
  assert.deepEqual(flow.calls.standard, SCENES);
  assert.equal(flow.calls.downloads, 0);
});

test("a planned image with no reported result is Needs action, not resent", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ replies: [agentReply(SCENES, { missing: new Set([2]) })] });
  const { results } = await run({ flow, ledger, prompts: SCENES, out });
  const third = results.find((r) => r.index === 2);
  assert.equal(third.status, "failed");
  assert.equal(third.needsAction, true);
  assert.deepEqual(flow.calls.standard, []);
});

test("an image that cannot be tied to one scene is never guessed", async () => {
  const { out, ledger } = setup();
  const reply = agentReply([SCENES[0], SCENES[1]], { extraPrompts: ["a red bus in London"] });
  const flow = fakeFlow({ replies: [reply] });
  const { results } = await run({ flow, ledger, prompts: SCENES, out });
  const third = results.find((r) => r.index === 2);
  assert.equal(third.needsAction, true, "an unmatched scene while unmatched images exist is not sent again");
  assert.deepEqual(flow.calls.standard, []);
  assert.equal(results.filter((r) => r.status === "done").length, 2);
});

test("a download that fails stays resumable and the next run downloads it without generating", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ replies: [agentReply(SCENES)] });
  flow.deps.downloadMedia = async () => { throw new Error("HTTP 503"); };
  const first = await run({ flow, ledger, prompts: SCENES, out });
  assert.ok(first.results.every((r) => r.resumable));
  const again = fakeFlow();
  const second = await run({ flow: again, ledger, prompts: SCENES, out, runId: "run-2" });
  assert.equal(again.calls.sends, 0);
  assert.ok(second.results.every((r) => r.status === "done"));
});

test("an account restriction stops the account: nothing is retried or handed to the standard path", async () => {
  const { out, ledger } = setup();
  const line = JSON.stringify([["wrb.fr", null, null, null, null, [7, null, [["type.googleapis.com/google.rpc.ErrorInfo", ["PUBLIC_ERROR_UNUSUAL_ACTIVITY"]]]], "generic"]]);
  const flow = fakeFlow({ replies: [`)]}'\n\n${line.length}\n${line}\n`] });
  const { result, results } = await run({ flow, ledger, prompts: SCENES, out });
  assert.equal(result.restricted, "PUBLIC_ERROR_UNUSUAL_ACTIVITY");
  assert.ok(results.every((r) => r.restricted));
  assert.deepEqual(flow.calls.standard, []);
});

test("more than 24 scenes: several requests on the account, one at a time", async () => {
  const { out, ledger } = setup();
  const prompts = Array.from({ length: 30 }, (_, i) => `documentary scene number ${i} with unique subject ${String.fromCharCode(97 + (i % 26))}${i}`);
  const flow = fakeFlow({ replies: [agentReply(prompts.slice(0, 15)), agentReply(prompts.slice(15))] });
  const { results } = await run({ flow, ledger, prompts, out });
  assert.equal(flow.calls.sends, 2);
  assert.equal(flow.calls.chats, 2);
  assert.equal(results.filter((r) => r.status === "done").length, 30);
});

test("the explicit IDs (request, scene, result) are recorded with each image", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ replies: [agentReply(SCENES, { order: [1, 2, 0] })] });
  const { results } = await run({ flow, ledger, prompts: SCENES, out });
  const r = results.find((x) => x.index === 2);
  assert.equal(r.mediaIds[0], "media-2");
  assert.equal(r.agentSceneId, "S03");
  assert.equal(r.agentPlaceholderId, "ph-2");
  assert.equal(r.agentChatId, "chat-1");
  assert.equal(r.agentMatch, "id");
});

test("a shared style is sent once and the agent is told each scene's ID", async () => {
  const { out, ledger } = setup();
  const style = "Realistic, painterly digital illustration with cinematic, semi-photoreal rendering, moody dramatic light, muted navy and amber grading, clean motion-graphic overlays.";
  const prompts = SCENES.map((t) => `${style} ${t}`);
  const flow = fakeFlow({ replies: [agentReply(SCENES)] });
  const { results } = await run({ flow, ledger, prompts, out });
  const msg = flow.calls.messages[0];
  assert.equal(msg.split(style).length, 2);
  assert.match(msg, /S03: a river polluted by industrial runoff/);
  assert.ok(results.every((r) => r.status === "done"));
});

test("too much traffic: the account rests, its scenes go to other accounts, never to the standard path here", async () => {
  const { out, ledger } = setup();
  const line = JSON.stringify([["wrb.fr", null, null, null, null, [8, null, [["type.googleapis.com/google.rpc.ErrorInfo", ["PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC"]]]], "generic"]]);
  const prompts = Array.from({ length: 30 }, (_, i) => `documentary scene number ${i} with unique subject ${i}`);
  const flow = fakeFlow({ replies: [`)]}'\n\n${line.length}\n${line}\n`] });
  const { result, results } = await run({ flow, ledger, prompts, out });
  assert.equal(flow.calls.sends, 1, "the second batch is not sent");
  assert.deepEqual(flow.calls.standard, []);
  assert.equal(result.coolDown, "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC");
  assert.equal(result.reassign.length, 30);
  assert.ok(results.every((r) => r.status === "rate_limited" && r.reassign));
});

test("HTTP 429 on the agent request also rests the account", async () => {
  const { out, ledger } = setup();
  const err = tagSubmission(new Error("Flow agent request failed: HTTP 429"), Submission.REJECTED, { httpStatus: 429 });
  const flow = fakeFlow({ sendErrors: [err] });
  const { result } = await run({ flow, ledger, prompts: SCENES, out });
  assert.equal(result.reassign.length, 3);
  assert.deepEqual(flow.calls.standard, []);
});

test("a few scenes use the standard path: an agent request would be slower", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow();
  await run({ flow, ledger, prompts: SCENES, out, extra: { agentMinScenes: 4 } });
  assert.equal(flow.calls.sends, 0);
  assert.deepEqual(flow.calls.standard, SCENES);
});

test("Stop during downloads, past the grace period: the images not yet saved are reported as resumable, nothing is generated again", async () => {
  const { out, ledger } = setup();
  let stop = false;
  const flow = fakeFlow({ replies: [agentReply(SCENES)] });
  const real = flow.deps.downloadMedia;
  flow.deps.downloadMedia = async (...a) => { await real(...a); stop = true; };
  const events = [];
  await runAgentSlice({
    page: {}, prompts: SCENES, promptIndices: [0, 1, 2], promptKeys: ["1", "2", "3"], totalAbsolute: 3,
    settings: { mediaKind: "image", generationMode: "agent", model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE", outputDir: out,
      _runId: "run-1", agentBatchGapMs: 0, agentMinScenes: 1, agentStopGraceMs: 0 },
    folderLabel: "acct-A", accountId: "acct-A", accountLabel: "acct-A", shouldStop: () => stop,
    onProgress: (e) => events.push(e), deps: { ...flow.deps, ledger },
  });
  const res = events.filter((e) => e.type === "PROMPT_RESULT");
  assert.equal(res.length, 3, "every scene gets a result");
  assert.equal(res.filter((r) => r.status === "done").length, 1);
  assert.ok(res.filter((r) => r.status === "failed").every((r) => r.resumable && r.needsAction));
  const again = fakeFlow();
  const second = await run({ flow: again, ledger, prompts: SCENES, out, runId: "run-2" });
  assert.equal(again.calls.sends, 0);
  assert.ok(second.results.every((r) => r.status === "done"));
});

test("Stop before a batch is sent: its scenes are reported, nothing was generated", async () => {
  const { out, ledger } = setup();
  const prompts = Array.from({ length: 30 }, (_, i) => `documentary scene number ${i} with unique subject ${i}`);
  let sends = 0;
  const flow = fakeFlow({ replies: [agentReply(prompts.slice(0, 15))] });
  const send = flow.deps.sendAgentMessage;
  flow.deps.sendAgentMessage = async (...a) => { sends++; return send(...a); };
  const events = [];
  await runAgentSlice({
    page: {}, prompts, promptIndices: prompts.map((_, i) => i), promptKeys: prompts.map((_, i) => String(i + 1)), totalAbsolute: 30,
    settings: { mediaKind: "image", generationMode: "agent", model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE", outputDir: out,
      _runId: "run-1", agentBatchGapMs: 1, agentMinScenes: 1 },
    folderLabel: "acct-A", accountId: "acct-A", accountLabel: "acct-A", shouldStop: () => sends >= 1 && flow.calls.downloads >= 0 && events.some((e) => e.status === "waiting"),
    onProgress: (e) => events.push(e), deps: { ...flow.deps, ledger },
  });
  const res = events.filter((e) => e.type === "PROMPT_RESULT");
  assert.equal(sends, 1);
  assert.equal(res.length, 30, "every scene gets a result");
  assert.ok(res.filter((r) => r.index >= 15).every((r) => r.status === "failed" && /Stopped before it was sent/.test(r.error)));
});

test("scenes an image could not be told apart by never share a request", () => {
  assert.equal(textsClash("A dog", "a  dog running in a park"), true);
  assert.equal(textsClash("A dog", "A cat"), false);
  const items = ["a city at night", "a city at night", "a city at night seen from a plane", "a farm", "a harbour", "a bridge"]
    .map((prompt) => ({ prompt }));
  const batches = planAgentBatches(items, { maxBatch: 24 });
  for (const b of batches) {
    for (let i = 0; i < b.length; i++) for (let j = i + 1; j < b.length; j++) assert.equal(textsClash(b[i].prompt, b[j].prompt), false);
  }
  assert.equal(batches.flat().length, 6);
  assert.equal(batches.length, 3, "the three city scenes need three requests; the others fill in");
});

test("the agent tidying punctuation, quotes or dashes still matches; a changed word does not", () => {
  const scenes = ["A soldier’s “last stand” — at the old fort", "A general’s map, torn in half"];
  const calls = [
    { placeholderId: "a", prompt: "Painterly style. A soldier's \"last stand\" - at the old fort.", fields: {} },
    { placeholderId: "b", prompt: "Painterly style. A general's map torn into half", fields: {} },
  ];
  const m = mapCallsToScenes(scenes, calls, {});
  assert.equal(m.mapping.get(0).call.placeholderId, "a");
  assert.equal(m.mapping.has(1), false, "'in' became 'into': not the same words");
  assert.equal(textsClash("A dog!", "a dog, running"), true);
});

test("an unmatched image's prompt is kept with the scene for auditing", async () => {
  const { out, ledger } = setup();
  const reply = agentReply([SCENES[0], SCENES[1]], { extraPrompts: ["a red bus in London"], named: false });
  const flow = fakeFlow({ replies: [reply] });
  const { results } = await run({ flow, ledger, prompts: SCENES, out });
  const third = results.find((r) => r.index === 2);
  assert.match(third.agentUnmatched[0].prompt, /a red bus in London/);
});

test("Stop during downloads, within the grace period: images Flow already made are still saved", async () => {
  const { out, ledger } = setup();
  let stop = false;
  const flow = fakeFlow({ replies: [agentReply(SCENES)] });
  const real = flow.deps.downloadMedia;
  flow.deps.downloadMedia = async (...a) => { await real(...a); stop = true; };
  const events = [];
  await runAgentSlice({
    page: {}, prompts: SCENES, promptIndices: [0, 1, 2], promptKeys: ["1", "2", "3"], totalAbsolute: 3,
    settings: { mediaKind: "image", generationMode: "agent", model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE", outputDir: out,
      _runId: "run-1", agentBatchGapMs: 0, agentMinScenes: 1, agentStopGraceMs: 30000 },
    folderLabel: "acct-A", accountId: "acct-A", accountLabel: "acct-A", shouldStop: () => stop,
    onProgress: (e) => events.push(e), deps: { ...flow.deps, ledger },
  });
  const res = events.filter((e) => e.type === "PROMPT_RESULT");
  assert.equal(res.filter((r) => r.status === "done").length, 3);
});

test("every scene of a request keeps the request and chat identity, even when the reply never comes", async () => {
  const { out, ledger } = setup();
  const flow = fakeFlow({ sendErrors: [tagSubmission(new Error("The agent did not finish in time"), Submission.UNKNOWN)] });
  await run({ flow, ledger, prompts: SCENES, out });
  const entries = Object.values(JSON.parse(fs.readFileSync(ledger.file, "utf8")).entries);
  assert.equal(entries.length, 3);
  assert.ok(entries.every((e) => e.state === "SUBMITTED_UNKNOWN" && e.agentChatId === "chat-1" && /^agentreq-/.test(e.agentRequestId)));
  assert.equal(new Set(entries.map((e) => e.agentRequestId)).size, 1, "one request identity for the whole batch");
});

test("scenes are listed as being made only while their request is out", async () => {
  const { activeAgentScenes } = await import("../lib/agent-runner.js");
  const { out, ledger } = setup();
  const seen = [];
  const flow = fakeFlow({ replies: [agentReply(SCENES)] });
  const send = flow.deps.sendAgentMessage;
  flow.deps.sendAgentMessage = async (...a) => { seen.push(activeAgentScenes.size); return send(...a); };
  await run({ flow, ledger, prompts: SCENES, out });
  assert.deepEqual(seen, [3]);
  assert.equal(activeAgentScenes.size, 0);
});

test("the reply timeout grows with the batch, within limits", async () => {
  const { agentReplyTimeoutMs } = await import("../lib/agent-runner.js");
  assert.ok(agentReplyTimeoutMs(1) < agentReplyTimeoutMs(13));
  assert.ok(agentReplyTimeoutMs(13) > 240000, "a 13-scene batch gets more than the old flat 240 s");
  assert.ok(agentReplyTimeoutMs(500) <= 600000);
});
