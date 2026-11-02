import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { LanguageSwitcher } from '../../components/LanguageSwitcher';
import { Logo } from '../../components/Logo';
import { usePrivateSeo } from '../../lib/seo';

// Split screen on wide displays: the brand panel on one side, the form on the other.
export function AuthCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  usePrivateSeo(title);
  return (
    <div className="grid min-h-[100svh] lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden overflow-hidden border-e border-line lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-10"
          style={{
            background:
              'radial-gradient(70% 60% at 30% 100%, rgb(216 178 106 / 0.28), transparent 70%), radial-gradient(50% 50% at 90% 10%, rgb(116 98 201 / 0.18), transparent 70%)',
          }}
        />
        <Link to="/" className="flex items-center gap-2.5">
          <Logo className="size-7" />
          <span className="font-display text-2xl">Karobar</span>
        </Link>
        <p className="display-lg max-w-[11ch]">
          {t('hero.title')} <em className="text-gradient">{t('hero.accent')}</em>
        </p>
        <span className="label">{t('hero.eyebrow')}</span>
      </aside>
      <section className="flex flex-col px-[var(--gutter)] py-8">
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 lg:invisible">
            <Logo className="size-7" />
            <span className="font-display text-2xl">Karobar</span>
          </Link>
          <LanguageSwitcher />
        </div>
        <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-8 py-12">
          <h1 className="display-md">{title}</h1>
          {children}
          {footer && <div className="text-sm text-muted">{footer}</div>}
        </div>
      </section>
    </div>
  );
}
