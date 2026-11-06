import { useEffect, useRef, useState } from 'react';

import { prefersReducedMotion } from '../../lib/motion';
import './mascot.css';

export type Mood = 'walking' | 'confused' | 'looking' | 'searching' | 'happy';

const MOUTHS: Record<Mood, string> = {
  walking: 'M100 85q10 6 20 0',
  confused: 'M100 88q5-5 10-1t10-1',
  looking: 'M103 87h14',
  searching: 'M102 89q8-6 16 0',
  happy: 'M97 81q13 13 26 0z',
};

/**
 * A small shopkeeper for the pages where something went wrong. It is drawn in layers, near limbs
 * bright and far limbs dark, and the layers shift against each other as the pointer moves, which
 * reads as depth without loading a 3D engine: the offline page has to work with no network.
 *
 * `moods` cycles on a timer. Clicking makes it hop and moves to the next mood.
 */
export function Mascot({
  moods,
  className = '',
  label,
}: {
  moods: readonly Mood[];
  className?: string;
  label: string;
}) {
  const root = useRef<HTMLButtonElement>(null);
  const [step, setStep] = useState(0);
  const [hops, setHops] = useState(0);
  const mood = moods[step % moods.length] ?? 'confused';

  useEffect(() => {
    if (moods.length < 2 || prefersReducedMotion()) return;
    const timer = window.setInterval(() => setStep((value) => value + 1), 6000);
    return () => window.clearInterval(timer);
  }, [moods.length]);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    const onMove = (event: PointerEvent) => {
      const element = root.current;
      if (!element) return;
      const rect = element.getBoundingClientRect();
      const limit = (value: number) => Math.max(-1, Math.min(1, value));
      const x = limit((event.clientX - rect.left - rect.width / 2) / 320);
      const y = limit((event.clientY - rect.top - rect.height / 2) / 320);
      element.style.setProperty('--look-x', x.toFixed(3));
      element.style.setProperty('--look-y', y.toFixed(3));
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, []);

  return (
    <button
      ref={root}
      type="button"
      aria-label={label}
      onClick={() => {
        setHops((value) => value + 1);
        setStep((value) => value + 1);
      }}
      className={`mascot ${className}`}
      data-mood={mood}
    >
      <span key={hops} className={hops ? 'mascot-hop' : 'mascot-still'}>
        <svg viewBox="0 0 220 280" aria-hidden="true" className="mascot-figure">
          <ellipse className="m-shadow" cx="110" cy="268" rx="56" ry="8" />
          <g className="m-body">
            <g className="m-limb m-leg-far">
              <rect x="114" y="172" width="24" height="80" rx="11" className="m-trouser-far" />
              <rect x="112" y="244" width="38" height="15" rx="7.5" className="m-shoe-far" />
            </g>
            <g className="m-limb m-arm-far">
              <rect x="146" y="106" width="19" height="70" rx="9.5" className="m-sleeve-far" />
              <circle cx="155.5" cy="180" r="9.5" className="m-skin" />
              <g className="m-phone">
                <rect x="147" y="184" width="17" height="28" rx="3" className="m-phone-body" />
                <rect x="150" y="188" width="11" height="17" rx="1" className="m-phone-glass" />
              </g>
            </g>
            <g className="m-limb m-leg-near">
              <rect x="84" y="172" width="24" height="80" rx="11" className="m-trouser" />
              <rect x="80" y="244" width="38" height="15" rx="7.5" className="m-shoe" />
            </g>
            <g className="m-torso">
              <rect x="70" y="96" width="80" height="90" rx="24" className="m-shirt" />
              <path
                d="M126 97h2a22 22 0 0 1 22 22v44a22 22 0 0 1-22 22h-2z"
                className="m-shirt-side"
              />
              <path d="M96 97l14 15 14-15z" className="m-collar" />
              <rect x="82" y="134" width="20" height="16" rx="3" className="m-pocket" />
            </g>
            <g className="m-limb m-arm-near">
              <rect x="56" y="106" width="19" height="72" rx="9.5" className="m-sleeve" />
              <circle cx="65.5" cy="182" r="9.5" className="m-skin" />
            </g>
            <g className="m-head">
              <rect x="99" y="84" width="22" height="20" rx="6" className="m-skin-shade" />
              <circle cx="148" cy="62" r="7.5" className="m-skin-shade" />
              <circle cx="110" cy="58" r="38" className="m-skin" />
              <path d="M138 34a38 38 0 0 1-6 55 38 38 0 0 0 6-55z" className="m-skin-shade" />
              <path d="M72 46a38 38 0 0 1 76 0z" className="m-cap" />
              <path d="M62 46h86a4 4 0 0 1 0 8H66q-10 0-4-8z" className="m-brim" />
              <g className="m-face">
                <ellipse cx="96" cy="72" rx="7.5" ry="8" className="m-eye" />
                <ellipse cx="124" cy="72" rx="7.5" ry="8" className="m-eye" />
                <g className="m-pupils">
                  <circle cx="96" cy="72" r="4" className="m-pupil" />
                  <circle cx="124" cy="72" r="4" className="m-pupil" />
                </g>
                <path d="M88 62q7-4 14-1" className="m-brow m-brow-near" />
                <path d="M118 61q7-3 14 1" className="m-brow m-brow-far" />
                <path d={MOUTHS[mood]} className="m-mouth" />
              </g>
            </g>
          </g>
          <g className="m-think">
            <text x="172" y="50">
              ?
            </text>
            <text x="190" y="82">
              ?
            </text>
            <text x="30" y="64">
              ?
            </text>
          </g>
          <g className="m-signal">
            <path d="M176 150a12 12 0 0 1 17 0" />
            <path d="M170 142a21 21 0 0 1 29 0" />
            <path d="M164 134a30 30 0 0 1 41 0" />
          </g>
          <g className="m-joy">
            <circle cx="36" cy="70" r="4" />
            <rect x="182" y="60" width="8" height="8" rx="2" />
            <circle cx="196" cy="118" r="3" />
            <rect x="22" y="124" width="7" height="7" rx="2" />
          </g>
        </svg>
      </span>
    </button>
  );
}
