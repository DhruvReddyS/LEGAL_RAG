/**
 * Follow a Deep review to the end: over SSE when that works, by polling when not.
 *
 * Deep takes minutes, so what matters is that the wait stays honest and survives
 * things going wrong. A dropped connection reconnects from the last event seen.
 * A proxy that eats streams, a stream cap, or a webview that will not send the
 * cookie falls back to polling, and one failed poll no longer ends the wait while
 * the job keeps running (audit F19). The final answer always comes from GET
 * /jobs/{id}: the stream reports progress and does not carry the result.
 */
import type { DeepReviewJob } from "./types";

export interface SseEvent {
  id: number | null;
  event: string;
  data: string;
}

/** Split complete events off a buffer, returning what is still incomplete. */
export function parseSse(buffer: string): { events: SseEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: SseEvent[] = [];
  for (const block of blocks) {
    let id: number | null = null;
    let event = "message";
    const data: string[] = [];
    let hasField = false;
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      hasField = true;
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
      if (field === "id") {
        const parsed = Number(value);
        id = Number.isInteger(parsed) ? parsed : null;
      } else if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (hasField) events.push({ id, event, data: data.join("\n") });
  }
  return { events, rest };
}

export interface JobView {
  progress: number | null;
  stageLabel: string | null;
  queuePosition: number | null;
  estimatedWaitSeconds: number | null;
  locatedSources: Array<Record<string, unknown>> | null;
}

export const EMPTY_VIEW: JobView = {
  progress: null,
  stageLabel: null,
  queuePosition: null,
  estimatedWaitSeconds: null,
  locatedSources: null,
};

export function viewFromEvent(view: JobView, event: SseEvent): JobView {
  let payload: { progress?: number; stage?: string; data?: Record<string, unknown> };
  try {
    payload = JSON.parse(event.data);
  } catch {
    return view;
  }
  const next: JobView = { ...view };
  if (typeof payload.progress === "number") next.progress = payload.progress;
  if (event.event === "stage" && typeof payload.data?.label === "string") next.stageLabel = payload.data.label;
  if (event.event === "located_sources" && Array.isArray(payload.data?.sources)) {
    next.locatedSources = payload.data!.sources as Array<Record<string, unknown>>;
  }
  // Once a stream is delivering stages the job has left the queue.
  if (event.event === "stage") {
    next.queuePosition = null;
    next.estimatedWaitSeconds = null;
  }
  return next;
}

type JobSnapshot = DeepReviewJob & {
  queue_position?: number | null;
  estimated_wait_seconds?: number | null;
  located_sources?: Array<Record<string, unknown>> | null;
};

export function viewFromJob(job: JobSnapshot): JobView {
  return {
    progress: job.progress,
    stageLabel: job.stage_label ?? null,
    queuePosition: job.queue_position ?? null,
    estimatedWaitSeconds: job.estimated_wait_seconds ?? null,
    locatedSources: job.located_sources ?? null,
  };
}

export const isTerminal = (job: Pick<DeepReviewJob, "status">) =>
  job.status === "succeeded" || job.status === "failed" || job.status === "cancelled";

export interface FollowDeps {
  /** Opens the stream. A non-OK response is returned, not thrown. */
  openStream(jobId: string, lastEventId: number, signal?: AbortSignal): Promise<Response>;
  /** Goes through the normal request path, which refreshes an expired session. */
  getJob(jobId: string, signal?: AbortSignal): Promise<DeepReviewJob>;
  sleep(ms: number, signal?: AbortSignal): Promise<void>;
  pollIntervalMs: number;
  /** No byte for this long means the connection is dead even if nothing says so. */
  idleTimeoutMs: number;
  maxStreamFailures: number;
  maxPollFailures: number;
}

export const DEFAULT_LIMITS = {
  pollIntervalMs: 1500,
  // The server sends a keep-alive roughly every ten seconds.
  idleTimeoutMs: 45_000,
  maxStreamFailures: 3,
  maxPollFailures: 40,
} as const;

function abortError(): Error {
  const error = new Error("Aborted");
  error.name = "AbortError";
  return error;
}

const isFatalStatus = (status: unknown) => status === 403 || status === 404;

async function readWithTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  timeoutMs: number,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      reader.read(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("stream idle")), timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

/** Reads one stream until it ends. Returns the last event id seen. */
async function drainStream(
  response: Response,
  deps: FollowDeps,
  state: { view: JobView; lastEventId: number },
  onUpdate: (view: JobView) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await readWithTimeout(reader, deps.idleTimeoutMs);
      if (signal?.aborted) throw abortError();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSse(buffer);
      buffer = parsed.rest;
      for (const event of parsed.events) {
        if (event.id !== null) state.lastEventId = event.id;
        if (event.event === "end") return;
        const next = viewFromEvent(state.view, event);
        if (next !== state.view) {
          state.view = next;
          onUpdate(next);
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}

export async function followJob(
  jobId: string,
  deps: FollowDeps,
  options: { signal?: AbortSignal; onUpdate?: (view: JobView) => void } = {},
): Promise<DeepReviewJob> {
  const { signal } = options;
  const onUpdate = options.onUpdate ?? (() => undefined);
  const state = { view: EMPTY_VIEW, lastEventId: 0 };
  const guard = () => {
    if (signal?.aborted) throw abortError();
  };

  // What the job looks like now, so a queued reader sees their place at once and
  // a job that finished while the page was closed returns without opening a stream.
  guard();
  let useStream = typeof ReadableStream !== "undefined";
  let streamFailures = 0;
  let pollFailures = 0;
  try {
    const job = await deps.getJob(jobId, signal);
    if (isTerminal(job)) return job;
    state.view = viewFromJob(job);
    onUpdate(state.view);
  } catch (error) {
    guard();
    if (isFatalStatus((error as { status?: unknown }).status)) throw error;
    pollFailures += 1;
  }

  while (useStream) {
    guard();
    try {
      const response = await deps.openStream(jobId, state.lastEventId, signal);
      if (response.status === 401) {
        // Going through the normal request path refreshes the session.
        await deps.getJob(jobId, signal);
        streamFailures += 1;
      } else if (!response.ok || !response.body) {
        // A cap, a proxy, or an old server. Polling still works in all of these.
        useStream = false;
        break;
      } else {
        await drainStream(response, deps, state, onUpdate, signal);
      }
      const job = await deps.getJob(jobId, signal);
      if (isTerminal(job)) return job;
      streamFailures += 1;
    } catch (error) {
      guard();
      if (isFatalStatus((error as { status?: unknown }).status)) throw error;
      streamFailures += 1;
    }
    if (streamFailures >= deps.maxStreamFailures) {
      useStream = false;
      break;
    }
    await deps.sleep(Math.min(8000, 500 * 2 ** streamFailures), signal);
  }

  for (;;) {
    guard();
    await deps.sleep(deps.pollIntervalMs, signal);
    guard();
    try {
      const job = await deps.getJob(jobId, signal);
      pollFailures = 0;
      if (isTerminal(job)) return job;
      state.view = viewFromJob(job);
      onUpdate(state.view);
    } catch (error) {
      guard();
      if (isFatalStatus((error as { status?: unknown }).status)) throw error;
      pollFailures += 1;
      if (pollFailures >= deps.maxPollFailures) throw error;
    }
  }
}

// ---------------------------------------------------------- resuming after reload

export interface ActiveJob {
  jobId: string;
  sessionId: string;
  startedAt: number;
}

type KeyValueStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const key = (userId: string) => `corpusil.active-job.v1:${userId}`;

/** Ids only. The question stays on the server, never in browser storage. */
export function rememberActiveJob(store: KeyValueStore, userId: string, job: ActiveJob): void {
  try {
    store.setItem(key(userId), JSON.stringify(job));
  } catch {
    // Storage disabled: a reload loses the progress display, not the job.
  }
}

export function forgetActiveJob(store: KeyValueStore, userId: string): void {
  try {
    store.removeItem(key(userId));
  } catch {
    // nothing to do
  }
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function readActiveJob(store: KeyValueStore, userId: string): ActiveJob | null {
  try {
    const raw = store.getItem(key(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ActiveJob>;
    if (typeof parsed.jobId !== "string" || !UUID_RE.test(parsed.jobId)) return null;
    if (typeof parsed.sessionId !== "string" || !UUID_RE.test(parsed.sessionId)) return null;
    return { jobId: parsed.jobId, sessionId: parsed.sessionId, startedAt: Number(parsed.startedAt) || Date.now() };
  } catch {
    return null;
  }
}
