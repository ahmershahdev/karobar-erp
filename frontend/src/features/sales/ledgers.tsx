import { useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Button, Field } from '../../components/form';
import { api } from '../../lib/api/client';
import { ApiError, unwrap } from '../../lib/api/errors';
import { env } from '../../lib/env';
import { formatMoney } from '../../lib/money';
import { useWorkspace } from '../workspace/hooks';
import { NUM, NUM_TH, TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';

const COLUMNS = ['current', 'days_1_30', 'days_31_60', 'days_61_90', 'over_90'] as const;

interface AgeingRow {
  id: number;
  name: string;
  current: string;
  days_1_30: string;
  days_31_60: string;
  days_61_90: string;
  over_90: string;
  advance: string;
  total: string;
}

// Says what is happening instead of leaving a blank panel while a report loads or fails.
export function ReportState({ pending, failed }: { pending: boolean; failed: boolean }) {
  const { t } = useTranslation();
  if (failed) return <Alert tone="error">{t('signIn.unavailable')}</Alert>;
  return pending ? <p className="text-muted">{t('led.loading')}</p> : null;
}

function AgeingTable({
  rows,
  nameLabel,
}: {
  rows: (AgeingRow & { whatsapp?: string })[];
  nameLabel: string;
}) {
  const { t, i18n } = useTranslation();
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  if (rows.length === 0) return <p className="text-muted">{t('led.allClear')}</p>;
  return (
    <div className="overflow-x-auto" data-lenis-prevent>
      <table className={`${TABLE} min-w-[46rem]`}>
        <thead>
          <tr>
            <th className={TH}>{nameLabel}</th>
            {COLUMNS.map((column) => (
              <th key={column} className={NUM_TH}>
                {t(`led.${column}`)}
              </th>
            ))}
            <th className={NUM_TH}>{t('led.advance')}</th>
            <th className={NUM_TH}>{t('led.total')}</th>
            {rows.some((row) => row.whatsapp) && <th className={TH} />}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-line">
              <td className={TD}>{row.name}</td>
              {COLUMNS.map((column) => (
                <td key={column} className={NUM}>
                  {money(row[column])}
                </td>
              ))}
              <td className={NUM}>{money(row.advance)}</td>
              <td className={`${NUM} font-medium`}>{money(row.total)}</td>
              {row.whatsapp && (
                <td className={TD}>
                  <a
                    href={row.whatsapp}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-ghost !py-2 !text-sm"
                  >
                    {t('share.remind')}
                  </a>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReceivablesPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const rows = useQuery({
    queryKey: [membership.tenant_id, 'invoices', 'ageing'],
    queryFn: () => unwrap(api.GET('/api/sales/ageing/')),
  });
  return (
    <>
      <PageTitle title={t('led.receivables')} subtitle={t('led.receivablesBody')} />
      <Panel title={t('led.receivables')}>
        <ReportState pending={rows.isPending} failed={rows.isError} />
        {rows.data && <AgeingTable rows={rows.data} nameLabel={t('sal.customer')} />}
      </Panel>
    </>
  );
}

export function PayablesPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const rows = useQuery({
    queryKey: [membership.tenant_id, 'bills', 'ageing'],
    queryFn: () => unwrap(api.GET('/api/purchasing/ageing/')),
  });
  return (
    <>
      <PageTitle title={t('led.payables')} subtitle={t('led.payablesBody')} />
      <Panel title={t('led.payables')}>
        <ReportState pending={rows.isPending} failed={rows.isError} />
        {rows.data && <AgeingTable rows={rows.data} nameLabel={t('pur.supplier')} />}
      </Panel>
    </>
  );
}

interface Statement {
  opening: string;
  closing: string;
  lines: {
    date: string;
    number: string;
    kind: string;
    charged: string;
    paid: string;
    balance: string;
  }[];
}

/** One customer's or supplier's account, opened from their row. */
export function StatementPanel({
  title,
  load,
  queryKey,
  onClose,
}: {
  title: ReactNode;
  load: (query: { start?: string; end?: string }) => Promise<Statement>;
  queryKey: string;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const statement = useQuery({
    queryKey: [membership.tenant_id, queryKey, start, end],
    queryFn: () => load({ ...(start ? { start } : {}), ...(end ? { end } : {}) }),
  });
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  return (
    <section className="rounded-[var(--radius-card)] border border-line bg-canvas p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl">{title}</h2>
        <Button variant="ghost" onClick={onClose}>
          {t('workspace.cancel')}
        </Button>
      </div>
      <div className="mb-4 grid gap-4 sm:grid-cols-2 md:max-w-lg">
        <Field
          label={t('led.from')}
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
        <Field
          label={t('led.to')}
          type="date"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
        />
      </div>
      <ReportState pending={statement.isPending} failed={statement.isError} />
      {statement.data && (
        <div className="overflow-x-auto" data-lenis-prevent>
          <table className={`${TABLE} min-w-[38rem]`}>
            <thead>
              <tr>
                <th className={TH}>{t('acc.date')}</th>
                <th className={TH}>{t('led.document')}</th>
                <th className={NUM_TH}>{t('led.charged')}</th>
                <th className={NUM_TH}>{t('led.paid')}</th>
                <th className={NUM_TH}>{t('led.balance')}</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-line">
                <td className={TD} colSpan={4}>
                  {t('led.opening')}
                </td>
                <td className={NUM}>{money(statement.data.opening)}</td>
              </tr>
              {statement.data.lines.map((line, index) => (
                <tr key={`${index}-${line.number}`} className="border-t border-line">
                  <td className={TD}>{line.date}</td>
                  <td className={TD}>
                    {t(`led.kind.${line.kind}`)} <span className="text-muted">{line.number}</span>
                  </td>
                  <td className={NUM}>{Number(line.charged) ? money(line.charged) : ''}</td>
                  <td className={NUM}>{Number(line.paid) ? money(line.paid) : ''}</td>
                  <td className={NUM}>{money(line.balance)}</td>
                </tr>
              ))}
              <tr className="border-t border-line-strong font-medium">
                <td className={TD} colSpan={4}>
                  {t('led.closing')}
                </td>
                <td className={NUM}>{money(statement.data.closing)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// A proxy in front of the API can answer with an HTML page, which must not surface as a JSON error.
export async function errorBody(response: Response): Promise<unknown> {
  try {
    return JSON.parse(await response.text());
  } catch {
    return undefined;
  }
}

/**
 * Opens a posted document as a PDF in the customer's language. The API needs the X-Tenant header,
 * which a plain link can't send, so the file is fetched and opened as a blob.
 */
/** Opens WhatsApp with the bill ready to send. The tab opens first, or the browser would treat it
 * as a pop-up, because the link only arrives after a request. */
export function ShareButtons({ invoiceId }: { invoiceId: number }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [problem, setProblem] = useState('');
  const share = () =>
    unwrap(api.GET('/api/sales/invoices/{id}/share/', { params: { path: { id: invoiceId } } }));
  return (
    <>
      <Button
        variant="ghost"
        onClick={() => {
          setProblem('');
          const tab = window.open('', '_blank');
          if (tab) tab.opener = null;
          share().then(
            (data) => {
              if (tab) tab.location.href = data.whatsapp;
            },
            () => {
              tab?.close();
              setProblem(t('signIn.unavailable'));
            },
          );
        }}
      >
        {t('share.whatsapp')}
      </Button>
      <Button
        variant="ghost"
        onClick={() => {
          setProblem('');
          share()
            .then((data) => navigator.clipboard.writeText(data.link))
            .then(
              () => setCopied(true),
              () => setProblem(t('signIn.unavailable')),
            );
        }}
      >
        {copied ? t('share.copied') : t('share.copy')}
      </Button>
      {problem && <p className="text-sm text-red">{problem}</p>}
    </>
  );
}

export function PrintButton({ path }: { path: string }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Button
        variant="ghost"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setProblem('');
          const language = i18n.resolvedLanguage ?? 'en';
          void fetch(`${env.apiBaseUrl}${path}?lang=${language}`, {
            credentials: 'same-origin',
            headers: { 'X-Tenant': membership.tenant_id },
          })
            .then(async (response) => {
              if (!response.ok) {
                throw new ApiError(response.status, await errorBody(response));
              }
              const url = URL.createObjectURL(await response.blob());
              window.open(url, '_blank', 'noopener');
              window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
            })
            .catch((error: unknown) => {
              setProblem(error instanceof Error ? error.message : t('signIn.unavailable'));
            })
            .finally(() => setBusy(false));
        }}
      >
        {t('led.print')}
      </Button>
      {problem && <Alert tone="error">{problem}</Alert>}
    </>
  );
}
