import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

const RESTORED_FOR = 4000;

// A small notice for when the connection drops mid-session. It never covers the screen: someone
// halfway through a form must not lose sight of what they typed.
export function ConnectionNotice() {
  const { t } = useTranslation();
  const [state, setState] = useState<'online' | 'lost' | 'restored'>(() =>
    navigator.onLine ? 'online' : 'lost',
  );

  useEffect(() => {
    let timer = 0;
    const onOffline = () => {
      window.clearTimeout(timer);
      setState('lost');
    };
    const onOnline = () => {
      setState('restored');
      timer = window.setTimeout(() => setState('online'), RESTORED_FOR);
    };
    window.addEventListener('offline', onOffline);
    window.addEventListener('online', onOnline);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('offline', onOffline);
      window.removeEventListener('online', onOnline);
    };
  }, []);

  if (state === 'online') return null;
  const restored = state === 'restored';
  return (
    <div
      role="status"
      className="fixed inset-x-4 top-20 z-[80] mx-auto flex w-fit max-w-[calc(100%-2rem)] items-center gap-3 rounded-2xl border border-line bg-canvas px-4 py-3 shadow-[var(--shadow-float)]"
    >
      <span
        className={`size-2.5 shrink-0 rounded-full ${restored ? 'bg-green' : 'animate-pulse bg-red'}`}
      />
      <span className="text-sm">
        <strong className="font-medium">
          {t(restored ? 'connection.restored' : 'connection.lost')}
        </strong>{' '}
        <span className="text-muted">
          {t(restored ? 'connection.restoredBody' : 'connection.lostBody')}
        </span>
      </span>
    </div>
  );
}
