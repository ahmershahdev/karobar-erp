import type { JSX } from 'react';
import { useTranslation } from 'react-i18next';

import { env } from '../../lib/env';
import { safeNext } from '../../lib/paths';
import { useAuthConfig } from './human';

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
      <path
        fill="var(--color-brand-google-blue)"
        d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.4h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.2-2.1 3.5-5.1 3.5-8.7Z"
      />
      <path
        fill="var(--color-brand-google-green)"
        d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.3v3.1A12 12 0 0 0 12 24Z"
      />
      <path
        fill="var(--color-brand-google-yellow)"
        d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6h-4a12 12 0 0 0 0 10.8l4-3.1Z"
      />
      <path
        fill="var(--color-brand-google-red)"
        d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.3 6.6l4 3.1c.9-2.9 3.6-4.9 6.7-4.9Z"
      />
    </svg>
  );
}

function FacebookMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
      <path
        fill="var(--color-brand-facebook)"
        d="M24 12a12 12 0 1 0-13.9 11.9v-8.4H7.1V12h3V9.4c0-3 1.8-4.7 4.5-4.7 1.3 0 2.7.2 2.7.2v3h-1.5c-1.5 0-2 .9-2 1.9V12h3.4l-.5 3.5h-2.9v8.4A12 12 0 0 0 24 12Z"
      />
    </svg>
  );
}

const MARKS: Record<string, () => JSX.Element> = { google: GoogleMark, facebook: FacebookMark };

// Full-page navigations, not fetches: the provider's pages must open in the top window, and the
// callback signs the browser in with the normal session cookie.
export function OAuthButtons({ next }: { next?: string | null }) {
  const { t } = useTranslation();
  const config = useAuthConfig();
  const providers = (config.data?.oauth_providers ?? []).filter((name) => name in MARKS);
  if (providers.length === 0) return null;
  const target = safeNext(next);
  const query = target ? `?next=${encodeURIComponent(target)}` : '';
  return (
    <div className="space-y-3">
      {providers.map((name) => {
        const Mark = MARKS[name] ?? GoogleMark;
        return (
          <a
            key={name}
            href={`${env.apiBaseUrl}/api/accounts/oauth/${name}/start/${query}`}
            className="flex w-full items-center justify-center gap-3 rounded-full border border-line px-5 py-3 text-sm transition-colors hover:border-ember"
          >
            <Mark />
            {t(`auth.continueWith.${name}`)}
          </a>
        );
      })}
      <div className="flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-line" />
        {t('auth.orEmail')}
        <span className="h-px flex-1 bg-line" />
      </div>
    </div>
  );
}
