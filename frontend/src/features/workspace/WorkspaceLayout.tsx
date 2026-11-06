import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, NavLink, Navigate, Outlet, useNavigate, useParams } from 'react-router';

import { Alert, Button } from '../../components/form';
import { LanguageSwitcher } from '../../components/LanguageSwitcher';
import { Logo } from '../../components/Logo';
import { api } from '../../lib/api/client';
import { setActiveTenant } from '../../lib/api/client';
import { can, type Me, type Membership } from '../../lib/api/types';
import { ensureCsrf, useMemberships, useSignOut } from '../auth/session';

export interface WorkspaceContext {
  me: Me;
  membership: Membership;
}

function VerifyBanner() {
  const { t } = useTranslation();
  const resend = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      await api.POST('/api/accounts/verify-email/resend/');
    },
  });
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-yellow/30 bg-yellow/10 px-4 py-3 text-sm text-yellow">
      <span>{t('workspace.unverified')}</span>
      <button
        type="button"
        className="underline underline-offset-4"
        disabled={resend.isPending || resend.isSuccess}
        onClick={() => resend.mutate()}
      >
        {resend.isSuccess ? t('workspace.resent') : t('workspace.resend')}
      </button>
    </div>
  );
}

function groupOf(path: string): 'workspace' | 'accounting' | 'inventory' {
  if (path.includes('/accounting/')) return 'accounting';
  if (path.includes('/inventory/')) return 'inventory';
  return 'workspace';
}

export function WorkspaceLayout({ me }: { me: Me }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const signOut = useSignOut();
  const { tenantId } = useParams();
  const memberships = useMemberships();

  if (memberships.isPending) return <div className="min-h-[100svh]" />;
  if (memberships.isError) {
    return (
      <div className="p-8">
        <Alert tone="error">{t('signIn.unavailable')}</Alert>
      </div>
    );
  }
  const list = memberships.data;
  const membership = list.find((row) => row.tenant_id === tenantId);
  if (!membership) {
    const first = list[0];
    return <Navigate to={first ? `/app/t/${first.tenant_id}` : '/app/new-business'} replace />;
  }
  // Set before the children render so every query they start carries the right X-Tenant.
  setActiveTenant(membership.tenant_id);

  const base = `/app/t/${membership.tenant_id}`;
  const links = [
    { to: base, label: t('workspace.overview'), show: true, end: true },
    {
      to: `${base}/members`,
      label: t('workspace.members'),
      show: can(membership, 'members', 'view'),
    },
    { to: `${base}/roles`, label: t('workspace.roles'), show: can(membership, 'roles', 'view') },
    { to: `${base}/audit`, label: t('workspace.audit'), show: can(membership, 'audit', 'view') },
    ...[
      { path: 'journal', label: t('acc.journal') },
      { path: 'chart', label: t('acc.chart') },
      { path: 'trial-balance', label: t('acc.trialBalance') },
      { path: 'ledger', label: t('acc.ledger') },
      { path: 'periods', label: t('acc.periods') },
    ].map((item) => ({
      to: `${base}/accounting/${item.path}`,
      label: item.label,
      show: can(membership, 'accounting', 'view'),
    })),
    ...[
      { path: 'products', label: t('inv.products') },
      { path: 'entries', label: t('inv.entries') },
      { path: 'on-hand', label: t('inv.onHandTitle') },
      { path: 'alerts', label: t('inv.alerts') },
      { path: 'setup', label: t('inv.setup') },
    ].map((item) => ({
      to: `${base}/inventory/${item.path}`,
      label: item.label,
      show: can(membership, 'inventory', 'view'),
    })),
  ];

  return (
    <div className="flex min-h-[100svh] flex-col md:flex-row">
      <aside className="border-b border-line bg-surface md:sticky md:top-0 md:h-[100svh] md:w-72 md:border-e md:border-b-0">
        <div className="flex h-full flex-col gap-5 p-4 md:gap-6 md:p-5">
          <div className="flex items-center justify-between">
            <Link to="/" className="inline-block">
              <Logo className="h-8 w-auto" />
            </Link>
            <button
              type="button"
              className="label rounded-full border border-line px-3 py-1.5 hover:border-ink hover:!text-ink md:hidden"
              onClick={() => {
                void signOut().then(() => navigate('/app/sign-in'));
              }}
            >
              {t('workspace.signOut')}
            </button>
          </div>
          <label className="block space-y-2">
            <span className="label">{t('workspace.business')}</span>
            <select
              className="w-full rounded-xl border border-line bg-canvas px-3 py-2.5 outline-none focus:border-ink"
              value={membership.tenant_id}
              onChange={(event) => {
                if (event.target.value === 'new') void navigate('/app/new-business');
                else void navigate(`/app/t/${event.target.value}`);
              }}
            >
              {list.map((row) => (
                <option key={row.tenant_id} value={row.tenant_id}>
                  {row.tenant_name}
                </option>
              ))}
              <option value="new">{t('workspace.newBusiness')}</option>
            </select>
          </label>
          <nav
            className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 md:mx-0 md:min-h-0 md:flex-1 md:flex-col md:overflow-y-auto md:px-0"
            data-lenis-prevent
          >
            {links
              .filter((link) => link.show)
              .map((link, index, shown) => {
                const group = groupOf(link.to);
                const first = index === 0 || groupOf(shown[index - 1]?.to ?? '') !== group;
                return (
                  <div key={link.to} className="contents">
                    {first && group !== 'workspace' && (
                      <span className="label mt-4 mb-1 hidden px-3 md:block">
                        {t(`workspace.groups.${group}`)}
                      </span>
                    )}
                    <NavLink
                      to={link.to}
                      end={link.end ?? false}
                      className={({ isActive }) =>
                        `rounded-xl px-3 py-2 text-sm whitespace-nowrap transition-colors ${
                          isActive
                            ? 'bg-ink text-canvas'
                            : 'text-muted hover:bg-raised hover:text-ink'
                        }`
                      }
                    >
                      {link.label}
                    </NavLink>
                  </div>
                );
              })}
          </nav>
          <div className="mt-auto hidden space-y-4 md:block">
            <LanguageSwitcher />
            <div className="text-xs text-muted">{me.email}</div>
            <Button
              variant="ghost"
              className="w-full"
              onClick={() => {
                void signOut().then(() => navigate('/app/sign-in'));
              }}
            >
              {t('workspace.signOut')}
            </Button>
          </div>
        </div>
      </aside>
      <main id="main" className="min-w-0 flex-1 space-y-6 p-4 md:p-10">
        <div className="flex justify-end md:hidden">
          <LanguageSwitcher />
        </div>
        {!me.email_verified && <VerifyBanner />}
        <Outlet context={{ me, membership } satisfies WorkspaceContext} />
      </main>
    </div>
  );
}
