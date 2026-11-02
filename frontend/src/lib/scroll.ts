import { useSyncExternalStore } from 'react';

export interface ScrollState {
  y: number;
  progress: number;
  direction: 'up' | 'down';
}

// One passive scroll listener shared by every component that cares (header, back-to-top ring),
// throttled to animation frames.
let state: ScrollState = { y: 0, progress: 0, direction: 'up' };
const listeners = new Set<() => void>();
let frame = 0;

function read(): void {
  frame = 0;
  const y = window.scrollY;
  const room = document.documentElement.scrollHeight - window.innerHeight;
  const direction = Math.abs(y - state.y) < 4 ? state.direction : y > state.y ? 'down' : 'up';
  state = { y, progress: room > 0 ? Math.min(1, y / room) : 0, direction };
  for (const listener of listeners) listener();
}

function onScroll(): void {
  if (!frame) frame = requestAnimationFrame(read);
}

function subscribe(listener: () => void): () => void {
  if (listeners.size === 0) {
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    read();
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    }
  };
}

export function useScroll(): ScrollState {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => state,
  );
}
