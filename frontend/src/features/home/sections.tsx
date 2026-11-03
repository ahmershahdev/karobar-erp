import { animate } from 'animejs';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Reveal } from '../../components/Reveal';
import { SectionHeading } from '../../components/SectionHeading';
import { prefersReducedMotion } from '../../lib/motion';

interface Titled {
  title: string;
  body: string;
}

function CountUp({ value }: { value: string }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const element = ref.current;
    const match = /^(\d+)(.*)$/.exec(value);
    if (!element || !match || prefersReducedMotion()) return;
    const target = Number(match[1]);
    const suffix = match[2] ?? '';
    element.textContent = `0${suffix}`;
    const state = { n: 0 };
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        observer.disconnect();
        animate(state, {
          n: target,
          duration: 1800,
          ease: 'outExpo',
          onUpdate: () => {
            element.textContent = `${Math.round(state.n)}${suffix}`;
          },
        });
      },
      { threshold: 0.6 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [value]);

  return <span ref={ref}>{value}</span>;
}

export function StatsBand() {
  const { t } = useTranslation();
  const items = t('home.stats.items', { returnObjects: true }) as {
    value: string;
    label: string;
  }[];
  return (
    <section className="border-y border-line bg-black/60 backdrop-blur-sm" data-morph="1">
      <div className="shell py-16 md:py-20">
        <span className="label mb-10 block !text-gold">{t('home.stats.eyebrow')}</span>
        <Reveal stagger className="grid grid-cols-2 gap-x-6 gap-y-12 lg:grid-cols-4">
          {items.map((item) => (
            <div key={item.label} className="space-y-3 border-s border-line ps-5">
              <p className="text-gradient font-display text-6xl leading-none md:text-7xl">
                <CountUp value={item.value} />
              </p>
              <p className="max-w-[18ch] text-sm text-muted">{item.label}</p>
            </div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

const SHOP_ACCENTS = [
  'var(--color-gold)',
  'var(--color-turquoise)',
  'var(--color-lavender)',
  'var(--color-coral)',
  'var(--color-mint)',
  'var(--color-pink)',
];

export function BuiltFor() {
  const { t } = useTranslation();
  const items = t('home.builtFor.items', { returnObjects: true }) as Titled[];
  return (
    <section data-morph="2" className="shell py-28 md:py-40">
      <SectionHeading
        index="05"
        eyebrow={t('home.builtFor.eyebrow')}
        title={t('home.builtFor.title')}
      />
      <Reveal
        stagger
        className="mt-16 grid gap-px overflow-hidden rounded-[var(--radius-card)] border border-line bg-line sm:grid-cols-2 lg:grid-cols-3"
      >
        {items.map((item, index) => (
          <article
            key={item.title}
            className="group relative overflow-hidden bg-black/85 p-8 backdrop-blur transition-colors duration-500 hover:bg-raised md:p-10"
          >
            <span
              aria-hidden="true"
              className="absolute inset-x-0 bottom-0 h-px origin-left scale-x-0 transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:scale-x-100 rtl:origin-right"
              style={{ background: SHOP_ACCENTS[index % SHOP_ACCENTS.length] }}
            />
            <span className="label" style={{ color: SHOP_ACCENTS[index % SHOP_ACCENTS.length] }}>
              {String(index + 1).padStart(2, '0')}
            </span>
            <h3 className="mt-10 font-display text-3xl">{item.title}</h3>
            <p className="mt-3 text-muted">{item.body}</p>
          </article>
        ))}
      </Reveal>
    </section>
  );
}

export function HowItWorks() {
  const { t } = useTranslation();
  const items = t('home.steps.items', { returnObjects: true }) as Titled[];
  return (
    <section data-morph="2" className="shell py-20 md:py-32">
      <SectionHeading index="06" eyebrow={t('home.steps.eyebrow')} title={t('home.steps.title')} />
      <Reveal stagger className="relative mt-16 grid gap-10 md:grid-cols-3 md:gap-6">
        {items.map((item, index) => (
          <article key={item.title} className="relative">
            <div className="flex items-center gap-4">
              <span className="flex size-12 shrink-0 items-center justify-center rounded-full border border-gold/50 font-mono text-sm text-gold">
                {index + 1}
              </span>
              {index < items.length - 1 && (
                <span
                  aria-hidden="true"
                  className="hidden h-px flex-1 bg-gradient-to-r from-gold/50 to-transparent md:block rtl:bg-gradient-to-l"
                />
              )}
            </div>
            <h3 className="mt-8 font-display text-3xl md:text-4xl">{item.title}</h3>
            <p className="mt-3 max-w-sm text-muted">{item.body}</p>
          </article>
        ))}
      </Reveal>
    </section>
  );
}

export function Roadmap() {
  const { t } = useTranslation();
  const items = t('home.roadmap.items', { returnObjects: true }) as (Titled & { key: string })[];
  const shipped = 3;
  return (
    <section data-morph="2" className="py-20 md:py-32">
      <div className="shell">
        <SectionHeading
          index="08"
          eyebrow={t('home.roadmap.eyebrow')}
          title={t('home.roadmap.title')}
        />
      </div>
      <div className="mt-16 overflow-x-auto pb-4" data-lenis-prevent>
        <Reveal stagger className="shell flex min-w-max gap-4">
          {items.map((item, index) => {
            const state = index < shipped ? 'done' : index === shipped ? 'next' : 'later';
            return (
              <article
                key={item.key}
                className={`relative w-64 shrink-0 rounded-[var(--radius-card)] border p-6 ${
                  state === 'done'
                    ? 'border-mint/30 bg-mint/[0.04]'
                    : state === 'next'
                      ? 'border-gold/50 bg-gold/[0.06]'
                      : 'border-line bg-black/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm text-gold">{item.key}</span>
                  <span
                    className={`label ${state === 'done' ? '!text-mint' : state === 'next' ? '!text-gold' : ''}`}
                  >
                    {t(`home.roadmap.${state}`)}
                  </span>
                </div>
                <h3 className="mt-8 font-display text-2xl">{item.title}</h3>
                <p className="mt-2 text-sm text-muted">{item.body}</p>
              </article>
            );
          })}
        </Reveal>
      </div>
    </section>
  );
}

export function Faq() {
  const { t } = useTranslation();
  const items = t('home.faq.items', { returnObjects: true }) as { q: string; a: string }[];
  const [open, setOpen] = useState(0);
  return (
    <section data-morph="2" className="shell grid gap-12 py-20 md:py-32 lg:grid-cols-[1fr_1.4fr]">
      <SectionHeading index="09" eyebrow={t('home.faq.eyebrow')} title={t('home.faq.title')} />
      <Reveal stagger className="border-t border-line">
        {items.map((item, index) => {
          const expanded = open === index;
          return (
            <div key={item.q} className="border-b border-line">
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={`faq-${index}`}
                onClick={() => setOpen(expanded ? -1 : index)}
                className="flex w-full items-center justify-between gap-6 py-6 text-start"
              >
                <span className="font-display text-2xl md:text-3xl">{item.q}</span>
                <span
                  aria-hidden="true"
                  className={`relative size-4 shrink-0 transition-transform duration-500 ${expanded ? 'rotate-45' : ''}`}
                >
                  <span className="absolute inset-x-0 top-1/2 h-px bg-gold" />
                  <span className="absolute inset-y-0 start-1/2 w-px bg-gold" />
                </span>
              </button>
              <div
                id={`faq-${index}`}
                role="region"
                aria-hidden={!expanded}
                className={`grid transition-[grid-template-rows] duration-500 ease-[var(--ease-out-expo)] ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
              >
                <p className="overflow-hidden pe-10 text-muted">
                  <span className="block pb-6">{item.a}</span>
                </p>
              </div>
            </div>
          );
        })}
      </Reveal>
    </section>
  );
}
