/**
 * downloadMedia must only ever leave a COMPLETE file at destPath: the Python
 * side picks up <run>/**\/NNN.mp4 straight off disk, so a half-written file
 * at the final name could be registered as a READY scene asset.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const { downloadMedia } = await import("../lib/flow-api.js");

function fakePage(body) {
  return {
    context: () => ({
      request: { get: async () => ({ ok: () => true, status: () => 200, body: async () => body }) },
    }),
  };
}

test("downloadMedia writes via a temp file and leaves only the finished .mp4", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-dl-"));
  const dest = path.join(dir, "013.mp4");
  const body = Buffer.concat([Buffer.from([0, 0, 0, 0x20]), Buffer.from("ftypisom"), Buffer.alloc(200, 1)]);
  await downloadMedia(fakePage(body), "media-1", dest, "https://flow-content.google/video/x");
  assert.deepEqual(fs.readdirSync(dir), ["013.mp4"]);
  assert.equal(fs.readFileSync(dest).length, body.length);
});

test("downloadMedia never leaves a file at destPath (or a .part) when the body is not media", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-dl-"));
  const dest = path.join(dir, "013.mp4");
  const src = fs.readFileSync(new URL("../lib/flow-api.js", import.meta.url), "utf8");
  assert.ok(src.includes("renameSync(partPath, destPath)"), "download must rename a temp file into place");
  // Non-media, non-retryable bytes fail on the first attempt (no retry sleeps).
  const page = fakePage(Buffer.alloc(200, 7));
  await assert.rejects(() => downloadMedia(page, "media-1", dest, null));
  assert.deepEqual(fs.readdirSync(dir), []);
});
