import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import type { Membership } from '../../lib/api/types';
import { ensureCsrf } from '../auth/session';
import { errorText } from '../workspace/hooks';

/** The business chat. Answers show as plain text, so nothing a model writes can run on the page. */
export function Chat({ membership }: { membership: Membership }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [showCheck, setShowCheck] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const keys = {
    messages: [membership.tenant_id, 'assistant', 'messages'],
    check: [membership.tenant_id, 'assistant', 'check'],
  };
  const check = useQuery({
    queryKey: keys.check,
    queryFn: () => unwrap(api.GET('/api/assistant/check/')),
    enabled: open,
  });
  const messages = useQuery({
    queryKey: keys.messages,
    queryFn: () => unwrap(api.GET('/api/assistant/messages/')),
    enabled: open,
  });
  const ask = useMutation({
    mutationFn: async (message: string) => {
      await ensureCsrf();
      return unwrap(api.POST('/api/assistant/ask/', { body: { message } }));
    },
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.messages }),
        client.invalidateQueries({ queryKey: keys.check }),
      ]),
  });
  const count = messages.data?.length;
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [count, ask.isPending, open]);

  const send = () => {
    const message = text.trim();
    if (!message || ask.isPending) return;
    setText('');
    ask.mutate(message);
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn btn-primary fixed end-5 bottom-5 z-50 shadow-[var(--shadow-float)]"
      >
        {t('chat.open')}
      </button>
    );
  }

  const off = check.data?.enabled === false;
  return (
    <section
      aria-label={t('chat.title')}
      className="fixed end-5 bottom-5 z-50 flex h-[min(38rem,calc(100svh-2.5rem))] w-[min(26rem,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-[var(--radius-card)] border border-line-strong bg-canvas shadow-[var(--shadow-float)]"
    >
      <header className="flex items-center justify-between gap-3 border-b border-line p-4">
        <h2 className="text-lg">{t('chat.title')}</h2>
        <button
          type="button"
          aria-label={t('chat.close')}
          onClick={() => setOpen(false)}
          className="grid size-10 place-items-center rounded-full border border-line"
        >
          &times;
        </button>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto p-4" data-lenis-prevent>
        <p className="rounded-xl bg-surface p-3 text-xs leading-relaxed text-muted">
          {off ? t('chat.off') : t('chat.notice')}
        </p>
        {messages.data?.map((message) => {
          const mine = message.role === 'user';
          return (
            <div key={message.id} className={mine ? 'ms-8' : 'me-8'}>
              <p
                className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                  mine ? 'bg-ink text-white' : 'bg-raised'
                }`}
              >
                {message.content}
              </p>
              <p
                className="mt-1 px-1 font-mono text-[0.65rem] text-muted"
                title={message.signature}
              >
                {t('chat.signed', { id: message.signature.slice(0, 12) })}
              </p>
            </div>
          );
        })}
        {ask.isPending && (
          <>
            <p className="ms-8 rounded-2xl bg-ink px-4 py-2.5 text-sm whitespace-pre-wrap text-white">
              {ask.variables}
            </p>
            <p className="me-8 animate-pulse rounded-2xl bg-raised px-4 py-2.5 text-sm text-muted motion-reduce:animate-none">
              {t('chat.thinking')}
            </p>
          </>
        )}
        {ask.isError && (
          <p className="text-sm text-red">{errorText(ask.error, t('signIn.unavailable'))}</p>
        )}
        <div ref={end} />
      </div>
      <div className="space-y-2 border-t border-line p-3">
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          <input
            aria-label={t('chat.placeholder')}
            placeholder={t('chat.placeholder')}
            maxLength={2000}
            disabled={off}
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="min-h-11 min-w-0 flex-1 rounded-xl border border-line bg-canvas px-3 outline-none focus:border-ink"
          />
          <button
            type="submit"
            disabled={off || ask.isPending || !text.trim()}
            className="btn btn-primary !py-2.5 !text-sm disabled:opacity-40"
          >
            {t('chat.send')}
          </button>
        </form>
        <button
          type="button"
          className="text-xs text-muted underline underline-offset-4"
          onClick={() => {
            setShowCheck(true);
            void check.refetch();
          }}
        >
          {t('chat.verify')}
        </button>
        {showCheck && check.data && (
          <p className={`text-xs ${check.data.ok ? 'text-green' : 'text-red'}`}>
            {check.data.ok ? t('chat.verified', { count: check.data.count }) : t('chat.tampered')}
          </p>
        )}
      </div>
    </section>
  );
}
