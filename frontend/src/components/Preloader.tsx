import { createTimeline, stagger } from 'animejs';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { finishIntro, isIntroPending } from '../lib/intro';
import { lockScroll, unlockScroll } from '../lib/scroll-lock';
import { MARK } from './mark';

// Starting positions are inline transforms, not Tailwind utilities: those set the separate CSS
// translate and scale properties, which would stack with the transform anime.js writes.
//
// The intro tells the logo's story once per page load and never waits on the network: the
// cloud draws itself, the three bars rise, the growth arrow shoots out of it, the wordmark
// lifts in over the orange swoosh while what Karobar keeps cycles below, and the screen lifts
// away in six panels from the centre out. The page can't scroll underneath until it has gone. About two and a half seconds; skipped for reduced motion and app screens.
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
    lockScroll('intro');
    const pick = (selector: string) => element.querySelectorAll(selector);
    const state = { value: 0 };
    const timeline = createTimeline({
      onComplete: () => {
        finishIntro();
        setDone(true);
      },
    });
    timeline
      .add(pick('[data-glow]'), { opacity: [0, 1], duration: 900, ease: 'outQuad' }, 0)
      .add(pick('[data-cloud]'), { strokeDashoffset: [1, 0], duration: 850, ease: 'inOutQuart' }, 0)
      .add(
        pick('[data-bar]'),
        { scaleY: [0, 1], duration: 520, delay: stagger(110), ease: 'outBack(1.6)' },
        450,
      )
      .add(
        pick('[data-arrow]'),
        { strokeDashoffset: [1, 0], opacity: [0, 1], duration: 600, ease: 'inQuart' },
        820,
      )
      .add(
        pick('[data-head]'),
        { scale: [0, 1], opacity: [0, 1], duration: 380, ease: 'outBack(2.2)' },
        1300,
      )
      .add(
        pick('[data-mark]'),
        { translateY: ['0rem', '-0.4rem', '0rem'], duration: 700, ease: 'inOutSine' },
        1300,
      )
      .add(
        pick('[data-letter]'),
        { translateY: ['110%', '0%'], duration: 700, delay: stagger(28), ease: 'outExpo' },
        900,
      )
      .add(
        pick('[data-swoosh]'),
        { strokeDashoffset: [1, 0], opacity: [0, 1], duration: 700, ease: 'outQuart' },
        1250,
      )
      .add(
        pick('[data-word]'),
        {
          translateY: ['100%', '0%', '0%', '-100%'],
          duration: 480,
          delay: stagger(300),
          ease: 'inOutQuart',
        },
        700,
      )
      .add(
        state,
        {
          value: 100,
          duration: 1900,
          ease: 'inOutQuart',
          onUpdate: () => {
            const value = Math.round(state.value);
            if (counter.current) counter.current.textContent = `${value}%`;
            if (bar.current) bar.current.style.transform = `scaleX(${value / 100})`;
          },
        },
        0,
      )
      .add(
        pick('[data-content]'),
        { opacity: [1, 0], scale: [1, 0.96], duration: 380, ease: 'inQuad' },
        2050,
      )
      .add(
        pick('[data-blind]'),
        {
          translateY: ['0%', '-101%'],
          duration: 900,
          delay: stagger(70, { from: 'center' }),
          ease: 'inOutExpo',
        },
        2200,
      )
      .add(
        pick('[data-edge]'),
        {
          translateY: ['100vh', '-2vh'],
          opacity: [1, 0],
          duration: 1000,
          delay: stagger(70, { from: 'center' }),
          ease: 'inOutExpo',
        },
        2200,
      );
    const failsafe = window.setTimeout(() => {
      finishIntro();
      setDone(true);
    }, 5000);
    return () => {
      window.clearTimeout(failsafe);
      timeline.pause();
      unlockScroll('intro');
    };
  }, [done]);

  if (done) return null;
  return (
    <div ref={root} aria-hidden="true" className="fixed inset-0 z-[90] overflow-hidden">
      {/* Six panels make up the screen; they lift away separately, centre first. */}
      <div className="absolute inset-0 flex">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="relative h-full flex-1">
            <div data-blind className="absolute -inset-x-px inset-y-0 bg-canvas" />
            <div
              data-edge
              className="absolute inset-x-0 top-0 h-0.5"
              style={{ background: 'var(--gradient-molten)', transform: 'translateY(100vh)' }}
            />
          </div>
        ))}
      </div>
      <div className="absolute inset-0">
        <div
          data-glow
          className="absolute inset-0 opacity-0"
          style={{
            background:
              'radial-gradient(45% 40% at 50% 38%, color-mix(in srgb, var(--color-azure) 28%, transparent), transparent 70%), radial-gradient(40% 30% at 62% 70%, color-mix(in srgb, var(--color-ember) 16%, transparent), transparent 70%)',
          }}
        />
        <div
          data-content
          className="absolute inset-0 flex flex-col justify-between p-[var(--gutter)]"
        >
          <div className="label flex justify-between">
            <span>Karobar ERP</span>
            <span>{t('preloader.tag')}</span>
          </div>

          <div className="flex flex-col items-center gap-5">
            <div className="relative grid place-items-center">
              {/* A slow halo in the logo's two colours, turning behind the mark. */}
              <div
                data-glow
                className="preloader-halo absolute size-44 rounded-full opacity-0 md:size-56"
              />
              <svg data-mark viewBox={MARK.viewBox} className="size-28 overflow-visible md:size-36">
                <defs>
                  <linearGradient id="pre-cloud" x1="0" y1="1" x2="1" y2="0">
                    <stop offset="0" stopColor="var(--color-blue)" />
                    <stop offset="1" stopColor="var(--color-sky)" />
                  </linearGradient>
                  <linearGradient id="pre-arrow" x1="0" y1="1" x2="1" y2="0">
                    <stop offset="0" stopColor="var(--color-coral)" />
                    <stop offset="1" stopColor="var(--color-yellow)" />
                  </linearGradient>
                </defs>
                <path
                  data-cloud
                  d={MARK.cloud}
                  pathLength={1}
                  fill="none"
                  stroke="url(#pre-cloud)"
                  strokeWidth="3.4"
                  strokeDasharray="1"
                  strokeDashoffset="1"
                />
                {MARK.bars.map((item) => (
                  <rect
                    key={item.x}
                    data-bar
                    x={item.x}
                    y={item.y}
                    width={MARK.barWidth}
                    height={item.height}
                    rx="0.8"
                    fill="url(#pre-cloud)"
                    style={{
                      transformBox: 'fill-box',
                      transformOrigin: 'bottom',
                      transform: 'scaleY(0)',
                    }}
                  />
                ))}
                <path
                  data-arrow
                  d={MARK.arrow}
                  pathLength={1}
                  fill="none"
                  stroke="url(#pre-arrow)"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeDasharray="1"
                  strokeDashoffset="1"
                  opacity="0"
                />
                <polygon
                  data-head
                  points={MARK.arrowHead}
                  fill="var(--color-yellow)"
                  opacity="0"
                  style={{
                    transformBox: 'fill-box',
                    transformOrigin: 'center',
                    transform: 'scale(0)',
                  }}
                />
              </svg>
            </div>

            <div className="flex flex-col items-center" dir="ltr">
              <div className="flex overflow-hidden pb-1 font-display text-5xl font-extrabold tracking-[-0.045em] md:text-7xl">
                {['K', 'a', 'r', 'o', 'b', 'a', 'r'].map((letter, index) => (
                  <span
                    key={`k${index}`}
                    data-letter
                    className="inline-block"
                    style={{ transform: 'translateY(110%)' }}
                  >
                    {letter}
                  </span>
                ))}
                {['E', 'R', 'P'].map((letter, index) => (
                  <span
                    key={`e${index}`}
                    data-letter
                    className="text-gradient inline-block"
                    style={{ transform: 'translateY(110%)' }}
                  >
                    {letter}
                  </span>
                ))}
              </div>
              {/* The swoosh under the logo's wordmark, curling up at the end. */}
              <svg viewBox="0 0 200 24" className="-mt-1 w-56 md:w-80" fill="none">
                <path
                  data-swoosh
                  d="M6 5 C62 25 140 25 182 10 C188 8 192 8 190 15"
                  pathLength={1}
                  stroke="url(#pre-arrow)"
                  strokeWidth="4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeDasharray="1"
                  strokeDashoffset="1"
                  opacity="0"
                />
              </svg>
            </div>

            <div className="relative h-[1.4em] w-48 overflow-hidden text-center text-sm text-muted md:text-base">
              {words.map((word) => (
                <span
                  key={word}
                  data-word
                  className="absolute inset-x-0 block"
                  style={{ transform: 'translateY(100%)' }}
                >
                  {word}
                </span>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-end justify-between">
              <span className="label">{t('preloader.loading')}</span>
              <span ref={counter} className="font-mono text-sm tabular-nums text-ember">
                0%
              </span>
            </div>
            <div className="h-0.5 w-full overflow-hidden rounded-full bg-line">
              <div
                ref={bar}
                className="h-full origin-left rounded-full rtl:origin-right"
                style={{ transform: 'scaleX(0)', background: 'var(--gradient-molten)' }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
