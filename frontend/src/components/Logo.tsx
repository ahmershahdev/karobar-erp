import { useId } from 'react';

import { MARK } from './mark';

/** The Karobar mark from the logo: a cloud of figures with the growth arrow leaving it. */
export function Logo({ className = 'size-8' }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox={MARK.viewBox} className={className} aria-hidden="true">
      <defs>
        <linearGradient id={`${id}c`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="var(--color-blue)" />
          <stop offset="1" stopColor="var(--color-sky)" />
        </linearGradient>
        <linearGradient id={`${id}a`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="var(--color-ember)" />
          <stop offset="1" stopColor="var(--color-yellow)" />
        </linearGradient>
      </defs>
      <path d={MARK.cloud} fill="none" stroke={`url(#${id}c)`} strokeWidth="3.4" />
      {MARK.bars.map((bar) => (
        <rect
          key={bar.x}
          x={bar.x}
          y={bar.y}
          width={MARK.barWidth}
          height={bar.height}
          rx="0.8"
          fill={`url(#${id}c)`}
        />
      ))}
      <path
        d={MARK.arrow}
        fill="none"
        stroke={`url(#${id}a)`}
        strokeWidth="3"
        strokeLinecap="round"
      />
      <polygon points={MARK.arrowHead} fill="var(--color-yellow)" />
    </svg>
  );
}

/** "Karobar" in the page's ink and "ERP" in the arrow's orange, as in the logo. */
export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`font-display font-extrabold tracking-[-0.04em] ${className}`} dir="ltr">
      Karobar<span className="text-gradient">ERP</span>
    </span>
  );
}
