import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Button, Field, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { saveBlob } from '../../lib/api/download';
import { unwrap } from '../../lib/api/errors';
import { can, type Account, type JournalEntry } from '../../lib/api/types';
import { formatMoney, fromMinor, toMinor } from '../../lib/money';
import { today } from '../../lib/dates';
import { errorText, useTenantAction, useWorkspace } from '../workspace/hooks';
import { NUM, TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';

function useAccounts() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'accounts'],
    queryFn: () => unwrap(api.GET('/api/accounting/accounts/')),
  });
}

function postable(accounts: Account[] | undefined): Account[] {
  return (accounts ?? []).filter((account) => !account.is_group && account.is_active !== false);
}

interface DraftLine {
  key: number;
  account: string;
  debit: string;
  credit: string;
  description: string;
}

function blankLine(key: number): DraftLine {
  return { key, account: '', debit: '', credit: '', description: '' };
}

function EntryEditor({ entry, onDone }: { entry?: JournalEntry; onDone: () => void }) {
  const { t, i18n } = useTranslation();
  const accounts = useAccounts();
  const [date, setDate] = useState(entry?.date ?? today());
  const [memo, setMemo] = useState(entry?.memo ?? '');
  const [lines, setLines] = useState<DraftLine[]>(() =>
    entry
      ? entry.lines.map((line, index) => ({
          key: index,
          account: String(line.account),
          debit: line.debit && toMinor(line.debit) ? line.debit : '',
          credit: line.credit && toMinor(line.credit) ? line.credit : '',
          description: line.description ?? '',
        }))
      : [blankLine(0), blankLine(1)],
  );
  const save = useTenantAction(['entries']);
  const debits = lines.reduce((sum, line) => sum + (toMinor(line.debit) || 0), 0);
  const credits = lines.reduce((sum, line) => sum + (toMinor(line.credit) || 0), 0);
  const invalid = lines.some(
    (line) => Number.isNaN(toMinor(line.debit)) || Number.isNaN(toMinor(line.credit)),
  );
  const balanced = debits === credits && debits > 0 && !invalid;

  const update = (key: number, patch: Partial<DraftLine>) => {
    setLines(lines.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  };

  const submit = () => {
    const body = {
      date,
      memo,
      lines: lines
        .filter((line) => line.account)
        .map((line) => ({
          account: Number(line.account),
          debit: fromMinor(toMinor(line.debit) || 0),
          credit: fromMinor(toMinor(line.credit) || 0),
          description: line.description,
        })),
    } as never;
    save.mutate(
      () =>
        entry
          ? unwrap(
              api.PUT('/api/accounting/entries/{id}/', {
                params: { path: { id: entry.id } },
                body,
              }),
            )
          : unwrap(api.POST('/api/accounting/entries/', { body })),
      { onSuccess: onDone },
    );
  };

  return (
    <Panel title={entry ? t('acc.editDraft') : t('acc.newEntry')}>
      <div className="grid gap-4 sm:grid-cols-[12rem_1fr]">
        <Field
          label={t('acc.date')}
          type="date"
          required
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <Field
          label={t('acc.memo')}
          maxLength={255}
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
        />
      </div>
      <div className="mt-6 overflow-x-auto" data-lenis-prevent>
        <table className={`${TABLE} min-w-[40rem]`}>
          <thead>
            <tr>
              <th className={TH}>{t('ledger.account')}</th>
              <th className={TH}>{t('acc.description')}</th>
              <th className={`${TH} text-end`}>{t('ledger.debit')}</th>
              <th className={`${TH} text-end`}>{t('ledger.credit')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.key} className="border-t border-line">
                <td className="py-2 pe-2">
                  <select
                    aria-label={t('ledger.account')}
                    className="w-full rounded-lg border border-line bg-black/50 px-2 py-2"
                    value={line.account}
                    onChange={(e) => update(line.key, { account: e.target.value })}
                  >
                    <option value="">-</option>
                    {postable(accounts.data).map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.code} {account.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pe-2">
                  <input
                    aria-label={t('acc.description')}
                    maxLength={255}
                    className="w-full rounded-lg border border-line bg-black/50 px-2 py-2"
                    value={line.description}
                    onChange={(e) => update(line.key, { description: e.target.value })}
                  />
                </td>
                {(['debit', 'credit'] as const).map((side) => (
                  <td key={side} className="w-36 py-2 pe-2">
                    <input
                      aria-label={t(`ledger.${side}`)}
                      inputMode="decimal"
                      placeholder="0.00"
                      className={`w-full rounded-lg border bg-black/50 px-2 py-2 text-end font-mono ${
                        Number.isNaN(toMinor(line[side])) ? 'border-coral' : 'border-line'
                      }`}
                      value={line[side]}
                      onChange={(e) =>
                        update(line.key, {
                          [side]: e.target.value,
                          ...(e.target.value
                            ? { [side === 'debit' ? 'credit' : 'debit']: '' }
                            : {}),
                        })
                      }
                    />
                  </td>
                ))}
                <td className="py-2">
                  <button
                    type="button"
                    aria-label={t('workspace.remove')}
                    className="px-2 text-muted hover:text-coral disabled:opacity-30"
                    disabled={lines.length <= 2}
                    onClick={() => setLines(lines.filter((item) => item.key !== line.key))}
                  >
                    &times;
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-line-strong">
              <td className="py-3">
                <Button
                  variant="ghost"
                  onClick={() =>
                    setLines([...lines, blankLine(Math.max(...lines.map((l) => l.key)) + 1)])
                  }
                >
                  {t('acc.addLine')}
                </Button>
              </td>
              <td className={`${TD} text-end`}>
                <span className={`label ${balanced ? '!text-mint' : '!text-coral'}`}>
                  {balanced
                    ? t('ledger.balanced')
                    : t('acc.difference', {
                        amount: formatMoney(debits - credits, i18n.resolvedLanguage),
                      })}
                </span>
              </td>
              <td className={NUM}>{formatMoney(debits, i18n.resolvedLanguage)}</td>
              <td className={NUM}>{formatMoney(credits, i18n.resolvedLanguage)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      {save.isError && (
        <div className="mt-4">
          <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
        </div>
      )}
      <div className="mt-6 flex flex-wrap gap-3">
        <Button disabled={save.isPending || invalid} onClick={submit}>
          {t('acc.saveDraft')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('workspace.cancel')}
        </Button>
      </div>
      <p className="mt-4 text-xs text-muted">{t('acc.draftHint')}</p>
    </Panel>
  );
}

function EntryRow({ entry, onEdit }: { entry: JournalEntry; onEdit: () => void }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const [open, setOpen] = useState(false);
  const action = useTenantAction(['entries', 'trial-balance']);
  const posted = entry.status === 'posted';
  return (
    <li className="border-t border-line">
      <button
        type="button"
        className="grid w-full grid-cols-[1fr_auto] gap-3 py-4 text-start sm:grid-cols-[9rem_7rem_1fr_auto]"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="font-mono text-sm">{entry.number ?? t('acc.draft')}</span>
        <span className="hidden text-sm text-muted sm:block">{entry.date}</span>
        <span className="hidden truncate sm:block">{entry.memo || '-'}</span>
        <span className="font-mono text-sm tabular-nums">
          {formatMoney(entry.total, i18n.resolvedLanguage)}
        </span>
      </button>
      {open && (
        <div className="space-y-4 pb-6">
          <div className="overflow-x-auto" data-lenis-prevent>
            <table className={TABLE}>
              <tbody>
                {entry.lines.map((line) => (
                  <tr key={line.id} className="border-t border-line">
                    <td className={TD}>
                      <span className="font-mono text-xs text-muted">{line.account_code}</span>{' '}
                      {line.account_name}
                      {line.description && (
                        <div className="text-xs text-muted">{line.description}</div>
                      )}
                    </td>
                    <td className={NUM}>
                      {toMinor(line.debit)
                        ? formatMoney(line.debit ?? '0', i18n.resolvedLanguage)
                        : ''}
                    </td>
                    <td className={NUM}>
                      {toMinor(line.credit)
                        ? formatMoney(line.credit ?? '0', i18n.resolvedLanguage)
                        : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="label">
            {posted
              ? t('acc.postedBy', {
                  who: entry.posted_by ?? '',
                  when: entry.posted_at
                    ? new Intl.DateTimeFormat(i18n.resolvedLanguage, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      }).format(new Date(entry.posted_at))
                    : '',
                })
              : t('acc.createdBy', { who: entry.created_by })}
            {entry.reversal_of !== null && ` · ${t('acc.reversalOf', { id: entry.reversal_of })}`}
            {entry.reversed_by !== null && ` · ${t('acc.reversed')}`}
          </p>
          {action.isError && (
            <Alert tone="error">{errorText(action.error, t('signIn.unavailable'))}</Alert>
          )}
          <div className="flex flex-wrap gap-3">
            {!posted && can(membership, 'accounting', 'post') && (
              <Button
                disabled={action.isPending}
                onClick={() =>
                  action.mutate(() =>
                    unwrap(
                      api.POST('/api/accounting/entries/{id}/post/', {
                        params: { path: { id: entry.id } },
                      }),
                    ),
                  )
                }
              >
                {t('acc.post')}
              </Button>
            )}
            {!posted && can(membership, 'accounting', 'update') && (
              <Button variant="ghost" onClick={onEdit}>
                {t('workspace.edit')}
              </Button>
            )}
            {!posted && can(membership, 'accounting', 'delete') && (
              <Button
                variant="danger"
                onClick={() =>
                  action.mutate(() =>
                    unwrap(
                      api.DELETE('/api/accounting/entries/{id}/', {
                        params: { path: { id: entry.id } },
                      }),
                    ),
                  )
                }
              >
                {t('workspace.remove')}
              </Button>
            )}
            {posted && entry.reversed_by === null && can(membership, 'accounting', 'post') && (
              <Button
                variant="ghost"
                disabled={action.isPending}
                onClick={() =>
                  action.mutate(() =>
                    unwrap(
                      api.POST('/api/accounting/entries/{id}/reverse/', {
                        params: { path: { id: entry.id } },
                        body: { date: today() },
                      }),
                    ),
                  )
                }
              >
                {t('acc.reverse')}
              </Button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

export function JournalPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const [status, setStatus] = useState<'' | 'draft' | 'posted'>('');
  const [editing, setEditing] = useState<JournalEntry | 'new' | null>(null);
  const entries = useQuery({
    queryKey: [membership.tenant_id, 'entries', status],
    queryFn: () =>
      unwrap(api.GET('/api/accounting/entries/', { params: { query: status ? { status } : {} } })),
  });
  return (
    <>
      <PageTitle guide="journal" title={t('acc.journal')} subtitle={t('acc.journalBody')} />
      {editing !== null ? (
        <EntryEditor
          key={editing === 'new' ? 'new' : editing.id}
          {...(editing === 'new' ? {} : { entry: editing })}
          onDone={() => setEditing(null)}
        />
      ) : (
        can(membership, 'accounting', 'create') && (
          <Button onClick={() => setEditing('new')}>{t('acc.newEntry')}</Button>
        )
      )}
      <Panel
        title={t('acc.entries')}
        action={
          <div role="group" className="flex gap-1">
            {(['', 'draft', 'posted'] as const).map((value) => (
              <button
                key={value || 'all'}
                type="button"
                aria-pressed={status === value}
                className={`rounded-full px-3 py-1 text-xs ${status === value ? 'bg-cream text-black' : 'text-muted hover:text-ink'}`}
                onClick={() => setStatus(value)}
              >
                {t(`acc.filter.${value || 'all'}`)}
              </button>
            ))}
          </div>
        }
      >
        <ul>
          {entries.data?.results.length === 0 && (
            <li className="py-4 text-sm text-muted">{t('workspace.none')}</li>
          )}
          {entries.data?.results.map((entry) => (
            <EntryRow key={entry.id} entry={entry} onEdit={() => setEditing(entry)} />
          ))}
        </ul>
      </Panel>
    </>
  );
}

export function ChartPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const accounts = useAccounts();
  const save = useTenantAction(['accounts']);
  const [form, setForm] = useState({ code: '', name: '', type: 'expense', parent: '' });
  const groups = (accounts.data ?? []).filter((account) => account.is_group);
  const depth = (account: Account): number => {
    // The API refuses cycles, but a visited set keeps a bad row from freezing the page.
    const seen = new Set<number>();
    let level = 0;
    let parent = account.parent;
    while (parent && !seen.has(parent)) {
      seen.add(parent);
      level += 1;
      parent = accounts.data?.find((item) => item.id === parent)?.parent ?? null;
    }
    return level;
  };
  return (
    <>
      <PageTitle guide="chart" title={t('acc.chart')} subtitle={t('acc.chartBody')} />
      {can(membership, 'accounting', 'create') && (
        <Panel title={t('acc.newAccount')}>
          <form
            className="grid gap-4 md:grid-cols-[8rem_1fr_10rem_1fr_auto] md:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate(
                () =>
                  unwrap(
                    api.POST('/api/accounting/accounts/', {
                      body: { ...form, parent: form.parent ? Number(form.parent) : null } as never,
                    }),
                  ),
                { onSuccess: () => setForm({ ...form, code: '', name: '' }) },
              );
            }}
          >
            <Field
              label={t('acc.code')}
              required
              maxLength={20}
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
            <Field
              label={t('acc.name')}
              required
              maxLength={150}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <Select
              label={t('acc.type')}
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              {['asset', 'liability', 'equity', 'income', 'expense'].map((type) => (
                <option key={type} value={type}>
                  {t(`acc.types.${type}`)}
                </option>
              ))}
            </Select>
            <Select
              label={t('acc.parent')}
              value={form.parent}
              onChange={(e) => setForm({ ...form, parent: e.target.value })}
            >
              <option value="">-</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.code} {group.name}
                </option>
              ))}
            </Select>
            <Button type="submit" disabled={save.isPending}>
              {t('workspace.save')}
            </Button>
          </form>
          {save.isError && (
            <div className="mt-4">
              <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
            </div>
          )}
        </Panel>
      )}
      <Panel title={t('acc.accounts')}>
        <ul>
          {accounts.data?.map((account) => (
            <li
              key={account.id}
              className={`flex items-baseline gap-4 border-t border-line py-3 ${account.is_group ? 'font-medium' : 'text-ink/85'}`}
              style={{ paddingInlineStart: `${depth(account) * 1.25}rem` }}
            >
              <span className="w-14 shrink-0 font-mono text-sm text-ember">{account.code}</span>
              <span className={account.is_group ? 'font-display text-xl' : ''}>{account.name}</span>
              <span className="label ms-auto hidden sm:inline">
                {t(`acc.types.${account.type}`)}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}

function useDownload() {
  return useMutation({
    mutationFn: async (run: () => Promise<{ blob: Blob; name: string }>) => {
      const { blob, name } = await run();
      saveBlob(blob, name);
    },
  });
}

export function TrialBalancePage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const [end, setEnd] = useState(today());
  const [start, setStart] = useState('');
  const query = { end, ...(start ? { start } : {}) };
  const report = useQuery({
    queryKey: [membership.tenant_id, 'trial-balance', start, end],
    queryFn: () => unwrap(api.GET('/api/accounting/reports/trial-balance/', { params: { query } })),
  });
  const download = useDownload();
  const balanced = report.data && report.data.total_debit === report.data.total_credit;
  return (
    <>
      <PageTitle
        guide="trialBalance"
        title={t('acc.trialBalance')}
        subtitle={t('acc.trialBalanceBody')}
      />
      <Panel
        title={t('acc.period')}
        action={
          <Button
            variant="ghost"
            disabled={download.isPending}
            onClick={() =>
              download.mutate(async () => ({
                blob: await unwrap(
                  api.GET('/api/accounting/reports/trial-balance/', {
                    params: { query: { ...query, export: 'csv' } },
                    parseAs: 'blob',
                  }),
                ),
                name: `trial-balance-${end}.csv`,
              }))
            }
          >
            {t('acc.exportCsv')}
          </Button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t('acc.from')}
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
          <Field
            label={t('acc.to')}
            type="date"
            required
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
        <div className="mt-6 overflow-x-auto" data-lenis-prevent>
          <table className={TABLE}>
            <thead>
              <tr>
                <th className={TH}>{t('acc.code')}</th>
                <th className={TH}>{t('ledger.account')}</th>
                <th className={`${TH} text-end`}>{t('ledger.debit')}</th>
                <th className={`${TH} text-end`}>{t('ledger.credit')}</th>
              </tr>
            </thead>
            <tbody>
              {report.data?.rows.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className={`${TD} font-mono text-ember`}>{row.code}</td>
                  <td className={TD}>{row.name}</td>
                  <td className={NUM}>
                    {toMinor(row.debit) ? formatMoney(row.debit, i18n.resolvedLanguage) : ''}
                  </td>
                  <td className={NUM}>
                    {toMinor(row.credit) ? formatMoney(row.credit, i18n.resolvedLanguage) : ''}
                  </td>
                </tr>
              ))}
            </tbody>
            {report.data && (
              <tfoot>
                <tr className="border-t border-ember/40 text-ember">
                  <td className={TD} colSpan={2}>
                    {t('ledger.total')}{' '}
                    <span className={`label ms-2 ${balanced ? '!text-mint' : '!text-coral'}`}>
                      {balanced ? t('ledger.balanced') : t('acc.outOfBalance')}
                    </span>
                  </td>
                  <td className={NUM}>
                    {formatMoney(report.data.total_debit, i18n.resolvedLanguage)}
                  </td>
                  <td className={NUM}>
                    {formatMoney(report.data.total_credit, i18n.resolvedLanguage)}
                  </td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
        {report.isError && (
          <Alert tone="error">{errorText(report.error, t('signIn.unavailable'))}</Alert>
        )}
      </Panel>
    </>
  );
}

export function LedgerPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const accounts = useAccounts();
  const [accountId, setAccountId] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const query = { ...(start ? { start } : {}), ...(end ? { end } : {}) };
  const ledger = useQuery({
    queryKey: [membership.tenant_id, 'ledger', accountId, start, end],
    enabled: Boolean(accountId),
    queryFn: () =>
      unwrap(
        api.GET('/api/accounting/accounts/{id}/ledger/', {
          params: { path: { id: Number(accountId) }, query },
        }),
      ),
  });
  const download = useDownload();
  return (
    <>
      <PageTitle guide="ledger" title={t('acc.ledger')} subtitle={t('acc.ledgerBody')} />
      <Panel
        title={t('ledger.account')}
        action={
          accountId && (
            <Button
              variant="ghost"
              onClick={() =>
                download.mutate(async () => ({
                  blob: await unwrap(
                    api.GET('/api/accounting/accounts/{id}/ledger/', {
                      params: {
                        path: { id: Number(accountId) },
                        query: { ...query, export: 'csv' },
                      },
                      parseAs: 'blob',
                    }),
                  ),
                  name: `ledger-${ledger.data?.account.code ?? accountId}.csv`,
                }))
              }
            >
              {t('acc.exportCsv')}
            </Button>
          )
        }
      >
        <div className="grid gap-4 md:grid-cols-[2fr_1fr_1fr]">
          <Select
            label={t('ledger.account')}
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
          >
            <option value="">-</option>
            {postable(accounts.data).map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} {account.name}
              </option>
            ))}
          </Select>
          <Field
            label={t('acc.from')}
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
          <Field
            label={t('acc.to')}
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
        {ledger.data && (
          <div className="mt-6 overflow-x-auto" data-lenis-prevent>
            <table className={`${TABLE} min-w-[36rem]`}>
              <thead>
                <tr>
                  <th className={TH}>{t('acc.date')}</th>
                  <th className={TH}>{t('acc.number')}</th>
                  <th className={TH}>{t('acc.memo')}</th>
                  <th className={`${TH} text-end`}>{t('ledger.debit')}</th>
                  <th className={`${TH} text-end`}>{t('ledger.credit')}</th>
                  <th className={`${TH} text-end`}>{t('acc.balance')}</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-line text-muted">
                  <td className={TD} colSpan={5}>
                    {t('acc.opening')}
                  </td>
                  <td className={NUM}>{formatMoney(ledger.data.opening, i18n.resolvedLanguage)}</td>
                </tr>
                {ledger.data.lines.map((line, index) => (
                  <tr key={`${line.entry_id}-${index}`} className="border-t border-line">
                    <td className={`${TD} whitespace-nowrap`}>{line.date}</td>
                    <td className={`${TD} font-mono text-xs`}>{line.number}</td>
                    <td className={TD}>{line.description || line.memo}</td>
                    <td className={NUM}>
                      {toMinor(line.debit) ? formatMoney(line.debit, i18n.resolvedLanguage) : ''}
                    </td>
                    <td className={NUM}>
                      {toMinor(line.credit) ? formatMoney(line.credit, i18n.resolvedLanguage) : ''}
                    </td>
                    <td className={NUM}>{formatMoney(line.balance, i18n.resolvedLanguage)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-ember/40 text-ember">
                  <td className={TD} colSpan={5}>
                    {t('acc.closing')}
                  </td>
                  <td className={NUM}>{formatMoney(ledger.data.closing, i18n.resolvedLanguage)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

export function PeriodsPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const years = useQuery({
    queryKey: [membership.tenant_id, 'fiscal-years'],
    queryFn: () => unwrap(api.GET('/api/accounting/fiscal-years/')),
  });
  const action = useTenantAction(['fiscal-years']);
  const latest = years.data?.[0];
  const createNext = () => {
    if (!latest) return;
    const start = new Date(`${latest.end}T00:00:00Z`);
    start.setUTCDate(start.getUTCDate() + 1);
    const end = new Date(start);
    end.setUTCFullYear(end.getUTCFullYear() + 1);
    end.setUTCDate(end.getUTCDate() - 1);
    const iso = (day: Date) => day.toISOString().slice(0, 10);
    action.mutate(() =>
      unwrap(
        api.POST('/api/accounting/fiscal-years/', {
          body: { start: iso(start), end: iso(end) } as never,
        }),
      ),
    );
  };
  return (
    <>
      <PageTitle guide="periods" title={t('acc.periods')} subtitle={t('acc.periodsBody')} />
      {action.isError && (
        <Alert tone="error">{errorText(action.error, t('signIn.unavailable'))}</Alert>
      )}
      {can(membership, 'accounting', 'create') && latest && (
        <Button onClick={createNext} disabled={action.isPending}>
          {t('acc.nextYear')}
        </Button>
      )}
      {years.data?.map((year) => (
        <Panel key={year.id} title={year.name ?? ''}>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {year.periods.map((period) => (
              <li
                key={period.id}
                className="flex items-center justify-between rounded-xl border border-line px-4 py-3"
              >
                <span>
                  <span className="label me-2">P{period.number}</span>
                  <span className="text-sm">
                    {period.start} &ndash; {period.end}
                  </span>
                </span>
                <button
                  type="button"
                  disabled={!can(membership, 'accounting', 'update') || action.isPending}
                  className={`label rounded-full border px-3 py-1 ${period.closed ? 'border-coral/50 !text-coral' : 'border-mint/40 !text-mint'}`}
                  onClick={() =>
                    action.mutate(() =>
                      unwrap(
                        api.PATCH('/api/accounting/periods/{id}/', {
                          params: { path: { id: period.id } },
                          body: { closed: !period.closed } as never,
                        }),
                      ),
                    )
                  }
                >
                  {period.closed ? t('acc.closed') : t('acc.open')}
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      ))}
    </>
  );
}
