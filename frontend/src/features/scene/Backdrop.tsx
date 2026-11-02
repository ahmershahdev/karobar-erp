import { Suspense, lazy, useCallback, useState } from 'react';

import { useReducedMotion } from '../../lib/motion';

const ParticleField = lazy(() => import('./ParticleField'));

// Fixed behind every public page. The soft gradients paint first and stay as the fallback, so
// nothing flashes while three.js downloads and the page still looks right without WebGL.
export function Backdrop() {
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);
  const onFailure = useCallback(() => setFailed(true), []);

  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(55% 45% at 72% 38%, rgb(216 178 106 / 0.16), transparent 70%), radial-gradient(40% 40% at 18% 80%, rgb(116 98 201 / 0.12), transparent 70%), radial-gradient(35% 30% at 90% 90%, rgb(79 209 193 / 0.07), transparent 70%)',
        }}
      />
      {!failed && (
        <Suspense fallback={null}>
          <ParticleField animate={!reduced} onFailure={onFailure} />
        </Suspense>
      )}
    </div>
  );
}
