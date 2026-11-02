import { animate } from 'animejs';
import { useEffect, useRef, useState } from 'react';

import { prefersReducedMotion } from '../lib/motion';

// Shown once per page load: a counter runs to 100 while fonts settle, then the panel lifts.
// It never waits on the network, so it can't hold the page hostage on a slow connection.
export function Preloader() {
  // The app screens are for work, so they skip the intro.
  const [done, setDone] = useState(
    () => prefersReducedMotion() || window.location.pathname.startsWith('/app'),
  );
  const panel = useRef<HTMLDivElement>(null);
  const counter = useRef<HTMLSpanElement>(null);
  const bar = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (done) return;
    const state = { value: 0 };
    const count = animate(state, {
      value: 100,
      duration: 1100,
      ease: 'inOutQuad',
      onUpdate: () => {
        const value = Math.round(state.value);
        if (counter.current) counter.current.textContent = String(value).padStart(3, '0');
        if (bar.current) bar.current.style.transform = `scaleX(${value / 100})`;
      },
      onComplete: () => {
        if (!panel.current) return;
        animate(panel.current, {
          translateY: ['0%', '-100%'],
          duration: 900,
          ease: 'inOutExpo',
          onComplete: () => setDone(true),
        });
      },
    });
    return () => {
      count.pause();
    };
  }, [done]);

  if (done) return null;
  return (
    <div
      ref={panel}
      aria-hidden="true"
      className="fixed inset-0 z-[90] flex flex-col justify-between bg-black p-[var(--gutter)]"
    >
      <div className="label flex justify-between">
        <span>Karobar ERP</span>
        <span>v0.1</span>
      </div>
      <div className="space-y-4">
        <span
          ref={counter}
          className="block font-display text-[clamp(5rem,22vw,16rem)] leading-none tabular-nums"
        >
          000
        </span>
        <div className="h-px w-full bg-line">
          <div ref={bar} className="h-px origin-left scale-x-0 bg-gold rtl:origin-right" />
        </div>
      </div>
    </div>
  );
}
