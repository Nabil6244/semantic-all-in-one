/**
 * Flow page helpers — ported from extension background.js patterns.
 * Runs inside Playwright page.evaluate / page context.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  api,
  secrets,
  urls,
  models,
  aspectRatios,
  timing,
  videoModels,
  videoDurations,
  videoResolutions,
  videoAspectRatios,
  resolveVideoModelKey,
} from "../config.js";

export { api, secrets, urls, models, aspectRatios, timing, videoModels, videoDurations, videoResolutions, videoAspectRatios, resolveVideoModelKey };

export class QuotaError extends Error {
  constructor(m) {
    super(m);
    this.name = "QuotaError";
  }
}
export class RateLimitError extends Error {
  constructor(m) {
    super(m);
    this.name = "RateLimitError";
  }
}
/**
 * The Flow account's Google session is gone or expired — raised ONLY after
 * re-checking the session, never from a bare 401.
 *
 * A 401 alone does not mean the account is signed out: Flow's IMAGE endpoint
 * is project-scoped and current, while the VIDEO endpoint is the legacy
 * global `/v1/video:*` one, and Google can reject the latter while the very
 * same token still generates images fine. Treating that as "signed out"
 * would mark a perfectly good account dead and stop scheduling it.
 */
export class AuthExpiredError extends Error {
  constructor(m) {
    super(m);
    this.name = "AuthExpiredError";
  }
}

/**
 * Google rejected the request even though the account's session is still
 * valid — i.e. the endpoint or its auth contract has moved, not the login.
 */
export class EndpointRejectedError extends Error {
  constructor(m) {
    super(m);
    this.name = "EndpointRejectedError";
  }
}

export class FatalError extends Error {
  constructor(m, recoverable = false) {
    super(m);
    this.name = "FatalError";
    this.recoverable = recoverable;
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Close newsletter / promo modals that block Flow UI but leave cookies intact. */
export async function dismissBlockingOverlays(page) {
  try {
    await page.keyboard.press("Escape");
    await sleep(250);
  } catch {
    /* ignore */
  }
  try {
    return await safeEvaluate(page, () => {
      const labels = [
        "close",
        "dismiss",
        "no thanks",
        "not now",
        "maybe later",
        "skip",
        "got it",
        "×",
      ];
      let clicked = 0;
      for (const btn of document.querySelectorAll(
        'button, [role="button"], [aria-label*="lose" i]',
      )) {
        const t = (
          btn.textContent ||
          btn.getAttribute("aria-label") ||
          ""
        ).toLowerCase();
        if (labels.some((l) => t.includes(l))) {
          try {
            btn.click();
            clicked++;
          } catch {
            /* ignore */
          }
        }
      }
      return clicked;
    });
  } catch {
    return 0;
  }
}

function isContextDestroyedError(err) {
  const m = String(err?.message || err);
  return (
    m.includes("Execution context was destroyed") ||
    m.includes("context was destroyed") ||
    m.includes("most likely because of a navigation") ||
    m.includes("Target closed") ||
    m.includes("Target page, context or browser has been closed")
  );
}

/** Retry page.evaluate when Flow's SPA navigates mid-call (common on video start). */
async function safeEvaluate(page, fn, arg, { retries = 4, settleMs = 700 } = {}) {
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      await page.waitForLoadState("domcontentloaded", { timeout: 20000 }).catch(() => {});
      if (attempt > 0) await sleep(settleMs * attempt);
      if (arg === undefined) return await page.evaluate(fn);
      return await page.evaluate(fn, arg);
    } catch (err) {
      lastErr = err;
      if (!isContextDestroyedError(err) || attempt >= retries) throw err;
    }
  }
  throw lastErr;
}

export async function waitForFlowReady(page, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const ready = await safeEvaluate(page, () => {
        const hasProject = !!window.location.href.match(/project\/([a-f0-9-]+)/);
        const hasRecaptcha =
          typeof grecaptcha !== "undefined" && !!grecaptcha?.enterprise;
        return { url: location.href, hasProject, hasRecaptcha };
      });
      if (ready.hasRecaptcha) return ready;
    } catch {
      /* navigation */
    }
    await sleep(800);
  }
  throw new FatalError("Timed out waiting for Flow page / reCAPTCHA", true);
}

export async function getSessionToken(page) {
  // Flow moved off labs.google onto flow.google.com, and the old
  // `/fx/api/auth/session` REST route no longer exists there at all (it now
  // 200s with the app's HTML shell, not JSON — confirmed live). The new app
  // is built on Google's internal Wiz framework, which never had a session
  // REST endpoint to begin with: it embeds the signed-in session's token
  // directly in the page as `window.WIZ_global_data.SNlM0e` when the page
  // loads. Reading that in-page value (no fetch, no new network request) is
  // the direct replacement for the old response body this function used to
  // return — everything downstream (waitForSessionToken's polling,
  // openOrCreateProject's `if (!token)` check) is unchanged.
  return safeEvaluate(page, () => {
    try {
      const data = window.WIZ_global_data;
      if (!data) return null;
      const raw = data.SNlM0e;
      // Defensive: SNlM0e is a bare string on every page observed so far;
      // tolerate a wrapped {e: "..."} shape too rather than assuming.
      const token = typeof raw === "string" ? raw : (raw && typeof raw.e === "string" ? raw.e : null);
      const trimmed = (token || "").trim();
      return trimmed ? trimmed : null;
    } catch {
      return null;
    }
  });
}

/**
 * Wait for Flow to actually hand out a session token.
 *
 * A fixed sleep was not enough: measured against real signed-in profiles, an
 * immediate read after navigation yields nothing (or a token Google rejects),
 * while the SAME profile answers normally a few seconds later. A single 1500ms
 * wait therefore reported perfectly good accounts as "not signed in" — and only
 * when several were started at once, which is why retrying one at a time
 * appeared to work: that page was already warm.
 */
export async function waitForSessionToken(page, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let delay = 500;
  for (;;) {
    let token = null;
    try {
      token = await getSessionToken(page);
    } catch {
      /* mid-navigation — treated the same as "not ready yet" */
    }
    if (token) return token;
    if (Date.now() >= deadline) return null;
    await sleep(Math.min(delay, Math.max(0, deadline - Date.now())));
    delay = Math.min(delay * 1.6, 3000);
  }
}

export async function getProjectId(page) {
  return safeEvaluate(page, () => {
    const m = window.location.href.match(/project\/([a-f0-9-]+)/);
    return m ? m[1] : null;
  });
}

export async function tryGetAccountEmail(page) {
  return safeEvaluate(page, () => {
    const t = document.body?.innerText || "";
    const m = t.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
    return m ? m[0] : null;
  }).catch(() => null);
}

/**
 * Create a new Flow project via the current "jHPbke" batchexecute RPC —
 * confirmed live (see flow-engine investigation notes): clicking "+ New
 * project" on flow.google.com's home page sends exactly
 *   f.req=[[["jHPbke","[\"projects/*\",[null,[\"<title>\"]],[null,22]]",null,"generic"]]]
 * (source-path=/, same bl/f.sid/at sourced from window.WIZ_global_data as
 * every other RPC in this file — no reCAPTCHA token, unlike ogiZ0b/YhhmEf)
 * and gets back `["<new-project-id>", ["<title>"]]`. Replaces the old
 * api.createProjectPath REST call (/fx/api/trpc/project.createProject),
 * which no longer exists on flow.google.com and was failing every project
 * creation with HTTP 400/401.
 */
export async function createFlowProject(page) {
  const title = new Date()
    .toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
    .replace(",", "");

  const out = await safeEvaluate(
    page,
    async ({ title, timeoutMs }) => {
      const wiz = window.WIZ_global_data || {};
      const at = wiz.SNlM0e;
      const bl = wiz.cfb2h;
      const fsid = wiz.FdrFJe;
      if (!at || !bl || !fsid) {
        return { error: "Missing WIZ session state (at/bl/f.sid)", recoverable: true };
      }

      const reqId = 100000 + Math.floor(Math.random() * 900000);
      const url =
        "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute" +
        "?rpcids=jHPbke&source-path=%2F" +
        "&bl=" + encodeURIComponent(bl) +
        "&f.sid=" + encodeURIComponent(fsid) +
        "&hl=en-GB&_reqid=" + reqId + "&rt=c";
      const args = ["projects/*", [null, [title]], [null, 22]];
      const bodyStr =
        "f.req=" + encodeURIComponent(JSON.stringify([[["jHPbke", JSON.stringify(args), null, "generic"]]])) +
        "&at=" + encodeURIComponent(at);

      const ac = new AbortController();
      const tm = setTimeout(() => ac.abort(), timeoutMs);
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
          body: bodyStr,
          credentials: "include",
          signal: ac.signal,
        });
        clearTimeout(tm);
        const text = await resp.text();
        if (!resp.ok) return { error: "HTTP " + resp.status, status: resp.status, errText: text.slice(0, 500) };
        return { success: true, text };
      } catch (e) {
        clearTimeout(tm);
        return { error: e.name === "AbortError" ? "Request timed out" : e.message, isTimeout: e.name === "AbortError" };
      }
    },
    { title, timeoutMs: timing.apiRequestTimeoutMs },
  );

  if (!out || out.error) {
    throw new FatalError("Could not create Flow project: " + (out?.error || "no response"), true);
  }

  const parsed = parseBatchExecuteResponse(out.text, "jHPbke");
  const projectId = Array.isArray(parsed) && typeof parsed[0] === "string" ? parsed[0] : null;
  if (!projectId) {
    throw new FatalError("Could not create Flow project: no projectId in response", true);
  }
  return projectId;
}

export async function openOrCreateProject(page) {
  let projectId = await getProjectId(page);
  if (projectId) return projectId;

  // Ensure we're on Flow home (not a dead URL). Same domain-check fix as
  // gotoFlow()/checkAuthStatus() — "/tools/flow" only ever existed on the
  // old labs.google URLs; on flow.google.com this must accept the current
  // domain too, or every call forces a needless re-navigation.
  const currentUrl = page.url();
  if (!currentUrl.includes("flow.google.com") && !currentUrl.includes("labs.google")) {
    await page.goto(urls.flowHome, { waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(1500);
  }

  // Poll rather than trusting the sleep above: a signed-in account can need
  // several seconds after navigation before the session route returns JSON.
  const token = await waitForSessionToken(page);
  if (!token) {
    throw new FatalError(
      "Not signed in to labs.google — open this account and sign in once",
      false,
    );
  }

  projectId = await createFlowProject(page);
  await page.goto(urls.flowProject(projectId), {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await waitForFlowReady(page);
  return projectId;
}

function uuid() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 3) | 8).toString(16);
  });
}

// No longer called (generateOneVideo's current YhhmEf request carries no
// client-supplied seed at all — confirmed live). Left in place rather than
// deleted: removing unused-but-harmless code is out of scope for this change.
function randomSeed() {
  return Math.floor(Math.random() * 300000);
}

/**
 * Fresh seed for the ogiZ0b image-generation call only. Range is a positive,
 * signed-32-bit-safe integer, matching the magnitude of real seeds observed
 * live from Flow's own UI (e.g. 943918382, 1757688819) — any integer is a
 * structurally valid seed, this range simply mirrors what Flow itself sends.
 */
function randomImageSeed() {
  return Math.floor(Math.random() * 0x7fffffff);
}

/**
 * POST to aisandbox with Bearer + reCAPTCHA token minted in-page.
 */
/**
 * Pull `Unknown name "FIELD" at 'requests[0]'` out of a Google 400 body.
 * Returns { field, path } or null.
 */
export function parseUnknownField(errText) {
  if (!errText) return null;
  const m = /Unknown name \\?"([^"\\]+)\\?" at '([^']*)'/.exec(String(errText));
  if (!m) return null;
  return { field: m[1], path: m[2] || "" };
}

/**
 * Remove one unknown field from a request body, at the path Google named.
 * Supports "" (top level) and "requests[N]" / "requests[N].sub.path".
 */
export function stripUnknownField(bodyObj, field, path) {
  if (!bodyObj || !field) return false;
  let target = bodyObj;
  for (const seg of String(path || "").split(".").filter(Boolean)) {
    const idx = /^([A-Za-z_$][\w$]*)\[(\d+)\]$/.exec(seg);
    if (idx) {
      const arr = target?.[idx[1]];
      if (!Array.isArray(arr)) return false;
      target = arr[Number(idx[2])];
    } else {
      target = target?.[seg];
    }
    if (!target || typeof target !== "object") return false;
  }
  if (!(field in target)) return false;
  delete target[field];
  return true;
}

// Backoff for 401s caused by a not-yet-warm Flow session.
const AUTH_RETRY_DELAYS_MS = [2500, 5000, 9000];

export async function apiPost(
  page,
  url,
  bodyObj,
  recaptchaAction,
  _retriedFields,
  _authAttempt,
) {
  const siteKey = secrets.recaptchaSiteKey;
  const timeoutMs = timing.apiRequestTimeoutMs;

  const out = await safeEvaluate(
    page,
    async ({ url, bodyObj, siteKey, recaptchaAction, timeoutMs }) => {
      const tokenRes = await fetch("/fx/api/auth/session", {
        credentials: "include",
      });
      if (!tokenRes.ok) return { error: "No auth session", recoverable: true };
      const { access_token: auth } = await tokenRes.json();
      if (!auth) return { error: "No access_token", recoverable: true };

      const grec = window.grecaptcha?.enterprise;
      if (!grec) return { error: "No reCAPTCHA", recoverable: true };
      const captcha = await grec.execute(siteKey, { action: recaptchaAction });
      if (!captcha) return { error: "reCAPTCHA execute failed", recoverable: true };

      if (bodyObj.clientContext?.recaptchaContext) {
        bodyObj.clientContext.recaptchaContext.token = captcha;
      }
      if (Array.isArray(bodyObj.requests)) {
        for (const req of bodyObj.requests) {
          if (req.clientContext?.recaptchaContext) {
            req.clientContext.recaptchaContext.token = captcha;
          }
        }
      }

      const ac = new AbortController();
      const tm = setTimeout(() => ac.abort(), timeoutMs);
      try {
        const rp = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "text/plain;charset=UTF-8",
            Authorization: "Bearer " + auth,
          },
          body: JSON.stringify(bodyObj),
          signal: ac.signal,
        });
        clearTimeout(tm);
        const tx = await rp.text();
        if (!rp.ok) {
          return {
            error: "HTTP " + rp.status,
            status: rp.status,
            errText: tx.substring(0, 500),
          };
        }
        try {
          return { success: true, data: JSON.parse(tx) };
        } catch {
          return { success: true, data: tx };
        }
      } catch (e) {
        clearTimeout(tm);
        return {
          error: e.name === "AbortError" ? "Request timed out" : e.message,
          isTimeout: e.name === "AbortError",
        };
      }
    },
    { url, bodyObj, siteKey, recaptchaAction, timeoutMs },
  );

  if (!out) throw new FatalError("Page evaluate failed", true);
  if (out.error) {
    if (out.status === 429 || (out.errText || "").includes("RESOURCE_EXHAUSTED")) {
      let reason = "RESOURCE_EXHAUSTED";
      try {
        const m = JSON.parse(out.errText);
        reason =
          m?.error?.details?.[0]?.reason || m?.error?.status || reason;
      } catch {}
      if (reason.includes("PER_MODEL") || reason.includes("DAILY_QUOTA")) {
        throw new QuotaError(
          "Daily quota reached for this model — try another model or account",
        );
      }
      throw new RateLimitError("Rate limited by Google");
    }
    if (
      out.status === 401 ||
      (out.errText || "").includes("UNAUTHENTICATED") ||
      (out.errText || "").includes("invalid authentication credentials")
    ) {
      // A 401 here is usually a RACE, not a signed-out account. Flow's SPA
      // needs a few seconds after navigation before /fx/api/auth/session
      // hands out a token Google will accept, and video jobs fire in that
      // first second (see generateOneVideo). Measured directly against all
      // nine signed-in profiles: querying immediately returns a token that
      // the API answers 401 to, while the same profile answers 200 once the
      // page has settled. So back off and retry with a fresh token before
      // concluding anything about the account.
      const authAttempt = (_authAttempt || 0) + 1;
      if (authAttempt <= AUTH_RETRY_DELAYS_MS.length) {
        const waitMs = AUTH_RETRY_DELAYS_MS[authAttempt - 1];
        console.warn(
          `[FLOW] 401 from ${url.split("/").pop()} — session likely not warm yet; ` +
            `retrying in ${waitMs}ms (attempt ${authAttempt}/${AUTH_RETRY_DELAYS_MS.length})`,
        );
        await sleep(waitMs);
        await waitForFlowReady(page).catch(() => {});
        return apiPost(page, url, bodyObj, recaptchaAction, _retriedFields, authAttempt);
      }

      // Retries exhausted — now it is worth deciding whose fault it is.
      let stillSignedIn = false;
      try {
        stillSignedIn = !!(await getSessionToken(page));
      } catch {
        stillSignedIn = false;
      }
      if (stillSignedIn) {
        throw new EndpointRejectedError(
          `Google kept rejecting this request (401) after ${authAttempt - 1} retries ` +
            `while the account is still signed in — endpoint ${url}`,
        );
      }
      throw new AuthExpiredError(
        "Flow account is signed out — open Accounts and sign in again",
      );
    }
    if (out.status === 403 || out.recoverable) {
      throw new FatalError(out.error + (out.errText ? ": " + out.errText : ""), true);
    }
    if (out.status === 400) {
      // Google periodically drops or renames fields in this private API
      // (e.g. `videoLengthSeconds` disappeared from batchAsyncGenerateVideoText,
      // which failed every video job with INVALID_ARGUMENT). The request is
      // rejected outright, so nothing was generated and retrying is safe.
      // Strip exactly the field Google named and retry once per field, rather
      // than pinning the payload to a shape Google may change again.
      const unknown = parseUnknownField(out.errText);
      const tried = _retriedFields || new Set();
      if (unknown && !tried.has(unknown.field)) {
        if (stripUnknownField(bodyObj, unknown.field, unknown.path)) {
          tried.add(unknown.field);
          console.warn(
            `[FLOW] Google rejected unknown field "${unknown.field}" at ` +
              `'${unknown.path}' — retrying without it.`,
          );
          return apiPost(page, url, bodyObj, recaptchaAction, tried, _authAttempt);
        }
      }
      throw new Error("Rejected (400): " + (out.errText || out.error));
    }
    throw new Error(out.error + (out.errText ? ": " + out.errText : ""));
  }
  return out.data;
}

/**
 * batchexecute codec — narrowly scoped to what Flow's ogiZ0b call needs.
 * Not a general RPC framework: just enough to build one request envelope
 * and parse one response back out.
 *
 * Request shape (confirmed live, see flow-engine/README or investigation
 * notes): f.req=[[[rpcid, JSON.stringify(args), null, "generic"]]]&at=<token>
 *
 * Response shape: Google's standard anti-hijacking-prefixed, length-chunked
 * batchexecute format:
 *   )]}'
 *   <byte-length>
 *   [["wrb.fr", rpcid, "<json-encoded-result>", null, null, null, "generic"], ...]
 *   <byte-length>
 *   [["e", 4, null, null, <n>]]
 */
function buildBatchExecuteRequest(rpcid, args, atToken) {
  const envelope = [[[rpcid, JSON.stringify(args), null, "generic"]]];
  return "f.req=" + encodeURIComponent(JSON.stringify(envelope)) + "&at=" + encodeURIComponent(atToken);
}

export function parseBatchExecuteResponse(text, rpcid) {
  let body = String(text || "");
  if (body.startsWith(")]}'")) body = body.slice(4);

  // Length-prefixed chunks: a line holding a declared byte length, then that
  // many bytes of JSON. NOT sliced by that declared length — verified live
  // against a real captured response that the declared count is 2 bytes
  // larger than what a JS string's .length actually measures after
  // fetch()/page.evaluate() has already decoded the body (almost certainly
  // a \r\n vs \n line-ending difference between Google's byte count and the
  // normalized string Playwright hands back). Every chunk's JSON is emitted
  // on its own single line in every response observed, so splitting on "\n"
  // and skipping bare-integer length-marker lines is both simpler and
  // actually correct against live data, where the byte-slicing approach
  // this replaces was not. Malformed/truncated input just yields nothing
  // parseable rather than throwing — callers treat "not found" as a
  // generation failure.
  const lines = body.split("\n");
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || /^\d+$/.test(line)) continue; // blank or a length-marker line
    let arr;
    try {
      arr = JSON.parse(line);
    } catch {
      continue;
    }
    if (!Array.isArray(arr)) continue;
    for (const entry of arr) {
      if (Array.isArray(entry) && entry[0] === "wrb.fr" && entry[1] === rpcid) {
        if (typeof entry[2] !== "string") return null;
        try {
          return JSON.parse(entry[2]);
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

/**
 * Pull {mediaId, fifeUrl, width, height} out of ogiZ0b's decoded result.
 * Anchored to the observed shape (parsed[0][0] = the media entry, its
 * field[6][0] = detail array containing the flow-content.google URL
 * somewhere, its last element = [width, height]) but searches rather than
 * assumes exact indices for the URL specifically, since "Google's response
 * shape drifts" was already true of the old REST response and is expected
 * to remain true here.
 */
export function extractOgiZ0bImageResult(parsed) {
  let mediaId = null;
  let fifeUrl = null;
  let width = null;
  let height = null;
  try {
    const entry = parsed?.[0]?.[0];
    if (Array.isArray(entry)) {
      if (typeof entry[0] === "string") mediaId = entry[0];
      const detail = entry[6]?.[0];
      if (Array.isArray(detail)) {
        const url = detail.find((v) => typeof v === "string" && v.startsWith("https://flow-content.google/"));
        if (url) fifeUrl = url;
      }
      const dims = entry[entry.length - 1];
      if (Array.isArray(dims) && dims.length === 2) {
        if (typeof dims[0] === "number") width = dims[0];
        if (typeof dims[1] === "number") height = dims[1];
      }
    }
  } catch {
    /* fall through to the last-resort scan below */
  }
  if (!fifeUrl && parsed) {
    // Last-resort deep scan — mirrors the old generateOneImage's own
    // defensive fallback for response-shape drift.
    const blob = JSON.stringify(parsed);
    const m = blob.match(/https:\/\/flow-content\.google\/[^"\\]+/i);
    if (m) fifeUrl = m[0].replace(/\\u003d/g, "=").replace(/\\u0026/g, "&");
  }
  if (!mediaId && fifeUrl) {
    const m = fifeUrl.match(/\/image\/([^?]+)/);
    if (m) mediaId = m[1];
  }
  return { mediaId, fifeUrl, width, height };
}

export async function generateOneImage(page, projectId, prompt, settings, promptIndex) {
  // Parity with generateOneVideo: never fire the API call while Flow's SPA is
  // still navigating. Without this the image path raced the page and threw
  // "Execution context was destroyed" — the video path already waited, which
  // is why videos succeeded and images failed in the same run.
  await waitForFlowReady(page);

  const seed =
    settings.seedMode === "fixed" && settings.seedValue != null
      ? settings.seedValue
      : randomImageSeed();
  const model = settings.model || models.default;
  const uuidA = uuid();
  const uuidB = uuid();
  const uuidC = uuid();

  const out = await safeEvaluate(
    page,
    async ({ projectId, model, prompt, seed, siteKey, recaptchaAction, uuidA, uuidB, uuidC, timeoutMs }) => {
      // WIZ_global_data carries the page's own CSRF/session state — same
      // mechanism getSessionToken()/checkAuthStatus() already read from
      // (SNlM0e), plus the batchexecute query params (cfb2h -> bl,
      // FdrFJe -> f.sid), confirmed live against this exact page.
      const wiz = window.WIZ_global_data || {};
      const at = wiz.SNlM0e;
      const bl = wiz.cfb2h;
      const fsid = wiz.FdrFJe;
      if (!at || !bl || !fsid) {
        return { error: "Missing WIZ session state (at/bl/f.sid)", recoverable: true };
      }

      const grec = window.grecaptcha?.enterprise;
      if (!grec) return { error: "No reCAPTCHA", recoverable: true };
      const captcha = await grec.execute(siteKey, { action: recaptchaAction });
      if (!captcha) return { error: "reCAPTCHA execute failed", recoverable: true };

      // Positional structure reproduced exactly as captured live — see
      // flow-engine investigation notes. "context" is reused verbatim at
      // both the per-request position and the batch-level position, exactly
      // as observed; array positions are the confirmed jspb wire encoding
      // for FlowService.BatchGenerateImages ("ogiZ0b"), not invented here.
      const context = [null, 22, null, null, null, projectId, null, null, null, null, [captcha, 1]];
      const request = [
        null, null, null,
        seed,              // field 4 — confirmed via static trace of the
                            // real Flow client (see investigation notes)
        3,
        model,
        null,
        context,
        [[[prompt]]],
        null, null, null,
        uuidA,
        uuidB,
      ];
      const args = [null, [request], 1, context, [uuidC]];

      const reqId = 100000 + Math.floor(Math.random() * 900000);
      const url =
        "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute" +
        "?rpcids=ogiZ0b" +
        "&source-path=" + encodeURIComponent("/project/" + projectId) +
        "&bl=" + encodeURIComponent(bl) +
        "&f.sid=" + encodeURIComponent(fsid) +
        "&hl=en-GB" +
        "&_reqid=" + reqId +
        "&rt=c";

      const bodyStr =
        "f.req=" + encodeURIComponent(JSON.stringify([[["ogiZ0b", JSON.stringify(args), null, "generic"]]])) +
        "&at=" + encodeURIComponent(at);

      const ac = new AbortController();
      const tm = setTimeout(() => ac.abort(), timeoutMs);
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
          body: bodyStr,
          credentials: "include",
          signal: ac.signal,
        });
        clearTimeout(tm);
        const text = await resp.text();
        if (!resp.ok) {
          return { error: "HTTP " + resp.status, status: resp.status, errText: text.slice(0, 500) };
        }
        return { success: true, text };
      } catch (e) {
        clearTimeout(tm);
        return {
          error: e.name === "AbortError" ? "Request timed out" : e.message,
          isTimeout: e.name === "AbortError",
        };
      }
    },
    {
      projectId, model, prompt, seed,
      siteKey: secrets.recaptchaSiteKey, recaptchaAction: api.recaptchaAction,
      uuidA, uuidB, uuidC, timeoutMs: timing.apiRequestTimeoutMs,
    },
  );

  if (!out) throw new FatalError("Page evaluate failed", true);
  if (out.error) {
    if (out.status === 429) throw new RateLimitError("Rate limited by Google");
    if (out.status === 401 || out.recoverable) {
      // Same race apiPost() already documents: the session can be a few
      // seconds from warm right after navigation. One re-check + retry,
      // reusing the same session-readiness wait as the rest of the file.
      await waitForFlowReady(page).catch(() => {});
      const stillSignedIn = await getSessionToken(page).catch(() => null);
      if (!stillSignedIn) {
        throw new AuthExpiredError("Flow account is signed out — open Accounts and sign in again");
      }
      throw new EndpointRejectedError(
        `Google rejected the image generation request (${out.status || out.error}) while the account is still signed in`,
      );
    }
    throw new Error(out.error + (out.errText ? ": " + out.errText : ""));
  }

  const parsed = parseBatchExecuteResponse(out.text, "ogiZ0b");
  const { mediaId, fifeUrl, width, height } = extractOgiZ0bImageResult(parsed);
  if (!mediaId) throw new Error("No mediaId in generation response");
  return { mediaId, fifeUrl, width, height };
}

/**
 * Mirror Flow's duration tab in the editor — ported verbatim from
 * background.js's syncFlowVideoDuration (chrome.scripting -> page.evaluate).
 * Best-effort: generation still proceeds if the tab isn't found.
 */
export async function syncFlowVideoDuration(page, seconds) {
  const allowed = new Set(videoDurations.options.map((o) => o.value));
  if (!allowed.has(seconds)) return;
  await page
    .evaluate(async (dur) => {
      const wait = (ms) => new Promise((r) => setTimeout(r, ms));
      const label = `${dur}s`;
      for (let attempt = 0; attempt < 20; attempt++) {
        const tab = [...document.querySelectorAll('[role="tab"]')].find(
          (el) => (el.textContent || "").trim() === label,
        );
        if (tab) {
          tab.click();
          await wait(400);
          return { ok: true };
        }
        await wait(250);
      }
      return { ok: false };
    }, seconds)
    .catch(() => null);
}

/**
 * Video RPC lifecycle — confirmed live (see flow-engine investigation notes):
 *   YhhmEf (start) -> workflowId/mediaId -> jwpduf (poll, ~5-8s interval)
 *   -> status 3 (complete) -> as29s (fetch final detail) -> signed
 *   flow-content.google/video/... URL.
 *
 * Every workflow entry across all three RPCs shares one recognizable shape:
 * [workflowId, projectId, mediaId, "CAE", null, DETAIL, ...] — "CAE" is a
 * stable literal marker observed in every response. Searching for it (rather
 * than hardcoding each RPC's different wrapping depth: YhhmEf nests it one
 * level deeper than jwpduf, and as29s returns it unwrapped) is the same
 * "search, don't assume a fixed index" approach extractOgiZ0bImageResult
 * already uses for response-shape drift.
 */
function findVideoWorkflowEntry(node, depth = 0) {
  if (!Array.isArray(node) || depth > 6) return null;
  if (
    typeof node[0] === "string" &&
    typeof node[1] === "string" &&
    typeof node[2] === "string" &&
    node[3] === "CAE"
  ) {
    return node;
  }
  for (const child of node) {
    const found = findVideoWorkflowEntry(child, depth + 1);
    if (found) return found;
  }
  return null;
}

function deepFindVideoContentUrl(node) {
  if (typeof node === "string" && node.startsWith("https://flow-content.google/video/")) return node;
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = deepFindVideoContentUrl(child);
      if (found) return found;
    }
  }
  return null;
}

// Status marker observed at workflowEntry[5][8][0] (DETAIL[8], itself a
// single-element array). Confirmed live across 5 consecutive polls: stayed
// 2 while processing, flipped to 3 on the same poll the CDN URL first
// appeared. No FAILED value has been observed — see pollVideoStatus's
// timeout fallback for that case.
const VIDEO_STATUS_PENDING = 2;
const VIDEO_STATUS_COMPLETE = 3;

export function extractVideoStartResult(parsed) {
  const entry = findVideoWorkflowEntry(parsed);
  return {
    workflowId: entry ? entry[0] || null : null,
    mediaId: entry ? entry[2] || null : null,
  };
}

export function extractVideoPollStatus(parsed) {
  const entry = findVideoWorkflowEntry(parsed);
  const detail = entry ? entry[5] : null;
  const statusArr = Array.isArray(detail) ? detail[8] : null;
  const status = Array.isArray(statusArr) ? statusArr[0] : null;
  return {
    status,
    workflowId: entry ? entry[0] || null : null,
    mediaId: entry ? entry[2] || null : null,
  };
}

export function extractAs29sVideoResult(parsed) {
  const entry = findVideoWorkflowEntry(parsed);
  let fifeUrl = deepFindVideoContentUrl(parsed);
  if (!fifeUrl && parsed) {
    // Last-resort deep scan, same convention as extractOgiZ0bImageResult.
    const blob = JSON.stringify(parsed);
    const m = blob.match(/https:\/\/flow-content\.google\/video\/[^"\\]+/i);
    if (m) fifeUrl = m[0].replace(/\\u003d/g, "=").replace(/\\u0026/g, "&");
  }
  return {
    mediaId: entry ? entry[2] || null : null,
    workflowId: entry ? entry[0] || null : null,
    fifeUrl,
  };
}

/**
 * Compact mode string YhhmEf expects. Two genuinely different shapes exist,
 * both confirmed via real live captures (not guessed):
 *
 *  - Veo 3.1 models (lite/fast/quality): Flow's own UI has NO duration or
 *    resolution picker for these at all — each is a single fixed
 *    combination, and the mode string IS the model key verbatim, e.g.
 *    "veo_3_1_t2v_lite" (live-confirmed). "veo_3_1_t2v_fast" and
 *    "veo_3_1_t2v_quality" follow the identical naming pattern — the exact
 *    same literal already used as their videoModels config key — so this
 *    is reusing a proven naming pattern, not guessing at an unrelated,
 *    structurally different value the way the old 720p bug was.
 *
 *  - "abra" (Flow's current UI displays it as "Omni 1.1 Flash"): the one
 *    model with a real duration (4/6/8/10s) and resolution (360p/720p)
 *    picker. Mode string: "abra_t2v_{duration}s" + "_360p" ONLY if
 *    resolution is 360p — 720p is the unmarked default and gets NO suffix.
 *    Live-confirmed:
 *      "abra_t2v_4s_360p"  (360p, 4s)
 *      "abra_t2v_6s_360p"  (360p, 6s)
 *      "abra_t2v_4s"       (720p, 4s — no suffix)
 *    8s/10s are the same "{n}s" substitution into this already-confirmed
 *    template, not a new guess. The OLD code had the resolution rule
 *    backwards — it always appended an explicit "_720p" suffix, which
 *    Google rejected with an application-level NOT_FOUND (wrb.fr status
 *    code 5). That backwards assumption is what broke every video
 *    generation until this was captured live and fixed.
 *
 * Aspect ratio (portrait/landscape) is deliberately NOT part of this
 * string: the prior working implementation computed a "_portrait" variant
 * via resolveVideoModelKey() but then stripped it again before use, so
 * aspect ratio has never actually varied the video mode string — only
 * image generation's aspectRatio does anything today.
 */
function buildVideoModeString(settings) {
  const modelKey = resolveVideoModelKey(settings.videoModel, false);
  if (modelKey !== "abra") return modelKey;

  const allowedDurations = videoDurations.options.map((o) => o.value);
  const requested = Number(settings.videoDuration);
  const duration = allowedDurations.includes(requested) ? requested : videoDurations.default;
  const suffix = settings.videoResolution === "360p" ? "_360p" : "";
  return `abra_t2v_${duration}s${suffix}`;
}

/**
 * Poll one video workflow via jwpduf until it completes. No client-supplied
 * seed and no reCAPTCHA token are sent by jwpduf itself (confirmed live —
 * only the initial YhhmEf call carries the captcha context); this only needs
 * at/bl/f.sid, same WIZ_global_data source as everywhere else in this file.
 */
export async function pollVideoStatus(page, workflowId, projectId) {
  const maxTries = Math.max(1, Math.ceil(timing.videoPollTimeoutMs / timing.videoPollIntervalMs));
  let errStreak = 0;
  for (let i = 0; i < maxTries; i++) {
    await sleep(timing.videoPollIntervalMs);

    const out = await safeEvaluate(
      page,
      async ({ workflowId, timeoutMs }) => {
        const wiz = window.WIZ_global_data || {};
        const at = wiz.SNlM0e;
        const bl = wiz.cfb2h;
        const fsid = wiz.FdrFJe;
        if (!at || !bl || !fsid) {
          return { error: "Missing WIZ session state (at/bl/f.sid)", recoverable: true };
        }
        const reqId = 100000 + Math.floor(Math.random() * 900000);
        const url =
          "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute" +
          "?rpcids=jwpduf&bl=" + encodeURIComponent(bl) +
          "&f.sid=" + encodeURIComponent(fsid) +
          "&hl=en-GB&_reqid=" + reqId + "&rt=c";
        const args = [null, null, [[workflowId]]];
        const bodyStr =
          "f.req=" + encodeURIComponent(JSON.stringify([[["jwpduf", JSON.stringify(args), null, "generic"]]])) +
          "&at=" + encodeURIComponent(at);
        const ac = new AbortController();
        const tm = setTimeout(() => ac.abort(), timeoutMs);
        try {
          const resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
            body: bodyStr,
            credentials: "include",
            signal: ac.signal,
          });
          clearTimeout(tm);
          const text = await resp.text();
          if (!resp.ok) return { error: "HTTP " + resp.status, status: resp.status, errText: text.slice(0, 500) };
          return { success: true, text };
        } catch (e) {
          clearTimeout(tm);
          return { error: e.name === "AbortError" ? "Request timed out" : e.message, isTimeout: e.name === "AbortError" };
        }
      },
      { workflowId, timeoutMs: timing.apiRequestTimeoutMs },
    );

    if (!out) throw new FatalError("Page evaluate failed", true);
    if (out.error) {
      if (out.status === 429) throw new RateLimitError("Rate limited by Google");
      if (out.status === 401 || out.recoverable) {
        if (++errStreak >= 5) {
          await waitForFlowReady(page).catch(() => {});
          const stillSignedIn = await getSessionToken(page).catch(() => null);
          if (!stillSignedIn) {
            throw new AuthExpiredError("Flow account is signed out — open Accounts and sign in again");
          }
          throw new EndpointRejectedError(
            `Google kept rejecting video polling (${out.status || out.error}) while the account is still signed in`,
          );
        }
        continue;
      }
      if (++errStreak >= 5) throw new Error("Video polling failed repeatedly: " + out.error);
      continue;
    }
    errStreak = 0;

    const parsed = parseBatchExecuteResponse(out.text, "jwpduf");
    const { status, mediaId } = extractVideoPollStatus(parsed);
    if (status === VIDEO_STATUS_COMPLETE) {
      return { workflowId, mediaId };
    }
    // status === VIDEO_STATUS_PENDING (or unrecognized) -> keep polling.
  }
  throw new Error("Video generation timed out after " + Math.round(timing.videoPollTimeoutMs / 1000) + "s");
}

/**
 * Generate one text->video job via the current YhhmEf/jwpduf/as29s lifecycle
 * and poll it to completion. Same {mediaId, fifeUrl} return contract
 * batch-runner.js already destructures, so callers are unchanged.
 */
export async function generateOneVideo(page, projectId, prompt, settings, promptIndex) {
  // Never fire the API call while Flow's SPA is still navigating — same
  // reason generateOneImage waits (see its comment).
  await waitForFlowReady(page);

  const mode = buildVideoModeString(settings);
  const uuidA = uuid();
  const uuidB = uuid();
  const uuidC = uuid();

  const out = await safeEvaluate(
    page,
    async ({ projectId, mode, prompt, siteKey, recaptchaAction, uuidA, uuidB, uuidC, timeoutMs }) => {
      const wiz = window.WIZ_global_data || {};
      const at = wiz.SNlM0e;
      const bl = wiz.cfb2h;
      const fsid = wiz.FdrFJe;
      if (!at || !bl || !fsid) {
        return { error: "Missing WIZ session state (at/bl/f.sid)", recoverable: true };
      }

      const grec = window.grecaptcha?.enterprise;
      if (!grec) return { error: "No reCAPTCHA", recoverable: true };
      const captcha = await grec.execute(siteKey, { action: recaptchaAction });
      if (!captcha) return { error: "reCAPTCHA execute failed", recoverable: true };

      // Positional structure reproduced exactly as captured live for
      // FlowService's video-generation RPC ("YhhmEf") — see flow-engine
      // investigation notes. Same context object shape as ogiZ0b's image
      // path, confirmed byte-identical.
      const context = [null, 22, null, null, null, projectId, null, null, null, null, [captcha, 1]];
      const request = [
        [null, null, [[[prompt]]]],
        mode,
        2,
        null,
        [null, null, null, null, uuidA, uuidB],
        null, null,
        [4],
      ];
      const args = [[request], context, [uuidC, 2]];

      const reqId = 100000 + Math.floor(Math.random() * 900000);
      const url =
        "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute" +
        "?rpcids=YhhmEf" +
        "&source-path=" + encodeURIComponent("/project/" + projectId) +
        "&bl=" + encodeURIComponent(bl) +
        "&f.sid=" + encodeURIComponent(fsid) +
        "&hl=en-GB" +
        "&_reqid=" + reqId +
        "&rt=c";

      const bodyStr =
        "f.req=" + encodeURIComponent(JSON.stringify([[["YhhmEf", JSON.stringify(args), null, "generic"]]])) +
        "&at=" + encodeURIComponent(at);

      const ac = new AbortController();
      const tm = setTimeout(() => ac.abort(), timeoutMs);
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
          body: bodyStr,
          credentials: "include",
          signal: ac.signal,
        });
        clearTimeout(tm);
        const text = await resp.text();
        if (!resp.ok) {
          return { error: "HTTP " + resp.status, status: resp.status, errText: text.slice(0, 500) };
        }
        return { success: true, text };
      } catch (e) {
        clearTimeout(tm);
        return {
          error: e.name === "AbortError" ? "Request timed out" : e.message,
          isTimeout: e.name === "AbortError",
        };
      }
    },
    {
      projectId, mode, prompt,
      siteKey: secrets.recaptchaSiteKey, recaptchaAction: api.videoRecaptchaAction,
      uuidA, uuidB, uuidC, timeoutMs: timing.apiRequestTimeoutMs,
    },
  );

  if (!out) throw new FatalError("Page evaluate failed", true);
  if (out.error) {
    if (out.status === 429) throw new RateLimitError("Rate limited by Google");
    if (out.status === 401 || out.recoverable) {
      await waitForFlowReady(page).catch(() => {});
      const stillSignedIn = await getSessionToken(page).catch(() => null);
      if (!stillSignedIn) {
        throw new AuthExpiredError("Flow account is signed out — open Accounts and sign in again");
      }
      throw new EndpointRejectedError(
        `Google rejected the video generation request (${out.status || out.error}) while the account is still signed in`,
      );
    }
    throw new Error(out.error + (out.errText ? ": " + out.errText : ""));
  }

  const startParsed = parseBatchExecuteResponse(out.text, "YhhmEf");
  const { workflowId } = extractVideoStartResult(startParsed);
  if (!workflowId) {
    // TEMPORARY diagnostic capture (see project notes) — passive only, never
    // alters control flow below, never fires on success. Written to the
    // run folder (already available via settings.outputDir) so a failure on
    // any machine can be inspected after the fact without DevTools.
    try {
      const diagDir = settings.outputDir || os.tmpdir();
      const diagPath = path.join(diagDir, "yhhmef-diagnostic.log");
      fs.appendFileSync(
        diagPath,
        JSON.stringify({
          ts: new Date().toISOString(),
          host: os.hostname(),
          promptIndex,
          prompt,
          mode,
          parsed: startParsed,
          rawResponse: out.text,
        }) + "\n",
      );
    } catch {
      // Best-effort only — a diagnostic-logging failure must never mask
      // the real error thrown below.
    }
    // A 200 OK with no usable result can mean genuinely different things
    // (a bad request, an application-level NOT_FOUND, Google's anti-abuse
    // system) — all confirmed live to hit this exact branch, and all
    // indistinguishable from a generic message. PUBLIC_ERROR_UNUSUAL_ACTIVITY
    // specifically is worth naming: it means the request itself was fine
    // and this needs no code change, just time — unlike the other cases.
    if (out.text.includes("PUBLIC_ERROR_UNUSUAL_ACTIVITY")) {
      throw new Error(
        "Video generation blocked by Google (PUBLIC_ERROR_UNUSUAL_ACTIVITY) — " +
          "this is an anti-abuse hold on this account/browser, not a request error. Wait and retry later.",
      );
    }
    throw new Error("Video generation did not start — no media returned");
  }

  await pollVideoStatus(page, workflowId, projectId);

  // Final detail fetch — as29s carries the actual signed /video/ URL, which
  // jwpduf's own responses never do (only status + thumbnail become
  // available mid-poll). No captcha token needed (confirmed live).
  const finalOut = await safeEvaluate(
    page,
    async ({ workflowId, timeoutMs }) => {
      const wiz = window.WIZ_global_data || {};
      const at = wiz.SNlM0e;
      const bl = wiz.cfb2h;
      const fsid = wiz.FdrFJe;
      if (!at || !bl || !fsid) {
        return { error: "Missing WIZ session state (at/bl/f.sid)", recoverable: true };
      }
      const reqId = 100000 + Math.floor(Math.random() * 900000);
      const url =
        "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute" +
        "?rpcids=as29s&bl=" + encodeURIComponent(bl) +
        "&f.sid=" + encodeURIComponent(fsid) +
        "&hl=en-GB&_reqid=" + reqId + "&rt=c";
      const args = [workflowId];
      const bodyStr =
        "f.req=" + encodeURIComponent(JSON.stringify([[["as29s", JSON.stringify(args), null, "generic"]]])) +
        "&at=" + encodeURIComponent(at);
      const ac = new AbortController();
      const tm = setTimeout(() => ac.abort(), timeoutMs);
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
          body: bodyStr,
          credentials: "include",
          signal: ac.signal,
        });
        clearTimeout(tm);
        const text = await resp.text();
        if (!resp.ok) return { error: "HTTP " + resp.status, status: resp.status, errText: text.slice(0, 500) };
        return { success: true, text };
      } catch (e) {
        clearTimeout(tm);
        return { error: e.name === "AbortError" ? "Request timed out" : e.message, isTimeout: e.name === "AbortError" };
      }
    },
    { workflowId, timeoutMs: timing.apiRequestTimeoutMs },
  );

  if (!finalOut || finalOut.error) {
    // Generation completed but the final detail fetch failed — surface
    // whatever the poll already knew rather than losing the result entirely.
    throw new Error(
      "Video finished generating but the final detail fetch (as29s) failed: " +
        (finalOut?.error || "no response"),
    );
  }

  const finalParsed = parseBatchExecuteResponse(finalOut.text, "as29s");
  const { mediaId, fifeUrl } = extractAs29sVideoResult(finalParsed);
  if (!mediaId) throw new Error("No mediaId in video generation response");
  return { mediaId, fifeUrl };
}

function _looksLikeMedia(buf) {
  if (!buf || buf.length < 32) return false;
  const b = Buffer.isBuffer(buf) ? buf : Buffer.from(buf);
  // PNG / JPEG / GIF / WEBP(RIFF) / MP4(ftyp) / WebM
  if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return true;
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return true;
  if (b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46) return true;
  if (b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46) return true;
  if (b.includes(Buffer.from("ftyp"))) return true;
  if (b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3) return true;
  return false;
}

/**
 * Download media into destPath. Tries direct URL (fifeUrl) first, then the
 * labs.google redirect-by-id, then an in-page authenticated fetch.
 * Retries briefly — Flow often returns a mediaId before the CDN object is ready,
 * which previously looked like "generated in browser but never downloaded".
 */
export async function downloadMedia(page, mediaId, destPath, directUrl = null) {
  const { mkdirSync, writeFileSync } = await import("node:fs");
  const pathMod = await import("node:path");
  mkdirSync(pathMod.dirname(destPath), { recursive: true });

  const tryWrite = async (label, getter) => {
    try {
      const body = await getter();
      if (!body || body.length < 64) {
        return { ok: false, error: `${label}: empty body`, retryable: true };
      }
      if (!_looksLikeMedia(body)) {
        const head = Buffer.from(body).slice(0, 80).toString("utf8").replace(/\s+/g, " ");
        const retryable =
          /not ready|pending|404|403|429|empty|json|html|<!doctype/i.test(head) ||
          head.trim().startsWith("{") ||
          head.trim().startsWith("<");
        return {
          ok: false,
          error: `${label}: not media bytes (${head.slice(0, 60)})`,
          retryable,
        };
      }
      writeFileSync(destPath, Buffer.from(body));
      return { ok: true };
    } catch (e) {
      const msg = String(e.message || e);
      const retryable = /HTTP 404|HTTP 403|HTTP 429|timeout|ECONN|not ready/i.test(msg);
      return { ok: false, error: `${label}: ${msg}`, retryable };
    }
  };

  const attemptOnce = async () => {
    const errors = [];
    let anyRetryable = false;

    if (directUrl) {
      const r = await tryWrite("directUrl", async () => {
        const resp = await page.context().request.get(directUrl, {
          maxRedirects: 10,
          timeout: timing.apiRequestTimeoutMs,
        });
        if (!resp.ok()) throw new Error(`HTTP ${resp.status()}`);
        return await resp.body();
      });
      if (r.ok) return { ok: true };
      errors.push(r.error);
      anyRetryable = anyRetryable || !!r.retryable;
    }

    // NOT updated for the labs.google -> flow.google.com migration (unlike
    // urls.flowHome/flowProject and checkAuthStatus's domain check above):
    // whether this backend path moved with the frontend, or is still served
    // from labs.google as a separate backend host, isn't confirmed. If media
    // downloads start failing after the migration, check this first — direct
    // fifeUrl (tried before this redirect fallback) may be masking it for now.
    const redirectUrl = `https://labs.google${api.mediaRedirectPath}?name=${encodeURIComponent(mediaId)}`;
    const r2 = await tryWrite("redirect", async () => {
      const resp = await page.context().request.get(redirectUrl, {
        maxRedirects: 10,
        timeout: timing.apiRequestTimeoutMs,
      });
      if (!resp.ok()) throw new Error(`HTTP ${resp.status()}`);
      const body = await resp.body();
      const asText = Buffer.from(body).slice(0, 200).toString("utf8").trim();
      if (asText.startsWith("{") || asText.startsWith("[")) {
        let parsed;
        try {
          parsed = JSON.parse(Buffer.from(body).toString("utf8"));
        } catch {
          return body;
        }
        const nested =
          parsed?.result?.data?.json?.url ||
          parsed?.result?.data?.url ||
          parsed?.url ||
          parsed?.downloadUrl ||
          null;
        if (typeof nested === "string" && nested.startsWith("http")) {
          const resp2 = await page.context().request.get(nested, {
            maxRedirects: 10,
            timeout: timing.apiRequestTimeoutMs,
          });
          if (!resp2.ok()) throw new Error(`nested HTTP ${resp2.status()}`);
          return await resp2.body();
        }
      }
      return body;
    });
    if (r2.ok) return { ok: true };
    errors.push(r2.error);
    anyRetryable = anyRetryable || !!r2.retryable;

    const r3 = await tryWrite("pageFetch", async () => {
      const buf = await safeEvaluate(page, async ({ redirectPath, id }) => {
        const r = await fetch(`${redirectPath}?name=${encodeURIComponent(id)}`, {
          credentials: "include",
        });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const ab = await r.arrayBuffer();
        return Array.from(new Uint8Array(ab));
      }, { redirectPath: api.mediaRedirectPath, id: mediaId });
      return Buffer.from(buf);
    });
    if (r3.ok) return { ok: true };
    errors.push(r3.error);
    anyRetryable = anyRetryable || !!r3.retryable;

    return {
      ok: false,
      retryable: anyRetryable,
      error: errors.join(" | "),
    };
  };

  // CDN / redirect often lags behind "mediaId ready" — especially for video.
  const delays = [0, 1500, 3000, 5000, 8000, 12000, 20000];
  let lastError = "";
  for (let i = 0; i < delays.length; i++) {
    if (delays[i] > 0) await sleep(delays[i]);
    const result = await attemptOnce();
    if (result.ok) return;
    lastError = result.error || "unknown download error";
    if (!result.retryable) break;
  }

  throw new Error(
    `Flow generated media but download failed for ${mediaId}: ${lastError}`,
  );
}

export async function checkAuthStatus(page) {
  try {
    // Flow moved off labs.google onto flow.google.com — accept either so an
    // already-loaded page (flow.google.com/project/<id>) isn't needlessly
    // re-navigated to flowHome on every check. labs.google is kept in case
    // it still resolves/redirects for some accounts.
    const url = page.url();
    if (!url.includes("labs.google") && !url.includes("flow.google.com")) {
      await page.goto(urls.flowHome, {
        waitUntil: "domcontentloaded",
        timeout: 45000,
      });
    }
    await dismissBlockingOverlays(page);
    // Same race as openOrCreateProject: one immediate read plus a 600ms retry
    // was not enough to distinguish "still loading" from "signed out", so the
    // Accounts panel reported healthy accounts as not signed in.
    let token = await waitForSessionToken(page, 12000);
    if (!token) {
      await dismissBlockingOverlays(page);
      token = await waitForSessionToken(page, 6000);
    }
    const email = token ? await tryGetAccountEmail(page) : null;
    return {
      authenticated: !!token,
      email,
      url: page.url(),
      hasProject: !!page.url().match(/project\/([a-f0-9-]+)/),
    };
  } catch (e) {
    return { authenticated: false, error: e.message };
  }
}
