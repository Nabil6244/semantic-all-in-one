/**
 * What is known about a generation request once it has failed, so retry decisions never depend on error-message wording.
 *
 *   NOT_SUBMITTED  nothing reached Google (page not ready, token missing, the UI never clicked Generate). Safe to try again.
 *   REJECTED       Google answered and refused before creating anything (HTTP 4xx, an ErrorInfo reason). Safe to try again,
 *                  subject to the reason (rate limit, quota, sign-out, an account restriction).
 *   UNKNOWN        the request may have been accepted (timeout or connection lost after sending, HTTP 5xx, a 200 we could not
 *                  read, the page navigated during the call, Generate clicked but no result seen). NEVER submitted again
 *                  automatically.
 *   ACCEPTED       Google created the job (a workflow / media id is known). Only polling, the final fetch and the download
 *                  may be repeated.
 */
export const Submission = Object.freeze({
  NOT_SUBMITTED: "not_submitted",
  REJECTED: "rejected",
  UNKNOWN: "unknown",
  ACCEPTED: "accepted",
});

/** Mark `err` with what is known about the submission (and the job, when accepted). Returns `err`. */
export function tagSubmission(err, submission, extra = {}) {
  const e = err instanceof Error ? err : new Error(String(err));
  if (!e.submission) e.submission = submission;
  for (const [k, v] of Object.entries(extra)) {
    if (v != null && e[k] == null) e[k] = v;
  }
  return e;
}

/** A failure's submission state; anything untagged that escaped a generation call is treated as UNKNOWN. */
export function submissionOf(err) {
  return err?.submission || Submission.UNKNOWN;
}

/** Safe to submit the same generation again (the earlier request certainly created nothing). */
export function provenNotCreated(err) {
  const s = err?.submission;
  return s === Submission.NOT_SUBMITTED || s === Submission.REJECTED;
}

/**
 * Google's anti-abuse / account-restriction answer. A stop condition: the prompt fails, the account's slice stops, nothing is
 * retried, sent through another mechanism, or handed to another account.
 */
export class AccountRestrictedError extends Error {
  constructor(reason) {
    super(`Flow refused this account's request (${reason}). Stopped: the request is not retried or sent another way.`);
    this.name = "AccountRestrictedError";
    this.reason = reason;
    this.submission = Submission.REJECTED;
  }
}

/** ErrorInfo reasons that mean the account is being restricted, not that the request was malformed. */
export const RESTRICTION_REASONS = new Set(["PUBLIC_ERROR_UNUSUAL_ACTIVITY"]);
/** ErrorInfo reasons that mean the account's generation quota is used up. */
export const QUOTA_REASONS = new Set(["PUBLIC_ERROR_USER_QUOTA_REACHED"]);

/**
 * The prompt needs a person: the generation may already exist on Flow (or belongs to another account), so the engine will not
 * submit it again on its own. Never retried inside the run.
 */
export class NeedsActionError extends Error {
  constructor(message, { ledgerState = null, key = null } = {}) {
    super(message);
    this.name = "NeedsActionError";
    this.ledgerState = ledgerState;
    this.key = key;
    this.submission = Submission.UNKNOWN;
  }
}

/**
 * The generation exists (job or media id known) but polling, the final fetch or the download did not finish. Kept in the
 * ledger; the next run for the same prompt resumes it instead of generating again.
 */
export class ResumableError extends Error {
  constructor(message, { ledgerState = null, key = null, cause = null } = {}) {
    super(message);
    this.name = "ResumableError";
    this.ledgerState = ledgerState;
    this.key = key;
    this.cause = cause;
    this.submission = Submission.ACCEPTED;
  }
}
