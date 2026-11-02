import { useMutation } from '@tanstack/react-query';
import { useState, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Logo } from '../components/Logo';
import { api } from '../lib/api/client';
import { usePrivateSeo } from '../lib/seo';

class SignInError extends Error {
  constructor(readonly kind: 'failed' | 'unavailable') {
    super(kind);
  }
}

async function signIn(credentials: { email: string; password: string }) {
  await api.GET('/api/accounts/csrf/');
  const { data, response } = await api.POST('/api/accounts/login/', { body: credentials });
  if (data) return data;
  throw new SignInError(
    response.status === 401 || response.status === 403 ? 'failed' : 'unavailable',
  );
}

export default function SignInPage() {
  const { t } = useTranslation();
  usePrivateSeo(t('signIn.title'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const mutation = useMutation({ mutationFn: signIn });

  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    mutation.mutate({ email, password });
  };

  const errorKind = mutation.error instanceof SignInError ? mutation.error.kind : 'unavailable';

  return (
    <section className="flex min-h-[100svh] items-center justify-center px-4 pt-[var(--header-height)]">
      <form
        onSubmit={submit}
        className="gradient-border w-full max-w-md space-y-6 p-8"
        noValidate={false}
      >
        <div className="flex items-center gap-3">
          <Logo className="size-9" />
          <h1 className="text-3xl">{t('signIn.title')}</h1>
        </div>
        <label className="block space-y-2">
          <span className="text-sm text-muted">{t('signIn.email')}</span>
          <input
            type="email"
            required
            maxLength={254}
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full rounded-xl border border-line bg-black/40 px-4 py-3 outline-none transition-colors focus:border-gold"
          />
        </label>
        <label className="block space-y-2">
          <span className="text-sm text-muted">{t('signIn.password')}</span>
          <input
            type="password"
            required
            maxLength={128}
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-xl border border-line bg-black/40 px-4 py-3 outline-none transition-colors focus:border-gold"
          />
        </label>
        {mutation.isError && (
          <p
            role="alert"
            className="rounded-xl border border-coral/40 bg-coral/10 px-4 py-3 text-sm text-coral"
          >
            {t(`signIn.${errorKind}`)}
          </p>
        )}
        {mutation.isSuccess && (
          <p role="status" className="text-sm text-mint">
            {mutation.data.email}
          </p>
        )}
        <button
          type="submit"
          disabled={mutation.isPending}
          className="w-full rounded-full py-3 font-medium text-black transition-opacity disabled:opacity-60"
          style={{ background: 'var(--gradient-ledger)' }}
        >
          {mutation.isPending ? t('signIn.working') : t('signIn.submit')}
        </button>
      </form>
    </section>
  );
}
