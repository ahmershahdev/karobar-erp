import { useTranslation } from 'react-i18next';

import { Breadcrumbs } from '../components/Breadcrumbs';
import { Reveal } from '../components/Reveal';
import { SectionHeading } from '../components/SectionHeading';
import { usePublicSeo } from '../lib/seo';
import { PUBLIC_ROUTES } from '../seo/site';

export default function SecurityPage() {
  const { t } = useTranslation();
  usePublicSeo(PUBLIC_ROUTES[2]);
  const items = t('security.items', { returnObjects: true }) as { title: string; body: string }[];
  return (
    <section className="mx-auto max-w-7xl px-4 pt-40 md:px-8">
      <Breadcrumbs
        trail={[
          { label: t('nav.home'), to: '/' },
          { label: t('nav.security'), to: '/security' },
        ]}
      />
      <div className="mt-10">
        <SectionHeading
          eyebrow={t('security.eyebrow')}
          title={t('security.title')}
          lead={t('security.lead')}
          gradient="var(--gradient-dusk)"
        />
      </div>
      <Reveal
        stagger
        className="mt-16 grid gap-px overflow-hidden rounded-[var(--radius-card)] border border-line bg-line md:grid-cols-2"
      >
        {items.map((item) => (
          <article
            key={item.title}
            className="bg-canvas p-8 transition-colors duration-500 hover:bg-surface"
          >
            <h3 className="text-xl">{item.title}</h3>
            <p className="mt-3 leading-relaxed text-muted">{item.body}</p>
          </article>
        ))}
      </Reveal>
      <p className="mt-10 text-sm text-muted">{t('security.report')}</p>
    </section>
  );
}
