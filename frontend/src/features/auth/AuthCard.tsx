import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { LanguageSwitcher } from '../../components/LanguageSwitcher';
import { Logo } from '../../components/Logo';
import { Reveal } from '../../components/Reveal';
import { useMediaQuery } from '../../lib/motion';
import { usePrivateSeo } from '../../lib/seo';
import { Backdrop } from '../scene/Backdrop';

// Split screen on wide displays: the live particle globe behind the brand panel on one side, the
// form on a quiet surface on the other. Phones get the form alone, with the brand line above it.
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
  // Mounted, not just hidden, only on wide screens: a hidden canvas would still animate.
  const wide = useMediaQuery('(min-width: 1024px)');

  return (
    <div className="relative grid min-h-[100svh] lg:grid-cols-[1.15fr_1fr]">
      {wide && <Backdrop side="left" />}
      <aside className="relative hidden flex-col justify-between p-12 lg:flex" data-morph="0">
        <Link to="/" className="flex items-center gap-2.5">
          <Logo className="size-8" />
          <span className="font-display text-3xl">Karobar</span>
        </Link>
        <div className="max-w-md space-y-8">
          <p className="font-display text-6xl leading-[0.95] tracking-tight xl:text-7xl">
            {t('hero.title')} <em className="text-gradient">{t('hero.accent')}</em>
          </p>
          <ul className="space-y-3">
            {benefits.map((benefit) => (
              <li key={benefit} className="flex items-center gap-3 text-ink/85">
                <svg viewBox="0 0 16 16" className="size-4 shrink-0 text-gold" aria-hidden="true">
                  <path d="m3 8.5 3 3 7-7" fill="none" stroke="currentColor" strokeWidth="1.6" />
                </svg>
                {benefit}
              </li>
            ))}
          </ul>
        </div>
        <span className="label">{t('hero.eyebrow')}</span>
      </aside>

      <section className="relative flex flex-col border-line bg-black/85 px-[var(--gutter)] py-8 backdrop-blur-xl lg:border-s">
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 lg:invisible">
            <Logo className="size-7" />
            <span className="font-display text-2xl">Karobar</span>
          </Link>
          <LanguageSwitcher />
        </div>
        <Reveal
          stagger
          className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-8 py-12"
        >
          <div className="space-y-3">
            <span className="label !text-gold lg:hidden">{t('auth.panelTitle')}</span>
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
