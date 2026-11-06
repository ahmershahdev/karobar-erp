import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Mascot } from '../features/mascot/Mascot';
import { canReachServer } from '../lib/online';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo } from './Logo';

type Status = 'lost' | 'checking' | 'restored';

const RETRY_EVERY = 6000;
const RESTORED_PAUSE = 1800;

/**
 * Shown when the app can't load a page without the network. It keeps checking on its own, and
 * when the connection returns it says so and carries on, so nobody has to know what to press.
 */
export function OfflineScreen() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<Status>('lost');
  const tips = t('offline.tips', { returnObjects: true }) as string[];

  const probe = useCallback(async () => {
    setStatus((await canReachServer()) ? 'restored' : 'lost');
  }, []);

  useEffect(() => {
    if (status === 'restored') return;
    const timer = window.setInterval(() => void probe(), RETRY_EVERY);
    return () => window.clearInterval(timer);
  }, [probe, status]);

  // The browser says the network came back: check right away, not at the next tick.
  useEffect(() => {
    const onOnline = () => void probe();
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, [probe]);

  useEffect(() => {
    if (status !== 'restored') return;
    const timer = window.setTimeout(() => window.location.reload(), RESTORED_PAUSE);
    return () => window.clearTimeout(timer);
  }, [status]);

  const restored = status === 'restored';
  return (
    <main className="shell flex min-h-[100svh] flex-col py-6">
      <div className="flex items-center justify-between">
        <Logo className="h-8 w-auto" />
        <LanguageSwitcher />
      </div>
      <div className="grid flex-1 items-center gap-8 py-10 md:grid-cols-2 md:gap-16">
        <Mascot
          moods={restored ? ['happy'] : ['searching', 'walking', 'confused']}
          label={t('mascot.label')}
          className="md:order-2"
        />
        <div className="space-y-6">
          <p
            role="status"
            className={`label inline-flex items-center gap-2 font-medium ${restored ? 'text-green' : 'text-red'}`}
          >
            <span
              className={`size-2 rounded-full ${restored ? 'bg-green' : 'animate-pulse bg-red'}`}
            />
            {t(`offline.status.${status}`)}
          </p>
          <h1 className="display-lg">{t(restored ? 'offline.restoredTitle' : 'offline.title')}</h1>
          <p className="max-w-md text-lg text-muted">
            {t(restored ? 'offline.restoredBody' : 'offline.body')}
          </p>
          {!restored && (
            <>
              <ul className="max-w-md space-y-3">
                {tips.map((tip, index) => (
                  <li key={tip} className="flex items-start gap-3">
                    <span className="grid size-7 shrink-0 place-items-center rounded-full bg-raised text-sm">
                      {index + 1}
                    </span>
                    <span className="pt-0.5">{tip}</span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className="btn btn-primary"
                disabled={status === 'checking'}
                onClick={() => {
                  setStatus('checking');
                  void probe();
                }}
              >
                {t('offline.retry')}
              </button>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
