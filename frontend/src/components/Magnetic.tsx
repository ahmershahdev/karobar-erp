import { useEffect, useRef, type ReactNode } from 'react';

import { prefersReducedMotion } from '../lib/motion';

// Pulls its child toward the pointer while the pointer is near, then springs back.
export function Magnetic({
  children,
  strength = 0.35,
}: {
  children: ReactNode;
  strength?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element || prefersReducedMotion() || !window.matchMedia('(pointer: fine)').matches) return;
    const onMove = (event: PointerEvent) => {
      const rect = element.getBoundingClientRect();
      const x = event.clientX - (rect.left + rect.width / 2);
      const y = event.clientY - (rect.top + rect.height / 2);
      element.style.transform = `translate3d(${x * strength}px, ${y * strength}px, 0)`;
    };
    const onLeave = () => {
      element.style.transform = 'translate3d(0, 0, 0)';
    };
    element.addEventListener('pointermove', onMove);
    element.addEventListener('pointerleave', onLeave);
    return () => {
      element.removeEventListener('pointermove', onMove);
      element.removeEventListener('pointerleave', onLeave);
    };
  }, [strength]);

  return (
    <span
      ref={ref}
      className="inline-block transition-transform duration-500 ease-[var(--ease-out-expo)]"
    >
      {children}
    </span>
  );
}
