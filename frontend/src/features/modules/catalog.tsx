import type { ReactNode } from 'react';

import type { ModuleKey } from './data';

const LINE = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  pathLength: 1,
  className: 'glyph-line',
};

const GLYPHS: Record<ModuleKey, ReactNode> = {
  inventory: (
    <>
      <path {...LINE} d="M20 74 60 54l40 20-40 20Z" />
      <path {...LINE} d="M20 74v20l40 20 40-20V74" />
      <path {...LINE} d="M60 94v20" />
      <path {...LINE} d="M32 48 60 34l28 14-28 14Z" />
      <path {...LINE} d="M32 48v14l28 14 28-14V48" />
    </>
  ),
  sales: (
    <>
      <path {...LINE} d="M34 14h52v92l-8-6-9 6-9-6-9 6-9-6-8 6Z" />
      <path {...LINE} d="M46 36h28M46 50h28M46 64h16" />
      <path {...LINE} d="M66 80h10" />
    </>
  ),
  pos: (
    <>
      <path {...LINE} d="M22 30h76v54H22Z" />
      <path {...LINE} d="M34 42v30M42 42v30M48 42v30M58 42v30M64 42v30M74 42v30M86 42v30" />
      <path {...LINE} d="M48 84l-6 20h36l-6-20" />
    </>
  ),
  purchasing: (
    <>
      <path {...LINE} d="M14 40h56v44H14Z" />
      <path {...LINE} d="M70 54h20l14 16v14H70Z" />
      <circle {...LINE} cx="32" cy="88" r="8" />
      <circle {...LINE} cx="86" cy="88" r="8" />
    </>
  ),
  accounting: (
    <>
      <path {...LINE} d="M60 18v84" />
      <path {...LINE} d="M24 34h72" />
      <path {...LINE} d="M24 34 12 66h24ZM96 34 84 66h24Z" />
      <path {...LINE} d="M40 102h40" />
    </>
  ),
  tax: (
    <>
      <circle {...LINE} cx="60" cy="60" r="42" />
      <path {...LINE} d="M42 78 78 42" />
      <circle {...LINE} cx="45" cy="45" r="6" />
      <circle {...LINE} cx="75" cy="75" r="6" />
    </>
  ),
  hr: (
    <>
      <circle {...LINE} cx="44" cy="42" r="12" />
      <path {...LINE} d="M20 96c2-18 12-28 24-28s22 10 24 28" />
      <circle {...LINE} cx="80" cy="48" r="10" />
      <path {...LINE} d="M70 72c4-3 7-4 10-4 10 0 18 8 20 24" />
    </>
  ),
  payroll: (
    <>
      <path {...LINE} d="M24 20h56v80H24Z" />
      <path {...LINE} d="M36 38h32M36 52h20M36 66h28" />
      <circle {...LINE} cx="86" cy="82" r="18" />
      <path {...LINE} d="M86 72v20M80 77h9a4 4 0 0 1 0 8h-6a4 4 0 0 0 0 8h9" />
    </>
  ),
};

export function ModuleGlyph({
  module,
  className = 'size-24',
}: {
  module: ModuleKey;
  className?: string;
}) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      {GLYPHS[module]}
    </svg>
  );
}
