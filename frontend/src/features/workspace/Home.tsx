import { useQuery } from '@tanstack/react-query';
import { lazy, Suspense, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { can } from '../../lib/api/types';
import { formatMoney, toMinor } from '../../lib/money';
import { useReducedMotion } from '../../lib/motion';
import { useTenantAction, useWorkspace } from './hooks';
import { Panel } from './ui';

const SalesChart = lazy(() => import('../reports/SalesChart'));

const COUNT_MS = 700;

function CountUp({ value }: { value: string }) {
  const { i18n } = useTranslation();
  const reduced = useReducedMotion();
  const target = toMinor(value);
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const started = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const progress = Math.min(1, (now - started) / COUNT_MS);
      setShown(Math.round(target * (1 - (1 - progress) ** 3)));
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, reduced]);
  return <>{formatMoney(reduced ? target : shown, i18n.resolvedLanguage)}</>;
}

function Stat({
  label,
  value,
  to,
  note,
}: {
  label: string;
  value: string | undefined;
  to: string;
  note?: string | undefined;
}) {
  return (
    <Link
      to={to}
      className="block rounded-[var(--radius-card)] border border-line bg-canvas p-5 transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-line-strong"
    >
      <p className="label">{label}</p>
      {value === undefined ? (
        <div className="mt-3 h-8 w-32 animate-pulse rounded-lg bg-raised motion-reduce:animate-none" />
      ) : (
        <p className="mt-2 text-3xl font-medium tracking-[-0.03em] tabular-nums">
          <CountUp value={value} />
        </p>
      )}
      {note && <p className="mt-1 text-sm text-muted">{note}</p>}
    </Link>
  );
}

const STEPS = [
  { key: 'store', path: 'inventory/setup' },
  { key: 'product', path: 'inventory/products' },
  { key: 'price', path: 'inventory/products' },
  { key: 'sale', path: 'counter' },
] as const;

const WARNINGS = [
  { key: 'low_stock', path: 'inventory/alerts' },
  { key: 'overdue', path: 'sales/owed-to-me' },
  { key: 'open_tills', path: 'counter' },
] as const;

function Automation() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const save = useTenantAction(['automation']);
  const settings = useQuery({
    queryKey: [membership.tenant_id, 'automation'],
    queryFn: () => unwrap(api.GET('/api/automation/')),
  });
  return (
    <Panel title={t('business.automation')}>
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          className="mt-1 size-5 accent-[var(--color-flame)]"
          disabled={!settings.data || save.isPending}
          checked={settings.data?.daily_summary ?? false}
          onChange={(event) => {
            const body = { daily_summary: event.target.checked };
            save.mutate(() => unwrap(api.PATCH('/api/automation/', { body })));
          }}
        />
        <span>
          <span className="block font-medium">{t('business.dailySummary')}</span>
          <span className="block text-sm text-muted">{t('business.dailySummaryBody')}</span>
        </span>
      </label>
    </Panel>
  );
}

/** The numbers, next steps and warnings on the business home page. Needs the reports permission:
 * they include profit, which a cashier shouldn't see, so others get the task tiles alone. */
export function Home() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const allowed = can(membership, 'reports', 'view');
  const base = `/app/${membership.tenant_slug}`;
  const home = useQuery({
    queryKey: [membership.tenant_id, 'report', 'home'],
    queryFn: () => unwrap(api.GET('/api/reports/home/')),
    enabled: allowed,
  });
  const report = useQuery({
    queryKey: [membership.tenant_id, 'report', 'dashboard'],
    queryFn: () => unwrap(api.GET('/api/reports/dashboard/')),
    enabled: allowed,
  });
  if (!allowed) return null;

  const setup = home.data?.setup;
  const done = setup ? STEPS.filter((step) => setup[step.key]).length : 0;
  const next = setup && STEPS.find((step) => !setup[step.key]);
  const warnings = home.data ? WARNINGS.filter((item) => home.data.attention[item.key] > 0) : [];
  const data = report.data;
  const reports = `${base}/reports/dashboard`;
  const hasSales = data?.sales_by_day.some((day) => Number(day.amount) > 0);

  return (
    <div className="space-y-6">
      {setup && next && (
        <Panel title={t('business.setupTitle')}>
          <p className="mb-3 text-sm text-muted">
            {t('business.setupProgress', { done, total: STEPS.length })}
          </p>
          <div className="mb-5 h-2 rounded-full bg-raised">
            <div
              className="h-2 rounded-full bg-flame transition-[width] duration-700 motion-reduce:transition-none"
              style={{ width: `${(done / STEPS.length) * 100}%` }}
            />
          </div>
          <ol className="divide-y divide-line">
            {STEPS.map((step, index) => {
              const finished = setup[step.key];
              return (
                <li key={step.key} className="flex items-center gap-4 py-3">
                  <span
                    aria-hidden="true"
                    className={`grid size-9 shrink-0 place-items-center rounded-full text-sm ${
                      finished ? 'bg-green text-white' : 'border border-line-strong'
                    }`}
                  >
                    {finished ? '✓' : index + 1}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span
                      className={`block ${finished ? 'text-muted line-through' : 'font-medium'}`}
                    >
                      {t(`business.steps.${step.key}.title`)}
                    </span>
                    {!finished && (
                      <span className="block text-sm text-muted">
                        {t(`business.steps.${step.key}.body`)}
                      </span>
                    )}
                  </span>
                  {step === next && (
                    <Link to={`${base}/${step.path}`} className="btn btn-primary !py-2.5 !text-sm">
                      {t('business.doThis')}
                    </Link>
                  )}
                </li>
              );
            })}
          </ol>
        </Panel>
      )}

      {warnings.length > 0 && (
        <Panel title={t('business.attention')}>
          <ul className="divide-y divide-line">
            {home.data &&
              warnings.map((item) => (
                <li key={item.key}>
                  <Link
                    to={`${base}/${item.path}`}
                    className="flex min-h-12 items-center justify-between gap-4 py-2 hover:text-ember"
                  >
                    <span>
                      {t(`business.warnings.${item.key}`, { count: home.data.attention[item.key] })}
                    </span>
                    <span aria-hidden="true" className="rtl:rotate-180">
                      &rarr;
                    </span>
                  </Link>
                </li>
              ))}
          </ul>
        </Panel>
      )}

      <section className="space-y-4">
        <h2 className="text-2xl">{t('business.today')}</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Stat label={t('rep.salesToday')} value={data?.sales_today} to={reports} />
          <Stat label={t('rep.salesMonth')} value={data?.sales_month} to={reports} />
          <Stat
            label={t('rep.profitMonth')}
            value={data?.gross_profit_month}
            to={reports}
            note={
              data && data.margin_percent !== null
                ? t('rep.margin', { percent: data.margin_percent })
                : undefined
            }
          />
          <Stat
            label={t('rep.owedToMe')}
            value={data?.receivable}
            to={`${base}/sales/owed-to-me`}
          />
          <Stat label={t('rep.iOwe')} value={data?.payable} to={reports} />
          <Stat
            label={t('rep.stockValue')}
            value={data?.stock_value}
            to={`${base}/inventory/on-hand`}
          />
        </div>
      </section>

      {membership.is_owner && <Automation />}

      <Panel title={t('rep.last30')}>
        {!data ? (
          <div className="h-64 animate-pulse rounded-xl bg-surface motion-reduce:animate-none" />
        ) : hasSales ? (
          <Suspense fallback={<div className="h-64" />}>
            <SalesChart days={data.sales_by_day} />
          </Suspense>
        ) : (
          <p className="py-10 text-center text-muted">{t('business.noSales')}</p>
        )}
      </Panel>
    </div>
  );
}
