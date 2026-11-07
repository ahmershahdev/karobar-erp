import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import type { ChatCard, ChatMessage, Membership } from '../../lib/api/types';
import { formatMoney } from '../../lib/money';
import { ensureCsrf } from '../auth/session';
import { errorText } from '../workspace/hooks';
import { ScreenIcon } from '../workspace/icons';

// Where each kind of draft lives, with the same name and picture as in the side menu.
const SCREENS = {
  sales_invoice: { path: 'sales/invoices', label: 'sal.invoices', icon: 'bills' },
  quotation: { path: 'sales/orders', label: 'sal.orders', icon: 'orders' },
  purchase_order: { path: 'purchasing/orders', label: 'pur.orders', icon: 'orders' },
} as const;

const BUBBLE = 'rounded-2xl bg-raised px-4 py-2.5 text-sm leading-relaxed';

/** A draft the chat proposed. Every value comes from the server's lookup, not from the model's
 * words, and nothing is saved until the person presses Confirm. */
export function DraftCard({
  message,
  membership,
  saved,
  messagesKey,
}: {
  message: ChatMessage;
  membership: Membership;
  saved: boolean;
  messagesKey: unknown[];
}) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const confirm = useMutation({
    mutationFn: async () => {
      const headers = { 'X-Tenant': membership.tenant_id };
      await ensureCsrf();
      return unwrap(
        api.POST('/api/assistant/drafts/{id}/confirm/', {
          params: { path: { id: message.id } },
          headers,
        }),
      );
    },
    onSettled: () => client.invalidateQueries({ queryKey: messagesKey }),
  });
  const card = message.card;
  if (!card) return null;
  if (card.problem) return <p className={BUBBLE}>{problemText(card.problem, t)}</p>;
  if (!card.kind || !card.party || !card.warehouse || !card.lines) return null;
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const party = card.kind === 'purchase_order' ? 'supplier' : 'customer';
  return (
    <div className="space-y-3 rounded-2xl border border-line-strong bg-canvas p-4 text-sm">
      <div>
        <p className="font-medium">{t(`chat.draft.kind.${card.kind}`)}</p>
        <p className="text-muted">{t(`chat.draft.${party}`, { name: card.party.name })}</p>
        <p className="text-muted">{t('chat.draft.warehouse', { name: card.warehouse.name })}</p>
      </div>
      <ul className="space-y-1 border-y border-line py-2">
        {card.lines.map((line, index) => (
          <li key={index} className="flex justify-between gap-3">
            <span className="min-w-0">
              <span dir="ltr" className="tabular-nums">
                {line.quantity} {line.unit_code}
              </span>{' '}
              {line.name}
            </span>
            <span className="shrink-0 tabular-nums">
              {line.unit_price === null ? (
                <span className="text-red">{t('chat.draft.noPrice')}</span>
              ) : (
                money(line.unit_price)
              )}
            </span>
          </li>
        ))}
      </ul>
      <p className="flex justify-between font-medium">
        <span>{t('chat.draft.total')}</span>
        <span className="tabular-nums">{money(card.total ?? '0')}</span>
      </p>
      {card.memo && <p className="text-muted">{card.memo}</p>}
      {!saved && (
        <>
          <p className="text-xs leading-relaxed text-muted">{t('chat.draft.hint')}</p>
          <button
            type="button"
            disabled={confirm.isPending || confirm.isSuccess}
            onClick={() => confirm.mutate()}
            className="btn btn-primary w-full !py-2.5 !text-sm disabled:opacity-40"
          >
            {confirm.isPending ? t('chat.draft.saving') : t('chat.draft.confirm')}
          </button>
        </>
      )}
      {confirm.isError && (
        <p className="text-sm text-red">{errorText(confirm.error, t('signIn.unavailable'))}</p>
      )}
    </div>
  );
}

/** The record that a draft was saved, with a way to open it. */
export function DraftSaved({ card, membership }: { card: ChatCard; membership: Membership }) {
  const { t } = useTranslation();
  if (!card.kind) return null;
  const screen = SCREENS[card.kind];
  return (
    <div className={`${BUBBLE} space-y-2`}>
      <p>{t('chat.draft.done')}</p>
      <Link
        to={`/app/${membership.tenant_slug}/${screen.path}`}
        className="inline-flex min-h-10 items-center gap-2 rounded-full border border-line bg-canvas px-3 font-medium hover:border-ink"
      >
        <ScreenIcon name={screen.icon} />
        {t(screen.label)}
      </Link>
    </div>
  );
}

function problemText(problem: NonNullable<ChatCard['problem']>, t: TFunction): string {
  if (problem.code === 'not_found' || problem.code === 'ambiguous') {
    return t(`chat.draft.problem.${problem.code}.${problem.field}`, {
      name: problem.name,
      options: problem.options.join(', '),
    });
  }
  return t(`chat.draft.problem.${problem.code}`);
}
