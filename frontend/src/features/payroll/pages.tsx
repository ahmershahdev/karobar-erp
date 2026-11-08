import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ConfirmButton } from '../../components/ConfirmButton';
import { Alert, Button, Field, Hint, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { ApiError, unwrap } from '../../lib/api/errors';
import { allPages } from '../../lib/api/pages';
import type { components } from '../../lib/api/schema';
import { can } from '../../lib/api/types';
import { formatMoney } from '../../lib/money';
import { env } from '../../lib/env';
import { postable, useAccounts } from '../purchasing/pages';
import { errorBody, PrintButton } from '../sales/ledgers';
import { errorText, useTenantAction, useWorkspace } from '../workspace/hooks';
import { NUM, NUM_TH, TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';

type Run = components['schemas']['PayrollRun'];
type RunDetail = components['schemas']['PayrollRunDetail'];
type Payslip = components['schemas']['Payslip'];
type TaxTable = components['schemas']['TaxTable'];
type Posted = components['schemas']['Posted'];

const KEYS = ['payroll-runs', 'payroll-run', 'payroll-tax-tables', 'payroll-opening-pay'];

function thisMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function monthName(month: string, locale: string | undefined): string {
  const [year, number] = month.split('-').map(Number);
  return new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(
    new Date(year ?? 2000, (number ?? 1) - 1, 1),
  );
}

function days(value: string): string {
  return String(Number(value));
}

// Payroll

function Payslips({ run }: { run: RunDetail }) {
  const { t, i18n } = useTranslation();
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const posted = run.status === 'posted';
  return (
    <div className="overflow-x-auto">
      <table className={TABLE}>
        <thead>
          <tr className="border-b border-line">
            <th className={TH}>{t('payroll.employee')}</th>
            <th className={NUM_TH}>{t('payroll.paidDays')}</th>
            <th className={NUM_TH}>{t('payroll.gross')}</th>
            <th className={NUM_TH}>{t('payroll.deductions')}</th>
            <th className={NUM_TH}>{t('payroll.tax')}</th>
            <th className={NUM_TH}>{t('payroll.net')}</th>
            {posted && <th className={TH}>{t('payroll.payslip')}</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {run.payslips.map((slip: Payslip) => (
            <tr key={slip.id}>
              <td className={TD}>
                <span className="font-medium">{slip.employee_name}</span>{' '}
                <span className="text-sm text-muted">{slip.employee_code}</span>
              </td>
              <td className={NUM}>
                {/* Pinned left to right, so Urdu and Arabic read 28.5 / 30, not 30 / 28.5. */}
                <span dir="ltr">
                  {days(slip.paid_days)} / {slip.month_days}
                </span>
                {Number(slip.unpaid_days) > 0 && (
                  <span className="block font-sans text-xs text-muted">
                    {t('payroll.unpaidDays', { days: days(slip.unpaid_days) })}
                  </span>
                )}
              </td>
              <td className={NUM}>{money(slip.gross)}</td>
              <td className={NUM}>{money(slip.deductions)}</td>
              <td className={NUM}>{money(slip.tax)}</td>
              <td className={`${NUM} font-medium`}>{money(slip.net)}</td>
              {posted && (
                <td className={TD}>
                  {/* Narrow, so a printing error wraps under the button instead of widening
                      the whole table. */}
                  <div className="max-w-56 space-y-2">
                    <PrintButton path={`/api/payroll/payslips/${slip.id}/pdf/`} />
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-line font-medium">
            <td className={TD}>{t('payroll.total', { people: run.people })}</td>
            <td className={NUM} />
            <td className={NUM}>{money(run.gross)}</td>
            <td className={NUM}>{money(run.deductions)}</td>
            <td className={NUM}>{money(run.tax)}</td>
            <td className={NUM}>{money(run.net)}</td>
            {posted && <td className={TD} />}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

// Paying a posted month

function TransferListButton({ id, month }: { id: number; month: string }) {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2">
      <Button
        variant="ghost"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setProblem('');
          void fetch(`${env.apiBaseUrl}/api/payroll/runs/${id}/transfer-list/`, {
            credentials: 'same-origin',
            headers: { 'X-Tenant': membership.tenant_id },
          })
            .then(async (response) => {
              if (!response.ok) {
                throw new ApiError(response.status, await errorBody(response));
              }
              const url = URL.createObjectURL(await response.blob());
              const link = document.createElement('a');
              link.href = url;
              link.download = `salaries-${month.slice(0, 7)}.csv`;
              link.click();
              window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
            })
            .catch((error: unknown) => {
              setProblem(error instanceof Error ? error.message : t('signIn.unavailable'));
            })
            .finally(() => setBusy(false));
        }}
      >
        {t('payroll.transferList')}
      </Button>
      {problem && <Alert tone="error">{problem}</Alert>}
    </div>
  );
}

function PayForm({ id }: { id: number }) {
  const { t } = useTranslation();
  const action = useTenantAction(KEYS);
  const accounts = useAccounts();
  const [paidOn, setPaidOn] = useState(new Date().toISOString().slice(0, 10));
  const [paidFrom, setPaidFrom] = useState('');
  const [reference, setReference] = useState('');
  const money = postable(accounts.data, 'asset');
  return (
    <form
      className="space-y-4 rounded-xl bg-surface p-4"
      onSubmit={(event) => {
        event.preventDefault();
        const body = { paid_on: paidOn, paid_from: Number(paidFrom), reference } as never;
        action.mutate(() =>
          unwrap(api.POST('/api/payroll/runs/{id}/pay/', { params: { path: { id } }, body })),
        );
      }}
    >
      <p className="font-medium">{t('payroll.payTitle')}</p>
      <Hint>{t('payroll.payHint')}</Hint>
      <div className="grid gap-4 md:grid-cols-3">
        <Field
          label={t('payroll.paidOn')}
          type="date"
          required
          value={paidOn}
          onChange={(e) => setPaidOn(e.target.value)}
        />
        <Select
          label={t('payroll.paidFrom')}
          required
          value={paidFrom}
          onChange={(e) => setPaidFrom(e.target.value)}
        >
          <option value="">-</option>
          {money.map((account) => (
            <option key={account.id} value={account.id}>
              {account.code} {account.name}
            </option>
          ))}
        </Select>
        <Field
          label={t('payroll.reference')}
          placeholder={t('payroll.referencePlaceholder')}
          maxLength={60}
          value={reference}
          onChange={(e) => setReference(e.target.value)}
        />
      </div>
      {accounts.isError && <Alert tone="error">{t('payroll.noAccounts')}</Alert>}
      {action.isError && (
        <Alert tone="error">{errorText(action.error, t('signIn.unavailable'))}</Alert>
      )}
      <Button type="submit" disabled={action.isPending}>
        {t('payroll.pay')}
      </Button>
    </form>
  );
}

function RunPanel({ id, onRemoved }: { id: number; onRemoved: () => void }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  // A key, not the text, so the message follows the language if it changes.
  const [notice, setNotice] = useState<'' | 'postedNow' | 'changed'>('');
  const run = useQuery({
    queryKey: [membership.tenant_id, 'payroll-run', id],
    queryFn: () => unwrap(api.GET('/api/payroll/runs/{id}/', { params: { path: { id } } })),
  });
  if (!run.data) {
    return null;
  }
  const detail = run.data;
  const draft = detail.status === 'draft';
  return (
    <Panel
      title={monthName(detail.month.slice(0, 7), i18n.resolvedLanguage)}
      action={
        <span className="text-sm text-muted">
          {draft ? t('payroll.draft') : `${t('payroll.posted')} · ${detail.number ?? ''}`}
          {detail.entry_number && ` · ${t('payroll.entry', { number: detail.entry_number })}`}
        </span>
      }
    >
      <div className="space-y-4">
        {draft && <Hint>{t('payroll.draftHint')}</Hint>}
        {detail.tax_table_name && (
          <p className="text-sm text-muted">
            {t('payroll.slabsUsed', { name: detail.tax_table_name })}
          </p>
        )}
        <Payslips run={detail} />
        {notice && (
          <Alert tone={notice === 'postedNow' ? 'success' : 'notice'}>
            {t(`payroll.${notice}`)}
          </Alert>
        )}
        {action.isError && (
          <Alert tone="error">{errorText(action.error, t('signIn.unavailable'))}</Alert>
        )}
        {detail.payment && (
          <Alert tone="success">
            {t('payroll.paid', {
              date: detail.payment.paid_on,
              account: detail.payment.paid_from_name,
              number: detail.payment.entry_number,
            })}
          </Alert>
        )}
        {!draft && (
          <div className="flex flex-wrap items-start gap-3">
            {can(membership, 'hr', 'view') && (
              <TransferListButton id={detail.id} month={detail.month} />
            )}
          </div>
        )}
        {!draft && !detail.payment && can(membership, 'payroll', 'post') && (
          <PayForm id={detail.id} />
        )}
        {draft && (
          <div className="flex flex-wrap gap-3">
            {can(membership, 'payroll', 'post') && (
              <Button
                disabled={action.isPending}
                onClick={() => {
                  setNotice('');
                  action.mutate(
                    () =>
                      unwrap(
                        api.POST('/api/payroll/runs/{id}/post/', { params: { path: { id } } }),
                      ),
                    {
                      onSuccess: (result) => {
                        const outcome = result as Posted;
                        setNotice(outcome.posted ? 'postedNow' : 'changed');
                      },
                    },
                  );
                }}
              >
                {t('payroll.post')}
              </Button>
            )}
            {can(membership, 'payroll', 'delete') && (
              <ConfirmButton
                onConfirm={() =>
                  action.mutate(
                    () =>
                      unwrap(api.DELETE('/api/payroll/runs/{id}/', { params: { path: { id } } })),
                    { onSuccess: onRemoved },
                  )
                }
              >
                {t('workspace.remove')}
              </ConfirmButton>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

// Pay from earlier in the tax year

function OpeningPayPanel({ month }: { month: string }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const save = useTenantAction(KEYS);
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const [employee, setEmployee] = useState('');
  const [taxable, setTaxable] = useState('');
  const [tax, setTax] = useState('');
  const [note, setNote] = useState('');
  const people = useQuery({
    queryKey: [membership.tenant_id, 'hr-employees', 'working'],
    queryFn: () =>
      allPages((cursor) =>
        unwrap(
          api.GET('/api/hr/employees/', {
            params: { query: { status: 'active', page_size: 200, cursor } as never },
          }),
        ),
      ),
  });
  const openings = useQuery({
    queryKey: [membership.tenant_id, 'payroll-opening-pay', month],
    queryFn: () => unwrap(api.GET('/api/payroll/opening-pay/', { params: { query: { month } } })),
  });
  return (
    <Panel title={t('payroll.openingTitle')}>
      <div className="space-y-4">
        <Hint>{t('payroll.openingHint')}</Hint>
        {openings.data?.length === 0 && <p className="text-muted">{t('payroll.openingNone')}</p>}
        {!!openings.data?.length && (
          <ul className="divide-y divide-line">
            {openings.data.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <span>
                  <span className="font-medium">{row.employee_name}</span>{' '}
                  <span className="text-sm text-muted">{row.employee_code}</span>
                  <span className="block text-sm text-muted">
                    {t('payroll.openingFigures', {
                      taxable: money(row.taxable),
                      tax: money(row.tax),
                    })}
                    {row.note && ` · ${row.note}`}
                  </span>
                </span>
                <ConfirmButton
                  onConfirm={() =>
                    save.mutate(() =>
                      unwrap(
                        api.DELETE('/api/payroll/opening-pay/{id}/', {
                          params: { path: { id: row.id } },
                        }),
                      ),
                    )
                  }
                >
                  {t('workspace.remove')}
                </ConfirmButton>
              </li>
            ))}
          </ul>
        )}
        <form
          className="grid gap-4 md:grid-cols-2 md:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            const body = { employee: Number(employee), month, taxable, tax, note } as never;
            save.mutate(() => unwrap(api.POST('/api/payroll/opening-pay/', { body })), {
              onSuccess: () => {
                setEmployee('');
                setTaxable('');
                setTax('');
                setNote('');
              },
            });
          }}
        >
          <Select
            label={t('payroll.employee')}
            required
            value={employee}
            onChange={(e) => setEmployee(e.target.value)}
          >
            <option value="">-</option>
            {people.data?.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name} ({person.code})
              </option>
            ))}
          </Select>
          <Field
            label={t('payroll.openingNote')}
            placeholder={t('payroll.openingNotePlaceholder')}
            maxLength={255}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <Field
            label={t('payroll.openingTaxable')}
            type="number"
            required
            min="0"
            step="0.01"
            inputMode="decimal"
            placeholder="290000"
            value={taxable}
            onChange={(e) => setTaxable(e.target.value)}
          />
          <Field
            label={t('payroll.openingTax')}
            type="number"
            required
            min="0"
            step="0.01"
            inputMode="decimal"
            placeholder="0"
            value={tax}
            onChange={(e) => setTax(e.target.value)}
          />
          <div>
            <Button type="submit" disabled={save.isPending}>
              {t('payroll.openingSave')}
            </Button>
          </div>
        </form>
        {save.isError && (
          <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
        )}
      </div>
    </Panel>
  );
}

export function PayrollPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const save = useTenantAction(KEYS);
  const [month, setMonth] = useState(thisMonth());
  const [open, setOpen] = useState<number | null>(null);
  const runs = useQuery({
    queryKey: [membership.tenant_id, 'payroll-runs'],
    queryFn: () => unwrap(api.GET('/api/payroll/runs/')),
  });
  const tables = useQuery({
    queryKey: [membership.tenant_id, 'payroll-tax-tables'],
    queryFn: () => unwrap(api.GET('/api/payroll/tax-tables/')),
  });
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  return (
    <>
      <PageTitle title={t('payroll.title')} subtitle={t('payroll.body')} />
      {can(membership, 'payroll', 'create') && (
        <Panel title={t('payroll.workOutTitle')}>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              const body = { month: `${month}-01` };
              save.mutate(() => unwrap(api.POST('/api/payroll/runs/', { body })), {
                onSuccess: (made) => setOpen((made as RunDetail).id),
              });
            }}
          >
            <Field
              label={t('payroll.month')}
              type="month"
              required
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
            <Button type="submit" disabled={save.isPending || !month}>
              {t('payroll.workOut')}
            </Button>
          </form>
          <div className="mt-3">
            <Hint>{t('payroll.workOutHint')}</Hint>
          </div>
          {save.isError && (
            <div className="mt-4 space-y-2">
              <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
              {tables.data?.length === 0 && (
                <Link
                  to={`/app/${membership.tenant_slug}/hr/tax-slabs`}
                  className="inline-flex min-h-11 items-center font-medium underline underline-offset-4"
                >
                  {t('payroll.openSlabs')}
                </Link>
              )}
            </div>
          )}
        </Panel>
      )}
      {can(membership, 'payroll', 'create') && can(membership, 'hr', 'view') && month && (
        <OpeningPayPanel month={`${month}-01`} />
      )}
      {open !== null && <RunPanel key={open} id={open} onRemoved={() => setOpen(null)} />}
      <Panel title={t('payroll.runs')}>
        {runs.data?.length === 0 && <p className="text-muted">{t('payroll.noRuns')}</p>}
        {!!runs.data?.length && (
          <div className="overflow-x-auto">
            <table className={TABLE}>
              <thead>
                <tr className="border-b border-line">
                  <th className={TH}>{t('payroll.month')}</th>
                  <th className={TH}>{t('payroll.status')}</th>
                  <th className={NUM_TH}>{t('payroll.people')}</th>
                  <th className={NUM_TH}>{t('payroll.tax')}</th>
                  <th className={NUM_TH}>{t('payroll.net')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {runs.data.map((run: Run) => (
                  <tr key={run.id}>
                    <td className={TD}>
                      <button
                        type="button"
                        className="min-h-11 text-start font-medium underline underline-offset-4"
                        onClick={() => setOpen(run.id)}
                      >
                        {monthName(run.month.slice(0, 7), i18n.resolvedLanguage)}
                      </button>
                    </td>
                    <td className={TD}>
                      {run.status === 'posted'
                        ? `${run.payment ? t('payroll.paidStatus') : t('payroll.posted')} · ${run.number ?? ''}`
                        : t('payroll.draft')}
                    </td>
                    <td className={NUM}>{run.people}</td>
                    <td className={NUM}>{money(run.tax)}</td>
                    <td className={NUM}>{money(run.net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

// Tax slabs

type SlabRow = { key: number; over: string; fixed: string; rate: string };

function TableForm({ table, onDone }: { table?: TaxTable; onDone: () => void }) {
  const { t } = useTranslation();
  const save = useTenantAction(KEYS);
  const [name, setName] = useState(table?.name ?? '');
  const [startsOn, setStartsOn] = useState(table?.starts_on ?? '');
  const [endsOn, setEndsOn] = useState(table?.ends_on ?? '');
  const [source, setSource] = useState(table?.source ?? '');
  const [rows, setRows] = useState<SlabRow[]>(
    table?.slabs.map((slab, key) => ({ key, ...slab })) ?? [
      { key: 0, over: '0', fixed: '0', rate: '0' },
    ],
  );
  const update = (key: number, patch: Partial<SlabRow>) =>
    setRows(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        const body = {
          country: table?.country ?? 'PK',
          name,
          starts_on: startsOn,
          ends_on: endsOn,
          source,
          slabs: rows.map(({ over, fixed, rate }) => ({ over, fixed, rate })),
        } as never;
        save.mutate(
          () =>
            table
              ? unwrap(
                  api.PUT('/api/payroll/tax-tables/{id}/', {
                    params: { path: { id: table.id } },
                    body,
                  }),
                )
              : unwrap(api.POST('/api/payroll/tax-tables/', { body })),
          { onSuccess: onDone },
        );
      }}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Field
          label={t('payroll.tableName')}
          placeholder={t('payroll.tableNamePlaceholder')}
          required
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Field
          label={t('payroll.startsOn')}
          type="date"
          required
          value={startsOn}
          onChange={(e) => setStartsOn(e.target.value)}
        />
        <Field
          label={t('payroll.endsOn')}
          type="date"
          required
          value={endsOn}
          onChange={(e) => setEndsOn(e.target.value)}
        />
      </div>
      <Field
        label={t('payroll.source')}
        placeholder={t('payroll.sourcePlaceholder')}
        hint={t('payroll.sourceHint')}
        required
        maxLength={500}
        value={source}
        onChange={(e) => setSource(e.target.value)}
      />
      <div className="space-y-3">
        <p className="label">{t('payroll.slabs')}</p>
        <Hint>{t('payroll.slabHint')}</Hint>
        {rows.map((row) => (
          <div key={row.key} className="grid gap-3 sm:grid-cols-[1fr_1fr_8rem_auto] sm:items-end">
            <Field
              label={t('payroll.over')}
              type="number"
              required
              min="0"
              step="0.01"
              inputMode="decimal"
              value={row.over}
              onChange={(e) => update(row.key, { over: e.target.value })}
            />
            <Field
              label={t('payroll.fixed')}
              type="number"
              required
              min="0"
              step="0.01"
              inputMode="decimal"
              value={row.fixed}
              onChange={(e) => update(row.key, { fixed: e.target.value })}
            />
            <Field
              label={t('payroll.rate')}
              type="number"
              required
              min="0"
              max="100"
              step="0.01"
              inputMode="decimal"
              value={row.rate}
              onChange={(e) => update(row.key, { rate: e.target.value })}
            />
            <Button
              variant="ghost"
              disabled={rows.length === 1}
              onClick={() => setRows(rows.filter((item) => item.key !== row.key))}
            >
              {t('workspace.remove')}
            </Button>
          </div>
        ))}
        <Button
          variant="ghost"
          disabled={rows.length >= 20}
          onClick={() =>
            setRows([
              ...rows,
              {
                key: Math.max(0, ...rows.map((row) => row.key)) + 1,
                over: '',
                fixed: '',
                rate: '',
              },
            ])
          }
        >
          {t('payroll.addSlab')}
        </Button>
      </div>
      {save.isError && <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={save.isPending}>
          {t('payroll.saveTable')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('workspace.cancel')}
        </Button>
      </div>
    </form>
  );
}

function TableCard({ table }: { table: TaxTable }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const remove = useTenantAction(KEYS);
  const [editing, setEditing] = useState(false);
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  if (editing) {
    return (
      <Panel title={table.name}>
        <TableForm table={table} onDone={() => setEditing(false)} />
      </Panel>
    );
  }
  return (
    <Panel
      title={table.name}
      action={
        <span className="text-sm text-muted tabular-nums">
          {table.starts_on} – {table.ends_on}
        </span>
      }
    >
      <div className="space-y-4">
        <div className="overflow-x-auto">
          <table className={TABLE}>
            <thead>
              <tr className="border-b border-line">
                <th className={NUM_TH}>{t('payroll.over')}</th>
                <th className={NUM_TH}>{t('payroll.fixed')}</th>
                <th className={NUM_TH}>{t('payroll.rate')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {table.slabs.map((slab) => (
                <tr key={slab.over}>
                  <td className={NUM}>{money(slab.over)}</td>
                  <td className={NUM}>{money(slab.fixed)}</td>
                  <td className={NUM}>{Number(slab.rate)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm text-muted">{table.source}</p>
        {remove.isError && (
          <Alert tone="error">{errorText(remove.error, t('signIn.unavailable'))}</Alert>
        )}
        <div className="flex flex-wrap gap-3">
          {can(membership, 'payroll', 'update') && (
            <Button variant="ghost" onClick={() => setEditing(true)}>
              {t('payroll.editTable')}
            </Button>
          )}
          {can(membership, 'payroll', 'delete') && (
            <ConfirmButton
              onConfirm={() =>
                remove.mutate(() =>
                  unwrap(
                    api.DELETE('/api/payroll/tax-tables/{id}/', {
                      params: { path: { id: table.id } },
                    }),
                  ),
                )
              }
            >
              {t('workspace.remove')}
            </ConfirmButton>
          )}
        </div>
      </div>
    </Panel>
  );
}

export function TaxSlabsPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const fill = useTenantAction(KEYS);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState<number | null>(null);
  const tables = useQuery({
    queryKey: [membership.tenant_id, 'payroll-tax-tables'],
    queryFn: () => unwrap(api.GET('/api/payroll/tax-tables/')),
  });
  return (
    <>
      <PageTitle title={t('payroll.slabsTitle')} subtitle={t('payroll.slabsBody')} />
      {can(membership, 'payroll', 'create') && (
        <Panel title={t('payroll.addTables')}>
          <div className="space-y-4">
            <Hint>{t('payroll.fillHint')}</Hint>
            <div className="flex flex-wrap gap-3">
              <Button
                disabled={fill.isPending}
                onClick={() =>
                  fill.mutate(() => unwrap(api.POST('/api/payroll/tax-tables/fill/')), {
                    onSuccess: (result) => setAdded((result as { added: number }).added),
                  })
                }
              >
                {t('payroll.fill')}
              </Button>
              <Button variant="ghost" onClick={() => setAdding(true)}>
                {t('payroll.newTable')}
              </Button>
            </div>
            {added !== null && <Alert tone="success">{t('payroll.filled', { added })}</Alert>}
            {fill.isError && (
              <Alert tone="error">{errorText(fill.error, t('signIn.unavailable'))}</Alert>
            )}
            {adding && <TableForm onDone={() => setAdding(false)} />}
          </div>
        </Panel>
      )}
      {tables.data?.length === 0 && (
        <Panel title={t('payroll.slabsTitle')}>
          <p className="text-muted">{t('payroll.noTables')}</p>
        </Panel>
      )}
      {tables.data?.map((table) => (
        <TableCard key={table.id} table={table} />
      ))}
    </>
  );
}
