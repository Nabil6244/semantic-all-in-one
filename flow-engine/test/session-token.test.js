/**
 * The session route serves an HTML interstitial while Flow's SPA is still
 * redirecting. Reading it as JSON threw
 *   `Unexpected token '<', "<!doctype "... is not valid JSON`
 * and a single short wait then reported signed-in accounts as signed out —
 * which is why "retry all" failed while retrying one at a time worked.
 * Run: node --test test/session-token.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const { getSessionToken, waitForSessionToken } = await import("../lib/flow-api.js");

/** Minimal page stub: runs the evaluated fn against a scripted fetch. */
function fakePage(responses) {
  let i = 0;
  return {
    calls: 0,
    async waitForLoadState() {},
    async evaluate(fn) {
      this.calls++;
      const r = responses[Math.min(i++, responses.length - 1)];
      globalThis.fetch = async () => {
        if (r === "throw") throw new Error("network");
        return { ok: r.ok !== false, text: async () => r.body };
      };
      return fn();
    },
  };
}

const HTML = '<!doctype html><html><head><title>Sign in</title></head></html>';
const JSON_OK = JSON.stringify({ access_token: "at-123" });

test("an HTML interstitial reads as 'not ready', never as a thrown SyntaxError", async () => {
  const page = fakePage([{ body: HTML }]);
  const token = await getSessionToken(page);   // must not throw
  assert.equal(token, null);
});

test("a real session body still yields the token", async () => {
  assert.equal(await getSessionToken(fakePage([{ body: JSON_OK }])), "at-123");
});

test("malformed and empty bodies are safe", async () => {
  for (const body of ["", "not json", "{", "null", "[]"]) {
    assert.equal(await getSessionToken(fakePage([{ body }])), null, JSON.stringify(body));
  }
});

test("a non-ok response is not parsed", async () => {
  assert.equal(await getSessionToken(fakePage([{ ok: false, body: JSON_OK }])), null);
});

test("a token arriving late is picked up instead of failing the account", async () => {
  // Exactly the observed shape: HTML first, JSON once the SPA settles.
  const page = fakePage([{ body: HTML }, { body: HTML }, { body: JSON_OK }]);
  assert.equal(await waitForSessionToken(page, 8000), "at-123");
  assert.ok(page.calls >= 3, "must have polled, not read once");
});

test("polling gives up and reports signed-out for a genuinely dead session", async () => {
  const page = fakePage([{ body: HTML }]);
  const started = Date.now();
  assert.equal(await waitForSessionToken(page, 1200), null);
  assert.ok(Date.now() - started >= 1000, "must actually wait before giving up");
  assert.ok(Date.now() - started < 6000, "must be bounded");
});

test("a mid-navigation evaluate error is treated as 'not ready', not fatal", async () => {
  const page = {
    calls: 0,
    async waitForLoadState() {},
    async evaluate() {
      this.calls++;
      if (this.calls < 3) throw new Error("Execution context was destroyed");
      return "at-456";
    },
  };
  assert.equal(await waitForSessionToken(page, 8000), "at-456");
});

test("the signed-out message is still reachable for a real sign-out", async () => {
  const src = await import("node:fs").then((fs) =>
    fs.readFileSync(new URL("../lib/flow-api.js", import.meta.url), "utf8"),
  );
  assert.match(src, /Not signed in to labs\.google/);
  // ...but only after polling, never off a single immediate read.
  assert.match(src, /await waitForSessionToken\(page\);\s*\n\s*if \(!token\)/);
});
