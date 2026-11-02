import { animate } from 'animejs';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, type Location } from 'react-router';

import { prefersReducedMotion } from '../lib/motion';
import { scrollToTop, useLenis } from '../lib/smooth-scroll';

function bothInApp(a: Location, b: Location): boolean {
  return a.pathname.startsWith('/app') && b.pathname.startsWith('/app');
}

interface Props {
  children: (location: Location) => ReactNode;
}

/**
 * Covers the page with an ink panel carrying the wordmark, swaps the route underneath, then
 * lifts the panel. The old page stays rendered until it is fully covered, so nothing pops.
 * Screens inside the app switch instantly; the curtain is for the public site.
 */
export function PageTransition({ children }: Props) {
  const location = useLocation();
  const [shown, setShown] = useState(location);
  const curtain = useRef<HTMLDivElement>(null);
  const lenis = useLenis();

  useEffect(() => {
    if (location.pathname === shown.pathname) return;
    if (bothInApp(location, shown)) return;
    const element = curtain.current;
    if (!element || prefersReducedMotion()) {
      setShown(location);
      scrollToTop(lenis);
      return;
    }
    let cancelled = false;
    const cover = animate(element, {
      clipPath: ['inset(100% 0 0 0)', 'inset(0% 0 0 0)'],
      duration: 650,
      ease: 'inOutExpo',
      onComplete: () => {
        if (cancelled) return;
        setShown(location);
        scrollToTop(lenis);
        animate(element, {
          clipPath: ['inset(0 0 0% 0)', 'inset(0 0 100% 0)'],
          duration: 750,
          delay: 120,
          ease: 'inOutExpo',
        });
      },
    });
    return () => {
      cancelled = true;
      cover.pause();
    };
  }, [location, shown, lenis]);

  return (
    <>
      {children(
        location.pathname === shown.pathname || bothInApp(location, shown) ? location : shown,
      )}
      <div
        ref={curtain}
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-[85] flex items-center justify-center bg-black [clip-path:inset(100%_0_0_0)]"
      >
        <span className="text-gradient font-display text-[18vw] leading-none">Karobar</span>
        <div
          className="absolute inset-x-0 bottom-0 h-px"
          style={{ background: 'var(--gradient-molten)' }}
        />
      </div>
    </>
  );
}
