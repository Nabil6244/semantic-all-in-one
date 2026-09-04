/**
 * Trimmed config for the flow-engine sidecar.
 *
 * This is a deliberately small subset of semantic-automator-main/config.js —
 * only what lib/flow-api.js, lib/batch-runner.js, and server.js actually import
 * (api, secrets.recaptchaSiteKey, urls.flowHome/flowProject, models,
 * aspectRatios, timing, defaults.flowSettings). Firebase, Stripe, admin,
 * access/quota/licensing, and branding are intentionally NOT here — this
 * engine has no dependency on any of that (verified against the original repo
 * before extraction). Do not add those back; if a future feature genuinely
 * needs them, it belongs in a licensing layer outside this engine, not here.
 *
 * `secrets.recaptchaSiteKey` below is a reCAPTCHA Enterprise *site key* —
 * by Google's own design these are meant to be embedded in client-side code
 * (they identify the site, not a caller); it is not a secret credential.
 */

export const secrets = {
  recaptchaSiteKey: "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV",
};

// Google migrated Flow off labs.google/fx/tools/flow onto its own domain
// (confirmed live: a real project now loads at
// https://flow.google.com/project/<id>, not the old labs.google path).
// flowHome is the guessed landing/creation page (https://flow.google.com/) —
// not independently confirmed the way flowProject's shape was; if account
// prepare/sign-in still fails after this change, check what flowHome
// actually redirects to and correct it here.
export const urls = {
  flowHome: "https://flow.google.com/",
  flowProject: (projectId) => `https://flow.google.com/project/${projectId}`,
};

export const api = {
  toolName: "PINHOLE",
  sessionPath: "/fx/api/auth/session",
  createProjectPath: "/fx/api/trpc/project.createProject",
  mediaRedirectPath: "/fx/api/trpc/media.getMediaUrlRedirect",
  batchGenerateImages: (projectId) =>
    `https://aisandbox-pa.googleapis.com/v1/projects/${projectId}/flowMedia:batchGenerateImages`,
  recaptchaAction: "IMAGE_GENERATION",
  recaptchaApplicationType: "RECAPTCHA_APPLICATION_TYPE_WEB",
  paygateTier: "PAYGATE_TIER_NOT_PAID",

  // ─── Video (text → video) — restored verbatim from semantic-automator-main's
  // root config.js / background.js (EtVideo/pollVideo) ───────────────────────
  batchAsyncGenerateVideoText:
    "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText",
  batchCheckAsyncVideoGenerationStatus:
    "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus",
  videoRecaptchaAction: "VIDEO_GENERATION",
};

export const models = {
  default: "NARWHAL",
  fallbackOrder: ["NARWHAL", "GEM_PIX_2", "HARBOR_SEAL"],
  labels: {
    HARBOR_SEAL: "NB Lite",
    NARWHAL: "NB 2",
    GEM_PIX_2: "NB Pro",
  },
  options: [
    { value: "HARBOR_SEAL", label: "NB Lite" },
    { value: "NARWHAL", label: "NB 2" },
    { value: "GEM_PIX_2", label: "NB Pro" },
  ],
};

export const aspectRatios = {
  default: "IMAGE_ASPECT_RATIO_LANDSCAPE",
  labels: {
    IMAGE_ASPECT_RATIO_LANDSCAPE: "16:9",
    IMAGE_ASPECT_RATIO_SQUARE: "1:1",
    IMAGE_ASPECT_RATIO_PORTRAIT: "9:16",
  },
  options: [
    { value: "IMAGE_ASPECT_RATIO_LANDSCAPE", label: "16:9" },
    { value: "IMAGE_ASPECT_RATIO_SQUARE", label: "1:1" },
    { value: "IMAGE_ASPECT_RATIO_PORTRAIT", label: "9:16" },
  ],
};

// ─── Video models (text → video) ───────────────────────────────────────────
// The veo_3_1_t2v_* values are restored verbatim from semantic-automator-
// main's root config.js and are ALSO Flow's own current mode-string literal
// for that model (live-confirmed for "veo_3_1_t2v_lite" — Flow's UI has no
// duration/resolution picker for Veo models at all, so the mode string is
// just the model key, unchanged). "abra" ("Omni 1.1 Flash" in Flow's current
// UI) is the one model with a real duration/resolution picker — see
// buildVideoModeString() in lib/flow-api.js for how those combine into its
// mode string.
// `value` is the LANDSCAPE `videoModelKey` base; resolveVideoModelKey() adds
// the `_portrait` suffix automatically for portrait output (only used for
// label/lookup purposes — see buildVideoModeString for why the video mode
// string itself does not currently vary by aspect ratio).
export const videoModels = {
  default: "veo_3_1_t2v_fast",
  labels: {
    abra: "Omni 1.1 Flash",
    veo_3_1_t2v_lite: "Veo 3.1 Lite",
    veo_3_1_t2v_fast: "Veo 3.1 Fast",
    veo_3_1_t2v_quality: "Veo 3.1 Quality",
  },
  options: [
    { value: "abra", label: "Omni 1.1 Flash" },
    { value: "veo_3_1_t2v_lite", label: "Veo 3.1 – Lite" },
    { value: "veo_3_1_t2v_fast", label: "Veo 3.1 – Fast" },
    { value: "veo_3_1_t2v_quality", label: "Veo 3.1 – Quality" },
  ],
};

export function resolveVideoModelKey(model, isPortrait) {
  let base = String(model || videoModels.default);
  if (base === "veo_3_1_t2v") base = "veo_3_1_t2v_quality";
  if (base === "veo_3_1_t2v_lite_low_priority") base = "veo_3_1_t2v_lite";
  base = base.replace(/_portrait$/, "");
  if (!videoModels.labels[base]) base = videoModels.default;
  return isPortrait ? `${base}_portrait` : base;
}

// Only meaningful for the "abra" (Omni) model — Veo models have no duration
// picker in Flow's UI and always generate at a fixed length. Live-confirmed
// for "abra" at 4s and 6s (both at 360p); 8s/10s follow the identical
// "{n}s" substitution into the same otherwise-fixed template, not a guess
// at a structurally different value the way the old 720p bug was.
export const videoDurations = {
  default: 8,
  options: [
    { value: 4, label: "4s" },
    { value: 6, label: "6s" },
    { value: 8, label: "8s" },
    { value: 10, label: "10s" },
  ],
};

// Only meaningful for the "abra" (Omni) model — Veo models have no
// resolution picker in Flow's UI. Live-confirmed: 720p is the unmarked
// default (buildVideoModeString adds no suffix for it); 360p is the one
// that gets an explicit "_360p" suffix. The old code had this backwards
// (always appended an explicit "_720p"), which is what broke every video
// generation — see buildVideoModeString's comment in lib/flow-api.js.
export const videoResolutions = {
  default: "720p",
  options: [
    { value: "360p", label: "360p" },
    { value: "720p", label: "720p" },
  ],
};

export const videoAspectRatios = {
  default: "VIDEO_ASPECT_RATIO_LANDSCAPE",
  fromImage: {
    IMAGE_ASPECT_RATIO_LANDSCAPE: "VIDEO_ASPECT_RATIO_LANDSCAPE",
    IMAGE_ASPECT_RATIO_SQUARE: "VIDEO_ASPECT_RATIO_LANDSCAPE",
    IMAGE_ASPECT_RATIO_PORTRAIT: "VIDEO_ASPECT_RATIO_PORTRAIT",
  },
};

export const timing = {
  apiRequestTimeoutMs: 60 * 1000,
  rateLimitRetrySeconds: [60, 120],
  quotaRetrySeconds: [60, 120],
  sessionRetrySeconds: [5, 15, 30],
  maxParallelImages: 4,
  imageSlotStaggerMs: 250,
  videoPollIntervalMs: 8000,
  videoPollTimeoutMs: 6 * 60 * 1000,
};

export const defaults = {
  flowSettings: {
    model: models.default,
    aspectRatio: aspectRatios.default,
    videoModel: videoModels.default,
    videoDuration: videoDurations.default,
    videoResolution: videoResolutions.default,
    mediaKind: "image",
    imageCount: 1,
    folder: "",
    autoDownload: true,
    delayMin: 3,
    delayMax: 8,
    seedMode: "random",
    seedValue: 42000,
    refreshFrequency: 5,
  },
};
