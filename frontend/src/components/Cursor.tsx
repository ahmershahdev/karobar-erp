import { useEffect, useRef } from 'react';

import { useMediaQuery, useReducedMotion } from '../lib/motion';

const CLICKABLE = 'a, button, select, label, summary, [role="button"], [role="tab"]';
const TYPING = 'input, textarea, [contenteditable="true"]';

/**
 * A small orange dot that sits exactly on the pointer, and a thin ring that follows a little
 * behind it. Over anything clickable the ring opens up and the dot hides; nothing is ever drawn
 * on top of the element itself (no fills, blurs or blend modes), so buttons keep their colours.
 * Over text fields both step aside and the system I-beam shows, so typing is never guessed at.
 * Fine pointers only, and never with reduced motion.
 */
export function Cursor() {
  const ring = useRef<HTMLDivElement>(null);
  const dot = useRef<HTMLDivElement>(null);
  const fine = useMediaQuery('(pointer: fine)');
  const reduced = useReducedMotion();

  useEffect(() => {
    const ringEl = ring.current;
    const dotEl = dot.current;
    if (!fine || reduced || !ringEl || !dotEl) return;
    const root = document.documentElement;
    root.classList.add('has-cursor');

    const pointer = { x: -100, y: -100 };
    const trail = { x: -100, y: -100, size: 34 };
    let state: 'idle' | 'hover' | 'typing' = 'idle';
    let pressed = false;
    let frame = 0;

    const onMove = (event: PointerEvent) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      root.dataset.cursorVisible = 'true';
    };
    const onOver = (event: PointerEvent) => {
      const element = event.target instanceof Element ? event.target : null;
      const next = element?.closest(TYPING)
        ? 'typing'
        : element?.closest(CLICKABLE)
          ? 'hover'
          : 'idle';
      if (next !== state) {
        state = next;
        ringEl.dataset.state = next;
        dotEl.dataset.state = next;
      }
    };
    const onLeave = () => {
      root.dataset.cursorVisible = 'false';
    };
    const onDown = () => {
      pressed = true;
    };
    const onUp = () => {
      pressed = false;
    };

    const tick = () => {
      trail.x += (pointer.x - trail.x) * 0.2;
      trail.y += (pointer.y - trail.y) * 0.2;
      const goal = state === 'hover' ? 56 : 34;
      trail.size += (goal - trail.size) * 0.18;
      const scale = pressed ? 0.85 : 1;
      ringEl.style.transform = `translate3d(${trail.x - trail.size / 2}px, ${trail.y - trail.size / 2}px, 0) scale(${scale})`;
      ringEl.style.width = ringEl.style.height = `${trail.size}px`;
      dotEl.style.transform = `translate3d(${pointer.x - 3}px, ${pointer.y - 3}px, 0)`;
      frame = requestAnimationFrame(tick);
    };

    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerover', onOver, { passive: true });
    window.addEventListener('pointerdown', onDown, { passive: true });
    window.addEventListener('pointerup', onUp, { passive: true });
    document.addEventListener('pointerleave', onLeave);
    tick();
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerover', onOver);
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('pointerup', onUp);
      document.removeEventListener('pointerleave', onLeave);
      root.classList.remove('has-cursor');
      delete root.dataset.cursorVisible;
    };
  }, [fine, reduced]);

  return (
    <div aria-hidden="true" className="cursor-layer pointer-events-none fixed inset-0 z-[95]">
      <div ref={ring} className="cursor-ring absolute top-0 left-0 rounded-full" />
      <div ref={dot} className="cursor-dot absolute top-0 left-0 size-1.5 rounded-full" />
    </div>
  );
}
