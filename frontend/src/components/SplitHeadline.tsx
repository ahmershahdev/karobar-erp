import { animate, stagger } from 'animejs';
import { useEffect, useRef } from 'react';

import { prefersReducedMotion } from '../lib/motion';

interface Props {
  text: string;
  accent?: string;
  className?: string;
  delay?: number;
}

function words(text: string, italic: boolean) {
  return text.split(' ').map((word, index) => (
    <span
      key={`${word}-${index}`}
      aria-hidden="true"
      className="me-[0.24em] inline-block overflow-hidden pb-[0.08em] align-bottom last:me-0"
    >
      <span
        data-word
        className={`inline-block will-change-transform ${italic ? 'text-gradient pe-[0.06em] italic' : ''}`}
      >
        {word}
      </span>
    </span>
  ));
}

// Splits by word, never by letter: Urdu and Arabic letters join, and splitting them would break
// the script apart. Screen readers get the whole sentence from aria-label.
export function SplitHeadline({ text, accent, className, delay = 200 }: Props) {
  const ref = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const targets = ref.current?.querySelectorAll<HTMLElement>('[data-word]');
    if (!targets?.length || prefersReducedMotion()) return;
    const animation = animate(targets, {
      translateY: ['105%', '0%'],
      rotate: ['4deg', '0deg'],
      duration: 1500,
      delay: stagger(60, { start: delay }),
      ease: 'outExpo',
    });
    return () => {
      animation.revert();
    };
  }, [text, accent, delay]);

  return (
    <h1 ref={ref} className={className} aria-label={accent ? `${text} ${accent}` : text} data-split>
      {words(text, false)}
      {accent && (
        <>
          <br />
          {words(accent, true)}
        </>
      )}
    </h1>
  );
}
