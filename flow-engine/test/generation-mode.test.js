import test from "node:test";
import assert from "node:assert/strict";

test("defaults.flowSettings.generationMode is ui (Flow web UI path)", async () => {
  const prev = process.env.FLOW_GENERATION_MODE;
  delete process.env.FLOW_GENERATION_MODE;
  try {
    const { defaults, resolveGenerationMode } = await import(`../config.js?t=${Date.now()}`);
    assert.equal(resolveGenerationMode(), "ui");
    assert.equal(defaults.flowSettings.generationMode, "ui");
  } finally {
    if (prev === undefined) delete process.env.FLOW_GENERATION_MODE;
    else process.env.FLOW_GENERATION_MODE = prev;
  }
});

test("resolveGenerationMode falls back to ui", async () => {
  const { resolveGenerationMode } = await import("../lib/generation-dispatch.js");
  assert.equal(resolveGenerationMode({}), "ui");
  assert.equal(resolveGenerationMode({ generationMode: "rpc" }), "rpc");
  assert.equal(resolveGenerationMode({ generationMode: "bogus" }), "ui");
});
