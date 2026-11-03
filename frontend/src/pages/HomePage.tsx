import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { Magnetic } from '../components/Magnetic';
import { Marquee } from '../components/Marquee';
import { Reveal } from '../components/Reveal';
import { ScrollWords } from '../components/ScrollWords';
import { SectionHeading } from '../components/SectionHeading';
import { SplitHeadline } from '../components/SplitHeadline';
import { BuiltFor, Faq, HowItWorks, Roadmap, StatsBand } from '../features/home/sections';
import { LedgerDemo } from '../features/ledger/LedgerDemo';
import { ModuleGallery } from '../features/modules/ModuleGallery';
import { isIntroPending } from '../lib/intro';
import { usePublicSeo } from '../lib/seo';
import { PUBLIC_ROUTES, SITE } from '../seo/site';

const RULE_ACCENTS = ['var(--gradient-molten)', 'var(--gradient-lagoon)', 'var(--gradient-dusk)'];

export default function HomePage() {
  const { t } = useTranslation();
  usePublicSeo(PUBLIC_ROUTES[0]);
  const [introDelay] = useState(() => (isIntroPending() ? 1500 : 150));
  const rules = t('promises.items', { returnObjects: true }) as { title: string; body: string }[];

  return (
    <>
      <section data-morph="0" className="relative flex min-h-[100svh] flex-col">
        <div className="shell flex flex-1 flex-col justify-end pt-[calc(var(--header-height)+2rem)] pb-10 md:pb-14">
          <Reveal className="mb-8 flex items-center gap-3">
            <span className="size-1.5 animate-pulse rounded-full bg-mint" />
            <span className="label">{t('hero.eyebrow')}</span>
          </Reveal>
          <SplitHeadline
            text={t('hero.title')}
            accent={t('hero.accent')}
            className="display-xl max-w-[13ch]"
            delay={introDelay}
          />
          <Reveal
            delay={introDelay + 500}
            className="mt-10 grid gap-8 border-t border-line pt-8 md:grid-cols-[1fr_auto] md:items-end"
          >
            <p className="max-w-lg text-base text-ink/75 md:text-lg">{t('hero.lead')}</p>
            <div className="flex flex-wrap items-center gap-3">
              <Magnetic>
                <Link
                  to="/app/sign-up"
                  data-cursor-stick
                  className="inline-flex items-center gap-3 rounded-full px-7 py-4 font-medium text-black"
                  style={{ background: 'var(--gradient-molten)' }}
                >
                  {t('auth.joinTitle')}
                  <span aria-hidden="true" className="rtl:rotate-180">
                    &rarr;
                  </span>
                </Link>
              </Magnetic>
              <Link
                to="/modules"
                data-cursor-stick
                className="rounded-full border border-line-strong px-7 py-4 transition-colors hover:border-gold hover:text-gold"
              >
                {t('hero.primary')}
              </Link>
            </div>
          </Reveal>
        </div>
        <div className="shell hidden justify-center pb-6 md:flex">
          <span className="relative h-10 w-px overflow-hidden bg-line" aria-hidden="true">
            <span className="absolute inset-0 bg-gold [animation:scroll-cue_2.4s_var(--ease-in-out-expo)_infinite]" />
          </span>
        </div>
      </section>

      <section data-morph="0" className="shell py-28 md:py-44">
        <span className="label mb-8 block !text-gold">[01] {t('manifesto.eyebrow')}</span>
        <ScrollWords
          text={t('manifesto.body')}
          className="display-md max-w-5xl font-display !leading-[1.12]"
        />
      </section>

      <Marquee items={t('marquee', { returnObjects: true }) as string[]} />
      <StatsBand />

      <section data-morph="1" className="shell py-28 md:py-40">
        <SectionHeading index="02" eyebrow={t('promises.eyebrow')} title={t('promises.title')} />
        <Reveal stagger className="mt-16 border-t border-line md:mt-24">
          {rules.map((rule, index) => (
            <article
              key={rule.title}
              className="group grid gap-4 border-b border-line py-10 md:grid-cols-[6rem_1fr_1fr] md:gap-10 md:py-14"
            >
              <span
                className="text-gradient font-display text-6xl leading-none md:text-7xl"
                style={{ ['--gradient' as string]: RULE_ACCENTS[index] }}
              >
                {String(index + 1).padStart(2, '0')}
              </span>
              <h3 className="font-display text-4xl leading-tight transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:translate-x-2 md:text-5xl rtl:group-hover:-translate-x-2">
                {rule.title}
              </h3>
              <p className="max-w-md text-muted md:pt-3">{rule.body}</p>
            </article>
          ))}
        </Reveal>
      </section>

      <section data-morph="1" className="shell py-20 md:py-32">
        <div className="grid items-center gap-14 lg:grid-cols-[1fr_1.1fr] lg:gap-20">
          <SectionHeading
            index="03"
            eyebrow={t('ledger.eyebrow')}
            title={t('ledger.title')}
            lead={t('ledger.body')}
          />
          <Reveal delay={150}>
            <LedgerDemo />
          </Reveal>
        </div>
      </section>

      <section data-morph="2" className="pt-20 md:pt-32">
        <div className="shell mb-14 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <SectionHeading
            index="04"
            eyebrow={t('modules.eyebrow')}
            title={t('modules.title')}
            lead={t('modules.lead')}
          />
          <Link to="/modules" className="label !text-gold hover:underline">
            {t('modules.all')}
          </Link>
        </div>
        <ModuleGallery />
      </section>

      <BuiltFor />
      <HowItWorks />

      <section data-morph="2" className="shell py-20 md:py-32">
        <SectionHeading index="07" eyebrow={t('languages.eyebrow')} title={t('languages.title')} />
        <Reveal stagger className="mt-14 divide-y divide-line border-y border-line">
          <p lang="en" dir="ltr" className="py-6 font-display text-5xl md:text-8xl">
            Invoice <em className="text-gradient">paid.</em>
          </p>
          <p
            lang="ur"
            dir="rtl"
            className="py-6 text-4xl leading-[1.9] md:text-7xl"
            style={{ fontFamily: 'var(--font-urdu)' }}
          >
            انوائس ادا ہو گئی۔
          </p>
          <p
            lang="ar"
            dir="rtl"
            className="py-6 text-4xl text-muted md:text-7xl"
            style={{ fontFamily: 'var(--font-arabic)' }}
          >
            تم دفع الفاتورة.
          </p>
        </Reveal>
        <p className="mt-8 max-w-xl text-muted">{t('languages.body')}</p>
      </section>

      <Roadmap />
      <Faq />

      <section data-morph="2" className="shell pb-6 text-center">
        <a
          href={SITE.repo}
          rel="noopener"
          className="label inline-flex items-center gap-2 hover:!text-gold"
        >
          {t('cta.title')} &middot; {t('cta.button')}
        </a>
      </section>
    </>
  );
}
