/**
 * Flow no longer accepts videoLengthSeconds on batchAsyncGenerateVideoText —
 * Google rejected every video job that sent it (400 INVALID_ARGUMENT), and
 * the app used to strip-and-retry around that on every single video job
 * (see the now-removed field-specific branch this replaces). The correct
 * fix is to never send a requested duration at all: Flow generates at its
 * own default length, and the renderer trims/loops the delivered clip to
 * the scene's real duration downstream (video_generator.py).
 *
 * These are static/source checks rather than a full page-mocked execution
 * of generateOneVideo() — Playwright's page.evaluate boundary makes a
 * functional mock heavy and fragile for what is fundamentally a "this
 * object literal must not contain this key" question. Matches the existing
 * convention in unknown-field.test.js (e.g. the AUTH_RETRY_DELAYS_MS test),
 * which verifies source shape rather than executing the browser-side code.
 *
 * Run: node --test test/video-duration.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../lib/flow-api.js", import.meta.url), "utf8");

function extractFunctionSource(fnStartMarker) {
  const start = src.indexOf(fnStartMarker);
  assert.ok(start >= 0, `could not find ${fnStartMarker}`);
  const rest = src.slice(start);
  // Next top-level `export `/`function ` declaration ends this function.
  const nextDecl = rest.slice(1).search(/^\s*(export |function |async function )/m);
  return nextDecl === -1 ? rest : rest.slice(0, nextDecl + 1);
}

const generateOneVideoSrc = extractFunctionSource(
  "export async function generateOneVideo(",
);

test("generateOneVideo no longer sends videoLengthSeconds", () => {
  // Matches it being set as a key/assignment/property access, not a bare
  // mention — the function keeps a comment documenting *why* it's gone,
  // which legitimately still contains the word.
  assert.doesNotMatch(generateOneVideoSrc, /videoLengthSeconds\s*[:=]|\.videoLengthSeconds\b/);
});

test("generateOneVideo does not read the operator's requested duration at all", () => {
  // The old `const duration = Number(settings.videoDuration) || videoDurations.default`
  // computation is gone entirely, not just unused — nothing in this function
  // should reference either source.
  assert.doesNotMatch(generateOneVideoSrc, /settings\.videoDuration/);
  assert.doesNotMatch(generateOneVideoSrc, /videoDurations\.default/);
});

test("generateOneVideo's video request carries no duration field of any name", () => {
  const reqMatch = /requests:\s*\[\s*\{([\s\S]*?)\},\s*\],/.exec(generateOneVideoSrc);
  assert.ok(reqMatch, "could not find the requests[0] object literal");
  const requestBody = reqMatch[1]
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
  // Top-level keys only: `key: value,` or shorthand `key,` — both terminate
  // the key name with `:` or `,` at the start of a (non-comment) line.
  const keys = [...requestBody.matchAll(/^\s*([A-Za-z_$][\w$]*)\s*[:,]/gm)].map((m) => m[1]);

  assert.deepEqual(
    keys.sort(),
    ["aspectRatio", "metadata", "seed", "textInput", "videoModelKey"].sort(),
    "the video request must carry exactly these fields — no duration field, replacement or otherwise",
  );

  // Belt-and-braces: no plausible duration-field alias snuck in under another name.
  for (const alias of [
    "duration",
    "videoLength",
    "lengthSeconds",
    "clipDuration",
    "durationSeconds",
    "videoDurationSeconds",
    "targetDuration",
  ]) {
    assert.ok(
      !keys.includes(alias),
      `found a duration-like field "${alias}" — Flow must not be told a duration`,
    );
  }
});

test("no duration-specific retry path exists — the generic unknown-field retry is untouched and field-agnostic", () => {
  // stripUnknownField/parseUnknownField (exercised generically for arbitrary
  // field names in unknown-field.test.js) is Google-API-drift infrastructure,
  // not a duration-specific workaround, and is intentionally left in place —
  // removing it would reduce resilience against any *other* field Google
  // drops next, which is out of scope for this duration cleanup. What must
  // be gone is any branch that treats videoLengthSeconds specially.
  assert.doesNotMatch(
    src,
    /unknown\.field === "videoLengthSeconds"/,
    "no field-specific special-casing for videoLengthSeconds should remain",
  );
});
