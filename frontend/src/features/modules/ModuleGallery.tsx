import { useEffect, useRef, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';

import { prefersReducedMotion } from '../../lib/motion';

const GRADIENTS = [
  'var(--gradient-lagoon)',
  'var(--gradient-molten)',
  'var(--gradient-blossom)',
  'var(--gradient-orchard)',
  'var(--gradient-aurora)',
  'var(--gradient-sunrise)',
  'var(--gradient-dusk)',
  'var(--gradient-earth)',
];

interface Item {
  title: string;
  body: string;
}

const WIDE = '(min-width: 1024px)';

function useWide(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(WIDE);
      media.addEventListener('change', onChange);
      return () => media.removeEventListener('change', onChange);
    },
    () => window.matchMedia(WIDE).matches,
    () => false,
  );
}

function ModuleCard({ item, index }: { item: Item; index: number }) {
  const gradient = GRADIENTS[index % GRADIENTS.length];
  return (
    <article className="card group flex h-full min-h-[22rem] flex-col justify-between overflow-hidden p-7 lg:min-h-0">
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-px opacity-70"
        style={{ background: gradient }}
      />
      <div className="flex items-start justify-between">
        <span className="label">{String(index + 1).padStart(2, '0')}</span>
        <span
          aria-hidden="true"
          className="size-12 rounded-full opacity-80 blur-[1px] transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:scale-125"
          style={{ background: gradient }}
        />
      </div>
      <span
        aria-hidden="true"
        className="outline-text pointer-events-none absolute -end-4 top-1/2 -translate-y-1/2 font-display text-[11rem] leading-none select-none"
      >
        {String(index + 1).padStart(2, '0')}
      </span>
      <div className="relative space-y-3">
        <h3 className="font-display text-4xl md:text-5xl">{item.title}</h3>
        <p className="max-w-sm text-muted">{item.body}</p>
      </div>
    </article>
  );
}

/**
 * On wide screens the section pins and the cards slide sideways as you scroll down; the
 * section's height is what gives the sideways track its scroll distance. Narrow screens and
 * reduced motion get a plain grid.
 */
export function ModuleGallery({ limit }: { limit?: number }) {
  const { t, i18n } = useTranslation();
  const items = (t('modules.items', { returnObjects: true }) as Item[]).slice(0, limit);
  const wide = useWide();
  const pinned = wide && !prefersReducedMotion();
  const section = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const rtl = i18n.dir() === 'rtl';

  useEffect(() => {
    if (!pinned) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const outer = section.current;
      const inner = track.current;
      if (!outer || !inner) return;
      const rect = outer.getBoundingClientRect();
      const distance = inner.scrollWidth - window.innerWidth;
      const progress = Math.min(1, Math.max(0, -rect.top / (rect.height - window.innerHeight)));
      inner.style.transform = `translate3d(${(rtl ? 1 : -1) * progress * distance}px, 0, 0)`;
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [pinned, rtl, items.length]);

  if (!pinned) {
    return (
      <div className="shell grid gap-4 sm:grid-cols-2">
        {items.map((item, index) => (
          <ModuleCard key={item.title} item={item} index={index} />
        ))}
      </div>
    );
  }

  return (
    <div ref={section} style={{ height: `${items.length * 45 + 60}vh` }} className="relative">
      <div className="sticky top-0 flex h-[100svh] items-center overflow-hidden">
        <div ref={track} className="flex gap-6 ps-[var(--gutter)] pe-[30vw] will-change-transform">
          {items.map((item, index) => (
            <div key={item.title} className="h-[62vh] w-[min(34rem,38vw)] shrink-0">
              <ModuleCard item={item} index={index} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
