import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';

import { PageHero } from '../components/PageHero';
import { Reveal } from '../components/Reveal';
import { ModuleGlyph, TiltCard } from '../features/modules/catalog';
import { MODULES, type ModuleCopy } from '../features/modules/data';
import { StatusChip } from '../features/modules/ModuleGallery';
import { prefersReducedMotion } from '../lib/motion';
import { usePublicSeo } from '../lib/seo';
import { useLenis } from '../lib/smooth-scroll';
import { PUBLIC_ROUTES } from '../seo/site';

export default function ModulesPage() {
  const { t } = useTranslation();
  const lenis = useLenis();
  usePublicSeo(PUBLIC_ROUTES[1]);
  const items = t('modules.items', { returnObjects: true }) as ModuleCopy[];

  const jump = (key: string) => {
    const target = document.getElementById(key);
    if (!target) return;
    if (lenis) lenis.scrollTo(target, { offset: -100, duration: 1.2 });
    else target.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  };

  // A Details link from the home page lands here with a hash. The page transition scrolls to
  // the top as it swaps routes, so the jump to the module has to run once this page is mounted.
  const { hash } = useLocation();
  useEffect(() => {
    const key = decodeURIComponent(hash.slice(1));
    const target = key ? document.getElementById(key) : null;
    if (!target) return;
    const frame = requestAnimationFrame(() => {
      if (lenis) lenis.scrollTo(target, { offset: -100, immediate: true });
      else target.scrollIntoView();
    });
    return () => cancelAnimationFrame(frame);
  }, [hash, lenis]);

  return (
    <>
      <PageHero
        trail={[
          { label: t('nav.home'), to: '/' },
          { label: t('nav.modules'), to: '/modules' },
        ]}
        index="01"
        eyebrow={t('modules.eyebrow')}
        title={t('modules.pageTitle')}
        accent={t('modules.pageAccent')}
        lead={t('modules.lead')}
      />

      <nav aria-label={t('modules.jump')} className="shell">
        <Reveal stagger className="flex flex-wrap gap-2">
          {MODULES.map((meta, index) => (
            <button
              key={meta.key}
              type="button"
              data-cursor-stick
              onClick={() => jump(meta.key)}
              className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember"
            >
              <span className="size-1.5 rounded-full" style={{ background: meta.color }} />
              {items[index]?.title}
            </button>
          ))}
        </Reveal>
      </nav>

      <div className="shell mt-16 space-y-6 md:mt-24 md:space-y-10">
        {MODULES.map((meta, index) => {
          const copy = items[index];
          if (!copy) return null;
          const flipped = index % 2 === 1;
          return (
            <section key={meta.key} id={meta.key} data-morph="2" className="scroll-mt-28">
              <Reveal>
                <TiltCard className="rounded-[2rem]">
                  <article className="relative grid overflow-hidden rounded-[2rem] border border-line bg-[linear-gradient(160deg,color-mix(in_srgb,_var(--color-raised)_96%,_transparent),color-mix(in_srgb,_var(--color-canvas)_94%,_transparent))] lg:grid-cols-2">
                    <div
                      aria-hidden="true"
                      className="absolute inset-x-0 top-0 h-px"
                      style={{ background: meta.gradient }}
                    />
                    <div
                      className={`relative flex min-h-[18rem] items-center justify-center overflow-hidden border-line p-10 lg:min-h-[28rem] ${
                        flipped ? 'lg:order-2 lg:border-s' : 'lg:border-e'
                      } border-b lg:border-b-0`}
                    >
                      <div
                        aria-hidden="true"
                        className="absolute size-[28rem] rounded-full opacity-25 blur-3xl transition-opacity duration-700 group-hover:opacity-45"
                        style={{ background: meta.gradient }}
                      />
                      <span
                        aria-hidden="true"
                        className="outline-text absolute start-6 top-4 font-display text-[9rem] leading-none select-none"
                      >
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <div className="relative" style={{ color: meta.color }}>
                        <ModuleGlyph module={meta.key} className="size-40 md:size-52" />
                      </div>
                    </div>
                    <div className="relative flex flex-col gap-6 p-8 md:p-12">
                      <StatusChip status={meta.status} milestone={meta.milestone} />
                      <h2 className="display-lg">{copy.title}</h2>
                      <p className="max-w-lg text-lg text-ink/80">{copy.body}</p>
                      <ul className="grid gap-3 sm:grid-cols-2">
                        {copy.points.map((point) => (
                          <li
                            key={point}
                            className="flex gap-3 rounded-2xl border border-line bg-black/30 p-4 text-sm"
                          >
                            <span
                              aria-hidden="true"
                              className="mt-1.5 size-1.5 shrink-0 rotate-45"
                              style={{ background: meta.color }}
                            />
                            {point}
                          </li>
                        ))}
                      </ul>
                      <div className="mt-auto rounded-2xl border border-ember/25 bg-ember/[0.05] p-5">
                        <p className="label !text-ember">{t('modules.inBooks')}</p>
                        <p className="mt-2 text-sm text-ink/85">{copy.books}</p>
                      </div>
                    </div>
                  </article>
                </TiltCard>
              </Reveal>
            </section>
          );
        })}
      </div>
    </>
  );
}
