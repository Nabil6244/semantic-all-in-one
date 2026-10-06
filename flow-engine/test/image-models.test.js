// Image model ids as Flow sends them today (captured live 2026-10-06 from Flow's own ogiZ0b requests):
// Nano Banana 2 = BELUGA, Nano Banana 2 Lite = HARBOR_SEAL, Nano Banana Pro = GEM_PIX_2. NARWHAL (the old Nano Banana 2) is
// retired: Google answers it with a bare gRPC 5 / NOT_FOUND.
import test from "node:test";
import assert from "node:assert/strict";
import { canonicalImageModel, defaults, models } from "../config.js";

test("Nano Banana 2 is BELUGA and is the default image model", () => {
  assert.equal(models.default, "BELUGA");
  assert.equal(models.labels.BELUGA, "NB 2");
  assert.equal(defaults.flowSettings.model, "BELUGA");
});

test("the retired NARWHAL id is never offered or tried", () => {
  assert.ok(!models.options.some((o) => o.value === "NARWHAL"));
  assert.ok(!models.fallbackOrder.includes("NARWHAL"));
  assert.ok(!("NARWHAL" in models.labels));
});

test("fallback order steps from Nano Banana 2 to Pro to Lite", () => {
  assert.deepEqual(models.fallbackOrder, ["BELUGA", "GEM_PIX_2", "HARBOR_SEAL"]);
});

test("a saved retired id becomes its replacement; current ids are unchanged", () => {
  assert.equal(canonicalImageModel("NARWHAL"), "BELUGA");
  for (const id of ["BELUGA", "HARBOR_SEAL", "GEM_PIX_2"]) assert.equal(canonicalImageModel(id), id);
  assert.equal(canonicalImageModel(undefined), undefined);
  assert.equal(canonicalImageModel(""), "");
});

test("a scene saved with NARWHAL is sent to Flow as BELUGA (batch runner, fake Flow)", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  const { runBatchSlice } = await import("../lib/batch-runner.js");
  const { GenerationLedger } = await import("../lib/generation-ledger.js");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-models-"));
  const out = path.join(dir, "flow", "runs", "run-1");
  fs.mkdirSync(out, { recursive: true });
  const sent = [];
  const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47]), Buffer.alloc(200, 1)]);
  const deps = {
    sleep: async () => {},
    openOrCreateProject: async () => "proj-0001-aaaa",
    createFlowProject: async () => "proj-0002-bbbb",
    flowGoto: async () => {},
    waitForFlowReady: async () => {},
    checkFlowReady: async () => ({ hasProject: true, hasRecaptcha: true }),
    flowReload: async () => {},
    generateOneMedia: async (_page, _pid, _prompt, s) => { sent.push(s.model); return { mediaId: "m-1", fifeUrl: null, via: "rpc" }; },
    resumeVideo: async () => ({ mediaId: "r-1", fifeUrl: null }),
    downloadMedia: async (_page, _id, dest) => { fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, PNG); },
    ledger: new GenerationLedger(path.join(dir, "ledger.json")),
  };
  await runBatchSlice({
    page: {}, prompts: ["a cargo ship at sunrise"], promptIndices: [0], promptKeys: ["scene-1"], totalAbsolute: 1,
    settings: { mediaKind: "image", model: "NARWHAL", outputDir: out, delayMin: 0, delayMax: 0, refreshFrequency: 1000, _runId: "run-1" },
    folderLabel: "acct-A", accountId: "acct-A", accountLabel: "acct-A", shouldStop: () => false, onProgress: () => {}, deps,
  });
  assert.deepEqual(sent, ["BELUGA"]);
});
