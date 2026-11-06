import { useSyncExternalStore } from 'react';

function subscribe(onChange: () => void): () => void {
  window.addEventListener('online', onChange);
  window.addEventListener('offline', onChange);
  return () => {
    window.removeEventListener('online', onChange);
    window.removeEventListener('offline', onChange);
  };
}

/** What the browser believes. It can say online on a dead Wi-Fi, so see `canReachServer`. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  );
}

/** A real round trip to our own server, skipping the browser and service worker caches. */
export async function canReachServer(): Promise<boolean> {
  try {
    const response = await fetch(`/favicon.png?ping=${Date.now()}`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(4000),
    });
    return response.ok;
  } catch {
    return false;
  }
}
