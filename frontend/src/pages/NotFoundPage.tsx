import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { usePrivateSeo } from '../lib/seo';

export default function NotFoundPage() {
  const { t } = useTranslation();
  usePrivateSeo(t('notFound.title'));
  return (
    <section className="flex min-h-[80svh] flex-col items-center justify-center gap-6 px-4 text-center">
      <p className="text-gradient font-display text-[8rem] leading-none md:text-[12rem]">404</p>
      <h1 className="text-3xl">{t('notFound.title')}</h1>
      <p className="text-muted">{t('notFound.body')}</p>
      <Link to="/" className="rounded-full bg-cream px-6 py-3 text-black">
        {t('notFound.home')}
      </Link>
    </section>
  );
}
