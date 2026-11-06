import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { Magnetic } from '../components/Magnetic';
import { Reveal } from '../components/Reveal';
import { ScrollWords } from '../components/ScrollWords';
import { SectionHeading } from '../components/SectionHeading';
import { SplitHeadline } from '../components/SplitHeadline';
import { ProductWindow } from '../features/home/ProductWindow';
import { BuiltFor, Faq, HowItWorks, Roadmap, StatsBand } from '../features/home/sections';
import { ModuleGallery } from '../features/modules/ModuleGallery';
import { isIntroPending } from '../lib/intro';
import { usePublicSeo } from '../lib/seo';
import { PUBLIC_ROUTES, SITE } from '../seo/site';

export default function HomePage() {
  const { t } = useTranslation();
  usePublicSeo(PUBLIC_ROUTES[0]);
  const [introDelay] = useState(() => (isIntroPending() ? 900 : 100));
  const rules = t('promises.items', { returnObjects: true }) as { title: string; body: string }[];

  return (
    <>
      <section className="shell pt-[calc(var(--header-height)+4rem)] md:pt-[calc(var(--header-height)+6.5rem)]">
        <Reveal delay={introDelay}>
          <p className="label">{t('hero.eyebrow')}</p>
        </Reveal>
        <SplitHeadline
          text={t('hero.title')}
          accent={t('hero.accent')}
          className="display-xl mt-6"
          delay={introDelay}
        />
        <Reveal
          delay={introDelay + 350}
          className="mt-10 flex flex-col gap-8 md:flex-row md:items-end md:justify-between"
        >
          <p className="max-w-xl text-lg text-muted md:text-xl">{t('hero.lead')}</p>
          <div className="flex shrink-0 flex-wrap items-center gap-3">
            <Magnetic strength={0.2}>
              <Link to="/app/sign-up" className="btn btn-primary">
                {t('auth.joinTitle')}
                <span aria-hidden="true" className="btn-arrow">
                  &rarr;
                </span>
              </Link>
            </Magnetic>
            <Link to="/modules" className="btn btn-ghost">
              {t('hero.primary')}
            </Link>
          </div>
        </Reveal>
      </section>

      <section className="shell pt-16 md:pt-24">
        <Reveal delay={introDelay + 500}>
          <ProductWindow />
        </Reveal>
        <div className="mt-16 grid gap-6 md:mt-24 md:grid-cols-2 md:gap-12">
          <SectionHeading index="01" eyebrow={t('ledger.eyebrow')} title={t('ledger.title')} />
          <Reveal className="md:pt-11">
            <p className="max-w-lg text-lg text-muted">{t('ledger.body')}</p>
          </Reveal>
        </div>
      </section>

      <section className="shell py-24 md:py-40">
        <p className="label mb-8 flex items-center gap-3">
          <span className="text-ember tabular-nums">02</span>
          {t('manifesto.eyebrow')}
        </p>
        <ScrollWords text={t('manifesto.body')} className="display-md max-w-5xl font-display" />
      </section>

      <StatsBand />

      <section className="shell py-24 md:py-36">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.4fr]">
          <div className="lg:sticky lg:top-[calc(var(--header-height)+3rem)] lg:self-start">
            <SectionHeading
              index="03"
              eyebrow={t('promises.eyebrow')}
              title={t('promises.title')}
            />
          </div>
          <Reveal stagger className="border-t border-line">
            {rules.map((rule) => (
              <article key={rule.title} className="border-b border-line py-10 md:py-14">
                <h3 className="text-3xl md:text-4xl">{rule.title}</h3>
                <p className="mt-4 max-w-lg text-lg text-muted">{rule.body}</p>
              </article>
            ))}
          </Reveal>
        </div>
      </section>

      <section className="shell pb-8">
        <div className="mb-12 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <SectionHeading
            index="04"
            eyebrow={t('modules.eyebrow')}
            title={t('modules.title')}
            lead={t('modules.lead')}
          />
          <Link to="/modules" className="btn btn-ghost w-fit shrink-0">
            {t('modules.all')}
          </Link>
        </div>
        <ModuleGallery />
      </section>

      <BuiltFor />
      <HowItWorks />

      <section className="shell py-24 md:py-36">
        <SectionHeading index="07" eyebrow={t('languages.eyebrow')} title={t('languages.title')} />
        <Reveal stagger className="mt-14 divide-y divide-line border-y border-line">
          <p
            lang="en"
            dir="ltr"
            className="py-6 font-display text-4xl tracking-[-0.04em] md:text-7xl"
          >
            Invoice <span className="text-flame">paid.</span>
          </p>
          <p
            lang="ur"
            dir="rtl"
            className="py-6 text-3xl leading-[1.9] md:text-6xl"
            style={{ fontFamily: 'var(--font-urdu)' }}
          >
            انوائس ادا ہو گئی۔
          </p>
          <p
            lang="ar"
            dir="rtl"
            className="py-6 text-3xl md:text-6xl"
            style={{ fontFamily: 'var(--font-arabic)' }}
          >
            تم دفع الفاتورة.
          </p>
        </Reveal>
        <p className="mt-8 max-w-xl text-muted">{t('languages.body')}</p>
      </section>

      <Roadmap />
      <Faq />

      <section className="shell pb-6 text-center">
        <a href={SITE.repo} rel="noopener" className="label hover:text-ink">
          {t('cta.title')} &middot; {t('cta.button')}
        </a>
      </section>
    </>
  );
}
