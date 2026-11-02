import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { SITE } from '../seo/site';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo } from './Logo';

export function Footer() {
  const { t } = useTranslation();
  return (
    <footer className="relative mt-32 border-t border-line">
      <div
        className="absolute inset-x-0 top-0 h-px"
        style={{ background: 'var(--gradient-ledger)' }}
      />
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-16 md:grid-cols-[2fr_1fr_1fr] md:px-8">
        <div className="space-y-4">
          <div className="flex items-center gap-3 font-display text-2xl">
            <Logo className="size-9" />
            Karobar ERP
          </div>
          <p className="max-w-sm text-sm text-muted">{t('hero.eyebrow')}</p>
          <div className="sm:hidden">
            <LanguageSwitcher />
          </div>
        </div>
        <ul className="space-y-3 text-sm">
          <li>
            <Link className="text-muted hover:text-gold" to="/">
              {t('nav.home')}
            </Link>
          </li>
          <li>
            <Link className="text-muted hover:text-gold" to="/modules">
              {t('nav.modules')}
            </Link>
          </li>
          <li>
            <Link className="text-muted hover:text-gold" to="/security">
              {t('nav.security')}
            </Link>
          </li>
        </ul>
        <ul className="space-y-3 text-sm">
          <li>
            <a className="text-muted hover:text-gold" href={SITE.repo} rel="noopener">
              {t('nav.source')}
            </a>
          </li>
          <li>
            <a className="text-muted hover:text-gold" href={`mailto:${SITE.email}`}>
              {SITE.email}
            </a>
          </li>
          <li className="text-muted">{t('footer.status')}</li>
        </ul>
      </div>
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-6 text-xs text-muted md:px-8">
          <span>
            {t('footer.built')}{' '}
            <a className="text-ink hover:text-gold" href={SITE.authorUrl} rel="noopener">
              {SITE.author}
            </a>
          </span>
          <span>
            {t('footer.rights')} &middot; {new Date().getFullYear()}
          </span>
        </div>
      </div>
    </footer>
  );
}
