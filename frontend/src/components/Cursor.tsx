import { useEffect, useRef } from 'react';

import { prefersReducedMotion } from '../lib/motion';

const INTERACTIVE = 'a, button, select, input, textarea, label, [data-cursor]';

// A dot that follows the pointer exactly and a ring that trails it. The ring grows over
// anything clickable and shows that element's data-cursor label, if it has one.
export function Cursor() {
  const dot = useRef<HTMLDivElement>(null);
  const ring = useRef<HTMLDivElement>(null);
  const label = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const fine = window.matchMedia('(pointer: fine)').matches;
    if (!fine || prefersReducedMotion()) return;
    const root = document.documentElement;
    root.classList.add('has-cursor');

    const target = { x: -100, y: -100 };
    const trail = { x: -100, y: -100 };
    let frame = 0;
    let hovering = false;

    const onMove = (event: PointerEvent) => {
      target.x = event.clientX;
      target.y = event.clientY;
      if (dot.current) dot.current.style.transform = `translate3d(${target.x}px, ${target.y}px, 0)`;
    };
    const onOver = (event: PointerEvent) => {
      const element = (event.target as Element | null)?.closest<HTMLElement>(INTERACTIVE);
      hovering = Boolean(element);
      ring.current?.classList.toggle('is-active', hovering);
      if (label.current) label.current.textContent = element?.dataset.cursor ?? '';
    };
    const tick = () => {
      trail.x += (target.x - trail.x) * 0.16;
      trail.y += (target.y - trail.y) * 0.16;
      if (ring.current) {
        ring.current.style.transform = `translate3d(${trail.x}px, ${trail.y}px, 0)`;
      }
      frame = requestAnimationFrame(tick);
    };

    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerover', onOver, { passive: true });
    tick();
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerover', onOver);
      root.classList.remove('has-cursor');
    };
  }, []);

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-[95] hidden [@media(pointer:fine)]:block"
    >
      <div
        ref={dot}
        className="absolute -top-[3px] -left-[3px] size-1.5 rounded-full bg-cream mix-blend-difference"
      />
      <div ref={ring} className="cursor-ring absolute top-0 left-0">
        <div className="flex size-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-cream/40 transition-[width,height,background-color,border-color] duration-500 ease-[var(--ease-out-expo)] [.is-active>&]:size-16 [.is-active>&]:border-gold [.is-active>&]:bg-gold/10">
          <span ref={label} className="label !text-[0.6rem] !text-gold" />
        </div>
      </div>
    </div>
  );
}
