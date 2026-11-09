import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ConfirmButton } from '../../components/ConfirmButton';
import { Alert, Button, Field, Hint, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { ApiError, errorBody, unwrap } from '../../lib/api/errors';
import { allPages } from '../../lib/api/pages';
import type { components } from '../../lib/api/schema';
import { can } from '../../lib/api/types';
import { today } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { env } from '../../lib/env';
import { GRATUITY_COUNTRIES, PROVINCES } from '../hr/provinces';
import { postable, useAccounts } from '../purchasing/pages';
import { PrintButton } from '../sales/ledgers';
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
  const [paidOn, setPaidOn] = useState(today);
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

function statusLabel(run: Run, t: (key: string) => string): string {
  if (run.status === 'draft') {
    return t('payroll.draft');
  }
  const word =
    run.status === 'reversed'
      ? t('payroll.reversedStatus')
      : run.payment
        ? t('payroll.paidStatus')
        : t('payroll.posted');
  return `${word} · ${run.number ?? ''}`;
}

function UndoForm({ id }: { id: number }) {
  const { t } = useTranslation();
  const action = useTenantAction(KEYS);
  const [reason, setReason] = useState('');
  return (
    <div className="space-y-4 rounded-xl border border-line p-4">
      <p className="font-medium">{t('payroll.undoTitle')}</p>
      <Hint>{t('payroll.undoHint')}</Hint>
      <Field
        label={t('payroll.undoReason')}
        placeholder={t('payroll.undoReasonPlaceholder')}
        maxLength={255}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      {action.isError && (
        <Alert tone="error">{errorText(action.error, t('signIn.unavailable'))}</Alert>
      )}
      <ConfirmButton
        message={t('payroll.undoConfirm')}
        disabled={action.isPending}
        onConfirm={() =>
          action.mutate(() =>
            unwrap(
              api.POST('/api/payroll/runs/{id}/reverse/', {
                params: { path: { id } },
                body: { reason },
              }),
            ),
          )
        }
      >
        {t('payroll.undo')}
      </ConfirmButton>
    </div>
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
          {statusLabel(detail, t)}
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
        {Number(detail.gratuity_change) !== 0 && (
          <p className="text-sm text-muted">
            {t('payroll.gratuityChange', {
              amount: formatMoney(detail.gratuity_change, i18n.resolvedLanguage),
            })}
          </p>
        )}
        {Number(detail.employer_contributions) > 0 && (
          <p className="text-sm text-muted">
            {t('payroll.employerShare', {
              amount: formatMoney(detail.employer_contributions, i18n.resolvedLanguage),
            })}
          </p>
        )}
        {notice && !(notice === 'postedNow' && detail.status === 'reversed') && (
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
        {detail.status === 'reversed' && (
          <Alert tone="notice">
            {t('payroll.reversedNote', { number: detail.reversal_number })}
            {detail.reversal_reason && ` ${detail.reversal_reason}`}
          </Alert>
        )}
        {detail.status === 'posted' && (
          <div className="flex flex-wrap items-start gap-3">
            {can(membership, 'hr', 'view') && (
              <TransferListButton id={detail.id} month={detail.month} />
            )}
          </div>
        )}
        {detail.status === 'posted' && !detail.payment && can(membership, 'payroll', 'post') && (
          <>
            <PayForm id={detail.id} />
            <UndoForm id={detail.id} />
          </>
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
  // Pay before Karobar feeds Pakistan's salary tax; the Gulf has none.
  const taxed = (useCountry().data?.holiday_country ?? 'PK') === 'PK';
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
      {taxed && can(membership, 'payroll', 'create') && can(membership, 'hr', 'view') && month && (
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
                    <td className={TD}>{statusLabel(run, t)}</td>
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

// EOBI and social security

type Wage = components['schemas']['MinimumWage'];
type Rate = components['schemas']['ContributionRate'];

const CONTRIBUTION_KEYS = ['payroll-minimum-wages', 'payroll-contribution-rates'];

function provinceName(code: string | undefined, t: (key: string) => string): string {
  return code ? t(`hr.provinces.${code}`) : t('payroll.everywhere');
}

function SourceField({
  value,
  onChange,
  gulf = false,
}: {
  value: string;
  onChange: (value: string) => void;
  gulf?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Field
      label={t('payroll.figureSource')}
      placeholder={t(
        gulf ? 'payroll.gulfSourcePlaceholder' : 'payroll.contributionSourcePlaceholder',
      )}
      hint={t('payroll.sourceHint')}
      required
      maxLength={500}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function WageForm({ wage, onDone }: { wage?: Wage; onDone: () => void }) {
  const { t } = useTranslation();
  const save = useTenantAction(CONTRIBUTION_KEYS);
  const empty = {
    province: wage?.province ?? '',
    starts_on: wage?.starts_on ?? '',
    amount: wage?.amount ?? '',
    source: wage?.source ?? '',
  };
  const [form, setForm] = useState(empty);
  const set = (patch: Partial<typeof empty>) => setForm({ ...form, ...patch });
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        const body = form as never;
        save.mutate(
          () =>
            wage
              ? unwrap(
                  api.PUT('/api/payroll/minimum-wages/{id}/', {
                    params: { path: { id: wage.id } },
                    body,
                  }),
                )
              : unwrap(api.POST('/api/payroll/minimum-wages/', { body })),
          {
            onSuccess: () => {
              setForm(empty);
              onDone();
            },
          },
        );
      }}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Select
          label={t('payroll.province')}
          required
          value={form.province}
          onChange={(e) => set({ province: e.target.value })}
        >
          <option value="">-</option>
          {PROVINCES.map((code) => (
            <option key={code} value={code}>
              {t(`hr.provinces.${code}`)}
            </option>
          ))}
        </Select>
        <Field
          label={t('payroll.from')}
          type="date"
          required
          value={form.starts_on}
          onChange={(e) => set({ starts_on: e.target.value })}
        />
        <Field
          label={t('payroll.monthlyWage')}
          type="number"
          required
          min="0.01"
          step="0.01"
          inputMode="decimal"
          placeholder="40000"
          value={form.amount}
          onChange={(e) => set({ amount: e.target.value })}
        />
      </div>
      <SourceField value={form.source} onChange={(source) => set({ source })} />
      {save.isError && <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={save.isPending}>
          {wage ? t('hr.save') : t('payroll.addWage')}
        </Button>
        {wage && (
          <Button variant="ghost" onClick={onDone}>
            {t('workspace.cancel')}
          </Button>
        )}
      </div>
    </form>
  );
}

const SCHEMES: Record<string, Rate['scheme'][]> = {
  PK: ['eobi', 'social_security'],
  SA: ['gosi_annuities', 'gosi_saned', 'gosi_hazards'],
  AE: ['gpssa'],
};

type Basis = 'wage' | 'pay' | 'insurable';

function basisOf(rate: Rate): Basis {
  if (rate.on_minimum_wage) {
    return 'wage';
  }
  return rate.on_insurable ? 'insurable' : 'pay';
}

function RateForm({ rate, onDone }: { rate?: Rate; onDone: () => void }) {
  // Wait for the business's country, so the form starts with that country's schemes.
  const country = useCountry().data?.holiday_country;
  if (!country) {
    return null;
  }
  return <CountryRateForm country={country} rate={rate} onDone={onDone} />;
}

function CountryRateForm({
  country,
  rate,
  onDone,
}: {
  country: string;
  rate?: Rate | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const save = useTenantAction(CONTRIBUTION_KEYS);
  const schemes = SCHEMES[country] ?? SCHEMES.PK ?? [];
  const pakistan = country === 'PK';
  const empty = {
    scheme: rate?.scheme ?? schemes[0] ?? 'eobi',
    province: rate?.province ?? '',
    starts_on: rate?.starts_on ?? '',
    employer_percent: rate?.employer_percent ?? '',
    employee_percent: rate?.employee_percent ?? '',
    basis: rate ? basisOf(rate) : pakistan ? 'wage' : 'insurable',
    wage_cap: rate?.wage_cap ?? '',
    wage_floor: rate?.wage_floor ?? '',
    applies_to: rate?.applies_to ?? 'all',
    first_insured_from: rate?.first_insured_from ?? '',
    source: rate?.source ?? '',
  };
  const [form, setForm] = useState<typeof empty & { basis: Basis }>(
    empty as typeof empty & { basis: Basis },
  );
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });
  const onWage = form.basis === 'wage';
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        const { basis, ...rest } = form;
        const body = {
          ...rest,
          on_minimum_wage: basis === 'wage',
          on_insurable: basis === 'insurable',
          wage_cap: onWage || !form.wage_cap ? null : form.wage_cap,
          wage_floor: onWage || !form.wage_floor ? null : form.wage_floor,
          first_insured_from: form.first_insured_from || null,
        } as never;
        save.mutate(
          () =>
            rate
              ? unwrap(
                  api.PUT('/api/payroll/contribution-rates/{id}/', {
                    params: { path: { id: rate.id } },
                    body,
                  }),
                )
              : unwrap(api.POST('/api/payroll/contribution-rates/', { body })),
          {
            onSuccess: () => {
              setForm(empty);
              onDone();
            },
          },
        );
      }}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Select
          label={t('payroll.scheme')}
          value={form.scheme}
          onChange={(e) => {
            const scheme = e.target.value as Rate['scheme'];
            set({ scheme, ...(pakistan ? { basis: scheme === 'eobi' ? 'wage' : 'pay' } : {}) });
          }}
        >
          {schemes.map((scheme) => (
            <option key={scheme} value={scheme}>
              {t(`payroll.schemes.${scheme}`)}
            </option>
          ))}
        </Select>
        {pakistan ? (
          <Select
            label={t('payroll.province')}
            value={form.province}
            onChange={(e) => set({ province: e.target.value as NonNullable<Rate['province']> })}
          >
            <option value="">{t('payroll.everywhere')}</option>
            {PROVINCES.map((code) => (
              <option key={code} value={code}>
                {t(`hr.provinces.${code}`)}
              </option>
            ))}
          </Select>
        ) : (
          <Select
            label={t('payroll.appliesTo')}
            value={form.applies_to}
            onChange={(e) => set({ applies_to: e.target.value as NonNullable<Rate['applies_to']> })}
          >
            <option value="all">{t('payroll.appliesAll')}</option>
            <option value="nationals">{t('payroll.appliesNationals')}</option>
            <option value="others">{t('payroll.appliesOthers')}</option>
          </Select>
        )}
        <Field
          label={t('payroll.from')}
          type="date"
          required
          value={form.starts_on}
          onChange={(e) => set({ starts_on: e.target.value })}
        />
        <Field
          label={t('payroll.employerPercent')}
          type="number"
          required
          min="0"
          max="100"
          step="0.01"
          inputMode="decimal"
          value={form.employer_percent}
          onChange={(e) => set({ employer_percent: e.target.value })}
        />
        <Field
          label={t('payroll.employeePercent')}
          type="number"
          required
          min="0"
          max="100"
          step="0.01"
          inputMode="decimal"
          value={form.employee_percent}
          onChange={(e) => set({ employee_percent: e.target.value })}
        />
        <Select
          label={t('payroll.workedOn')}
          value={form.basis}
          onChange={(e) => set({ basis: e.target.value as Basis })}
        >
          {pakistan && <option value="wage">{t('payroll.onMinimumWage')}</option>}
          <option value="pay">{t('payroll.onPay')}</option>
          {!pakistan && <option value="insurable">{t('payroll.onInsurable')}</option>}
        </Select>
        {!onWage && (
          <>
            <Field
              label={t('payroll.wageCap')}
              hint={t('payroll.wageCapHint')}
              type="number"
              min="0.01"
              step="0.01"
              inputMode="decimal"
              value={form.wage_cap}
              onChange={(e) => set({ wage_cap: e.target.value })}
            />
            <Field
              label={t('payroll.wageFloor')}
              hint={t('payroll.wageFloorHint')}
              type="number"
              min="0.01"
              step="0.01"
              inputMode="decimal"
              value={form.wage_floor}
              onChange={(e) => set({ wage_floor: e.target.value })}
            />
          </>
        )}
        {!pakistan && (
          <Field
            label={t('payroll.firstInsuredFrom')}
            hint={t('payroll.firstInsuredFromHint')}
            type="date"
            value={form.first_insured_from}
            onChange={(e) => set({ first_insured_from: e.target.value })}
          />
        )}
      </div>
      <SourceField value={form.source} onChange={(source) => set({ source })} gulf={!pakistan} />
      {save.isError && <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={save.isPending}>
          {rate ? t('hr.save') : t('payroll.addRate')}
        </Button>
        {rate && (
          <Button variant="ghost" onClick={onDone}>
            {t('workspace.cancel')}
          </Button>
        )}
      </div>
    </form>
  );
}

function RowActions({ onEdit, onRemove }: { onEdit: () => void; onRemove: () => void }) {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  return (
    <div className="flex flex-wrap gap-2">
      {can(membership, 'payroll', 'update') && (
        <Button variant="ghost" onClick={onEdit}>
          {t('payroll.editTable')}
        </Button>
      )}
      {can(membership, 'payroll', 'delete') && (
        <ConfirmButton onConfirm={onRemove}>{t('workspace.remove')}</ConfirmButton>
      )}
    </div>
  );
}

function MinimumWagesPanel() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const remove = useTenantAction(CONTRIBUTION_KEYS);
  const [editing, setEditing] = useState<number | null>(null);
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const wages = useQuery({
    queryKey: [membership.tenant_id, 'payroll-minimum-wages'],
    queryFn: () => unwrap(api.GET('/api/payroll/minimum-wages/')),
  });
  return (
    <Panel title={t('payroll.minimumWages')}>
      <div className="space-y-4">
        {wages.data?.length === 0 && <p className="text-muted">{t('payroll.noWages')}</p>}
        {!!wages.data?.length && (
          <ul className="divide-y divide-line">
            {wages.data.map((wage: Wage) =>
              editing === wage.id ? (
                <li key={wage.id} className="py-3">
                  <WageForm wage={wage} onDone={() => setEditing(null)} />
                </li>
              ) : (
                <li key={wage.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{provinceName(wage.province, t)}</span>{' '}
                    <span className="tabular-nums">{money(wage.amount)}</span>
                    <span className="block text-sm text-muted">
                      {t('payroll.from')} <span className="tabular-nums">{wage.starts_on}</span>
                      {' · '}
                      {wage.source}
                    </span>
                  </span>
                  <RowActions
                    onEdit={() => setEditing(wage.id)}
                    onRemove={() =>
                      remove.mutate(() =>
                        unwrap(
                          api.DELETE('/api/payroll/minimum-wages/{id}/', {
                            params: { path: { id: wage.id } },
                          }),
                        ),
                      )
                    }
                  />
                </li>
              ),
            )}
          </ul>
        )}
        {remove.isError && (
          <Alert tone="error">{errorText(remove.error, t('signIn.unavailable'))}</Alert>
        )}
        {can(membership, 'payroll', 'create') && <WageForm onDone={() => undefined} />}
      </div>
    </Panel>
  );
}

function RatesPanel() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const remove = useTenantAction(CONTRIBUTION_KEYS);
  const [editing, setEditing] = useState<number | null>(null);
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const pakistan = (useCountry().data?.holiday_country ?? 'PK') === 'PK';
  const rates = useQuery({
    queryKey: [membership.tenant_id, 'payroll-contribution-rates'],
    queryFn: () => unwrap(api.GET('/api/payroll/contribution-rates/')),
  });
  return (
    <Panel title={t('payroll.ratesTitle')}>
      <div className="space-y-4">
        {!pakistan && <Hint>{t('payroll.gulfRatesHint')}</Hint>}
        {rates.data?.length === 0 && (
          <p className="text-muted">{t(pakistan ? 'payroll.noRates' : 'payroll.noGulfRates')}</p>
        )}
        {!!rates.data?.length && (
          <ul className="divide-y divide-line">
            {rates.data.map((rate: Rate) =>
              editing === rate.id ? (
                <li key={rate.id} className="py-3">
                  <RateForm rate={rate} onDone={() => setEditing(null)} />
                </li>
              ) : (
                <li key={rate.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">
                      {t(`payroll.schemes.${rate.scheme}`)}
                      {rate.province ? ` · ${provinceName(rate.province, t)}` : ''}
                    </span>
                    <span className="block">
                      {t('payroll.rateFigures', {
                        employer: Number(rate.employer_percent),
                        employee: Number(rate.employee_percent),
                      })}{' '}
                      {t(`payroll.basisShort.${basisOf(rate)}`)}
                      {rate.wage_cap && ` ${t('payroll.upTo', { cap: money(rate.wage_cap) })}`}
                      {rate.wage_floor &&
                        ` ${t('payroll.atLeast', { floor: money(rate.wage_floor) })}`}
                    </span>
                    {(rate.applies_to !== 'all' || rate.first_insured_from) && (
                      <span className="block text-sm">
                        {rate.applies_to === 'nationals' && t('payroll.appliesNationals')}
                        {rate.applies_to === 'others' && t('payroll.appliesOthers')}
                        {rate.first_insured_from &&
                          ` ${t('payroll.insuredFromShort', { date: rate.first_insured_from })}`}
                      </span>
                    )}
                    <span className="block text-sm text-muted">
                      {t('payroll.from')} <span className="tabular-nums">{rate.starts_on}</span>
                      {' · '}
                      {rate.source}
                    </span>
                  </span>
                  <RowActions
                    onEdit={() => setEditing(rate.id)}
                    onRemove={() =>
                      remove.mutate(() =>
                        unwrap(
                          api.DELETE('/api/payroll/contribution-rates/{id}/', {
                            params: { path: { id: rate.id } },
                          }),
                        ),
                      )
                    }
                  />
                </li>
              ),
            )}
          </ul>
        )}
        {remove.isError && (
          <Alert tone="error">{errorText(remove.error, t('signIn.unavailable'))}</Alert>
        )}
        {can(membership, 'payroll', 'create') && <RateForm onDone={() => undefined} />}
      </div>
    </Panel>
  );
}

export function ContributionsPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const pakistan = (useCountry().data?.holiday_country ?? 'PK') === 'PK';
  const fill = useTenantAction(CONTRIBUTION_KEYS);
  const [added, setAdded] = useState<number | null>(null);
  return (
    <>
      <PageTitle
        title={t('payroll.contributionsTitle')}
        subtitle={t('payroll.contributionsBody')}
      />
      {pakistan && can(membership, 'payroll', 'create') && (
        <Panel title={t('payroll.addFigures')}>
          <div className="space-y-4">
            <Hint>{t('payroll.contributionsFillHint')}</Hint>
            <Button
              disabled={fill.isPending}
              onClick={() =>
                fill.mutate(() => unwrap(api.POST('/api/payroll/contributions/fill/')), {
                  onSuccess: (result) => setAdded((result as { added: number }).added),
                })
              }
            >
              {t('payroll.contributionsFill')}
            </Button>
            {added !== null && (
              <Alert tone="success">{t('payroll.filledFigures', { added })}</Alert>
            )}
            {fill.isError && (
              <Alert tone="error">{errorText(fill.error, t('signIn.unavailable'))}</Alert>
            )}
          </div>
        </Panel>
      )}
      <RatesPanel />
      {pakistan && <MinimumWagesPanel />}
    </>
  );
}

// End-of-service gratuity

type GratuityRule = components['schemas']['GratuityRule'];
type Band = { key: number; years: string; share: string; after: boolean };

const GRATUITY_KEYS = ['payroll-gratuity-rules', 'payroll-gratuity'];

function useCountry() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'hr-settings'],
    queryFn: () => unwrap(api.GET('/api/hr/settings/')),
  });
}

export function GratuityPanel({ employee }: { employee: number }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const pay = useTenantAction([...GRATUITY_KEYS, 'hr-employees']);
  const accounts = useAccounts();
  const settings = useCountry();
  const [reason, setReason] = useState<'ended' | 'resigned'>('ended');
  const [paidOn, setPaidOn] = useState(today);
  const [paidFrom, setPaidFrom] = useState('');
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const gulf = GRATUITY_COUNTRIES.includes(settings.data?.holiday_country ?? '');
  const [dateTouched, setDateTouched] = useState(false);
  const quote = useQuery({
    queryKey: [membership.tenant_id, 'payroll-gratuity', employee],
    queryFn: () =>
      unwrap(
        api.GET('/api/payroll/employees/{id}/gratuity/', { params: { path: { id: employee } } }),
      ),
    enabled: gulf,
  });
  if (!gulf || !quote.data) {
    return null;
  }
  const data = quote.data;
  // It can't be paid before the person left, so start the date no earlier than that.
  const leftOn = data.left_on ?? '';
  const shownPaidOn = !dateTouched && leftOn > paidOn ? leftOn : paidOn;
  return (
    <Panel title={t('payroll.gratuityTitle')}>
      <div className="space-y-4">
        <p>{t('payroll.gratuityAccrued', { amount: money(data.accrued) })}</p>
        {data.payout && (
          <Alert tone="success">
            {t('payroll.gratuityPaid', {
              amount: money(data.payout.amount),
              date: data.payout.paid_on,
              account: data.payout.paid_from_name,
              number: data.payout.entry_number,
            })}
          </Alert>
        )}
        {!data.payout && data.if_ended !== null && (
          <div className="space-y-4 rounded-xl bg-surface p-4">
            <p className="font-medium">{t('payroll.gratuityDue')}</p>
            <ul className="space-y-1">
              <li>{t('payroll.gratuityIfEnded', { amount: money(data.if_ended) })}</li>
              <li>{t('payroll.gratuityIfResigned', { amount: money(data.if_resigned ?? '0') })}</li>
            </ul>
            <Hint>
              {t('payroll.gratuityDueHint', { days: data.service_days })}
              {settings.data?.holiday_country === 'AE' && ` ${t('payroll.gratuityDueUae')}`}
            </Hint>
            {can(membership, 'payroll', 'post') && (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  const body = {
                    reason,
                    paid_on: shownPaidOn,
                    paid_from: Number(paidFrom),
                  } as never;
                  pay.mutate(() =>
                    unwrap(
                      api.POST('/api/payroll/employees/{id}/gratuity/pay/', {
                        params: { path: { id: employee } },
                        body,
                      }),
                    ),
                  );
                }}
              >
                <div className="grid gap-4 md:grid-cols-3">
                  <Select
                    label={t('payroll.gratuityReason')}
                    value={reason}
                    onChange={(e) => setReason(e.target.value as 'ended' | 'resigned')}
                  >
                    <option value="ended">{t('payroll.reasonEnded')}</option>
                    <option value="resigned">{t('payroll.reasonResigned')}</option>
                  </Select>
                  <Field
                    label={t('payroll.paidOn')}
                    type="date"
                    required
                    value={shownPaidOn}
                    onChange={(e) => {
                      setDateTouched(true);
                      setPaidOn(e.target.value);
                    }}
                  />
                  <Select
                    label={t('payroll.paidFrom')}
                    required
                    value={paidFrom}
                    onChange={(e) => setPaidFrom(e.target.value)}
                  >
                    <option value="">-</option>
                    {postable(accounts.data, 'asset').map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.code} {account.name}
                      </option>
                    ))}
                  </Select>
                </div>
                {accounts.isError && <Alert tone="error">{t('payroll.noAccounts')}</Alert>}
                {pay.isError && (
                  <Alert tone="error">{errorText(pay.error, t('signIn.unavailable'))}</Alert>
                )}
                <Button type="submit" disabled={pay.isPending}>
                  {t('payroll.gratuityPay')}
                </Button>
              </form>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

function RuleForm({ rule, onDone }: { rule?: GratuityRule; onDone: () => void }) {
  const { t } = useTranslation();
  const save = useTenantAction(GRATUITY_KEYS);
  const settings = useCountry();
  const [form, setForm] = useState({
    country: rule?.country ?? (settings.data?.holiday_country === 'SA' ? 'SA' : 'AE'),
    starts_on: rule?.starts_on ?? '',
    first_years: rule?.first_years ?? '5',
    first_days: rule?.first_days ?? '',
    later_days: rule?.later_days ?? '',
    month_days: rule?.month_days ?? '30',
    min_years: rule?.min_years ?? '0',
    cap_months: rule?.cap_months ?? '',
    wage: rule?.wage ?? 'basic',
    excludes_nationals: rule?.excludes_nationals ?? false,
    excludes_unpaid_days: rule?.excludes_unpaid_days ?? false,
    source: rule?.source ?? '',
  });
  const [bands, setBands] = useState<Band[]>(
    (rule?.resignation ?? []).map((band, key) => ({
      key,
      years: band.years,
      share: band.share,
      after: band.after,
    })),
  );
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });
  const setBand = (key: number, patch: Partial<Band>) =>
    setBands(bands.map((band) => (band.key === key ? { ...band, ...patch } : band)));
  const number = (
    key: 'first_years' | 'first_days' | 'later_days' | 'month_days' | 'min_years',
  ) => (
    <Field
      label={t(`payroll.rule.${key}`)}
      type="number"
      required
      min="0"
      step="0.01"
      inputMode="decimal"
      value={form[key]}
      onChange={(e) => set({ [key]: e.target.value })}
    />
  );
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        const body = {
          ...form,
          cap_months: form.cap_months || null,
          resignation: bands.map(({ years, share, after }) => ({ years, share, after })),
        } as never;
        save.mutate(
          () =>
            rule
              ? unwrap(
                  api.PUT('/api/payroll/gratuity-rules/{id}/', {
                    params: { path: { id: rule.id } },
                    body,
                  }),
                )
              : unwrap(api.POST('/api/payroll/gratuity-rules/', { body })),
          { onSuccess: onDone },
        );
      }}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Select
          label={t('payroll.rule.country')}
          value={form.country}
          onChange={(e) => set({ country: e.target.value as GratuityRule['country'] })}
        >
          <option value="AE">{t('hr.countries.AE')}</option>
          <option value="SA">{t('hr.countries.SA')}</option>
        </Select>
        <Field
          label={t('payroll.from')}
          type="date"
          required
          value={form.starts_on}
          onChange={(e) => set({ starts_on: e.target.value })}
        />
        <Select
          label={t('payroll.rule.wage')}
          value={form.wage}
          onChange={(e) => set({ wage: e.target.value as GratuityRule['wage'] })}
        >
          <option value="basic">{t('payroll.rule.basic')}</option>
          <option value="full">{t('payroll.rule.full')}</option>
        </Select>
        {number('first_years')}
        {number('first_days')}
        {number('later_days')}
        {number('month_days')}
        {number('min_years')}
        <Field
          label={t('payroll.rule.cap_months')}
          hint={t('payroll.wageCapHint')}
          type="number"
          min="0.01"
          step="0.01"
          inputMode="decimal"
          value={form.cap_months}
          onChange={(e) => set({ cap_months: e.target.value })}
        />
      </div>
      <div className="space-y-2">
        {(['excludes_nationals', 'excludes_unpaid_days'] as const).map((key) => (
          <label
            key={key}
            className="flex min-h-11 items-center gap-3 rounded-xl border border-line px-3 focus-within:ring-2 focus-within:ring-azure"
          >
            <input
              type="checkbox"
              className="size-5"
              checked={form[key]}
              onChange={(e) => set({ [key]: e.target.checked })}
            />
            {t(`payroll.rule.${key}`)}
          </label>
        ))}
      </div>
      <div className="space-y-3">
        <p className="label">{t('payroll.rule.resignation')}</p>
        <Hint>{t('payroll.rule.resignationHint')}</Hint>
        {bands.map((band) => (
          <div key={band.key} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end">
            <Field
              label={t('payroll.rule.bandYears')}
              type="number"
              required
              min="0"
              step="0.01"
              inputMode="decimal"
              value={band.years}
              onChange={(e) => setBand(band.key, { years: e.target.value })}
            />
            <Field
              label={t('payroll.rule.bandShare')}
              required
              pattern="\d{1,3}/\d{1,3}"
              placeholder="1/3"
              value={band.share}
              onChange={(e) => setBand(band.key, { share: e.target.value })}
            />
            <label className="flex min-h-11 items-center gap-2">
              <input
                type="checkbox"
                className="size-5"
                checked={band.after}
                onChange={(e) => setBand(band.key, { after: e.target.checked })}
              />
              {t('payroll.rule.bandAfter')}
            </label>
            <Button
              variant="ghost"
              onClick={() => setBands(bands.filter((item) => item.key !== band.key))}
            >
              {t('workspace.remove')}
            </Button>
          </div>
        ))}
        <Button
          variant="ghost"
          disabled={bands.length >= 10}
          onClick={() =>
            setBands([
              ...bands,
              {
                key: Math.max(0, ...bands.map((band) => band.key)) + 1,
                years: '',
                share: '',
                after: false,
              },
            ])
          }
        >
          {t('payroll.rule.addBand')}
        </Button>
      </div>
      <Field
        label={t('payroll.source')}
        placeholder={t('payroll.sourcePlaceholder')}
        hint={t('payroll.sourceHint')}
        required
        maxLength={1000}
        value={form.source}
        onChange={(e) => set({ source: e.target.value })}
      />
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

function whole(share: string): boolean {
  const [top, bottom] = share.split('/');
  return top !== undefined && top === bottom;
}

function RuleCard({ rule }: { rule: GratuityRule }) {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const remove = useTenantAction(GRATUITY_KEYS);
  const [editing, setEditing] = useState(false);
  const title = `${t(`hr.countries.${rule.country}`)} · ${t('payroll.from')} ${rule.starts_on}`;
  if (editing) {
    return (
      <Panel title={title}>
        <RuleForm rule={rule} onDone={() => setEditing(false)} />
      </Panel>
    );
  }
  return (
    <Panel title={title}>
      <div className="space-y-3">
        <p>
          {t('payroll.rule.summary', {
            firstDays: Number(rule.first_days),
            firstYears: Number(rule.first_years),
            laterDays: Number(rule.later_days),
          })}{' '}
          {rule.wage === 'basic' ? t('payroll.rule.onBasic') : t('payroll.rule.onFull')}
        </p>
        <ul className="list-disc space-y-1 ps-5 text-sm text-muted">
          {Number(rule.min_years) > 0 && (
            <li>{t('payroll.rule.minSummary', { years: Number(rule.min_years) })}</li>
          )}
          {rule.cap_months && (
            <li>{t('payroll.rule.capSummary', { months: Number(rule.cap_months) })}</li>
          )}
          {rule.excludes_nationals && <li>{t('payroll.rule.excludes_nationals')}</li>}
          {rule.excludes_unpaid_days && <li>{t('payroll.rule.excludes_unpaid_days')}</li>}
          {(rule.resignation ?? []).map((band) => (
            <li key={`${band.years}${band.share}`}>
              {t(band.after ? 'payroll.rule.bandSummaryAfter' : 'payroll.rule.bandSummary', {
                years: Number(band.years),
                share: whole(band.share) ? t('payroll.rule.all') : band.share,
              })}
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted">{rule.source}</p>
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
                    api.DELETE('/api/payroll/gratuity-rules/{id}/', {
                      params: { path: { id: rule.id } },
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

export function EndOfServicePage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const fill = useTenantAction(GRATUITY_KEYS);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState<number | null>(null);
  const rules = useQuery({
    queryKey: [membership.tenant_id, 'payroll-gratuity-rules'],
    queryFn: () => unwrap(api.GET('/api/payroll/gratuity-rules/')),
  });
  return (
    <>
      <PageTitle title={t('payroll.endOfServiceTitle')} subtitle={t('payroll.endOfServiceBody')} />
      {can(membership, 'payroll', 'create') && (
        <Panel title={t('payroll.addFigures')}>
          <div className="space-y-4">
            <Hint>{t('payroll.endOfServiceFillHint')}</Hint>
            <div className="flex flex-wrap gap-3">
              <Button
                disabled={fill.isPending}
                onClick={() =>
                  fill.mutate(() => unwrap(api.POST('/api/payroll/gratuity-rules/fill/')), {
                    onSuccess: (result) => setAdded((result as { added: number }).added),
                  })
                }
              >
                {t('payroll.endOfServiceFill')}
              </Button>
              <Button variant="ghost" onClick={() => setAdding(true)}>
                {t('payroll.rule.new')}
              </Button>
            </div>
            {added !== null && (
              <Alert tone="success">{t('payroll.filledFigures', { added })}</Alert>
            )}
            {fill.isError && (
              <Alert tone="error">{errorText(fill.error, t('signIn.unavailable'))}</Alert>
            )}
            {adding && <RuleForm onDone={() => setAdding(false)} />}
          </div>
        </Panel>
      )}
      {rules.data?.length === 0 && (
        <Panel title={t('payroll.endOfServiceTitle')}>
          <p className="text-muted">{t('payroll.noRules')}</p>
        </Panel>
      )}
      {rules.data?.map((rule) => (
        <RuleCard key={rule.id} rule={rule} />
      ))}
    </>
  );
}
