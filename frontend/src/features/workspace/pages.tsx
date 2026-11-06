import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { Alert, Button, Field, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { MODULES, can, type Me, type Role } from '../../lib/api/types';
import { ScreenIcon } from './icons';
import { AuthCard } from '../auth/AuthCard';
import { ensureCsrf, sessionKeys } from '../auth/session';
import { Home } from './Home';
import { errorText, useTenantAction, useWorkspace } from './hooks';
import { PageTitle, Panel } from './ui';

const CURRENCIES = ['PKR', 'AED', 'SAR', 'QAR', 'OMR', 'KWD', 'BHD', 'USD', 'EUR', 'GBP'];

export function NewBusinessPage({ me }: { me: Me }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage;
  const currencyName = new Intl.DisplayNames(language, { type: 'currency' });
  const navigate = useNavigate();
  const client = useQueryClient();
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('PKR');
  const [startMonth, setStartMonth] = useState(7);
  const [valuation, setValuation] = useState<'average' | 'fifo'>('average');
  const create = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      return unwrap(
        api.POST('/api/tenants/', {
          body: {
            name,
            base_currency: currency,
            locale: 'en',
            fiscal_year_start_month: startMonth,
            valuation_method: valuation,
          },
        }),
      );
    },
    onSuccess: async (membership) => {
      await client.invalidateQueries({ queryKey: sessionKeys.tenants });
      void navigate(`/app/${membership.tenant_slug}`);
    },
  });
  const resend = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      await unwrap(api.POST('/api/accounts/verify-email/resend/'));
    },
  });
  return (
    <AuthCard title={t('workspace.newBusiness')} subtitle={t('workspace.newBusinessBody')}>
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        {!me.email_verified && (
          <Alert tone="error">
            {t('workspace.unverified')}{' '}
            <button
              type="button"
              className="underline underline-offset-4"
              disabled={resend.isPending || resend.isSuccess}
              onClick={() => resend.mutate()}
            >
              {resend.isSuccess ? t('workspace.resent') : t('workspace.resend')}
            </button>
          </Alert>
        )}
        <Field
          label={t('workspace.businessName')}
          hint={t('hints.businessName')}
          placeholder={t('workspace.businessNamePlaceholder')}
          required
          maxLength={150}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Select
          label={t('workspace.currency')}
          hint={t('hints.currency')}
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
        >
          {CURRENCIES.map((code) => (
            <option key={code} value={code}>
              {code} - {currencyName.of(code)}
            </option>
          ))}
        </Select>
        <Select
          label={t('workspace.fiscalStart')}
          hint={t('hints.fiscalStart')}
          value={startMonth}
          onChange={(e) => setStartMonth(Number(e.target.value))}
        >
          {Array.from({ length: 12 }, (_, index) => (
            <option key={index} value={index + 1}>
              {new Intl.DateTimeFormat(language, { month: 'long' }).format(
                new Date(2026, index, 1),
              )}
            </option>
          ))}
        </Select>
        <Select
          label={t('workspace.valuation')}
          value={valuation}
          onChange={(e) => setValuation(e.target.value as 'average' | 'fifo')}
        >
          <option value="average">{t('workspace.average')}</option>
          <option value="fifo">{t('workspace.fifo')}</option>
        </Select>
        <p className="text-xs text-muted">{t('workspace.valuationHint')}</p>
        {create.isError && (
          <Alert tone="error">{errorText(create.error, t('signIn.unavailable'))}</Alert>
        )}
        <Button type="submit" className="w-full" disabled={create.isPending || !me.email_verified}>
          {t('workspace.create')}
        </Button>
      </form>
    </AuthCard>
  );
}

// The everyday jobs, in the words a shopkeeper would use, so nobody has to know that "Stock
// entries" or "Trial balance" is the screen they want.
const TASKS = [
  { key: 'counter', icon: 'counter', path: 'counter', module: 'pos' },
  { key: 'sell', icon: 'bills', path: 'sales/invoices', module: 'sales' },
  { key: 'takeMoney', icon: 'payments', path: 'sales/receipts', module: 'sales' },
  { key: 'whoOwes', icon: 'audit', path: 'sales/owed-to-me', module: 'sales' },
  { key: 'howBusiness', icon: 'dashboard', path: 'reports/dashboard', module: 'reports' },
  { key: 'addProduct', icon: 'products', path: 'inventory/products', module: 'inventory' },
  { key: 'moveStock', icon: 'entries', path: 'inventory/entries', module: 'inventory' },
  { key: 'seeStock', icon: 'on-hand', path: 'inventory/on-hand', module: 'inventory' },
  { key: 'warnings', icon: 'alerts', path: 'inventory/alerts', module: 'inventory' },
  { key: 'buy', icon: 'suppliers', path: 'purchasing/orders', module: 'purchasing' },
  { key: 'money', icon: 'journal', path: 'accounting/journal', module: 'accounting' },
  { key: 'team', icon: 'members', path: 'members', module: 'members' },
];

export function OverviewPage() {
  const { t } = useTranslation();
  const { me, membership } = useWorkspace();
  const modules = Object.keys(MODULES).filter((module) => can(membership, module, 'view'));
  const tasks = TASKS.filter((task) => can(membership, task.module, 'view'));
  return (
    <>
      <PageTitle
        guide="overview"
        title={membership.tenant_name}
        subtitle={t('workspace.welcome', { name: me.full_name || me.email })}
      />
      <Home />
      {tasks.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-2xl">{t('workspace.tasks.title')}</h2>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {tasks.map((task) => (
              <Link
                key={task.key}
                to={`/app/${membership.tenant_slug}/${task.path}`}
                className="group flex min-h-24 items-center gap-4 rounded-[var(--radius-card)] border border-line bg-canvas p-4 transition-colors hover:border-ink"
              >
                <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-raised text-ink">
                  <ScreenIcon name={task.icon} className="size-7" />
                </span>
                <span>
                  <span className="block text-lg leading-snug font-medium">
                    {t(`workspace.tasks.${task.key}.title`)}
                  </span>
                  <span className="block text-sm text-muted">
                    {t(`workspace.tasks.${task.key}.body`)}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}
      <Panel title={t('workspace.yourAccess')}>
        <p className="mb-4 text-sm text-muted">
          {membership.is_owner ? t('workspace.owner') : (membership.role ?? t('workspace.noRole'))}
        </p>
        <div className="flex flex-wrap gap-2">
          {modules.map((module) => (
            <span key={module} className="rounded-full border border-line px-3 py-1 text-xs">
              {t(`modulesShort.${module}`)}
            </span>
          ))}
        </div>
      </Panel>
    </>
  );
}

function useRoles() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'roles'],
    queryFn: async () => (await unwrap(api.GET('/api/roles/'))) as Role[],
    enabled: can(membership, 'roles', 'view') || can(membership, 'members', 'view'),
  });
}

export function MembersPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const roles = useRoles();
  const members = useQuery({
    queryKey: [membership.tenant_id, 'members'],
    queryFn: () => unwrap(api.GET('/api/members/')),
  });
  const invitations = useQuery({
    queryKey: [membership.tenant_id, 'invitations'],
    queryFn: () => unwrap(api.GET('/api/invitations/')),
  });
  const [email, setEmail] = useState('');
  const [roleId, setRoleId] = useState('');
  const mutation = useTenantAction(['members', 'invitations']);
  const run = (call: () => Promise<unknown>) => {
    mutation.mutate(call);
  };

  const invite = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    run(async () => {
      await unwrap(
        api.POST('/api/invitations/', {
          body: { email, role: roleId ? Number(roleId) : null } as never,
        }),
      );
      setEmail('');
    });
  };
  const roleOptions = (
    <>
      <option value="">{t('workspace.noRole')}</option>
      {roles.data?.map((role) => (
        <option key={role.id} value={role.id}>
          {role.name}
        </option>
      ))}
    </>
  );

  return (
    <>
      <PageTitle guide="members" title={t('workspace.members')} />
      {mutation.isError && (
        <Alert tone="error">{errorText(mutation.error, t('signIn.unavailable'))}</Alert>
      )}
      {can(membership, 'members', 'create') && (
        <Panel title={t('workspace.invite')}>
          <form className="grid gap-4 md:grid-cols-[2fr_1fr_auto] md:items-end" onSubmit={invite}>
            <Field
              label={t('signIn.email')}
              type="email"
              required
              maxLength={254}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Select
              label={t('workspace.role')}
              value={roleId}
              onChange={(e) => setRoleId(e.target.value)}
            >
              {roleOptions}
            </Select>
            <Button type="submit" disabled={mutation.isPending}>
              {t('workspace.sendInvite')}
            </Button>
          </form>
        </Panel>
      )}
      <Panel title={t('workspace.members')}>
        <ul className="divide-y divide-line">
          {members.data?.results.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <div>{row.full_name || row.email}</div>
                <div className="text-xs text-muted">{row.email}</div>
              </div>
              {row.is_owner ? (
                <span className="text-xs text-ember">{t('workspace.owner')}</span>
              ) : (
                <div className="flex items-center gap-2">
                  <select
                    aria-label={t('workspace.role')}
                    className="rounded-lg border border-line bg-canvas px-2 py-1.5 text-sm"
                    value={row.role ?? ''}
                    disabled={!can(membership, 'members', 'update')}
                    onChange={(e) => {
                      const role = e.target.value ? Number(e.target.value) : null;
                      run(() =>
                        unwrap(
                          api.PATCH('/api/members/{id}/', {
                            params: { path: { id: row.id } },
                            body: { role },
                          }),
                        ),
                      );
                    }}
                  >
                    {roleOptions}
                  </select>
                  {can(membership, 'members', 'delete') && (
                    <Button
                      variant="danger"
                      onClick={() =>
                        run(() =>
                          unwrap(
                            api.DELETE('/api/members/{id}/', { params: { path: { id: row.id } } }),
                          ),
                        )
                      }
                    >
                      {t('workspace.remove')}
                    </Button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title={t('workspace.invitations')}>
        <ul className="divide-y divide-line">
          {invitations.data?.results.length === 0 && (
            <li className="py-3 text-sm text-muted">{t('workspace.none')}</li>
          )}
          {invitations.data?.results.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <div>{row.email}</div>
                <div className="text-xs text-muted">
                  {row.role_name ?? t('workspace.noRole')} &middot;{' '}
                  {t(`workspace.status.${row.status}`)}
                </div>
              </div>
              {row.status === 'pending' && can(membership, 'members', 'delete') && (
                <Button
                  variant="ghost"
                  onClick={() =>
                    run(() =>
                      unwrap(
                        api.DELETE('/api/invitations/{id}/', { params: { path: { id: row.id } } }),
                      ),
                    )
                  }
                >
                  {t('workspace.revoke')}
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}

export function RolesPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const roles = useRoles();
  const [name, setName] = useState('');
  const [grants, setGrants] = useState<Record<string, string[]>>({});
  const [editing, setEditing] = useState<number | null>(null);
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      // The generated type marks the read-only id as required on input; the API ignores it.
      const body = { name, permissions: grants } as never;
      if (editing === null) await unwrap(api.POST('/api/roles/', { body }));
      else await unwrap(api.PATCH('/api/roles/{id}/', { params: { path: { id: editing } }, body }));
    },
    onSuccess: async () => {
      setName('');
      setGrants({});
      setEditing(null);
      await client.invalidateQueries({ queryKey: [membership.tenant_id, 'roles'] });
    },
  });
  const remove = useMutation({
    mutationFn: async (id: number) => {
      await ensureCsrf();
      await unwrap(api.DELETE('/api/roles/{id}/', { params: { path: { id } } }));
    },
    onSuccess: () => client.invalidateQueries({ queryKey: [membership.tenant_id, 'roles'] }),
  });
  const toggle = (module: string, actionName: string) => {
    const current = grants[module] ?? [];
    const next = current.includes(actionName)
      ? current.filter((a) => a !== actionName)
      : [...current, actionName];
    setGrants({ ...grants, [module]: next });
  };
  const canEdit = can(membership, 'roles', editing === null ? 'create' : 'update');
  const error = save.error ?? remove.error;

  return (
    <>
      <PageTitle guide="roles" title={t('workspace.roles')} subtitle={t('workspace.rolesBody')} />
      {error && <Alert tone="error">{errorText(error, t('signIn.unavailable'))}</Alert>}
      <Panel title={t('workspace.roles')}>
        <ul className="divide-y divide-line">
          {roles.data?.map((role) => (
            <li key={role.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <div>{role.name}</div>
                <div className="text-xs text-muted">
                  {Object.keys(role.permissions)
                    .map((m) => t(`modulesShort.${m}`))
                    .join(', ') || t('workspace.none')}
                </div>
              </div>
              <div className="flex gap-2">
                {can(membership, 'roles', 'update') && (
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setEditing(role.id);
                      setName(role.name);
                      setGrants(role.permissions);
                    }}
                  >
                    {t('workspace.edit')}
                  </Button>
                )}
                {can(membership, 'roles', 'delete') && (
                  <Button variant="danger" onClick={() => remove.mutate(role.id)}>
                    {t('workspace.remove')}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Panel>
      {canEdit && (
        <Panel title={editing === null ? t('workspace.newRole') : t('workspace.editRole')}>
          <form
            className="space-y-5"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate();
            }}
          >
            <Field
              label={t('workspace.roleName')}
              required
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <div className="overflow-x-auto" data-lenis-prevent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted">
                    <th className="py-2 text-start font-medium">{t('workspace.module')}</th>
                    {['view', 'create', 'update', 'delete', 'post'].map((a) => (
                      <th key={a} className="px-2 py-2 font-medium">
                        {t(`workspace.actions.${a}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(MODULES).map(([module, actions]) => (
                    <tr key={module} className="border-t border-line">
                      <td className="py-2">{t(`modulesShort.${module}`)}</td>
                      {['view', 'create', 'update', 'delete', 'post'].map((a) => (
                        <td key={a} className="px-2 py-2 text-center">
                          {actions.includes(a) && (
                            <input
                              type="checkbox"
                              aria-label={`${module} ${a}`}
                              className="size-4 accent-[var(--color-ember)]"
                              checked={(grants[module] ?? []).includes(a)}
                              onChange={() => toggle(module, a)}
                            />
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex gap-3">
              <Button type="submit" disabled={save.isPending}>
                {t('workspace.save')}
              </Button>
              {editing !== null && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setEditing(null);
                    setName('');
                    setGrants({});
                  }}
                >
                  {t('workspace.cancel')}
                </Button>
              )}
            </div>
          </form>
        </Panel>
      )}
    </>
  );
}

export function AuditPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const events = useQuery({
    queryKey: [membership.tenant_id, 'audit'],
    queryFn: () => unwrap(api.GET('/api/audit/')),
  });
  const format = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  return (
    <>
      <PageTitle guide="audit" title={t('workspace.audit')} subtitle={t('workspace.auditBody')} />
      <Panel title={t('workspace.recent')}>
        <div className="overflow-x-auto" data-lenis-prevent>
          <table className="w-full text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-2 text-start font-medium">{t('workspace.when')}</th>
                <th className="py-2 text-start font-medium">{t('workspace.who')}</th>
                <th className="py-2 text-start font-medium">{t('workspace.what')}</th>
                <th className="py-2 text-start font-medium">{t('workspace.changes')}</th>
              </tr>
            </thead>
            <tbody>
              {events.data?.results.map((row) => (
                <tr key={row.id} className="border-t border-line align-top">
                  <td className="py-2 pe-4 whitespace-nowrap">{format.format(new Date(row.at))}</td>
                  <td className="py-2 pe-4">{row.user ?? '-'}</td>
                  <td className="py-2 pe-4">
                    {row.action} {row.model.split('.').at(-1)} #{row.object_id}
                  </td>
                  <td className="py-2 font-mono text-xs text-muted">
                    {JSON.stringify(row.changes)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
