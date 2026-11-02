import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { Marquee } from '../components/Marquee';
import { Reveal } from '../components/Reveal';
import { SectionHeading } from '../components/SectionHeading';
import { SplitHeadline } from '../components/SplitHeadline';
import { HeroBackdrop } from '../features/hero/HeroBackdrop';
import { LedgerDemo } from '../features/ledger/LedgerDemo';
import { ModuleGrid } from '../features/modules/ModuleGrid';
import { usePublicSeo } from '../lib/seo';
import { PUBLIC_ROUTES, SITE } from '../seo/site';

const PROMISE_ACCENTS = [
  'var(--gradient-ledger)',
  'var(--gradient-lagoon)',
  'var(--gradient-dusk)',
];

export default function HomePage() {
  const { t } = useTranslation();
  usePublicSeo(PUBLIC_ROUTES[0]);
  const promises = t('promises.items', { returnObjects: true }) as {
    title: string;
    body: string;
  }[];

  return (
    <>
      <section className="relative flex min-h-[100svh] items-end overflow-hidden pb-20 md:pb-28">
        <HeroBackdrop />
        <div className="relative mx-auto w-full max-w-7xl px-4 md:px-8">
          <Reveal>
            <p className="mb-6 inline-flex items-center gap-3 rounded-full border border-cream/15 bg-black/30 px-4 py-2 text-xs tracking-wide text-cream/80 backdrop-blur">
              <span className="size-1.5 rounded-full bg-mint" />
              {t('hero.eyebrow')}
            </p>
          </Reveal>
          <SplitHeadline
            text={t('hero.title')}
            className="max-w-5xl text-5xl leading-[0.98] sm:text-7xl lg:text-8xl"
          />
          <Reveal
            delay={600}
            className="mt-8 flex flex-col gap-8 md:flex-row md:items-end md:justify-between"
          >
            <p className="max-w-xl text-lg text-cream/80">{t('hero.lead')}</p>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/modules"
                className="rounded-full px-6 py-3 font-medium text-black transition-transform duration-300 hover:-translate-y-0.5"
                style={{ background: 'var(--gradient-ledger)' }}
              >
                {t('hero.primary')}
              </Link>
              <a
                href={SITE.repo}
                rel="noopener"
                className="rounded-full border border-cream/25 px-6 py-3 text-cream backdrop-blur transition-colors hover:border-gold hover:text-gold"
              >
                {t('hero.secondary')}
              </a>
            </div>
          </Reveal>
        </div>
      </section>

      <Marquee items={t('marquee', { returnObjects: true }) as string[]} />

      <section className="mx-auto max-w-7xl px-4 py-32 md:px-8">
        <SectionHeading eyebrow={t('promises.eyebrow')} title={t('promises.title')} />
        <Reveal stagger className="mt-16 grid gap-4 md:grid-cols-3">
          {promises.map((promise, index) => (
            <article
              key={promise.title}
              className="gradient-border p-8"
              style={{ ['--gradient' as string]: PROMISE_ACCENTS[index] }}
            >
              <span
                className="text-gradient font-display text-6xl"
                style={{ ['--gradient' as string]: PROMISE_ACCENTS[index] }}
              >
                {index + 1}
              </span>
              <h3 className="mt-8 text-2xl">{promise.title}</h3>
              <p className="mt-3 leading-relaxed text-muted">{promise.body}</p>
            </article>
          ))}
        </Reveal>
      </section>

      <section className="relative overflow-hidden py-32">
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-10 opacity-40"
          style={{
            background: 'radial-gradient(50% 60% at 80% 50%, var(--color-maroon), transparent 70%)',
          }}
        />
        <div className="mx-auto grid max-w-7xl items-center gap-16 px-4 md:px-8 lg:grid-cols-2">
          <SectionHeading
            eyebrow={t('ledger.eyebrow')}
            title={t('ledger.title')}
            lead={t('ledger.body')}
          />
          <Reveal delay={200}>
            <LedgerDemo />
          </Reveal>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-32 md:px-8">
        <div className="flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
          <SectionHeading
            eyebrow={t('modules.eyebrow')}
            title={t('modules.title')}
            lead={t('modules.lead')}
            gradient="var(--gradient-lagoon)"
          />
          <Link to="/modules" className="text-sm text-gold underline-offset-8 hover:underline">
            {t('hero.primary')}
          </Link>
        </div>
        <div className="mt-16">
          <ModuleGrid limit={4} />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-32 md:px-8">
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.2fr]">
          <SectionHeading
            eyebrow={t('languages.eyebrow')}
            title={t('languages.title')}
            lead={t('languages.body')}
            gradient="var(--gradient-orchard)"
          />
          <Reveal stagger className="grid gap-3">
            <p lang="en" dir="ltr" className="font-display text-4xl md:text-6xl">
              Invoice paid.
            </p>
            <p
              lang="ur"
              dir="rtl"
              className="text-gradient text-4xl leading-[1.9] md:text-6xl"
              style={{
                fontFamily: 'var(--font-urdu)',
                ['--gradient' as string]: 'var(--gradient-orchard)',
              }}
            >
              انوائس ادا ہو گئی۔
            </p>
            <p
              lang="ar"
              dir="rtl"
              className="text-4xl text-muted md:text-6xl"
              style={{ fontFamily: 'var(--font-arabic)' }}
            >
              تم دفع الفاتورة.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 md:px-8">
        <Reveal className="relative overflow-hidden rounded-[2rem] px-8 py-20 text-center md:px-16 md:py-28">
          <div
            aria-hidden="true"
            className="absolute inset-0 -z-10"
            style={{ background: 'var(--gradient-aurora)' }}
          />
          <h2 className="mx-auto max-w-3xl text-4xl md:text-6xl">{t('cta.title')}</h2>
          <p className="mx-auto mt-5 max-w-xl text-lg text-cream/80">{t('cta.body')}</p>
          <a
            href={SITE.repo}
            rel="noopener"
            className="mt-10 inline-flex rounded-full bg-cream px-7 py-3.5 font-medium text-black transition-transform duration-300 hover:-translate-y-0.5"
          >
            {t('cta.button')}
          </a>
        </Reveal>
      </section>
    </>
  );
}
