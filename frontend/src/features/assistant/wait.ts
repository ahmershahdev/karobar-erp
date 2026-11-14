import { api } from '../../lib/api/client';
import { ApiError, unwrap } from '../../lib/api/errors';

export type Job = Awaited<ReturnType<typeof fetchJob>>;

const POLL_MS = 1500;
// The server gives up on a job after about two minutes; the screen stops a little later.
const POLL_LIMIT = 90;
// A weak connection drops a request now and then; the answer is still on its way.
export const MISSES_ALLOWED = 5;

function fetchJob(id: number, headers: Record<string, string>) {
  return unwrap(api.GET('/api/assistant/jobs/{id}/', { params: { path: { id } }, headers }));
}

/** Poll a chat job until it ends. Resolves with nothing when `stopped` says the screen moved on. */
export async function waitFor(
  id: number,
  headers: Record<string, string>,
  stopped: () => boolean,
  pollMs = POLL_MS,
): Promise<Job | undefined> {
  let misses = 0;
  for (let tries = 0; tries < POLL_LIMIT; tries += 1) {
    await new Promise((done) => window.setTimeout(done, pollMs));
    if (stopped()) return undefined;
    let job: Job;
    try {
      job = await fetchJob(id, headers);
    } catch (error) {
      // The server saying no (signed out, job gone) is an answer; anything else may pass.
      const refused =
        error instanceof ApiError && error.status < 500 && ![408, 429].includes(error.status);
      misses += 1;
      if (refused || misses > MISSES_ALLOWED) throw error;
      continue;
    }
    misses = 0;
    if (job.status === 'done') return job;
    if (job.status === 'failed') throw new ApiError(503, { detail: job.error });
  }
  throw new ApiError(503, {});
}
