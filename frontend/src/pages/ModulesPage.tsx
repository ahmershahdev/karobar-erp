import { useTranslation } from 'react-i18next';

import { PageHero } from '../components/PageHero';
import { Reveal } from '../components/Reveal';
import { usePublicSeo } from '../lib/seo';
import { PUBLIC_ROUTES } from '../seo/site';

const GRADIENTS = [
  'var(--gradient-lagoon)',
  'var(--gradient-molten)',
  'var(--gradient-blossom)',
  'var(--gradient-orchard)',
  'var(--gradient-aurora)',
  'var(--gradient-sunrise)',
  'var(--gradient-dusk)',
  'var(--gradient-earth)',
];

export default function ModulesPage() {
  const { t } = useTranslation();
  usePublicSeo(PUBLIC_ROUTES[1]);
  const items = t('modules.items', { returnObjects: true }) as { title: string; body: string }[];
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
      <section data-morph="2" className="shell">
        <Reveal stagger className="border-t border-line">
          {items.map((item, index) => (
            <article
              key={item.title}
              className="group grid gap-4 border-b border-line py-10 md:grid-cols-[5rem_1fr_1.1fr] md:items-baseline md:gap-10 md:py-14"
            >
              <span className="label">{String(index + 1).padStart(2, '0')}</span>
              <h2 className="flex items-center gap-4 font-display text-5xl md:text-7xl">
                <span
                  aria-hidden="true"
                  className="size-3 shrink-0 rounded-full transition-transform duration-700 group-hover:scale-150"
                  style={{ background: GRADIENTS[index % GRADIENTS.length] }}
                />
                {item.title}
              </h2>
              <p className="max-w-md text-lg text-muted">{item.body}</p>
            </article>
          ))}
        </Reveal>
      </section>
    </>
  );
}
