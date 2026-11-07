import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router';

import { Alert, Button, Field, PasswordField, SubmitButton } from '../../components/form';
import { api } from '../../lib/api/client';
import { safeNext } from '../../lib/paths';
import { ApiError, unwrap } from '../../lib/api/errors';
import { AuthCard } from './AuthCard';
import { needsCheckbox, useHumanCheck } from './human';
import { OAuthButtons } from './OAuthButtons';
import { ensureCsrf, sessionKeys, useMe } from './session';

function messageOf(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.status < 500 ? error.message : fallback;
}

const OAUTH_ERRORS = new Set([
  'oauth_failed',
  'oauth_state',
  'oauth_cancelled',
  'provider_unavailable',
  'email_missing',
  'email_in_use',
  'account_disabled',
]);

function submitting(handler: () => void) {
  return (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    handler();
  };
}

const LINK = 'text-ember underline-offset-4 hover:underline';

// A CSRF rejection is a 403 too, and telling someone their password is wrong wouldn't help them.
function badCredentials(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.body as { code?: unknown } | undefined)?.code === 'authentication_failed'
  );
}

export function SignInPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const human = useHumanCheck('login');
  const oauthError = params.get('error');
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      const proof = await human.proof();
      return unwrap(api.POST('/api/accounts/login/', { body: { email, password, ...proof } }));
    },
    onError: (error) => {
      if (needsCheckbox(error)) human.requireCheckbox();
    },
    onSuccess: async (me) => {
      client.setQueryData(sessionKeys.me, me);
      await client.invalidateQueries({ queryKey: sessionKeys.tenants });
      const next = params.get('next');
      void navigate(safeNext(next) ?? '/app');
    },
  });

  return (
    <AuthCard
      title={t('auth.welcome')}
      subtitle={t('auth.welcomeBody')}
      footer={
        <>
          {t('auth.noAccount')}{' '}
          <Link className={LINK} to={`/signup${params.size ? `?${params.toString()}` : ''}`}>
            {t('auth.signUp')}
          </Link>
        </>
      }
    >
      {oauthError && OAUTH_ERRORS.has(oauthError) && (
        <div className="mb-5">
          <Alert tone="error">{t(`auth.oauthErrors.${oauthError}`)}</Alert>
        </div>
      )}
      <div className="mb-5">
        <OAuthButtons next={params.get('next')} />
      </div>
      <form className="relative space-y-5" onSubmit={submitting(() => mutation.mutate())}>
        {human.honeypot}
        <Field
          label={t('signIn.email')}
          type="email"
          required
          maxLength={254}
          autoComplete="username"
          autoFocus
          placeholder={t('auth.emailPlaceholder')}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <div className="space-y-2">
          <PasswordField
            label={t('signIn.password')}
            required
            maxLength={128}
            autoComplete="current-password"
            placeholder={t('auth.passwordPlaceholder')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="text-end">
            <Link className={`${LINK} text-sm`} to="/forgot-password">
              {t('auth.forgot')}
            </Link>
          </div>
        </div>
        {human.checkbox}
        {mutation.isError && !needsCheckbox(mutation.error) && (
          <Alert tone="error">
            {badCredentials(mutation.error)
              ? t('signIn.failed')
              : messageOf(mutation.error, t('signIn.unavailable'))}
          </Alert>
        )}
        {badCredentials(mutation.error) && (
          <p className="text-sm text-muted">{t('auth.googleHint')}</p>
        )}
        <SubmitButton door pending={mutation.isPending || human.waitingForCheckbox}>
          {mutation.isPending ? t('signIn.working') : t('signIn.submit')}
        </SubmitButton>
        {human.notice}
      </form>
    </AuthCard>
  );
}

export function SignUpPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ full_name: '', email: '', password: '' });
  const human = useHumanCheck('signup');
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      const proof = await human.proof();
      await unwrap(api.POST('/api/accounts/signup/', { body: { ...form, ...proof } }));
    },
    onError: (error) => {
      if (needsCheckbox(error)) human.requireCheckbox();
    },
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => {
    setForm({ ...form, [key]: e.target.value });
  };

  if (mutation.isSuccess) {
    return (
      <AuthCard title={t('auth.checkEmail')}>
        <p className="text-muted">{t('auth.checkEmailBody', { email: form.email })}</p>
        <Link className={LINK} to={`/login${params.size ? `?${params.toString()}` : ''}`}>
          {t('signIn.title')}
        </Link>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={t('auth.joinTitle')}
      subtitle={t('auth.joinBody')}
      footer={
        <>
          {t('auth.haveAccount')}{' '}
          <Link className={LINK} to="/login">
            {t('signIn.title')}
          </Link>
        </>
      }
    >
      <div className="mb-5">
        <OAuthButtons next={params.get('next')} />
      </div>
      <form className="relative space-y-5" onSubmit={submitting(() => mutation.mutate())}>
        {human.honeypot}
        <Field
          label={t('auth.fullName')}
          maxLength={150}
          autoComplete="name"
          autoFocus
          placeholder={t('auth.namePlaceholder')}
          value={form.full_name}
          onChange={set('full_name')}
        />
        <Field
          label={t('signIn.email')}
          type="email"
          required
          maxLength={254}
          autoComplete="email"
          placeholder={t('auth.emailPlaceholder')}
          value={form.email}
          onChange={set('email')}
        />
        <PasswordField
          label={t('signIn.password')}
          showStrength
          required
          minLength={12}
          maxLength={128}
          autoComplete="new-password"
          placeholder={t('auth.newPasswordPlaceholder')}
          value={form.password}
          onChange={set('password')}
        />
        <p className="text-xs text-muted">{t('auth.passwordHint')}</p>
        {human.checkbox}
        {mutation.isError && !needsCheckbox(mutation.error) && (
          <Alert tone="error">{messageOf(mutation.error, t('signIn.unavailable'))}</Alert>
        )}
        <SubmitButton door pending={mutation.isPending || human.waitingForCheckbox}>
          {t('auth.signUp')}
        </SubmitButton>
        {human.notice}
      </form>
    </AuthCard>
  );
}

/** A page opened from an emailed link: it sends the link's token once and says how it went. */
function EmailLinkPage({
  title,
  done,
  send,
}: {
  title: string;
  done: string;
  send: (token: string) => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const client = useQueryClient();
  const token = params.get('token') ?? '';
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      await send(token);
    },
    onSuccess: () => client.invalidateQueries({ queryKey: sessionKeys.me }),
  });
  const { mutate } = mutation;
  // Development mode runs effects twice, and a second send of a one-time link fails.
  const sent = useRef('');
  useEffect(() => {
    if (!token || sent.current === token) return;
    sent.current = token;
    mutate();
  }, [token, mutate]);

  return (
    <AuthCard title={title}>
      {mutation.isPending && <p className="text-muted">{t('auth.verifying')}</p>}
      {mutation.isSuccess && <Alert tone="success">{done}</Alert>}
      {(mutation.isError || !token) && (
        <Alert tone="error">{messageOf(mutation.error, t('auth.badLink'))}</Alert>
      )}
      <Link className={LINK} to="/app">
        {t('auth.continue')}
      </Link>
    </AuthCard>
  );
}

export function VerifyEmailPage() {
  const { t } = useTranslation();
  return (
    <EmailLinkPage
      title={t('auth.verifyTitle')}
      done={t('auth.verified')}
      send={(token) => unwrap(api.POST('/api/accounts/verify-email/', { body: { token } }))}
    />
  );
}

/** Opened from the link sent to a new address. The person may not be signed in on this device. */
export function ConfirmEmailPage() {
  const { t } = useTranslation();
  return (
    <EmailLinkPage
      title={t('auth.confirmTitle')}
      done={t('auth.emailChanged')}
      send={(token) => unwrap(api.POST('/api/accounts/email/confirm/', { body: { token } }))}
    />
  );
}

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const human = useHumanCheck('password_reset');
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      const proof = await human.proof();
      await unwrap(api.POST('/api/accounts/password-reset/', { body: { email, ...proof } }));
    },
    onError: (error) => {
      if (needsCheckbox(error)) human.requireCheckbox();
    },
  });
  return (
    <AuthCard title={t('auth.forgot')} subtitle={t('auth.forgotBody')}>
      {mutation.isSuccess ? (
        <Alert tone="success">{t('auth.resetSent')}</Alert>
      ) : (
        <form className="relative space-y-5" onSubmit={submitting(() => mutation.mutate())}>
          {human.honeypot}
          <Field
            label={t('signIn.email')}
            type="email"
            required
            maxLength={254}
            autoComplete="email"
            autoFocus
            placeholder={t('auth.emailPlaceholder')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {human.checkbox}
          {mutation.isError && !needsCheckbox(mutation.error) && (
            <Alert tone="error">{messageOf(mutation.error, t('signIn.unavailable'))}</Alert>
          )}
          <SubmitButton pending={mutation.isPending || human.waitingForCheckbox}>
            {t('auth.sendLink')}
          </SubmitButton>
          {human.notice}
        </form>
      )}
      <Link className={`${LINK} mt-6 inline-block text-sm`} to="/login">
        &larr; {t('signIn.title')}
      </Link>
    </AuthCard>
  );
}

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [password, setPassword] = useState('');
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      await unwrap(
        api.POST('/api/accounts/password-reset/confirm/', {
          body: { uid: params.get('uid') ?? '', token: params.get('token') ?? '', password },
        }),
      );
    },
  });
  return (
    <AuthCard title={t('auth.newPassword')} subtitle={t('auth.resetBody')}>
      {mutation.isSuccess ? (
        <>
          <Alert tone="success">{t('auth.passwordChanged')}</Alert>
          <Link className={LINK} to="/login">
            {t('signIn.title')}
          </Link>
        </>
      ) : (
        <form className="space-y-5" onSubmit={submitting(() => mutation.mutate())}>
          <PasswordField
            label={t('auth.newPassword')}
            showStrength
            required
            minLength={12}
            maxLength={128}
            autoComplete="new-password"
            autoFocus
            placeholder={t('auth.newPasswordPlaceholder')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p className="text-xs text-muted">{t('auth.passwordHint')}</p>
          {mutation.isError && (
            <Alert tone="error">{messageOf(mutation.error, t('auth.badLink'))}</Alert>
          )}
          <SubmitButton pending={mutation.isPending}>{t('auth.savePassword')}</SubmitButton>
        </form>
      )}
    </AuthCard>
  );
}

export function AcceptInvitePage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const me = useMe();
  const token = params.get('token') ?? '';
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      return unwrap(api.POST('/api/invitations/accept/', { body: { token } }));
    },
    onSuccess: async (membership) => {
      await client.invalidateQueries({ queryKey: sessionKeys.tenants });
      void navigate(`/app/${membership.tenant_slug}`);
    },
  });

  if (me.isPending) return null;
  if (!me.data) {
    const next = encodeURIComponent(`/accept-invite?token=${token}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return (
    <AuthCard title={t('auth.inviteTitle')}>
      <p className="text-muted">{t('auth.inviteBody', { email: me.data.email })}</p>
      {mutation.isError && (
        <Alert tone="error">{messageOf(mutation.error, t('auth.badLink'))}</Alert>
      )}
      <Button
        className="w-full"
        disabled={!token || mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {t('auth.join')}
      </Button>
    </AuthCard>
  );
}
