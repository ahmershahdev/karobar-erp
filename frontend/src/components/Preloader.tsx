import { createTimeline, stagger } from 'animejs';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { finishIntro, isIntroPending } from '../lib/intro';

// The intro runs once per page load and never waits on the network: the logo draws itself, the
// four things Karobar keeps cycle past, and the screen opens like a ledger, top half up and
// bottom half down. About two seconds; skipped for reduced motion and on app screens.
export function Preloader() {
  const { t } = useTranslation();
  const [done, setDone] = useState(() => !isIntroPending());
  const root = useRef<HTMLDivElement>(null);
  const counter = useRef<HTMLSpanElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  const words = t('preloader.words', { returnObjects: true }) as string[];

  useEffect(() => {
    const element = root.current;
    if (done || !element) return;
    const state = { value: 0 };
    const timeline = createTimeline({
      onComplete: () => {
        finishIntro();
        setDone(true);
      },
    });
    timeline
      .add(element.querySelectorAll('[data-stroke]'), {
        strokeDashoffset: [120, 0],
        duration: 900,
        delay: stagger(120),
        ease: 'inOutQuart',
      })
      .add(
        element.querySelectorAll('[data-fill]'),
        { opacity: [0, 1], duration: 400, ease: 'outQuad' },
        '-=300',
      )
      .add(
        state,
        {
          value: 100,
          duration: 1500,
          ease: 'inOutQuart',
          onUpdate: () => {
            const value = Math.round(state.value);
            if (counter.current) counter.current.textContent = String(value).padStart(3, '0');
            if (bar.current) bar.current.style.transform = `scaleX(${value / 100})`;
          },
        },
        0,
      )
      .add(
        element.querySelectorAll('[data-word]'),
        {
          translateY: ['100%', '0%', '0%', '-100%'],
          duration: 520,
          delay: stagger(340),
          ease: 'inOutQuart',
        },
        150,
      )
      .add(element.querySelector('[data-content]') ?? [], { opacity: [1, 0], duration: 300 }, 1700)
      .add(
        element.querySelector('[data-top]') ?? [],
        { translateY: ['0%', '-100%'], duration: 900, ease: 'inOutExpo' },
        1850,
      )
      .add(
        element.querySelector('[data-bottom]') ?? [],
        { translateY: ['0%', '100%'], duration: 900, ease: 'inOutExpo' },
        1850,
      )
      .add(
        element.querySelector('[data-seam]') ?? [],
        { scaleX: [1, 0], opacity: [1, 0], duration: 500, ease: 'outQuad' },
        1850,
      );
    const failsafe = window.setTimeout(() => {
      finishIntro();
      setDone(true);
    }, 4000);
    return () => {
      window.clearTimeout(failsafe);
      timeline.pause();
    };
  }, [done]);

  if (done) return null;
  return (
    <div ref={root} aria-hidden="true" className="fixed inset-0 z-[90]">
      <div data-top className="absolute inset-x-0 top-0 h-1/2 bg-black" />
      <div data-bottom className="absolute inset-x-0 bottom-0 h-1/2 bg-black" />
      <div
        data-seam
        className="absolute inset-x-0 top-1/2 h-px"
        style={{ background: 'var(--gradient-molten)' }}
      />
      <div
        data-content
        className="absolute inset-0 flex flex-col justify-between p-[var(--gutter)]"
      >
        <div className="label flex justify-between">
          <span>Karobar ERP</span>
          <span>{t('preloader.tag')}</span>
        </div>

        <svg
          viewBox="0 0 32 32"
          className="absolute start-1/2 bottom-[calc(50%+1.5rem)] size-16 -translate-x-1/2 md:size-20 rtl:translate-x-1/2"
        >
          <rect
            data-stroke
            x="3"
            y="4"
            width="11"
            height="24"
            rx="3"
            fill="none"
            stroke="var(--color-gold)"
            strokeWidth="0.6"
            strokeDasharray="120"
            strokeDashoffset="120"
          />
          <rect
            data-stroke
            x="18"
            y="4"
            width="11"
            height="24"
            rx="3"
            fill="none"
            stroke="var(--color-turquoise)"
            strokeWidth="0.6"
            strokeDasharray="120"
            strokeDashoffset="120"
          />
          <rect
            data-fill
            x="9"
            y="14.5"
            width="14"
            height="3"
            rx="1.5"
            fill="var(--color-cream)"
            opacity="0"
          />
        </svg>
        <div className="absolute inset-x-0 top-[calc(50%+1.25rem)] mx-auto h-[1.2em] w-fit overflow-hidden font-display text-3xl md:text-5xl">
          {words.map((word) => (
            <span
              key={word}
              data-word
              className="absolute inset-x-0 block translate-y-full text-center"
            >
              {word}
            </span>
          ))}
          <span className="invisible">
            {words.reduce((a, b) => (b.length > a.length ? b : a), '')}
          </span>
        </div>

        <div className="space-y-3">
          <div className="flex items-end justify-between">
            <span className="label">{t('preloader.loading')}</span>
            <span ref={counter} className="font-mono text-sm tabular-nums text-gold">
              000
            </span>
          </div>
          <div className="h-px w-full bg-line">
            <div ref={bar} className="h-px origin-left scale-x-0 bg-gold rtl:origin-right" />
          </div>
        </div>
      </div>
    </div>
  );
}
