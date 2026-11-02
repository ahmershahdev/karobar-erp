import { Suspense, lazy, useCallback, useState } from 'react';

import { useReducedMotion } from '../../lib/motion';

const HeroCanvas = lazy(() => import('./HeroCanvas'));

// The CSS gradient is painted first and stays as the fallback, so the hero never flashes
// black while three.js downloads and still looks right where WebGL is missing.
export function HeroBackdrop() {
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);
  const onFailure = useCallback(() => setFailed(true), []);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div
        className="absolute inset-0 opacity-80"
        style={{
          background:
            'radial-gradient(60% 50% at 30% 35%, var(--color-indigo), transparent 70%), radial-gradient(45% 40% at 75% 30%, var(--color-magenta), transparent 70%), radial-gradient(50% 45% at 60% 75%, var(--color-teal), transparent 70%), var(--color-navy)',
        }}
      />
      {!failed && (
        <Suspense fallback={null}>
          <HeroCanvas animate={!reduced} onFailure={onFailure} />
        </Suspense>
      )}
      <div className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-b from-transparent to-canvas" />
    </div>
  );
}
