import { createTimeline } from 'animejs';
import { useEffect, useRef, useState } from 'react';

import { finishIntro, isIntroPending } from '../lib/intro';
import { lockScroll, unlockScroll } from '../lib/scroll-lock';
import { Logo } from './Logo';

// Once per page load and never waits on the network: the logo rises out of a mask, a hairline
// draws under it, and the white screen fades into the white page. About a second; skipped for
// reduced motion and app screens.
export function Preloader() {
  const [done, setDone] = useState(() => !isIntroPending());
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = root.current;
    if (done || !element) return;
    lockScroll('intro');
    const finish = () => {
      finishIntro();
      setDone(true);
    };
    const pick = (selector: string) => element.querySelectorAll(selector);
    const timeline = createTimeline({ onComplete: finish })
      .add(pick('[data-logo]'), { translateY: ['100%', '0%'], duration: 700, ease: 'outExpo' }, 0)
      .add(pick('[data-rule]'), { scaleX: [0, 1], duration: 800, ease: 'inOutQuart' }, 100)
      .add(element, { opacity: [1, 0], duration: 350, ease: 'outQuad' }, 950);
    // The page can never stay trapped behind the intro, whatever happens to the timeline.
    const failsafe = window.setTimeout(finish, 3000);
    return () => {
      window.clearTimeout(failsafe);
      timeline.pause();
      unlockScroll('intro');
    };
  }, [done]);

  if (done) return null;
  return (
    <div
      ref={root}
      aria-hidden="true"
      className="fixed inset-0 z-[90] flex items-center justify-center bg-canvas"
    >
      <div className="flex w-52 flex-col items-center gap-6 md:w-64">
        <div className="overflow-hidden">
          {/* An inline transform, not a utility: Tailwind's translate would stack with anime.js. */}
          <div data-logo style={{ transform: 'translateY(100%)' }}>
            <Logo variant="full" className="h-auto w-full" />
          </div>
        </div>
        <div
          data-rule
          className="h-px w-full origin-center bg-line-strong"
          style={{ transform: 'scaleX(0)' }}
        />
      </div>
    </div>
  );
}
