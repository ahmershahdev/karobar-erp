# Chat fixes tracker

Found on 2026-11-14 by reading the chat code and checking the running dev stack. Items 1 to 7
are fixed on the branch `fix/chat-queue`. Delete this file when the unticked items are done.

## Why the chat did not answer on 2026-11-14

Chat answers share the one Celery queue with the nightly jobs. The dev `.env` has
`DEMO_MODE=true`, so Celery beat sent the missed `reset_demo` job 22 seconds after `npm run dev`
started. On Windows the worker runs one job at a time (`--pool=solo`), and the rebuild takes half
an hour or more, so every question waited behind it and the screen gave up after two minutes.

- Three questions were still `waiting` in `assistant_chatjob`, and all three were in the Redis
  `celery` list behind `reset_demo`.
- Groq was checked with the dev key and the default model (`openai/gpt-oss-120b`): a plain answer,
  a `look_up_product` call and a `draft_sales_invoice` call each came back in under a second.
- Production runs `--concurrency=2` on the same queue (`deploy/compose.prod.yaml`), so two long
  jobs would block the chat there too.

With the fix, `npm run dev` starts a second worker for the `chat` queue, so restart it once
after pulling. Celery does not reload code.

## To fix

- [x] **1. Chat gets its own queue and worker.** Route `apps.assistant.tasks.answer_question` to
      a `chat` queue; add a worker for it in `scripts/dev.mjs` and `deploy/compose.prod.yaml`.
      Slow nightly jobs can then never block an answer. This is the fix that matters most.
- [x] **2. The question shows twice while waiting.** `frontend/src/features/assistant/Chat.tsx`:
      the message list is refreshed after the question is saved (line 68) and shows it, and the
      pending bubble (line 186) shows `ask.variables` again. Show it from one place only.
- [x] **3. Abandoned questions are still answered later.** `backend/apps/assistant/tasks.py:54`:
      the screen gives up after `JOB_PATIENCE`, but the row stays `waiting`, so the worker answers
      it whenever it is free. Answers land late and out of order and use Groq quota. Fail a job
      older than `JOB_PATIENCE` instead of answering it, and give the task an `expires`.
- [x] **4. The same job can be answered twice.** The task checks the status but never claims the
      job, so a redelivered task (`acks_late`) can write a second answer. Claim it with a
      conditional update before answering. Rare; not reproduced.
- [x] **5. Groq failures are never logged.** `tasks.py:64` catches `AssistantError` without a log
      line, and `backend/apps/platform/http.py:39` drops the HTTP status. A rate limit, a bad key
      and a malformed tool call all look the same. Log the status and Groq's error code.
- [x] **6. One failed poll ends the wait.** `Chat.tsx:29`: a single network error shows the error
      message, and the answer that arrives later only appears on the next refresh. Tolerate a few
      failed polls.
- [x] **7. Reload or reopen during a wait.** No "thinking" is shown and a second question can be
      sent while the first is still running. Resume polling for a job that is still waiting, or
      refuse a second question on the server.

## Tests to add with the fixes

- [x] A job older than `QUEUE_PATIENCE` (75 seconds) is failed, not answered.
- [x] A job delivered twice gets one answer.
- [x] A Groq error is logged with its status.
- [x] The question appears once while waiting and once after the answer (Vitest, in
      `frontend/src/features/assistant/Chat.test.tsx`).
- [ ] The same in Playwright against the real stack, with the end-to-end tests.

## How each was fixed

1. `CELERY_TASK_ROUTES` sends `answer_question` to the `chat` queue; `scripts/dev.mjs` and
   `deploy/compose.prod.yaml` each run a worker for it. Seen on 2026-11-14: with `reset_demo`
   running on the main worker, the chat worker took its tasks at once.
2. The saved question is put into the message list from the reply to `ask/`; the extra bubble
   only shows until the server has it.
3. The task is sent with `expires` and the worker only claims a job younger than
   `QUEUE_PATIENCE`. Celery drops an expired task without running it, so the row is ended when
   the screen polls it.
4. `ChatJob.started_at` is set by one conditional update; a second delivery finds it set and
   ends the job instead of answering again.
5. `post_json` raises on an HTTP error with the status and Groq's short code, and `complete()`
   logs them. An empty reply is logged with its `finish_reason`.
6. The screen allows five failed polls in a row before giving up; a refusal (401, 404) still
   stops it at once.
7. `check/` returns the job still being answered, the screen picks its wait up again, and a
   second question meanwhile gets 409.

## To check, not confirmed

- `openai/gpt-oss-120b` is a reasoning model, and `MAX_ANSWER_TOKENS = 700` may also count its
  reasoning. A harder question could come back with empty text, which the chat reports as
  "can't answer right now". The log line "Groq reply could not be used ... finish_reason
  length" now shows it; raise the limit if it appears.
- The Groq rate limit on this key (already an open question in `docs/status.md`).
