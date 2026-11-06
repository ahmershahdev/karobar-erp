import { animate } from 'animejs';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, type Location } from 'react-router';

import { prefersReducedMotion } from '../lib/motion';
import { isAppPath } from '../lib/paths';
import { lockScroll, unlockScroll } from '../lib/scroll-lock';
import { scrollToTop, useLenis } from '../lib/smooth-scroll';

// The veil belongs to the public site. Going to or from sign-in, or anywhere in the app, someone
// is trying to get something done, so the screen just changes.
function touchesApp(a: Location, b: Location): boolean {
  return isAppPath(a.pathname) || isAppPath(b.pathname);
}

interface Props {
  children: (location: Location) => ReactNode;
}

/**
 * Between public pages, a white veil fades in, the route swaps underneath it, and it fades away.
 * The old page stays rendered until it is covered and nothing scrolls meanwhile.
 */
export function PageTransition({ children }: Props) {
  const location = useLocation();
  const [shown, setShown] = useState(location);
  const veil = useRef<HTMLDivElement>(null);
  const lenis = useLenis();

  useEffect(() => {
    if (location.pathname === shown.pathname) return;
    const element = veil.current;
    if (!element || touchesApp(location, shown) || prefersReducedMotion()) {
      setShown(location);
      scrollToTop(lenis);
      return;
    }
    lockScroll('transition');
    let cancelled = false;
    // Swapping the route re-runs this effect; once the reveal has started it owns the lock and
    // releases it when the veil has gone.
    let revealing = false;
    const cover = animate(element, {
      opacity: [0, 1],
      duration: 240,
      ease: 'outQuad',
      onComplete: () => {
        if (cancelled) return;
        revealing = true;
        setShown(location);
        scrollToTop(lenis);
        animate(element, {
          opacity: [1, 0],
          duration: 360,
          delay: 60,
          ease: 'inOutQuad',
          onComplete: () => unlockScroll('transition'),
        });
      },
    });
    return () => {
      cancelled = true;
      cover.pause();
      if (!revealing) unlockScroll('transition');
    };
  }, [location, shown, lenis]);

  return (
    <>
      {children(
        location.pathname === shown.pathname || touchesApp(location, shown) ? location : shown,
      )}
      <div
        ref={veil}
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-[85] bg-canvas opacity-0"
      />
    </>
  );
}
