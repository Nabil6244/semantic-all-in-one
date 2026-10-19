/**
 * reCAPTCHA mint for Flow batchexecute / agent requests.
 *
 * Prefer the project page's own grecaptcha (what Flow's UI uses). Minting on a
 * hidden /about tab by injecting enterprise.js was the older extension path;
 * after Flow's 2026-10-18 frontend cut, that path is answered with
 * PUBLIC_ERROR_UNUSUAL_ACTIVITY on both ogiZ0b and agent StreamChat while the
 * project-page token still matches what Flow itself sends.
 *
 * Prefer a site key detected from the page over the hardcoded fallback — a
 * mismatched key is also answered with UNUSUAL_ACTIVITY.
 */
import { secrets } from "../config.js";
import { batchexecute } from "./batchexecute-config.js";

const ABOUT_URL = "https://flow.google.com/about";

/** @param {import('playwright').Page} page */
async function detectSiteKeyOnPage(page) {
  return page.evaluate(() => {
    try {
      const cfg = typeof ___grecaptcha_cfg !== "undefined" ? ___grecaptcha_cfg : undefined;
      const clients = cfg && cfg.clients;
      if (!clients) return "";
      for (const ck of Object.keys(clients)) {
        const client = clients[ck];
        for (const p of Object.keys(client)) {
          const v = client[p];
          if (v && typeof v === "object") {
            for (const p2 of Object.keys(v)) {
              const v2 = v[p2];
              if (v2 && typeof v2 === "object" && v2.sitekey) return v2.sitekey;
            }
          }
        }
      }
    } catch {
      /* ignore */
    }
    return "";
  });
}

/**
 * Mint on the project tab with the page's already-loaded grecaptcha.
 * @param {import('playwright').Page} projectPage
 * @param {string} action
 */
export async function mintCaptchaOnProjectPage(projectPage, action) {
  const started = Date.now();
  const detected = await detectSiteKeyOnPage(projectPage);
  const siteKey = detected || secrets.recaptchaSiteKey;
  if (!siteKey) throw new Error("site key unresolved on project page");
  const token = await projectPage.evaluate(
    async ({ siteKey, action }) => {
      const grec = window.grecaptcha?.enterprise;
      if (!grec?.execute) return { token: null, error: "grecaptcha.enterprise not available on project page" };
      await new Promise((resolve) => {
        try {
          grec.ready(resolve);
        } catch {
          resolve();
        }
      });
      try {
        const token = await Promise.race([
          grec.execute(siteKey, { action }),
          new Promise((_, reject) => setTimeout(() => reject(new Error("execute timeout")), 15000)),
        ]);
        return { token, error: null };
      } catch (e) {
        return { token: null, error: String(e?.message || e) };
      }
    },
    { siteKey, action },
  );
  if (!token?.token) {
    throw new Error(token?.error || "reCAPTCHA execute on project page returned empty token");
  }
  return {
    token: String(token.token),
    mintedOn: "project",
    durationMs: Date.now() - started,
    siteKeySource: detected ? "detected" : "config",
  };
}

/**
 * Extension-parity mint on a hidden /about tab (fallback only).
 * @param {import('playwright').Page} projectPage
 * @param {string} action IMAGE_GENERATION | VIDEO_GENERATION | CHAT_GENERATION | …
 */
export async function mintCaptchaLikeExtension(projectPage, action) {
  const siteKeyConfigured = secrets.recaptchaSiteKey;
  const context = projectPage.context();
  const about = await context.newPage();
  const started = Date.now();
  try {
    await about.goto(ABOUT_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
    const token = await about.evaluate(
      async ({ siteKey, action }) => {
        function detectSiteKey() {
          try {
            const cfg = typeof ___grecaptcha_cfg !== "undefined" ? ___grecaptcha_cfg : undefined;
            const clients = cfg && cfg.clients;
            if (!clients) return "";
            for (const ck of Object.keys(clients)) {
              const client = clients[ck];
              for (const p of Object.keys(client)) {
                const v = client[p];
                if (v && typeof v === "object") {
                  for (const p2 of Object.keys(v)) {
                    const v2 = v[p2];
                    if (v2 && typeof v2 === "object" && v2.sitekey) return v2.sitekey;
                  }
                }
              }
            }
          } catch {
            /* ignore */
          }
          return "";
        }

        function injectGrecaptcha(key) {
          try {
            if (window.grecaptcha?.enterprise?.execute) return;
            if (!key) return;
            if (document.querySelector("script[data-af-recaptcha]")) return;
            try {
              if (window.trustedTypes?.createPolicy) {
                window.trustedTypes.createPolicy("default", {
                  createScriptURL: (u) => {
                    if (/^https:\/\/(www\.google\.com\/recaptcha\/|www\.gstatic\.com\/recaptcha\/)/.test(u))
                      return u;
                    throw new Error("blocked");
                  },
                  createScript: (s) => s,
                  createHTML: (s) => s,
                });
              }
            } catch {
              /* default policy already exists */
            }
            const s = document.createElement("script");
            const nEl = document.querySelector("script[nonce]");
            if (nEl?.nonce) s.nonce = nEl.nonce;
            s.src =
              "https://www.google.com/recaptcha/enterprise.js?render=" + encodeURIComponent(key);
            s.async = true;
            s.setAttribute("data-af-recaptcha", "1");
            (document.head || document.documentElement).appendChild(s);
          } catch {
            /* best-effort */
          }
        }

        async function waitGrecaptcha(ms) {
          const deadline = Date.now() + ms;
          for (;;) {
            if (window.grecaptcha?.enterprise?.execute) return true;
            if (Date.now() > deadline) return false;
            await new Promise((r) => setTimeout(r, 300));
          }
        }

        const detected = detectSiteKey();
        // Prefer the key Flow already loaded on this page.
        const key = detected || siteKey;
        if (!window.grecaptcha?.enterprise?.execute) {
          injectGrecaptcha(key);
        }
        if (!(await waitGrecaptcha(10000))) {
          return { token: null, error: "grecaptcha.enterprise not available on /about" };
        }
        if (!key) return { token: null, error: "site key unresolved" };
        await new Promise((resolve) => {
          try {
            window.grecaptcha.enterprise.ready(resolve);
          } catch {
            resolve();
          }
        });
        try {
          const token = await Promise.race([
            window.grecaptcha.enterprise.execute(key, { action }),
            new Promise((_, reject) =>
              setTimeout(() => reject(new Error("execute timeout")), 15000),
            ),
          ]);
          return { token, error: null, keySource: detected ? "detected" : "config" };
        } catch (e) {
          return { token: null, error: String(e?.message || e) };
        }
      },
      { siteKey: siteKeyConfigured, action },
    );

    if (!token?.token) {
      throw new Error(token?.error || "reCAPTCHA execute on /about returned empty token");
    }
    return {
      token: String(token.token),
      mintedOn: ABOUT_URL,
      durationMs: Date.now() - started,
      siteKeySource: token.keySource || "unknown",
    };
  } finally {
    try {
      await about.close();
    } catch {
      /* ignore */
    }
  }
}

/**
 * Prefer project-page mint (Flow UI parity); fall back to /about injection.
 */
export async function mintCaptchaWithFallback(projectPage, action) {
  let projectErr;
  try {
    return await mintCaptchaOnProjectPage(projectPage, action);
  } catch (e) {
    projectErr = e;
  }
  try {
    const about = await mintCaptchaLikeExtension(projectPage, action);
    return {
      ...about,
      projectError: String(projectErr?.message || projectErr),
    };
  } catch (aboutErr) {
    throw new Error(
      `captcha failed (project: ${projectErr?.message || projectErr}; about: ${aboutErr?.message || aboutErr})`,
    );
  }
}

/** Headers matching Auto Flow adapter batchexecute POST. */
export const BATCHEXECUTE_HEADERS = {
  "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
  "X-Same-Domain": "1",
};

export function extensionHl() {
  return "en";
}

/** Random _reqid in the extension's 1e5–1e6 range. */
export function extensionReqId() {
  return Math.floor(100000 + Math.random() * 900000);
}

export function captchaActionForMedia(mediaKind) {
  return mediaKind === "video"
    ? batchexecute.captchaActions.video
    : batchexecute.captchaActions.image;
}
