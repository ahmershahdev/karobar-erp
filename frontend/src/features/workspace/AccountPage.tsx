import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { ConfirmButton } from '../../components/ConfirmButton';
import { Alert, Button, Field, PasswordField } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { ensureCsrf, sessionKeys } from '../auth/session';
import { errorText, useWorkspace } from './hooks';
import { PageTitle, Panel } from './ui';

function useAccountAction<T>(call: (value: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (value: T) => {
      await ensureCsrf();
      return call(value);
    },
    onSuccess: () => client.invalidateQueries({ queryKey: sessionKeys.me }),
  });
}

function Outcome({
  action,
  done,
}: {
  action: { isError: boolean; isSuccess: boolean; error: unknown };
  done: ReactNode;
}) {
  const { t } = useTranslation();
  if (action.isError) {
    return <Alert tone="error">{errorText(action.error, t('signIn.unavailable'))}</Alert>;
  }
  return action.isSuccess ? <Alert tone="success">{done}</Alert> : null;
}

function NoPassword() {
  const { t } = useTranslation();
  return (
    <p className="text-sm text-muted">
      {t('account.noPassword')}{' '}
      <Link className="underline underline-offset-4" to="/forgot-password">
        {t('account.setPassword')}
      </Link>
    </p>
  );
}

function NameForm() {
  const { t } = useTranslation();
  const { me } = useWorkspace();
  const [name, setName] = useState(me.full_name);
  const save = useAccountAction((full_name: string) =>
    unwrap(api.PATCH('/api/accounts/me/', { body: { full_name } })),
  );
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    save.mutate(name);
  };
  return (
    <Panel title={t('account.nameTitle')}>
      <form className="max-w-md space-y-4" onSubmit={submit}>
        <Field
          label={t('account.name')}
          autoComplete="name"
          maxLength={150}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Outcome action={save} done={t('account.saved')} />
        <Button type="submit" disabled={save.isPending || name.trim() === me.full_name}>
          {t('account.save')}
        </Button>
      </form>
    </Panel>
  );
}

function EmailForm() {
  const { t } = useTranslation();
  const { me } = useWorkspace();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [sentTo, setSentTo] = useState('');
  const send = useAccountAction(async (body: { email: string; current_password: string }) => {
    await unwrap(api.POST('/api/accounts/email/', { body }));
    setSentTo(body.email);
    setEmail('');
    setPassword('');
  });
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    send.mutate({ email: email.trim(), current_password: password });
  };
  return (
    <Panel title={t('account.emailTitle')}>
      <p className="mb-4 text-sm text-muted">{t('account.currentEmail', { email: me.email })}</p>
      {me.has_password ? (
        <form className="max-w-md space-y-4" onSubmit={submit}>
          <Field
            label={t('account.newEmail')}
            type="email"
            autoComplete="email"
            required
            maxLength={254}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <PasswordField
            label={t('account.currentPassword')}
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Outcome action={send} done={t('account.linkSent', { email: sentTo })} />
          <Button type="submit" disabled={send.isPending}>
            {t('account.sendLink')}
          </Button>
        </form>
      ) : (
        <NoPassword />
      )}
    </Panel>
  );
}

function PasswordForm() {
  const { t } = useTranslation();
  const { me } = useWorkspace();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const change = useAccountAction(async (body: { current_password: string; password: string }) => {
    await unwrap(api.POST('/api/accounts/password/', { body }));
    setCurrent('');
    setNext('');
  });
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    change.mutate({ current_password: current, password: next });
  };
  return (
    <Panel title={t('account.passwordTitle')}>
      {me.has_password ? (
        <form className="max-w-md space-y-4" onSubmit={submit}>
          <PasswordField
            label={t('account.currentPassword')}
            autoComplete="current-password"
            required
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
          <PasswordField
            label={t('account.newPassword')}
            autoComplete="new-password"
            showStrength
            required
            minLength={12}
            value={next}
            onChange={(event) => setNext(event.target.value)}
          />
          <Outcome action={change} done={t('account.passwordChanged')} />
          <Button type="submit" disabled={change.isPending}>
            {t('account.changePassword')}
          </Button>
        </form>
      ) : (
        <NoPassword />
      )}
    </Panel>
  );
}

function DeleteForm() {
  const { t } = useTranslation();
  const { me } = useWorkspace();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const remove = useMutation({
    mutationFn: async () => {
      await ensureCsrf();
      await unwrap(
        api.POST('/api/accounts/delete/', { body: { current_password: password, email } }),
      );
    },
    onSuccess: () => {
      // Nothing cached about the old account may show after it is gone.
      client.clear();
      void navigate('/', { replace: true });
    },
  });
  const typed = email.trim().toLowerCase() === me.email;
  return (
    <Panel title={t('account.deleteTitle')}>
      <p className="mb-4 max-w-prose text-sm text-muted">{t('account.deleteBody')}</p>
      {me.has_password ? (
        <div className="max-w-md space-y-4">
          <PasswordField
            label={t('account.currentPassword')}
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Field
            label={t('account.typeEmail', { email: me.email })}
            autoComplete="off"
            spellCheck={false}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          {remove.isError && (
            <Alert tone="error">{errorText(remove.error, t('signIn.unavailable'))}</Alert>
          )}
          <ConfirmButton
            message={t('confirm.deleteAccount')}
            disabled={remove.isPending || !password || !typed}
            onConfirm={() => remove.mutate()}
          >
            {t('account.deleteButton')}
          </ConfirmButton>
        </div>
      ) : (
        <NoPassword />
      )}
    </Panel>
  );
}

/** Settings that belong to the person, not to the business they are looking at. */
export function AccountPage() {
  const { t } = useTranslation();
  return (
    <>
      <PageTitle title={t('account.title')} subtitle={t('account.subtitle')} />
      <NameForm />
      <EmailForm />
      <PasswordForm />
      <DeleteForm />
    </>
  );
}
