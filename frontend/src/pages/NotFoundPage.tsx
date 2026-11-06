import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router';

import { Mascot } from '../features/mascot/Mascot';
import { usePrivateSeo } from '../lib/seo';

const MOODS = ['walking', 'confused', 'looking'] as const;

export default function NotFoundPage() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  usePrivateSeo(t('notFound.title'));
  const reasons = t('notFound.reasons', { returnObjects: true }) as string[];
  const links = [
    { to: '/modules', label: t('nav.modules') },
    { to: '/security', label: t('nav.security') },
    { to: '/login', label: t('nav.signIn') },
  ];

  return (
    <section className="shell grid min-h-[100svh] items-center gap-10 pt-[calc(var(--header-height)+2rem)] pb-16 md:grid-cols-2 md:gap-16">
      <div className="overflow-hidden md:order-2">
        <Mascot moods={MOODS} label={t('mascot.label')} />
        <p className="label mt-3 text-center">{t('mascot.hint')}</p>
      </div>
      <div className="space-y-6">
        <p className="label text-ember">{t('notFound.code')}</p>
        <h1 className="display-lg">{t('notFound.title')}</h1>
        <p className="max-w-md text-lg text-muted">{t('notFound.body')}</p>
        <p
          className="w-fit max-w-full truncate rounded-lg bg-raised px-3 py-1.5 font-mono text-sm"
          dir="ltr"
        >
          {pathname}
        </p>
        <div className="space-y-2">
          <p className="font-medium">{t('notFound.whyTitle')}</p>
          <ul className="max-w-md list-disc space-y-1 ps-5 text-muted">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to="/" className="btn btn-primary">
            {t('notFound.home')}
          </Link>
          <button type="button" className="btn btn-ghost" onClick={() => void navigate(-1)}>
            {t('notFound.back')}
          </button>
        </div>
        <nav aria-label={t('notFound.linksTitle')} className="flex flex-wrap gap-x-5 gap-y-1">
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="text-muted underline underline-offset-4 hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </section>
  );
}
