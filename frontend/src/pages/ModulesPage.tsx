import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';

import { PageHero } from '../components/PageHero';
import { Reveal } from '../components/Reveal';
import { ModuleGlyph } from '../features/modules/catalog';
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

  // The pill of the module being read is highlighted: the section crossing a band just below
  // the sticky bar is the current one.
  const [active, setActive] = useState<string>(MODULES[0].key);
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) if (entry.isIntersecting) setActive(entry.target.id);
      },
      { rootMargin: '-35% 0px -60% 0px' },
    );
    for (const meta of MODULES) {
      const section = document.getElementById(meta.key);
      if (section) observer.observe(section);
    }
    return () => observer.disconnect();
  }, []);

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
        eyebrow={t('modules.eyebrow')}
        title={t('modules.pageTitle')}
        accent={t('modules.pageAccent')}
        lead={t('modules.lead')}
      />

      <nav
        aria-label={t('modules.jump')}
        className="shell sticky top-[calc(var(--header-height)+0.5rem)] z-30"
      >
        <div className="flex w-fit max-w-full gap-1 overflow-x-auto rounded-full border border-line bg-canvas/85 p-1 backdrop-blur-xl [scrollbar-width:none]">
          {MODULES.map((meta, index) => {
            const current = active === meta.key;
            return (
              <button
                key={meta.key}
                type="button"
                aria-current={current ? 'true' : undefined}
                onClick={() => jump(meta.key)}
                className={`shrink-0 rounded-full px-4 py-2 text-sm transition-colors duration-300 ${
                  current ? 'bg-ink text-canvas' : 'text-muted hover:text-ink'
                }`}
              >
                {items[index]?.title}
              </button>
            );
          })}
        </div>
      </nav>

      <div className="shell mt-12 md:mt-20">
        {MODULES.map((meta, index) => {
          const copy = items[index];
          if (!copy) return null;
          return (
            <section
              key={meta.key}
              id={meta.key}
              className="group scroll-mt-36 border-t border-line py-14 md:py-20"
            >
              <Reveal className="grid gap-10 lg:grid-cols-[1fr_1.7fr] lg:gap-16">
                <div className="space-y-8">
                  <StatusChip status={meta.status} milestone={meta.milestone} />
                  <ModuleGlyph module={meta.key} className="size-20 text-ink md:size-24" />
                </div>
                <div>
                  <h2 className="display-lg">{copy.title}</h2>
                  <p className="mt-5 max-w-xl text-lg text-muted">{copy.body}</p>
                  <ul className="mt-10 grid gap-x-10 border-t border-line sm:grid-cols-2">
                    {copy.points.map((point) => (
                      <li key={point} className="border-b border-line py-4 text-sm">
                        {point}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-8 rounded-xl bg-surface p-5">
                    <p className="label">{t('modules.inBooks')}</p>
                    <p className="mt-1.5 text-sm">{copy.books}</p>
                  </div>
                </div>
              </Reveal>
            </section>
          );
        })}
      </div>
    </>
  );
}
