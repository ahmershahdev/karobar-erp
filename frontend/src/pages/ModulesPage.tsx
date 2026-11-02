import { useTranslation } from 'react-i18next';

import { Breadcrumbs } from '../components/Breadcrumbs';
import { SectionHeading } from '../components/SectionHeading';
import { ModuleGrid } from '../features/modules/ModuleGrid';
import { usePublicSeo } from '../lib/seo';
import { PUBLIC_ROUTES } from '../seo/site';

export default function ModulesPage() {
  const { t } = useTranslation();
  usePublicSeo(PUBLIC_ROUTES[1]);
  return (
    <section className="mx-auto max-w-7xl px-4 pt-40 md:px-8">
      <Breadcrumbs
        trail={[
          { label: t('nav.home'), to: '/' },
          { label: t('nav.modules'), to: '/modules' },
        ]}
      />
      <div className="mt-10">
        <SectionHeading
          eyebrow={t('modules.eyebrow')}
          title={t('modules.title')}
          lead={t('modules.lead')}
          gradient="var(--gradient-lagoon)"
        />
      </div>
      <div className="mt-16">
        <ModuleGrid />
      </div>
    </section>
  );
}
