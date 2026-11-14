import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor as until } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '../../i18n';
import { api } from '../../lib/api/client';
import type { Membership } from '../../lib/api/types';
import { Chat } from './Chat';
import { MISSES_ALLOWED, waitFor } from './wait';

vi.mock('../auth/session', () => ({ ensureCsrf: () => Promise.resolve() }));

type Reply = { status: number; body: unknown };
type Row = { id: number; role: string; content: string; signature: string; card: null };

const membership = { tenant_id: 'shop' } as Membership;
const ok = (body: unknown): Reply => ({ status: 200, body });

function row(id: number, role: string, content: string): Row {
  return { id, role, content, signature: `sig${id}`.padEnd(12, '0'), card: null };
}

function job(status: string, answer: Row | null = null, error = '') {
  return { id: 7, status, question: row(1, 'user', 'How are sales?'), answer, error };
}

/** Answers each request from a list per path; the last answer for a path repeats. */
function serve(routes: Record<string, (Reply | Error)[]>) {
  const calls: string[] = [];
  const answer = (method: string) => (path: string) => {
    calls.push(`${method} ${path}`);
    const queue = routes[`${method} ${path}`];
    const next = queue && queue.length > 1 ? queue.shift() : queue?.[0];
    if (!next) throw new Error(`unexpected ${method} ${path}`);
    if (next instanceof Error) return Promise.reject(next);
    const response = new Response(null, { status: next.status });
    return Promise.resolve(
      next.status < 400 ? { data: next.body, response } : { error: next.body, response },
    );
  };
  vi.spyOn(api, 'GET').mockImplementation(answer('GET') as never);
  vi.spyOn(api, 'POST').mockImplementation(answer('POST') as never);
  return calls;
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Chat membership={membership} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole('button'));
}

const JOB = 'GET /api/assistant/jobs/{id}/';
const check = (waiting: number | null) =>
  ok({ enabled: true, ok: true, count: 0, broken_at: null, waiting });

const both = [row(1, 'user', 'How are sales?'), row(2, 'assistant', 'Good today.')];

beforeEach(() => {
  Element.prototype.scrollIntoView = () => undefined;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('waiting for a chat answer', () => {
  const poll = (routes: (Reply | Error)[], stopped = () => false) => {
    serve({ [JOB]: routes });
    return waitFor(7, {}, stopped, 1);
  };

  it('returns the job once it is done', async () => {
    const done = job('done', row(2, 'assistant', 'Good.'));
    expect(await poll([ok(job('waiting')), ok(done)])).toEqual(done);
  });

  it('carries on after a few failed polls', async () => {
    const blips = Array.from({ length: MISSES_ALLOWED - 1 }, () => new TypeError('offline'));
    const done = job('done', row(2, 'assistant', 'Good.'));
    expect(await poll([...blips, { status: 502, body: {} }, ok(job('waiting')), ok(done)])).toEqual(
      done,
    );
  });

  it('gives up when the polls keep failing', async () => {
    await expect(poll([new TypeError('offline')])).rejects.toThrow('offline');
  });

  it('stops at once when the server refuses', async () => {
    const calls = serve({ [JOB]: [{ status: 404, body: { detail: 'Not found.' } }] });
    await expect(waitFor(7, {}, () => false, 1)).rejects.toThrow('Not found.');
    expect(calls).toHaveLength(1);
  });

  it('reports a failed job with its message', async () => {
    await expect(poll([ok(job('failed', null, 'Try again.'))])).rejects.toThrow('Try again.');
  });

  it('stops quietly when the screen has moved on', async () => {
    expect(await poll([ok(job('waiting'))], () => true)).toBeUndefined();
  });
});

describe('the chat screen', () => {
  it(
    'shows a question once while waiting and once after the answer',
    { timeout: 20000 },
    async () => {
      serve({
        'GET /api/assistant/check/': [check(null)],
        // Read once before the question; until the job ends, changes reach the list from it.
        'GET /api/assistant/messages/': [ok([]), ok(both)],
        'POST /api/assistant/ask/': [{ status: 202, body: job('waiting') }],
        [JOB]: [ok(job('waiting')), ok(job('done', row(2, 'assistant', 'Good today.')))],
      });
      show();
      const input = await screen.findByRole('textbox');
      fireEvent.change(input, { target: { value: 'How are sales?' } });
      fireEvent.submit(input);
      await screen.findByRole('status');
      expect(screen.getAllByText('How are sales?')).toHaveLength(1);
      await screen.findByText('Good today.', undefined, { timeout: 8000 });
      expect(screen.getAllByText('How are sales?')).toHaveLength(1);
      expect(screen.getAllByText('Good today.')).toHaveLength(1);
      await until(() => expect(screen.queryByRole('status')).toBeNull());
    },
  );

  it(
    'picks up a question still being answered when it is opened again',
    { timeout: 20000 },
    async () => {
      const calls = serve({
        'GET /api/assistant/check/': [check(7), check(null)],
        'GET /api/assistant/messages/': [ok([row(1, 'user', 'How are sales?')]), ok(both)],
        [JOB]: [ok(job('done', row(2, 'assistant', 'Good today.')))],
      });
      show();
      await screen.findByRole('status');
      expect(screen.getByRole('textbox').closest('form')?.querySelector('button')?.disabled).toBe(
        true,
      );
      await screen.findByText('Good today.', undefined, { timeout: 8000 });
      await until(() => expect(screen.queryByRole('status')).toBeNull());
      expect(calls.filter((call) => call === JOB)).toHaveLength(1);
    },
  );

  it('says so when the server is still answering the last question', async () => {
    serve({
      'GET /api/assistant/check/': [check(null)],
      'GET /api/assistant/messages/': [ok([])],
      'POST /api/assistant/ask/': [
        { status: 409, body: { detail: 'Still being answered.', code: 'still_answering' } },
      ],
    });
    show();
    const input = await screen.findByRole('textbox');
    fireEvent.change(input, { target: { value: 'Again' } });
    fireEvent.submit(input);
    expect((await screen.findByRole('alert')).textContent).toBe('Still being answered.');
  });
});
