import { animate, stagger } from 'animejs';
import { useEffect, useRef } from 'react';

import { prefersReducedMotion } from '../lib/motion';

interface Props {
  text: string;
  className?: string;
}

// Splits by word, not by letter: Urdu and Arabic letters join, and splitting them would break
// the script apart. Screen readers get the whole sentence from aria-label.
export function SplitHeadline({ text, className }: Props) {
  const ref = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const words = ref.current?.querySelectorAll<HTMLElement>('[data-word]');
    if (!words?.length || prefersReducedMotion()) return;
    const animation = animate(words, {
      translateY: ['110%', '0%'],
      rotate: ['6deg', '0deg'],
      opacity: [0, 1],
      duration: 1400,
      delay: stagger(70, { start: 250 }),
      ease: 'outExpo',
    });
    return () => {
      animation.revert();
    };
  }, [text]);

  return (
    <h1 ref={ref} className={className} aria-label={text} data-split>
      {text.split(' ').map((word, index) => (
        <span
          key={`${word}-${index}`}
          aria-hidden="true"
          className="inline-block overflow-hidden pb-[0.12em] align-bottom"
        >
          <span data-word className="inline-block will-change-transform">
            {word}
          </span>
          {' '}
        </span>
      ))}
    </h1>
  );
}
