import { useEffect, useRef } from 'react';

import { useMediaQuery, useReducedMotion } from '../lib/motion';

type Mode = 'idle' | 'link' | 'stick' | 'text' | 'media';

const LINKS = 'a, button, select, label, [role="button"], [data-cursor]';
const TEXT = 'input, textarea, [contenteditable="true"]';
const MEDIA = 'img, canvas, video, [data-cursor-media]';

/**
 * Karobar's cursor: an orange ledger tick inside a trailing ring.
 *
 * - Over links the ring opens up and shows the element's data-cursor label.
 * - Over buttons and pills marked data-cursor-stick it wraps the element's own shape, like a
 *   highlighter laid over it, and leans toward the pointer.
 * - Over fields it becomes a thin caret, so it never hides where text will go.
 * - It shrinks on press, and fades out when the pointer leaves the window.
 * Fine pointers only, and never with reduced motion: touch and keyboard users keep the system's.
 */
export function Cursor() {
  const ring = useRef<HTMLDivElement>(null);
  const dot = useRef<HTMLDivElement>(null);
  const label = useRef<HTMLSpanElement>(null);
  const fine = useMediaQuery('(pointer: fine)');
  const reduced = useReducedMotion();

  useEffect(() => {
    if (!fine || reduced) return;
    const root = document.documentElement;
    const ringEl = ring.current;
    const dotEl = dot.current;
    if (!ringEl || !dotEl) return;
    root.classList.add('has-cursor');

    const pointer = { x: -100, y: -100 };
    const shape = { x: -100, y: -100, w: 36, h: 36, r: 18 };
    let mode: Mode = 'idle';
    let target: HTMLElement | null = null;
    let pressed = false;
    let visible = false;
    let frame = 0;

    const setMode = (next: Mode, element: HTMLElement | null) => {
      mode = next;
      target = element;
      ringEl.dataset.mode = next;
      if (label.current)
        label.current.textContent = next === 'link' ? (element?.dataset.cursor ?? '') : '';
    };

    const onMove = (event: PointerEvent) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      if (!visible) {
        visible = true;
        root.dataset.cursorVisible = 'true';
      }
    };
    const onOver = (event: PointerEvent) => {
      const element = event.target instanceof Element ? event.target : null;
      const stick = element?.closest<HTMLElement>('[data-cursor-stick]');
      const link = element?.closest<HTMLElement>(LINKS);
      if (stick) setMode('stick', stick);
      else if (element?.closest(TEXT)) setMode('text', null);
      else if (link) setMode('link', link);
      else if (element?.closest(MEDIA)) setMode('media', null);
      else setMode('idle', null);
    };
    const onLeave = () => {
      visible = false;
      root.dataset.cursorVisible = 'false';
    };
    const onDown = () => {
      pressed = true;
    };
    const onUp = () => {
      pressed = false;
    };

    const tick = () => {
      let goal = { x: pointer.x, y: pointer.y, w: 36, h: 36, r: 18 };
      if (mode === 'link') goal = { ...goal, w: 76, h: 76, r: 38 };
      if (mode === 'text') goal = { ...goal, w: 2, h: 26, r: 1 };
      if (mode === 'media') goal = { ...goal, w: 92, h: 92, r: 46 };
      if (mode === 'stick' && target?.isConnected) {
        const rect = target.getBoundingClientRect();
        const pull = 0.12;
        goal = {
          x: rect.left + rect.width / 2 + (pointer.x - (rect.left + rect.width / 2)) * pull,
          y: rect.top + rect.height / 2 + (pointer.y - (rect.top + rect.height / 2)) * pull,
          w: rect.width + 14,
          h: rect.height + 14,
          r: Math.min(
            rect.height + 14,
            parseFloat(getComputedStyle(target).borderRadius) + 7 || 12,
          ),
        };
      }
      const ease = mode === 'stick' ? 0.22 : 0.18;
      shape.x += (goal.x - shape.x) * ease;
      shape.y += (goal.y - shape.y) * ease;
      shape.w += (goal.w - shape.w) * 0.2;
      shape.h += (goal.h - shape.h) * 0.2;
      shape.r += (goal.r - shape.r) * 0.2;
      const scale = pressed ? 0.82 : 1;
      ringEl.style.transform = `translate3d(${shape.x - shape.w / 2}px, ${shape.y - shape.h / 2}px, 0) scale(${scale})`;
      ringEl.style.width = `${shape.w}px`;
      ringEl.style.height = `${shape.h}px`;
      ringEl.style.borderRadius = `${shape.r}px`;
      dotEl.style.transform = `translate3d(${pointer.x}px, ${pointer.y}px, 0) rotate(45deg) scale(${mode === 'idle' ? 1 : 0})`;
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
    <div
      aria-hidden="true"
      className="cursor-layer pointer-events-none fixed inset-0 z-[95] hidden [@media(pointer:fine)]:block"
    >
      <div
        ref={ring}
        className="cursor-ring absolute top-0 left-0 flex items-center justify-center"
      >
        <span ref={label} className="cursor-label" />
      </div>
      {/* A small rotated square: the tick an accountant puts beside a checked figure. */}
      <div ref={dot} className="cursor-dot absolute -top-[3px] -left-[3px] size-1.5" />
    </div>
  );
}
