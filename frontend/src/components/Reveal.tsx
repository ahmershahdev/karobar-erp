import { animate, stagger } from 'animejs';
import { useEffect, useRef, type ElementType, type ReactNode } from 'react';

import { prefersReducedMotion } from '../lib/motion';

interface Props {
  children: ReactNode;
  as?: ElementType;
  className?: string;
  // Animate direct children one after another instead of the wrapper as one block.
  stagger?: boolean;
  delay?: number;
}

export function Reveal({
  children,
  as: Tag = 'div',
  className,
  stagger: staggered,
  delay = 0,
}: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element || prefersReducedMotion()) return;
    const targets = staggered ? Array.from(element.children) : [element];
    for (const target of targets) (target as HTMLElement).style.opacity = '0';

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        observer.disconnect();
        animate(targets, {
          opacity: [0, 1],
          translateY: ['2.5rem', '0rem'],
          filter: ['blur(8px)', 'blur(0px)'],
          duration: 1100,
          delay: staggered ? stagger(90, { start: delay }) : delay,
          ease: 'outExpo',
        });
      },
      { rootMargin: '0px 0px -12% 0px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [staggered, delay]);

  return (
    <Tag ref={ref} className={className}>
      {children}
    </Tag>
  );
}
