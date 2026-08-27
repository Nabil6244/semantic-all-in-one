/**
 * Flow page helpers — ported from extension background.js patterns.
 * Runs inside Playwright page.evaluate / page context.
 */
import {
  api,
  secrets,
  urls,
  models,
  aspectRatios,
  timing,
  videoModels,
  videoDurations,
  videoAspectRatios,
  resolveVideoModelKey,
} from "../config.js";

export { api, secrets, urls, models, aspectRatios, timing, videoModels, videoDurations, videoAspectRatios, resolveVideoModelKey };

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
  return safeEvaluate(page, async () => {
    try {
      const r = await fetch("/fx/api/auth/session", { credentials: "include" });
      if (!r.ok) return null;
      const j = await r.json();
      return j.access_token || null;
    } catch {
      return null;
    }
  });
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

  const result = await safeEvaluate(
    page,
    async ({ createPath, toolName, projectTitle }) => {
      try {
        const p = await fetch(createPath, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            json: { projectTitle, toolName },
          }),
        });
        if (!p.ok) return { error: "HTTP " + p.status };
        const d = await p.json();
        const id =
          d?.result?.data?.json?.result?.projectId ||
          d?.result?.data?.json?.projectId ||
          null;
        return id ? { projectId: id } : { error: "No projectId in response" };
      } catch (e) {
        return { error: e.message };
      }
    },
    {
      createPath: api.createProjectPath,
      toolName: api.toolName,
      projectTitle: title,
    },
  );

  if (!result?.projectId) {
    throw new FatalError(
      "Could not create Flow project: " + (result?.error || "unknown"),
      true,
    );
  }
  return result.projectId;
}

export async function openOrCreateProject(page) {
  let projectId = await getProjectId(page);
  if (projectId) return projectId;

  // Ensure we're on Flow home (not a dead URL)
  if (!page.url().includes("/tools/flow")) {
    await page.goto(urls.flowHome, { waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(1500);
  }

  const token = await getSessionToken(page);
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

function randomSeed() {
  return Math.floor(Math.random() * 300000);
}

/**
 * POST to aisandbox with Bearer + reCAPTCHA token minted in-page.
 */
export async function apiPost(page, url, bodyObj, recaptchaAction) {
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
    if (out.status === 403 || out.recoverable) {
      throw new FatalError(out.error + (out.errText ? ": " + out.errText : ""), true);
    }
    if (out.status === 400) {
      throw new Error("Rejected (400): " + (out.errText || out.error));
    }
    throw new Error(out.error + (out.errText ? ": " + out.errText : ""));
  }
  return out.data;
}

export async function generateOneImage(page, projectId, prompt, settings, promptIndex) {
  const batchId = uuid();
  const sessionId = ";" + Date.now() + promptIndex;
  const body = {
    clientContext: {
      recaptchaContext: {
        applicationType: api.recaptchaApplicationType,
        token: "PLACEHOLDER",
      },
      projectId,
      tool: api.toolName,
      sessionId,
    },
    mediaGenerationContext: { batchId },
    useNewMedia: true,
    requests: [
      {
        clientContext: {
          recaptchaContext: {
            applicationType: api.recaptchaApplicationType,
            token: "PLACEHOLDER",
          },
          projectId,
          tool: api.toolName,
          sessionId,
        },
        imageAspectRatio: settings.aspectRatio || aspectRatios.default,
        imageInputs: [],
        imageModelName: settings.model || models.default,
        seed:
          settings.seedMode === "fixed" && settings.seedValue != null
            ? settings.seedValue
            : randomSeed(),
        structuredPrompt: { parts: [{ text: prompt }] },
      },
    ],
  };

  const data = await apiPost(
    page,
    api.batchGenerateImages(projectId),
    body,
    api.recaptchaAction,
  );

  let mediaId = null;
  let fifeUrl = null;
  if (data?.workflows) {
    for (const w of data.workflows) {
      if (w?.metadata?.primaryMediaId) {
        mediaId = w.metadata.primaryMediaId;
        break;
      }
    }
  }
  // Always harvest fifeUrl from media[], even when mediaId came from workflows —
  // previously we `break`s as soon as an id was found and never read the URL,
  // so downloads fell back to the flaky redirect-only path.
  if (data?.media) {
    for (const m of data.media) {
      const id = m?.name || m?.mediaId;
      if (id && !mediaId) mediaId = id;
      const url =
        m?.image?.generatedImage?.fifeUrl ||
        m?.image?.fifeUrl ||
        m?.fifeUrl ||
        m?.url ||
        null;
      if (url && !fifeUrl) fifeUrl = url;
    }
  }
  if (!fifeUrl && data && typeof data === "object") {
    // Last-resort deep scan — Google's response shape drifts.
    const blob = JSON.stringify(data);
    const m = blob.match(/https:\/\/[^"\\]*fife[^"\\]*/i) || blob.match(/"fifeUrl"\s*:\s*"([^"]+)"/i);
    if (m) fifeUrl = (m[1] || m[0]).replace(/\\u003d/g, "=").replace(/\\+/g, "");
  }
  if (!mediaId) throw new Error("No mediaId in generation response");
  return { mediaId, fifeUrl };
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

function harvestFifeUrl(data, mediaEntry = null) {
  /** Pull a direct CDN URL from Google's drifting response shapes. */
  const fromEntry = (m) =>
    m?.video?.generatedVideo?.fifeUrl ||
    m?.video?.fifeUrl ||
    m?.video?.uri ||
    m?.video?.url ||
    m?.image?.generatedImage?.fifeUrl ||
    m?.image?.fifeUrl ||
    m?.fifeUrl ||
    m?.url ||
    m?.downloadUrl ||
    null;
  let fifeUrl = fromEntry(mediaEntry);
  if (!fifeUrl && data?.media && Array.isArray(data.media)) {
    for (const m of data.media) {
      fifeUrl = fromEntry(m);
      if (fifeUrl) break;
    }
  }
  if (!fifeUrl && data && typeof data === "object") {
    const blob = JSON.stringify(data);
    const m =
      blob.match(/https:\/\/[^"\\]*fife[^"\\]*/i) ||
      blob.match(/"fifeUrl"\s*:\s*"([^"]+)"/i) ||
      blob.match(/"downloadUrl"\s*:\s*"(https:[^"]+)"/i);
    if (m) fifeUrl = (m[1] || m[0]).replace(/\\u003d/g, "=").replace(/\\+/g, "");
  }
  return fifeUrl || null;
}

/**
 * Poll one async video job by mediaId until it finishes — ported verbatim
 * from background.js's pollVideo. Matches Flow's status response shape:
 * media[0].mediaMetadata.mediaStatus.mediaGenerationStatus.
 */
export async function pollVideoStatus(page, mediaId, projectId) {
  const maxTries = Math.max(1, Math.ceil(timing.videoPollTimeoutMs / timing.videoPollIntervalMs));
  let errStreak = 0;
  let lastFife = null;
  for (let i = 0; i < maxTries; i++) {
    await sleep(timing.videoPollIntervalMs);
    let data;
    try {
      data = await apiPost(
        page,
        api.batchCheckAsyncVideoGenerationStatus,
        { media: [{ name: mediaId, projectId }] },
        api.videoRecaptchaAction,
      );
    } catch (e) {
      const msg = String(e?.message || e);
      if (msg.includes("401") || msg.includes("expired")) throw e;
      if (++errStreak >= 5) throw new Error("Video polling failed repeatedly: " + msg);
      continue;
    }
    errStreak = 0;
    const m = data?.media?.[0];
    const status = m?.mediaMetadata?.mediaStatus?.mediaGenerationStatus;
    const harvested = harvestFifeUrl(data, m);
    if (harvested) lastFife = harvested;
    if (
      status === "MEDIA_GENERATION_STATUS_COMPLETED" ||
      status === "MEDIA_GENERATION_STATUS_COMPLETE" ||
      status === "MEDIA_GENERATION_STATUS_SUCCESSFUL"
    ) {
      // Prefer a direct download URL when Google returns one — redirect-by-id
      // often fails while the clip is already visible in Flow.
      return { mediaId, fifeUrl: harvested || lastFife || null };
    }
    if (status === "MEDIA_GENERATION_STATUS_FAILED") {
      const ms = m.mediaMetadata.mediaStatus;
      throw new Error("Video generation failed: " + (ms.failureReason || ms.errorMessage || "unknown reason"));
    }
  }
  throw new Error("Video generation timed out after " + Math.round(timing.videoPollTimeoutMs / 1000) + "s");
}

/**
 * Generate one text->video job and poll it to completion — ported verbatim
 * from background.js's EtVideo (single-slot form; batch-runner.js handles
 * the imageCount/multi-slot loop the same way it already does for images).
 */
export async function generateOneVideo(page, projectId, prompt, settings, promptIndex) {
  const aspect = videoAspectRatios.fromImage[settings.aspectRatio] || videoAspectRatios.default;
  const isPortrait = aspect === "VIDEO_ASPECT_RATIO_PORTRAIT";
  const modelKey = resolveVideoModelKey(settings.videoModel || settings.model, isPortrait);
  const duration = Number(settings.videoDuration) || videoDurations.default;
  const seed =
    settings.seedMode === "fixed" && settings.seedValue != null ? settings.seedValue : randomSeed();

  // Never click Flow's duration tabs before the API call — that SPA navigation
  // destroys Playwright's execution context in the first second of video jobs.
  await waitForFlowReady(page);

  const body = {
    mediaGenerationContext: { batchId: uuid() },
    clientContext: {
      projectId,
      tool: api.toolName,
      sessionId: ";" + Date.now() + promptIndex,
      userPaygateTier: api.paygateTier,
      recaptchaContext: {
        applicationType: api.recaptchaApplicationType,
        token: "PLACEHOLDER",
      },
    },
    requests: [
      {
        aspectRatio: aspect,
        seed,
        metadata: {},
        videoLengthSeconds: duration,
        textInput: { structuredPrompt: { parts: [{ text: prompt }] } },
        videoModelKey: modelKey,
      },
    ],
    useV2ModelConfig: true,
  };

  const gen = await apiPost(page, api.batchAsyncGenerateVideoText, body, api.videoRecaptchaAction);
  const mediaId = gen?.media?.[0]?.name || null;
  if (!mediaId) throw new Error("Video generation did not start — no media returned");

  let result = await pollVideoStatus(page, mediaId, projectId);
  // CDN URL often appears a beat after COMPLETE — one extra harvest helps download.
  if (!result.fifeUrl) {
    await sleep(2000);
    try {
      const data = await apiPost(
        page,
        api.batchCheckAsyncVideoGenerationStatus,
        { media: [{ name: mediaId, projectId }] },
        api.videoRecaptchaAction,
      );
      const url = harvestFifeUrl(data, data?.media?.[0]);
      if (url) result = { mediaId, fifeUrl: url };
    } catch {
      /* keep poll result */
    }
  }
  return result;
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
    if (!page.url().includes("labs.google")) {
      await page.goto(urls.flowHome, {
        waitUntil: "domcontentloaded",
        timeout: 45000,
      });
    }
    await dismissBlockingOverlays(page);
    let token = await getSessionToken(page);
    if (!token) {
      await dismissBlockingOverlays(page);
      await sleep(600);
      token = await getSessionToken(page);
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
