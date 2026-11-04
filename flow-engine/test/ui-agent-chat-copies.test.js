/**
 * The agent's chat copies of its images ("Option 1".."Option 6") are never counted as new stills (live 2026-11-04):
 * with no gallery tile in the DOM they used to be, the wait ended early with 10 of 11 scenes unread (tile_not_found),
 * and those scenes were made again.
 */
import test from "node:test";
import assert from "node:assert/strict";

const { collectStillUrls } = await import("../lib/flow-ui-agent.js");

const img = (n, alt) => ({ tagName: "IMG", src: `https://flow.google.com/asb/tok${n}=w1376`, currentSrc: "", alt, naturalWidth: 1376, naturalHeight: 768 });

function pageWith({ tiles, chat }) {
  return {
    evaluate: async (fn, arg) => {
      const prev = globalThis.document;
      globalThis.document = {
        querySelectorAll: (sel) => (sel.includes("flow-grid-tile-container") ? tiles : [...tiles, ...chat]),
      };
      try { return fn(arg); } finally { globalThis.document = prev; }
    },
  };
}

const chat = [1, 2, 3, 4, 5, 6].map((i) => img(100 + i, `Option ${i}`));

test("chat copies are not stills while the gallery has no tile in the DOM", async () => {
  assert.deepEqual(await collectStillUrls(pageWith({ tiles: [], chat })), []);
});

test("gallery tiles are counted, chat copies beside them are not", async () => {
  const tiles = [img(1, "Tile displaying a user's image"), img(2, "")];
  const urls = await collectStillUrls(pageWith({ tiles, chat }));
  assert.deepEqual(urls, tiles.map((t) => t.src));
});
