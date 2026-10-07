/**
 * An agent image job as a worker pool (orchestrator.js uses it for jobs of agent.minScenes or more NEW images).
 *
 *   job scenes -> agent requests (<= agent.maxBatch scenes, balanced, look-alike texts kept apart) -> queue
 *   every healthy account = one worker: it takes the next request only after its previous one has FINISHED (results
 *   reconciled and written to the ledger by runAgentSlice), so an account never has two agent requests out at once.
 *
 * No job-size ceiling and no account ceiling of its own: every healthy account the job may use takes part (the engine-wide
 * timing.maxParallelAccounts browser cap still applies, as for every Flow job). An account Flow asks to slow down (too much
 * traffic, quota, agent capacity, HTTP 429) rests for agent.coolDownMs; what it had not made goes back to the queue for the
 * other accounts (runAgentSlice marked those scenes REJECTED = nothing created, so they are safe to send again). A scene
 * whose image Flow already made on one account (download-only) is handed to that account, never counted as a new image.
 *
 * Scenes the agent made nothing for come back here: five or more are sent as one more agent round, fewer go through the
 * standard path (runStandard). Uncertain scenes never come back: runAgentSlice leaves them in the ledger as Needs action.
 */
import { agent as agentConfig } from "../config.js";
import { splitSharedStyle } from "./agent-api.js";
import { planAgentBatches } from "./agent-runner.js";
import { LedgerState } from "./generation-ledger.js";

const NOTHING_CREATED = new Set([LedgerState.FAILED_BEFORE_SUBMISSION, LedgerState.REJECTED]);
const RESUMABLE = new Set([LedgerState.ACCEPTED, LedgerState.MEDIA_ID_KNOWN, LedgerState.DOWNLOAD_FAILED]);

/**
 * How a scene stands before the job: "new" (needs a generation), "download" (made on Flow, only the file is missing; its
 * owner account fetches it) or "other" (already saved, or uncertain and blocked). A confirmed Retry makes a scene new
 * unless its file is already saved.
 */
export function sceneStanding(entry, { confirmed = false } = {}) {
  if (!entry || NOTHING_CREATED.has(entry.state)) return "new";
  if (RESUMABLE.has(entry.state)) return "download";
  if (entry.state === LedgerState.COMPLETED_LOCAL) return confirmed ? "new" : "other";
  return confirmed ? "new" : "other";
}

/**
 * How an image job is routed, decided BEFORE any account split. Scenes still inside an agent request that has not returned
 * are held back (busy). The rest count as new images or not (sceneStanding); agent mode is used when the job asks for it
 * and has at least `minScenes` new images, otherwise the standard path takes the whole job.
 */
export function planImageJob({ prompts, promptKeys = null, settings = {}, ledger, active = new Map(), keyOf, minScenes = agentConfig.minScenes, agentRequested = false }) {
  const confirmed = new Set((settings.confirmResubmitKeys || []).map(String));
  const busy = [];
  const poolItems = [];
  let fresh = 0;
  prompts.forEach((prompt, index) => {
    const promptKey = promptKeys?.[index] ?? null;
    const key = keyOf({ prompt, promptKey, index, settings });
    const making = active.get(key);
    if (making) {
      busy.push({ index, prompt, by: making });
      return;
    }
    const entry = ledger.get(key);
    const standing = sceneStanding(entry, { confirmed: promptKey != null && confirmed.has(String(promptKey)) });
    if (standing === "new") fresh++;
    poolItems.push({ index, prompt, promptKey, owner: standing === "download" ? entry.accountId : null });
  });
  return { agentPool: !!agentRequested && fresh >= minScenes, fresh, busy, poolItems };
}

/** Cut scenes into agent requests: same rules as one account's batches (balanced, size and clash limits). */
export function planPoolBatches(items, { maxBatch = agentConfig.maxBatch, maxChars = agentConfig.maxMessageChars } = {}) {
  if (!items.length) return [];
  const style = splitSharedStyle(items.map((it) => it.prompt));
  const withText = items.map((it, j) => ({ ...it, text: style.texts[j] }));
  const styleChars = style.opening.length + style.ending.length;
  return planAgentBatches(withText, {
    maxBatch, lenOf: (it) => it.text.length, textOf: (it) => it.text, maxChars: Math.max(2000, maxChars - styleChars),
  }).map((batch) => batch.map(({ text, ...it }) => it));
}

/**
 * Run the job. `items` are { index, prompt, promptKey, owner } (owner = account id for download-only scenes).
 * Dependencies: prepare(account) -> page (throws when the account cannot be used), runSlice({ account, page, items }) ->
 * runAgentSlice's result (called with deferFallback), runStandard({ account, page, items }) -> runBatchSlice's result.
 * Returns { batchesRun, accountsUsed, maxConcurrent, unrun: [{ item, reason }] } (unrun = never handled: no healthy
 * account left, or stopped before it was sent; nothing was generated for them).
 */
export async function runAgentPool({
  items, accounts, isStopped = () => false, prepare, runSlice, runStandard,
  onAccountState = () => {}, now = () => Date.now(), sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  coolDownMs = agentConfig.coolDownMs, minScenes = agentConfig.minScenes, maxBatch = agentConfig.maxBatch,
  maxChars = agentConfig.maxMessageChars, batchGapMs = agentConfig.batchGapMs, maxRounds = 2,
}) {
  const state = new Map(accounts.map((a) => [a.id, { gone: false, coolUntil: 0, page: null, lastBatchAt: 0 }]));
  const unrun = [];
  let batchesRun = 0;
  let busy = 0;
  let maxConcurrent = 0;
  const accountsUsed = new Set();

  const usable = (a) => !state.get(a.id).gone;
  const cooling = (a) => state.get(a.id).coolUntil > now();

  async function pageFor(a) {
    const st = state.get(a.id);
    if (st.page) return st.page;
    st.page = await prepare(a);
    return st.page;
  }

  async function runRound(roundItems) {
    const byOwner = new Map();
    const shared = [];
    for (const it of roundItems) {
      if (it.owner && state.has(it.owner) && usable({ id: it.owner })) {
        if (!byOwner.has(it.owner)) byOwner.set(it.owner, []);
        byOwner.get(it.owner).push(it);
      } else {
        shared.push(it);   // owner gone or unknown: runAgentSlice's ledger check blocks or regenerates it safely
      }
    }
    const queue = planPoolBatches(shared, { maxBatch, maxChars });
    const ownQueues = new Map([...byOwner].map(([id, its]) => [id, chunk(its, maxBatch)]));
    const fallback = [];

    const nextJob = (a) => {
      const own = ownQueues.get(a.id);
      if (own?.length) return own.shift();
      return queue.length ? queue.shift() : null;
    };
    const workLeft = () => queue.length > 0 || [...ownQueues.values()].some((q) => q.length);

    async function worker(a) {
      for (;;) {
        if (isStopped() || !usable(a)) return;
        if (cooling(a)) {
          if (!workLeft() && busy === 0) return;
          await sleep(1000);
          continue;
        }
        const job = nextJob(a);
        if (!job) {
          if (busy === 0 && !workLeft()) return;
          await sleep(250);   // another account may hand work back (cool-down)
          continue;
        }
        // Counted as busy from the moment it is claimed: an idle account must never conclude "no work left, nobody busy"
        // while this batch is still being started.
        busy++;
        const st = state.get(a.id);
        let page;
        try {
          page = await pageFor(a);
        } catch (e) {
          st.gone = true;
          onAccountState(a, "error", String(e?.message || e));
          queue.unshift(job);   // nothing was sent: another account takes it
          busy--;
          return;
        }
        if (st.lastBatchAt && batchGapMs > 0) {
          const wait = st.lastBatchAt + batchGapMs - now();
          if (wait > 0) await sleep(wait);
          if (isStopped()) { queue.unshift(job); busy--; return; }
        }
        maxConcurrent = Math.max(maxConcurrent, busy);
        accountsUsed.add(a.id);
        let result;
        try {
          result = await runSlice({ account: a, page, items: job });
        } catch (e) {
          // The account broke mid-request. Its scenes' ledger state says what was sent: an automatic resend is blocked
          // for anything uncertain, so handing the batch to another account cannot duplicate a request.
          // A Retry's permission covered the request just sent, not a second one: the handed-on scenes lose it.
          result = { error: e, reassign: job.map((it) => ({ index: it.index, prompt: it.prompt, promptKey: it.promptKey, noConfirm: true })) };
          st.gone = true;
          onAccountState(a, "error", String(e?.message || e));
        } finally {
          busy--;
          batchesRun++;
          st.lastBatchAt = now();
        }
        if (result?.coolDown) {
          st.coolUntil = now() + coolDownMs;
          onAccountState(a, "cooldown", `Flow asked this account to slow down (${result.coolDown}); resting`);
        }
        if (result?.restricted || result?.authExpired) {
          st.gone = true;
          onAccountState(a, "error", result.restricted ? `Flow restricted this account (${result.restricted})` : "Signed out");
        }
        if (result?.reassign?.length) {
          const back = result.reassign.map((r) => ({ index: r.index, prompt: r.prompt, promptKey: r.promptKey ?? null, noConfirm: !!r.noConfirm }));
          for (const b of planPoolBatches(back, { maxBatch, maxChars })) queue.push(b);
        }
        if (result?.fallback?.length) fallback.push(...result.fallback.map((r) => ({ index: r.index, prompt: r.prompt, promptKey: r.promptKey ?? null })));
      }
    }

    await Promise.all(accounts.filter(usable).map((a) => worker(a)));
    // Work no healthy account can take (every account gone, or stopped): report it, nothing was generated for it.
    for (const job of [...queue, ...[...ownQueues.values()].flat()]) {
      for (const it of job) unrun.push({ item: it, reason: isStopped() ? "stopped" : "no_account" });
    }
    queue.length = 0;
    return fallback;
  }

  let leftover = await runRound(items);
  for (let round = 2; round <= maxRounds && leftover.length >= minScenes && !isStopped(); round++) {
    leftover = await runRound(leftover);   // five or more the agent did not make: one more agent round
  }
  if (leftover.length && !isStopped()) {
    // Fewer than five (or still left after the extra round): the standard path, on the first healthy account.
    const a = accounts.find((x) => usable(x) && !cooling(x)) || accounts.find(usable);
    if (!a) {
      for (const it of leftover) unrun.push({ item: it, reason: "no_account" });
    } else {
      try {
        const page = await pageFor(a);
        accountsUsed.add(a.id);
        await runStandard({ account: a, page, items: leftover });
      } catch (e) {
        for (const it of leftover) unrun.push({ item: it, reason: "no_account" });
      }
    }
  } else if (leftover.length) {
    for (const it of leftover) unrun.push({ item: it, reason: "stopped" });
  }
  return { batchesRun, accountsUsed, maxConcurrent, unrun };
}

function chunk(arr, n) {
  const out = [];
  for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n));
  return out;
}
