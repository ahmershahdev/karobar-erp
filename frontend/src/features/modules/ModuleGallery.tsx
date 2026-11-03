import type { CSSProperties } from 'react';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { useMediaQuery, useReducedMotion } from '../../lib/motion';
import { ModuleGlyph, TiltCard } from './catalog';
import { MODULES, type ModuleCopy } from './data';

// Pinning needs room for a whole card: the 70vh slot must fit the card's 30rem minimum.
const ROOMY = '(min-width: 1024px) and (min-height: 700px)';

export function StatusChip({ status, milestone }: { status: string; milestone: string }) {
  const { t } = useTranslation();
  const built = status === 'built';
  return (
    <span
      className={`inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1 font-mono text-[0.62rem] tracking-[0.14em] uppercase ${
        built ? 'border-mint/30 text-mint' : 'border-line-strong text-muted'
      }`}
    >
      <span
        className={`size-1.5 rounded-full ${built ? 'bg-mint' : status === 'next' ? 'bg-ember' : 'bg-muted/50'}`}
      />
      {built ? t('modules.status.built', { milestone }) : t('modules.status.coming', { milestone })}
    </span>
  );
}

export function ModuleCard({ index, copy }: { index: number; copy: ModuleCopy }) {
  const { t } = useTranslation();
  const meta = MODULES[index];
  if (!meta) return null;
  return (
    <TiltCard className="h-full rounded-[var(--radius-card)]">
      <article
        style={{ '--module-gradient': meta.gradient } as CSSProperties}
        className="module-card relative flex h-full min-h-[30rem] flex-col overflow-hidden rounded-[var(--radius-card)] bg-[linear-gradient(160deg,color-mix(in_srgb,_var(--color-raised)_95%,_transparent),color-mix(in_srgb,_var(--color-canvas)_92%,_transparent))] p-7 md:p-8"
      >
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-px"
          style={{ background: meta.gradient }}
        />
        <div
          aria-hidden="true"
          className="absolute -end-24 -top-24 size-72 rounded-full opacity-20 blur-3xl transition-opacity duration-700 group-hover:opacity-40"
          style={{ background: meta.gradient }}
        />
        <span
          aria-hidden="true"
          className="outline-text absolute end-6 bottom-4 font-display text-[7rem] leading-none font-extrabold select-none"
        >
          {String(index + 1).padStart(2, '0')}
        </span>
        <div className="relative flex items-start justify-between gap-4">
          <span className="label">{String(index + 1).padStart(2, '0')} / 08</span>
          <StatusChip status={meta.status} milestone={meta.milestone} />
        </div>
        <div
          className="relative my-8 grid size-24 place-items-center rounded-2xl border border-line bg-black/40 transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:-translate-y-1 md:size-28"
          style={{ color: meta.color }}
        >
          <ModuleGlyph module={meta.key} className="size-16 md:size-20" />
        </div>
        <div className="relative flex flex-1 flex-col">
          <h3 className="font-display text-4xl leading-none md:text-5xl">{copy.title}</h3>
          <p className="mt-4 text-sm leading-relaxed text-muted">{copy.body}</p>
          <ul className="mt-6 mb-8 space-y-2.5 text-sm">
            {copy.points.slice(0, 3).map((point) => (
              <li key={point} className="flex gap-3 text-ink/85">
                <span
                  aria-hidden="true"
                  className="mt-2 size-1 shrink-0 rotate-45"
                  style={{ background: meta.color }}
                />
                {point}
              </li>
            ))}
          </ul>
          <Link
            to={`/modules#${meta.key}`}
            className="relative mt-auto inline-flex w-fit items-center gap-2 rounded-full border border-ember/40 px-4 py-2 font-mono text-[0.7rem] tracking-[0.14em] text-ember uppercase transition-colors hover:border-ember hover:bg-ember/10"
          >
            {t('modules.more')}
            <span
              aria-hidden="true"
              className="transition-transform duration-500 group-hover:translate-x-1 rtl:rotate-180 rtl:group-hover:-translate-x-1"
            >
              &rarr;
            </span>
          </Link>
        </div>
      </article>
    </TiltCard>
  );
}

/**
 * On wide screens the section pins and the cards slide sideways as you scroll down; the
 * section's height is what gives the sideways track its scroll distance. Narrow screens and
 * reduced motion get a plain grid.
 */
export function ModuleGallery() {
  const { t, i18n } = useTranslation();
  const items = t('modules.items', { returnObjects: true }) as ModuleCopy[];
  const roomy = useMediaQuery(ROOMY);
  const reduced = useReducedMotion();
  const pinned = roomy && !reduced;
  const section = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLDivElement>(null);
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
      if (bar.current) bar.current.style.transform = `scaleX(${progress})`;
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
      <div className="shell grid gap-5 sm:grid-cols-2">
        {items.map((copy, index) => (
          <ModuleCard key={copy.title} index={index} copy={copy} />
        ))}
      </div>
    );
  }

  return (
    <div ref={section} style={{ height: `${items.length * 45 + 60}vh` }} className="relative">
      <div className="sticky top-0 flex h-[100svh] flex-col justify-center overflow-hidden">
        <div ref={track} className="flex gap-6 ps-[var(--gutter)] pe-[30vw] will-change-transform">
          {items.map((copy, index) => (
            <div key={copy.title} className="h-[70vh] max-h-[40rem] w-[min(30rem,34vw)] shrink-0">
              <ModuleCard index={index} copy={copy} />
            </div>
          ))}
        </div>
        <div className="shell mt-10">
          <div className="h-px w-full bg-line">
            <div
              ref={bar}
              className="h-px origin-left bg-ember rtl:origin-right"
              style={{ transform: 'scaleX(0)' }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
