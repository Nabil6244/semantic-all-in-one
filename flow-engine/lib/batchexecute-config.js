/**
 * Flow batchexecute RPC constants — keep in sync with the Chrome extension
 * remote config (flow_google block in naming-Bysx_Vg_.js DEBUG_RC / server rc).
 *
 * Parity checklist when Google changes Flow:
 * - origin + batchexecute_path + rpcids match extension flow_google
 * - captcha site_key + actions (IMAGE_GENERATION / VIDEO_GENERATION)
 * - image_aspects / video_aspects numeric wire values
 * - Do not reintroduce aisandbox-pa.googleapis.com REST for generate/poll
 */

export const batchexecute = {
  origin: "https://flow.google.com",
  appName: "AiSandboxAngularFrontend",
  path: "/_/AiSandboxAngularFrontend/data/batchexecute",
  captchaActions: {
    image: "IMAGE_GENERATION",
    video: "VIDEO_GENERATION",
    uploadImage: "IMAGE_UPLOAD",
    audio: "AUDIO_GENERATION",
  },
  rpcids: {
    imageGenerate: "ogiZ0b",
    imageUpload: "maseQ",
    imageUpscale: "SPrCad",
    videoText: "YhhmEf",
    videoStartImage: "eb1hJf",
    videoStartEndImage: "nprQif",
    videoReferenceImages: "MZZa6b",
    videoEdit: "VideoEdit",
    videoPoll: "jwpduf",
    getMedia: "as29s",
    videoUpscale: "VideoUpscale",
    entityCreate: "CreateEntity",
    entityUpdate: "UpdateEntity",
    mediaSetVisibility: "SetVisibility",
    workflowSetName: "SetName",
    audioGenerate: "AudioGen",
    getCredits: "GetCredits",
    projectCreate: "jHPbke",
  },
  /** Extension DEBUG_RC.flow_google.image_aspects */
  imageAspectWire: {
    landscape: 3,
    portrait: 2,
    square: 1,
    IMAGE_ASPECT_RATIO_LANDSCAPE: 3,
    IMAGE_ASPECT_RATIO_PORTRAIT: 2,
    IMAGE_ASPECT_RATIO_SQUARE: 1,
  },
  videoAspectWire: {
    VIDEO_ASPECT_RATIO_LANDSCAPE: 2,
    VIDEO_ASPECT_RATIO_PORTRAIT: 1,
    landscape: 2,
    portrait: 1,
  },
};

/**
 * @param {string} rpcId
 * @param {object} q
 * @param {string} q.bl
 * @param {string} q.fsid
 * @param {string} q.hl
 * @param {number|string} q.reqId
 * @param {string} [q.sourcePath] encoded path segment after source-path=
 */
export function buildBatchexecuteUrl(rpcId, { bl, fsid, hl, reqId, sourcePath = "%2F" }) {
  const base = `${batchexecute.origin}${batchexecute.path}`;
  return (
    `${base}?rpcids=${encodeURIComponent(rpcId)}` +
    `&source-path=${sourcePath}` +
    `&bl=${encodeURIComponent(bl)}` +
    `&f.sid=${encodeURIComponent(fsid)}` +
    `&hl=${encodeURIComponent(hl)}` +
    `&_reqid=${reqId}` +
    `&rt=c`
  );
}

/** @param {string} [aspectRatioSetting] from settings.aspectRatio */
export function resolveImageAspectWireValue(aspectRatioSetting) {
  const key = aspectRatioSetting || "IMAGE_ASPECT_RATIO_LANDSCAPE";
  return batchexecute.imageAspectWire[key] ?? batchexecute.imageAspectWire.IMAGE_ASPECT_RATIO_LANDSCAPE;
}

export const RPC_UI_FALLBACK_REASON = "PUBLIC_ERROR_UNUSUAL_ACTIVITY";

/** @param {unknown} err */
export function isEligibleForRpcToUiFallback(err) {
  if (!err) return false;
  const msg = String(err.message || err);
  if (msg.includes(RPC_UI_FALLBACK_REASON)) return true;
  if (err.name === "MissingMediaIdError" && msg.includes("Flow RPC rejected")) return true;
  return false;
}
