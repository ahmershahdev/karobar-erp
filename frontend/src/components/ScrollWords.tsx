import { useEffect, useRef, type ElementType } from 'react';

import { prefersReducedMotion } from '../lib/motion';

interface Props {
  text: string;
  as?: ElementType;
  className?: string;
}

// Each word brightens as the paragraph crosses the screen, tied to the scroll position rather
// than to a timer, so reading speed sets the pace.
export function ScrollWords({ text, as: Tag = 'p', className }: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element || prefersReducedMotion()) return;
    const words = Array.from(element.querySelectorAll<HTMLElement>('[data-word]'));
    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = element.getBoundingClientRect();
      const start = window.innerHeight * 0.85;
      const end = window.innerHeight * 0.35;
      const progress = Math.min(
        1,
        Math.max(0, (start - rect.top) / (start - end + rect.height * 0.6)),
      );
      const lit = progress * words.length;
      words.forEach((word, index) => {
        word.style.opacity = String(0.16 + 0.84 * Math.min(1, Math.max(0, lit - index)));
      });
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [text]);

  return (
    <Tag ref={ref} className={className}>
      {text.split(' ').map((word, index) => (
        <span key={`${word}-${index}`} data-word className="transition-opacity duration-200">
          {word}{' '}
        </span>
      ))}
    </Tag>
  );
}
