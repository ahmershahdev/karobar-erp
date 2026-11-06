import Lenis from 'lenis';
import { useEffect, type ReactNode } from 'react';

import { useReducedMotion } from './motion';
import { publishLenis } from './smooth-scroll';

export function SmoothScroll({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced) return;
    const instance = new Lenis({ lerp: 0.09, wheelMultiplier: 0.9, autoRaf: true });
    publishLenis(instance);
    // A loading screen that started before Lenis existed still holds its lock.
    if (document.documentElement.classList.contains('scroll-locked')) instance.stop();
    return () => {
      instance.destroy();
      publishLenis(null);
    };
  }, [reduced]);

  return children;
}
