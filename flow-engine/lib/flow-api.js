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

export async function waitForFlowReady(page, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const ready = await page.evaluate(() => {
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
  return page.evaluate(async () => {
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
  return page.evaluate(() => {
    const m = window.location.href.match(/project\/([a-f0-9-]+)/);
    return m ? m[1] : null;
  });
}

export async function tryGetAccountEmail(page) {
  return page.evaluate(() => {
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

  const result = await page.evaluate(
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

  const out = await page.evaluate(
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
  if (!mediaId && data?.media) {
    for (const m of data.media) {
      const id = m?.name || m?.mediaId;
      if (id) {
        mediaId = id;
        break;
      }
      const url = m?.image?.generatedImage?.fifeUrl;
      if (url) fifeUrl = url;
    }
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

/**
 * Poll one async video job by mediaId until it finishes — ported verbatim
 * from background.js's pollVideo. Matches Flow's status response shape:
 * media[0].mediaMetadata.mediaStatus.mediaGenerationStatus.
 */
export async function pollVideoStatus(page, mediaId, projectId) {
  const maxTries = Math.max(1, Math.ceil(timing.videoPollTimeoutMs / timing.videoPollIntervalMs));
  let errStreak = 0;
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
    if (
      status === "MEDIA_GENERATION_STATUS_COMPLETED" ||
      status === "MEDIA_GENERATION_STATUS_COMPLETE" ||
      status === "MEDIA_GENERATION_STATUS_SUCCESSFUL"
    ) {
      return mediaId;
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

  if (duration !== videoDurations.default) {
    await syncFlowVideoDuration(page, duration);
  }

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
        ...(duration !== videoDurations.default ? { videoLengthSeconds: duration } : {}),
        textInput: { structuredPrompt: { parts: [{ text: prompt }] } },
        videoModelKey: modelKey,
      },
    ],
    useV2ModelConfig: true,
  };

  const gen = await apiPost(page, api.batchAsyncGenerateVideoText, body, api.videoRecaptchaAction);
  const mediaId = gen?.media?.[0]?.name || null;
  if (!mediaId) throw new Error("Video generation did not start — no media returned");

  const finalId = await pollVideoStatus(page, mediaId, projectId);
  return { mediaId: finalId };
}

/**
 * Download media via Flow redirect into a local file path.
 */
export async function downloadMedia(page, mediaId, destPath) {
  const redirectUrl = `https://labs.google${api.mediaRedirectPath}?name=${mediaId}`;
  const resp = await page.context().request.get(redirectUrl, {
    maxRedirects: 10,
    timeout: timing.apiRequestTimeoutMs,
  });
  if (!resp.ok()) {
    // Fallback: try in-page blob fetch
    const buf = await page.evaluate(async (path) => {
      const r = await fetch(path, { credentials: "include" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const ab = await r.arrayBuffer();
      return Array.from(new Uint8Array(ab));
    }, api.mediaRedirectPath + "?name=" + mediaId);
    const { writeFileSync } = await import("node:fs");
    writeFileSync(destPath, Buffer.from(buf));
    return;
  }
  const { writeFileSync } = await import("node:fs");
  writeFileSync(destPath, await resp.body());
}

export async function checkAuthStatus(page) {
  try {
    if (!page.url().includes("labs.google")) {
      await page.goto(urls.flowHome, {
        waitUntil: "domcontentloaded",
        timeout: 45000,
      });
    }
    const token = await getSessionToken(page);
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
