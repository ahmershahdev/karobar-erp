import { animate } from 'animejs';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, type Location } from 'react-router';

import { prefersReducedMotion } from '../lib/motion';
import { scrollToTop, useLenis } from '../lib/smooth-scroll';

interface Props {
  children: (location: Location) => ReactNode;
}

/**
 * Covers the page with a gradient curtain, swaps the route underneath, then lifts the curtain.
 * The old page stays rendered until it is fully covered, so nothing pops.
 */
export function PageTransition({ children }: Props) {
  const location = useLocation();
  const [shown, setShown] = useState(location);
  const curtain = useRef<HTMLDivElement>(null);
  const lenis = useLenis();

  useEffect(() => {
    if (location.pathname === shown.pathname) return;
    const element = curtain.current;
    if (!element || prefersReducedMotion()) {
      setShown(location);
      scrollToTop(lenis);
      return;
    }
    let cancelled = false;
    element.style.transformOrigin = '50% 100%';
    const cover = animate(element, {
      scaleY: [0, 1],
      duration: 520,
      ease: 'inOutQuart',
      onComplete: () => {
        if (cancelled) return;
        setShown(location);
        scrollToTop(lenis);
        element.style.transformOrigin = '50% 0%';
        animate(element, { scaleY: [1, 0], duration: 620, delay: 80, ease: 'inOutQuart' });
      },
    });
    return () => {
      cancelled = true;
      cover.pause();
    };
  }, [location, shown, lenis]);

  return (
    <>
      {children(location.pathname === shown.pathname ? location : shown)}
      <div
        ref={curtain}
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-50 origin-bottom scale-y-0"
        style={{ background: 'var(--gradient-aurora)' }}
      >
        <div
          className="absolute inset-x-0 bottom-0 h-1"
          style={{ background: 'var(--gradient-ledger)' }}
        />
      </div>
    </>
  );
}
