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
  ];

  return (
    <div className="flex min-h-[100svh] flex-col md:flex-row">
      <aside className="border-b border-line bg-surface/70 backdrop-blur md:sticky md:top-0 md:h-[100svh] md:w-72 md:border-e md:border-b-0">
        <div className="flex h-full flex-col gap-5 p-4 md:gap-6 md:p-5">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2.5">
              <Logo className="size-7" />
              <span className="font-display text-2xl">Karobar</span>
            </Link>
            <button
              type="button"
              className="label rounded-full border border-line px-3 py-1.5 hover:border-gold hover:!text-gold md:hidden"
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
              className="w-full rounded-xl border border-line bg-black/40 px-3 py-2.5 outline-none focus:border-gold"
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
          <nav className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 md:mx-0 md:flex-col md:px-0">
            {links
              .filter((link) => link.show)
              .map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.end ?? false}
                  className={({ isActive }) =>
                    `rounded-xl px-3 py-2 text-sm whitespace-nowrap transition-colors ${
                      isActive
                        ? 'bg-cream text-black'
                        : 'text-muted hover:bg-white/5 hover:text-ink'
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              ))}
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
      <main className="min-w-0 flex-1 space-y-6 p-4 md:p-10">
        <div className="flex justify-end md:hidden">
          <LanguageSwitcher />
        </div>
        {!me.email_verified && <VerifyBanner />}
        <Outlet context={{ me, membership } satisfies WorkspaceContext} />
      </main>
    </div>
  );
}
