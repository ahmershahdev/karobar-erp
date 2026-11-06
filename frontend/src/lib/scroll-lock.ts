import { getLenis } from './smooth-scroll';

// The loading screen and the page transition both cover the page; while either is up the page
// must not scroll underneath it and the scrollbar must not show. Each holder takes a named lock,
// so the transition finishing can't release the loading screen's lock or the other way round.
const holders = new Set<string>();

function apply(): void {
  const locked = holders.size > 0;
  document.documentElement.classList.toggle('scroll-locked', locked);
  const lenis = getLenis();
  if (locked) lenis?.stop();
  else lenis?.start();
}

export function lockScroll(holder: string): void {
  holders.add(holder);
  apply();
}

export function unlockScroll(holder: string): void {
  holders.delete(holder);
  apply();
}
