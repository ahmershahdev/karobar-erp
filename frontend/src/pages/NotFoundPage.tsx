import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { usePrivateSeo } from '../lib/seo';

export default function NotFoundPage() {
  const { t } = useTranslation();
  usePrivateSeo(t('notFound.title'));
  return (
    <section className="shell flex min-h-[100svh] flex-col justify-center gap-8 pt-[var(--header-height)]">
      <span className="label">404</span>
      <h1 className="display-xl max-w-[10ch]">{t('notFound.title')}</h1>
      <p className="max-w-md text-lg text-muted">{t('notFound.body')}</p>
      <Link to="/" className="btn btn-ghost w-fit">
        {t('notFound.home')}
      </Link>
    </section>
  );
}
