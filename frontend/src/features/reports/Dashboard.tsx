import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { formatMoney } from '../../lib/money';
import { ReportState } from '../sales/ledgers';
import { useWorkspace } from '../workspace/hooks';
import { NUM, TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';
import SalesChart from './SalesChart';

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-line bg-canvas p-5">
      <p className="label">{label}</p>
      <p className="mt-2 text-3xl font-medium tracking-[-0.03em] tabular-nums">{value}</p>
      {note && <p className="mt-1 text-sm text-muted">{note}</p>}
    </div>
  );
}

// Loaded on its own, so the chart library is only fetched by people who open this page.
export default function DashboardPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const report = useQuery({
    queryKey: [membership.tenant_id, 'report', 'dashboard'],
    queryFn: () => unwrap(api.GET('/api/reports/dashboard/')),
  });
  const data = report.data;
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const biggest = Math.max(1, ...(data?.top_products ?? []).map((row) => Number(row.amount)));

  return (
    <>
      <PageTitle title={t('rep.dashboard')} subtitle={t('rep.dashboardBody')} />
      <ReportState pending={report.isPending} failed={report.isError} />
      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Stat label={t('rep.salesToday')} value={money(data.sales_today)} />
            <Stat label={t('rep.salesMonth')} value={money(data.sales_month)} />
            <Stat
              label={t('rep.profitMonth')}
              value={money(data.gross_profit_month)}
              {...(data.margin_percent === null
                ? {}
                : { note: t('rep.margin', { percent: data.margin_percent }) })}
            />
            <Stat label={t('rep.stockValue')} value={money(data.stock_value)} />
            <Stat label={t('rep.owedToMe')} value={money(data.receivable)} />
            <Stat label={t('rep.iOwe')} value={money(data.payable)} />
          </div>

          <Panel title={t('rep.last30')}>
            <SalesChart days={data.sales_by_day} />
            <details className="mt-4">
              <summary className="cursor-pointer text-sm text-muted">{t('rep.asTable')}</summary>
              <div className="mt-3 max-h-64 overflow-y-auto" data-lenis-prevent>
                <table className={TABLE}>
                  <thead>
                    <tr>
                      <th className={TH}>{t('acc.date')}</th>
                      <th className={`${TH} text-end`}>{t('pur.amount')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.sales_by_day.map((day) => (
                      <tr key={day.date} className="border-t border-line">
                        <td className={TD}>{day.date}</td>
                        <td className={NUM}>{money(day.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </Panel>

          <Panel title={t('rep.topProducts')}>
            {data.top_products.length === 0 ? (
              <p className="text-muted">{t('rep.noSalesYet')}</p>
            ) : (
              <ul className="space-y-4">
                {data.top_products.map((row) => (
                  <li key={row.name}>
                    <div className="flex justify-between gap-4 text-sm">
                      <span>{row.name}</span>
                      <span className="font-mono tabular-nums">{money(row.amount)}</span>
                    </div>
                    <div className="mt-1.5 h-2 rounded-full bg-raised">
                      <div
                        className="h-2 rounded-full bg-azure"
                        style={{ width: `${(Number(row.amount) / biggest) * 100}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </>
  );
}
