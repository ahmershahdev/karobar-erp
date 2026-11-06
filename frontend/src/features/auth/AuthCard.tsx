import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { LanguageSwitcher } from '../../components/LanguageSwitcher';
import { Logo } from '../../components/Logo';
import { Reveal } from '../../components/Reveal';
import { usePrivateSeo } from '../../lib/seo';

// Split screen on wide displays: the promise on a quiet tinted panel, the form on white. Phones
// get the form alone, with the logo above it.
export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  usePrivateSeo(title);
  const benefits = t('auth.benefits', { returnObjects: true }) as string[];

  return (
    <div className="grid min-h-[100svh] lg:grid-cols-[1fr_1.1fr]">
      <aside className="hidden flex-col justify-between border-e border-line bg-surface p-12 lg:flex">
        <Link to="/" className="inline-block w-fit">
          <Logo className="h-9 w-auto" />
        </Link>
        <div className="max-w-md space-y-8">
          <p className="display-md font-display font-medium">
            {t('hero.title')} <span className="text-flame">{t('hero.accent')}</span>
          </p>
          <ul className="space-y-3">
            {benefits.map((benefit) => (
              <li key={benefit} className="flex items-center gap-3 text-muted">
                <svg viewBox="0 0 16 16" className="size-4 shrink-0 text-green" aria-hidden="true">
                  <path d="m3 8.5 3 3 7-7" fill="none" stroke="currentColor" strokeWidth="1.6" />
                </svg>
                {benefit}
              </li>
            ))}
          </ul>
        </div>
        <span className="label">{t('hero.eyebrow')}</span>
      </aside>

      <section className="flex flex-col bg-canvas px-[var(--gutter)] py-6 lg:py-8">
        <div className="flex items-center justify-between">
          <Link to="/" className="inline-block lg:invisible">
            <Logo className="h-8 w-auto" />
          </Link>
          <LanguageSwitcher />
        </div>
        <Reveal
          stagger
          className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-8 py-12"
        >
          <div className="space-y-3">
            <h1 className="display-md">{title}</h1>
            {subtitle && <p className="text-muted">{subtitle}</p>}
          </div>
          <div>{children}</div>
          {footer && <div className="text-sm text-muted">{footer}</div>}
        </Reveal>
      </section>
    </div>
  );
}
