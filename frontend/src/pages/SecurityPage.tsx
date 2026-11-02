import { useTranslation } from 'react-i18next';

import { PageHero } from '../components/PageHero';
import { Reveal } from '../components/Reveal';
import { usePublicSeo } from '../lib/seo';
import { PUBLIC_ROUTES } from '../seo/site';

export default function SecurityPage() {
  const { t } = useTranslation();
  usePublicSeo(PUBLIC_ROUTES[2]);
  const items = t('security.items', { returnObjects: true }) as { title: string; body: string }[];
  return (
    <>
      <PageHero
        trail={[
          { label: t('nav.home'), to: '/' },
          { label: t('nav.security'), to: '/security' },
        ]}
        index="02"
        eyebrow={t('security.eyebrow')}
        title={t('security.pageTitle')}
        accent={t('security.pageAccent')}
        lead={t('security.lead')}
      />
      <section data-morph="2" className="shell">
        <Reveal
          stagger
          className="grid gap-px overflow-hidden rounded-[var(--radius-card)] border border-line bg-line sm:grid-cols-2"
        >
          {items.map((item, index) => (
            <article
              key={item.title}
              className="space-y-4 bg-black/85 p-7 backdrop-blur transition-colors duration-500 hover:bg-raised md:p-10"
            >
              <span className="label !text-gold">{String(index + 1).padStart(2, '0')}</span>
              <h2 className="font-display text-3xl md:text-4xl">{item.title}</h2>
              <p className="text-muted">{item.body}</p>
            </article>
          ))}
        </Reveal>
        <p className="mt-10 max-w-2xl text-sm text-muted">{t('security.report')}</p>
      </section>
    </>
  );
}
