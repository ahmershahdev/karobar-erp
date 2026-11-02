import { prefersReducedMotion } from './motion';

// True only while the intro of this page load is still on screen. The hero reads it to decide
// whether to wait for the preloader to lift; later visits to the home page start straight away.
let introPending =
  typeof window !== 'undefined' &&
  !prefersReducedMotion() &&
  !window.location.pathname.startsWith('/app');

export function isIntroPending(): boolean {
  return introPending;
}

export function finishIntro(): void {
  introPending = false;
}
