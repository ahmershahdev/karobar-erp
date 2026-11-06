import { useTranslation } from 'react-i18next';

import { Magnetic } from '../components/Magnetic';
import { PageHero } from '../components/PageHero';
import { Reveal } from '../components/Reveal';
import { SectionHeading } from '../components/SectionHeading';
import { usePublicSeo } from '../lib/seo';
import { PUBLIC_ROUTES, SITE } from '../seo/site';

export default function SecurityPage() {
  const { t } = useTranslation();
  usePublicSeo(PUBLIC_ROUTES[2]);
  const practices = t('security.items', { returnObjects: true }) as {
    title: string;
    body: string;
  }[];
  const flow = t('security.flow.items', { returnObjects: true }) as {
    title: string;
    body: string;
  }[];
  const tested = t('security.tested.items', { returnObjects: true }) as string[];

  return (
    <>
      <PageHero
        trail={[
          { label: t('nav.home'), to: '/' },
          { label: t('nav.security'), to: '/security' },
        ]}
        eyebrow={t('security.eyebrow')}
        title={t('security.pageTitle')}
        accent={t('security.pageAccent')}
        lead={t('security.pageLead')}
      />

      <section className="shell py-12 md:py-20">
        <SectionHeading
          index="01"
          eyebrow={t('security.flow.eyebrow')}
          title={t('security.flow.title')}
        />
        <Reveal stagger className="mt-14 grid gap-4 lg:grid-cols-3">
          {flow.map((item, index) => (
            <article key={item.title} className="card relative overflow-hidden p-8">
              <div className="flex items-center gap-4">
                <span className="flex size-11 items-center justify-center rounded-xl bg-raised text-ink">
                  <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
                    <rect
                      x="5"
                      y="10"
                      width="14"
                      height="10"
                      rx="2"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                    />
                    <path
                      d="M8 10V7a4 4 0 0 1 8 0v3"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                    />
                  </svg>
                </span>
                <span className="label tabular-nums">0{index + 1}</span>
              </div>
              <h3 className="mt-8 text-2xl">{item.title}</h3>
              <p className="mt-3 text-muted">{item.body}</p>
            </article>
          ))}
        </Reveal>
      </section>

      <section className="shell py-12 md:py-20">
        <SectionHeading index="02" eyebrow={t('security.eyebrow')} title={t('security.lead')} />
        <Reveal
          stagger
          className="mt-14 grid gap-px overflow-hidden rounded-[var(--radius-card)] border border-line bg-line sm:grid-cols-2"
        >
          {practices.map((item, index) => (
            <article
              key={item.title}
              className="space-y-4 bg-canvas p-7 transition-colors duration-300 hover:bg-surface md:p-10"
            >
              <span className="label tabular-nums">{String(index + 1).padStart(2, '0')}</span>
              <h3 className="text-2xl md:text-3xl">{item.title}</h3>
              <p className="text-muted">{item.body}</p>
            </article>
          ))}
        </Reveal>
      </section>

      <section className="shell py-12 md:py-20">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.2fr]">
          <SectionHeading
            index="03"
            eyebrow={t('security.tested.eyebrow')}
            title={t('security.tested.title')}
          />
          <Reveal stagger className="border-t border-line">
            {tested.map((item) => (
              <p key={item} className="flex items-start gap-4 border-b border-line py-5">
                <svg
                  viewBox="0 0 16 16"
                  className="mt-1 size-4 shrink-0 text-green"
                  aria-hidden="true"
                >
                  <path d="m3 8.5 3 3 7-7" fill="none" stroke="currentColor" strokeWidth="1.6" />
                </svg>
                <span className="text-muted">{item}</span>
              </p>
            ))}
          </Reveal>
        </div>
      </section>

      <section className="shell py-12 md:py-20">
        <Reveal className="card flex flex-col items-start gap-8 overflow-hidden p-8 md:flex-row md:items-center md:justify-between md:p-14">
          <div className="space-y-3">
            <h2 className="display-md">{t('security.reportTitle')}</h2>
            <p className="max-w-lg text-muted">{t('security.reportBody')}</p>
          </div>
          <Magnetic>
            <a
              href={`${SITE.repo}/security/advisories/new`}
              rel="noopener"
              className="btn btn-primary"
            >
              {t('security.reportButton')}
            </a>
          </Magnetic>
        </Reveal>
      </section>
    </>
  );
}
