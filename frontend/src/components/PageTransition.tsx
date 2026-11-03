import { createTimeline } from 'animejs';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, type Location } from 'react-router';

import { prefersReducedMotion } from '../lib/motion';
import { lockScroll, unlockScroll } from '../lib/scroll-lock';
import { scrollToTop, useLenis } from '../lib/smooth-scroll';
import { Logo, Wordmark } from './Logo';

function bothInApp(a: Location, b: Location): boolean {
  return a.pathname.startsWith('/app') && b.pathname.startsWith('/app');
}

interface Props {
  children: (location: Location) => ReactNode;
}

// The layers are taller than the screen and rounded at both ends, so their leading edge is a
// curve while it crosses the viewport and the screen is fully covered once they reach the
// middle position. Positions are in vh so the curve has the same depth on every screen.
const BELOW = '100vh';
const COVERING = '-30vh';
const ABOVE = '-170vh';

/**
 * An orange wave and then a navy panel sweep up over the page, the mark and wordmark show while
 * the route swaps underneath, and both carry on upward to reveal the new page. The old page
 * stays rendered until it is fully covered, nothing scrolls while the curtain is up, and screens
 * inside the app switch instantly.
 */
export function PageTransition({ children }: Props) {
  const location = useLocation();
  const [shown, setShown] = useState(location);
  const root = useRef<HTMLDivElement>(null);
  const lenis = useLenis();

  useEffect(() => {
    if (location.pathname === shown.pathname) return;
    if (bothInApp(location, shown)) return;
    const element = root.current;
    if (!element || prefersReducedMotion()) {
      setShown(location);
      scrollToTop(lenis);
      return;
    }
    const accent = element.querySelector('[data-accent]');
    const panel = element.querySelector('[data-panel]');
    const brand = element.querySelector('[data-brand]');
    if (!accent || !panel || !brand) return;
    lockScroll('transition');
    let cancelled = false;
    // Swapping the route re-runs this effect; once the reveal has started it owns the lock and
    // releases it when the curtain has fully gone.
    let revealing = false;
    const cover = createTimeline({
      onComplete: () => {
        if (cancelled) return;
        revealing = true;
        setShown(location);
        scrollToTop(lenis);
        createTimeline({ onComplete: () => unlockScroll('transition') })
          .add(
            brand,
            { opacity: [1, 0], translateY: ['0rem', '-1rem'], duration: 300, ease: 'inQuad' },
            120,
          )
          .add(panel, { translateY: [COVERING, ABOVE], duration: 900, ease: 'inOutQuart' }, 260)
          .add(accent, { translateY: [COVERING, ABOVE], duration: 900, ease: 'inOutQuart' }, 360);
      },
    })
      .add(accent, { translateY: [BELOW, COVERING], duration: 700, ease: 'inOutQuart' }, 0)
      .add(panel, { translateY: [BELOW, COVERING], duration: 700, ease: 'inOutQuart' }, 110)
      .add(
        brand,
        { opacity: [0, 1], translateY: ['1rem', '0rem'], duration: 400, ease: 'outQuart' },
        520,
      );
    return () => {
      cancelled = true;
      cover.pause();
      if (!revealing) unlockScroll('transition');
    };
  }, [location, shown, lenis]);

  return (
    <>
      {children(
        location.pathname === shown.pathname || bothInApp(location, shown) ? location : shown,
      )}
      <div ref={root} aria-hidden="true" className="pointer-events-none fixed inset-0 z-[85]">
        <div
          data-accent
          className="absolute inset-x-[-10vw] top-0 h-[170vh] rounded-[50%/14vh]"
          style={{ background: 'var(--gradient-molten)', transform: `translateY(${BELOW})` }}
        />
        <div
          data-panel
          className="absolute inset-x-[-10vw] top-0 h-[170vh] rounded-[50%/14vh] bg-canvas"
          style={{ transform: `translateY(${BELOW})` }}
        />
        <div
          data-brand
          className="absolute inset-0 flex flex-col items-center justify-center gap-4 opacity-0"
        >
          <Logo className="size-16 md:size-20" />
          <Wordmark className="text-4xl md:text-6xl" />
        </div>
      </div>
    </>
  );
}
