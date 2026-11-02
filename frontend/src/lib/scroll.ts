import { useSyncExternalStore } from 'react';

export interface ScrollState {
  y: number;
  progress: number;
  direction: 'up' | 'down';
}

// One passive scroll listener shared by every component that cares (header, back-to-top ring),
// throttled to animation frames.
let state: ScrollState = { y: 0, progress: 0, direction: 'up' };
// Where the current direction was last confirmed. Measuring from here, not from the previous
// frame, means a slow scroll of a pixel or two per frame still flips the direction.
let anchor = 0;
const listeners = new Set<() => void>();
let frame = 0;
const THRESHOLD = 8;

function read(): void {
  frame = 0;
  const y = window.scrollY;
  const room = document.documentElement.scrollHeight - window.innerHeight;
  let direction = state.direction;
  if (Math.abs(y - anchor) >= THRESHOLD) {
    direction = y > anchor ? 'down' : 'up';
    anchor = y;
  } else if ((direction === 'down' && y > anchor) || (direction === 'up' && y < anchor)) {
    anchor = y;
  }
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
