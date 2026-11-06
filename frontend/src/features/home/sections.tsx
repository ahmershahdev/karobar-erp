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
    <section className="shell">
      <div className="border-y border-line py-14 md:py-20">
        <p className="label mb-10">{t('home.stats.eyebrow')}</p>
        <Reveal stagger className="grid grid-cols-2 gap-x-6 gap-y-12 lg:grid-cols-4">
          {items.map((item) => (
            <div key={item.label} className="space-y-2">
              <p className="font-display text-5xl leading-none font-medium tracking-[-0.04em] tabular-nums md:text-6xl">
                <CountUp value={item.value} />
              </p>
              <p className="max-w-[20ch] text-sm text-muted">{item.label}</p>
            </div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

export function BuiltFor() {
  const { t } = useTranslation();
  const items = t('home.builtFor.items', { returnObjects: true }) as Titled[];
  return (
    <section className="shell py-24 md:py-36">
      <SectionHeading
        index="05"
        eyebrow={t('home.builtFor.eyebrow')}
        title={t('home.builtFor.title')}
      />
      <Reveal
        stagger
        className="mt-14 grid gap-x-10 border-t border-line sm:grid-cols-2 lg:grid-cols-3"
      >
        {items.map((item) => (
          <article key={item.title} className="border-b border-line py-8">
            <h3 className="text-2xl">{item.title}</h3>
            <p className="mt-2 text-muted">{item.body}</p>
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
    <section className="bg-surface py-24 md:py-36">
      <div className="shell">
        <SectionHeading
          index="06"
          eyebrow={t('home.steps.eyebrow')}
          title={t('home.steps.title')}
        />
        <Reveal stagger className="mt-14 grid gap-10 md:grid-cols-3 md:gap-8">
          {items.map((item, index) => (
            <article key={item.title} className="border-t border-line-strong pt-6">
              <span className="label text-ember tabular-nums">{index + 1}</span>
              <h3 className="mt-6 text-3xl">{item.title}</h3>
              <p className="mt-3 max-w-sm text-muted">{item.body}</p>
            </article>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

export function Roadmap() {
  const { t } = useTranslation();
  const items = t('home.roadmap.items', { returnObjects: true }) as (Titled & { key: string })[];
  const shipped = 4;
  return (
    <section className="shell py-24 md:py-36">
      <SectionHeading
        index="08"
        eyebrow={t('home.roadmap.eyebrow')}
        title={t('home.roadmap.title')}
      />
      <Reveal stagger className="mt-14 border-t border-line">
        {items.map((item, index) => {
          const state = index < shipped ? 'done' : index === shipped ? 'next' : 'later';
          return (
            <article
              key={item.key}
              className="grid gap-1 border-b border-line py-6 md:grid-cols-[5rem_1fr_1.4fr_7rem] md:items-baseline md:gap-8"
            >
              <span className="label tabular-nums">{item.key}</span>
              <h3 className="text-2xl">{item.title}</h3>
              <p className="text-sm text-muted">{item.body}</p>
              <span
                className={`label md:text-end ${state === 'done' ? '!text-green' : state === 'next' ? '!text-ember' : ''}`}
              >
                {t(`home.roadmap.${state}`)}
              </span>
            </article>
          );
        })}
      </Reveal>
    </section>
  );
}

export function Faq() {
  const { t } = useTranslation();
  const items = t('home.faq.items', { returnObjects: true }) as { q: string; a: string }[];
  const [open, setOpen] = useState(0);
  return (
    <section className="shell grid gap-12 py-24 md:py-36 lg:grid-cols-[1fr_1.4fr]">
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
                <span className="text-xl font-medium tracking-[-0.02em] md:text-2xl">{item.q}</span>
                <span
                  aria-hidden="true"
                  className={`relative size-3.5 shrink-0 transition-transform duration-500 ${expanded ? 'rotate-45' : ''}`}
                >
                  <span className="absolute inset-x-0 top-1/2 h-px bg-ink" />
                  <span className="absolute inset-y-0 start-1/2 w-px bg-ink" />
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
