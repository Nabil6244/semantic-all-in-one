/**
 * History: Flow's old batchAsyncGenerateVideoText endpoint rejected every
 * job that sent videoLengthSeconds (400 INVALID_ARGUMENT), so the app never
 * sent a requested duration at all — Flow generated at its own default
 * length, and the renderer trimmed/looped the delivered clip to the scene's
 * real duration downstream (video_generator.py). That endpoint is gone;
 * generateOneVideo now calls the current YhhmEf/jwpduf/as29s lifecycle (see
 * flow-engine investigation notes), whose compact mode string (e.g.
 * "abra_t2v_4s_360p") DOES carry an explicit duration. The renderer-trims-
 * anyway reasoning still applies, so the app deliberately keeps requesting
 * the fixed, cheapest duration rather than the operator's setting — these
 * tests now check that against the new implementation's actual shape.
 *
 * These are static/source checks rather than a full page-mocked execution
 * of generateOneVideo() — Playwright's page.evaluate boundary makes a
 * functional mock heavy and fragile for what is fundamentally a "this
 * string/object literal must not contain this value" question. Matches the
 * existing convention in unknown-field.test.js (e.g. the AUTH_RETRY_DELAYS_MS
 * test), which verifies source shape rather than executing the browser-side
 * code.
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

test("generateOneVideo's compact mode string is the one confirmed-working literal, not a template", () => {
  // Flow's current API (YhhmEf) DOES accept an explicit duration/resolution
  // — unlike the old batchAsyncGenerateVideoText this replaces — but only
  // "abra_t2v_4s_360p" has ever been confirmed live. A templated resolution
  // that silently defaulted to an untested "720p" previously broke every
  // video generation (HTTP 200 but an application-level NOT_FOUND). Until a
  // wider set of combinations is live-verified the same way this project
  // verified everything else, buildVideoModeString must return that one
  // literal unconditionally, never a settings-derived template.
  const buildFnSrc = src.slice(
    src.indexOf("function buildVideoModeString"),
    src.indexOf("function buildVideoModeString") + 300,
  );
  assert.match(buildFnSrc, /return\s+"abra_t2v_4s_360p"/, "must return the one confirmed-working literal");
  assert.doesNotMatch(buildFnSrc, /settings\.videoDuration/);
  assert.doesNotMatch(buildFnSrc, /settings\.videoResolution/);
  assert.doesNotMatch(buildFnSrc, /settings\.videoModel/);
});

test("generateOneVideo's YhhmEf request carries no top-level seed field", () => {
  // The live YhhmEf request (confirmed) carries no client-supplied seed —
  // unlike ogiZ0b's image request, which still does (untouched, see
  // generateOneImage). Belt-and-braces: no plausible seed-field alias
  // should appear inside generateOneVideo's own request-building code.
  for (const alias of ["seed", "randomSeed()"]) {
    assert.ok(
      !generateOneVideoSrc.includes(alias),
      `found "${alias}" in generateOneVideo — Flow's current video RPC takes no client seed`,
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
