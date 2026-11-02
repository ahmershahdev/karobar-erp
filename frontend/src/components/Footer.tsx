import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { SITE } from '../seo/site';
import { LanguageSwitcher } from './LanguageSwitcher';

export function Footer() {
  const { t } = useTranslation();
  const columns = [
    {
      title: t('footer.explore'),
      links: [
        { label: t('nav.home'), to: '/' },
        { label: t('nav.modules'), to: '/modules' },
        { label: t('nav.security'), to: '/security' },
        { label: t('nav.signIn'), to: '/app' },
      ],
    },
  ];
  return (
    <footer className="relative mt-24 overflow-hidden border-t border-line bg-black pt-16 md:mt-40">
      <div className="shell grid gap-12 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="space-y-5">
          <p className="display-md max-w-[16ch] font-display">{t('footer.tagline')}</p>
          <a
            href={`mailto:${SITE.email}`}
            className="inline-block text-lg text-gold hover:underline"
          >
            {SITE.email}
          </a>
        </div>
        {columns.map((column) => (
          <div key={column.title} className="space-y-4">
            <p className="label">{column.title}</p>
            <ul className="space-y-2">
              {column.links.map((link) => (
                <li key={link.to}>
                  <Link to={link.to} className="text-ink/80 transition-colors hover:text-gold">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="space-y-4">
          <p className="label">{t('footer.project')}</p>
          <ul className="space-y-2">
            <li>
              <a className="text-ink/80 hover:text-gold" href={SITE.repo} rel="noopener">
                {t('nav.source')}
              </a>
            </li>
            <li>
              <a className="text-ink/80 hover:text-gold" href={`${SITE.repo}/wiki`} rel="noopener">
                {t('footer.wiki')}
              </a>
            </li>
            <li className="text-muted">{t('footer.status')}</li>
          </ul>
        </div>
      </div>
      <div className="shell mt-16 flex flex-wrap items-center justify-between gap-4 border-t border-line py-6">
        <span className="label">
          {t('footer.built')}{' '}
          <a className="!text-ink hover:!text-gold" href={SITE.authorUrl} rel="noopener">
            {SITE.author}
          </a>
        </span>
        <LanguageSwitcher />
        <span className="label">
          {t('footer.rights')} &middot; {new Date().getFullYear()}
        </span>
      </div>
      <p
        aria-hidden="true"
        className="pointer-events-none -mb-[0.22em] text-center font-display text-[24vw] leading-[0.8] tracking-[-0.05em] text-gradient select-none"
      >
        Karobar
      </p>
    </footer>
  );
}
