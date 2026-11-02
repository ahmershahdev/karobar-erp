import type Lenis from 'lenis';
import { useSyncExternalStore } from 'react';

// The Lenis instance lives outside React so any component can read it without the provider
// having to set state from an effect.
let current: Lenis | null = null;
const listeners = new Set<() => void>();

export function publishLenis(instance: Lenis | null): void {
  current = instance;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useLenis(): Lenis | null {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => null,
  );
}

export function scrollToTop(lenis: Lenis | null): void {
  if (lenis) lenis.scrollTo(0, { immediate: true });
  else window.scrollTo(0, 0);
}
