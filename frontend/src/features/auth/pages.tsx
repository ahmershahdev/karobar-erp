import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router';

import { Alert, Button, Field, PasswordField, SubmitButton } from '../../components/form';
import { api } from '../../lib/api/client';
import { ApiError, unwrap } from '../../lib/api/errors';
import { AuthCard } from './AuthCard';
import { ensureCsrf, sessionKeys, useMe } from './session';

function messageOf(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.status < 500 ? error.message : fallback;
}

function submitting(handler: () => void) {
  return (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    handler();
  };
}

const LINK = 'text-gold underline-offset-4 hover:underline';

export function SignInPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      return unwrap(api.POST('/api/accounts/login/', { body: { email, password } }));
    },
    onSuccess: async (me) => {
      client.setQueryData(sessionKeys.me, me);
      await client.invalidateQueries({ queryKey: sessionKeys.tenants });
      const next = params.get('next');
      void navigate(next?.startsWith('/app') ? next : '/app');
    },
  });

  return (
    <AuthCard
      title={t('auth.welcome')}
      subtitle={t('auth.welcomeBody')}
      footer={
        <>
          {t('auth.noAccount')}{' '}
          <Link className={LINK} to={`/app/sign-up${params.size ? `?${params.toString()}` : ''}`}>
            {t('auth.signUp')}
          </Link>
        </>
      }
    >
      <form className="space-y-5" onSubmit={submitting(() => mutation.mutate())}>
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
            <Link className={`${LINK} text-sm`} to="/app/forgot-password">
              {t('auth.forgot')}
            </Link>
          </div>
        </div>
        {mutation.isError && (
          <Alert tone="error">
            {mutation.error instanceof ApiError && mutation.error.status === 403
              ? t('signIn.failed')
              : t('signIn.unavailable')}
          </Alert>
        )}
        <SubmitButton pending={mutation.isPending}>
          {mutation.isPending ? t('signIn.working') : t('signIn.submit')}
        </SubmitButton>
      </form>
    </AuthCard>
  );
}

export function SignUpPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ full_name: '', email: '', password: '' });
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      await unwrap(api.POST('/api/accounts/signup/', { body: form }));
    },
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => {
    setForm({ ...form, [key]: e.target.value });
  };

  if (mutation.isSuccess) {
    return (
      <AuthCard title={t('auth.checkEmail')}>
        <p className="text-muted">{t('auth.checkEmailBody', { email: form.email })}</p>
        <Link className={LINK} to={`/app/sign-in${params.size ? `?${params.toString()}` : ''}`}>
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
          <Link className={LINK} to="/app/sign-in">
            {t('signIn.title')}
          </Link>
        </>
      }
    >
      <form className="space-y-5" onSubmit={submitting(() => mutation.mutate())}>
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
        {mutation.isError && (
          <Alert tone="error">{messageOf(mutation.error, t('signIn.unavailable'))}</Alert>
        )}
        <SubmitButton pending={mutation.isPending}>{t('auth.signUp')}</SubmitButton>
      </form>
    </AuthCard>
  );
}

export function VerifyEmailPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const client = useQueryClient();
  const token = params.get('token') ?? '';
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      await unwrap(api.POST('/api/accounts/verify-email/', { body: { token } }));
    },
    onSuccess: () => client.invalidateQueries({ queryKey: sessionKeys.me }),
  });
  const { mutate } = mutation;
  useEffect(() => {
    if (token) mutate();
  }, [token, mutate]);

  return (
    <AuthCard title={t('auth.verifyTitle')}>
      {mutation.isPending && <p className="text-muted">{t('auth.verifying')}</p>}
      {mutation.isSuccess && <Alert tone="success">{t('auth.verified')}</Alert>}
      {(mutation.isError || !token) && (
        <Alert tone="error">{messageOf(mutation.error, t('auth.badLink'))}</Alert>
      )}
      <Link className={LINK} to="/app">
        {t('auth.continue')}
      </Link>
    </AuthCard>
  );
}

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const mutation = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      await unwrap(api.POST('/api/accounts/password-reset/', { body: { email } }));
    },
  });
  return (
    <AuthCard title={t('auth.forgot')} subtitle={t('auth.forgotBody')}>
      {mutation.isSuccess ? (
        <Alert tone="success">{t('auth.resetSent')}</Alert>
      ) : (
        <form className="space-y-5" onSubmit={submitting(() => mutation.mutate())}>
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
          {mutation.isError && (
            <Alert tone="error">{messageOf(mutation.error, t('signIn.unavailable'))}</Alert>
          )}
          <SubmitButton pending={mutation.isPending}>{t('auth.sendLink')}</SubmitButton>
        </form>
      )}
      <Link className={`${LINK} mt-6 inline-block text-sm`} to="/app/sign-in">
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
          <Link className={LINK} to="/app/sign-in">
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
      void navigate(`/app/t/${membership.tenant_id}`);
    },
  });

  if (me.isPending) return null;
  if (!me.data) {
    const next = encodeURIComponent(`/app/accept-invite?token=${token}`);
    return <Navigate to={`/app/sign-in?next=${next}`} replace />;
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
