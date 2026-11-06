import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { SITE } from '../seo/site';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo } from './Logo';
import { Magnetic } from './Magnetic';
import { Reveal } from './Reveal';
import { RollText } from './RollText';

const SHIPPED = 4;
const MILESTONES = 7;
const LATEST = 'v0.4.0';

function useLocalTime(locale: string | undefined): string {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Karachi',
  }).format(now);
}

function FooterLink({ to, href, children }: { to?: string; href?: string; children: string }) {
  const className = 'footer-link group inline-flex text-muted transition-colors hover:text-ink';
  return to ? (
    <Link to={to} className={className}>
      <RollText tone="inherit">{children}</RollText>
    </Link>
  ) : (
    <a href={href} rel="noopener" className={className}>
      <RollText tone="inherit">{children}</RollText>
    </a>
  );
}

// The wordmark set across the full width at the foot of every page, barely there until the
// pointer lights it in the logo's orange.
function GiantWordmark() {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div
      ref={ref}
      aria-hidden="true"
      dir="ltr"
      className="footer-giant relative overflow-hidden px-[var(--gutter)] pt-6"
      onPointerMove={(event) => {
        const element = ref.current;
        if (!element) return;
        const rect = element.getBoundingClientRect();
        element.style.setProperty('--gx', `${event.clientX - rect.left}px`);
        element.style.setProperty('--gy', `${event.clientY - rect.top}px`);
      }}
    >
      <p className="text-center font-display text-[16vw] leading-[0.95] font-semibold tracking-[-0.06em] whitespace-nowrap">
        KarobarERP
      </p>
    </div>
  );
}

export function Footer() {
  const { t, i18n } = useTranslation();
  const time = useLocalTime(i18n.resolvedLanguage);

  const columns = [
    {
      title: t('footer.explore'),
      links: [
        { label: t('nav.home'), to: '/' },
        { label: t('nav.modules'), to: '/modules' },
        { label: t('nav.security'), to: '/security' },
        { label: t('nav.signIn'), to: '/login' },
      ],
    },
    {
      title: t('footer.project'),
      links: [
        { label: t('nav.source'), href: SITE.repo },
        { label: t('footer.wiki'), href: `${SITE.repo}/wiki` },
        { label: t('footer.releases'), href: `${SITE.repo}/releases` },
        { label: t('footer.report'), href: `${SITE.repo}/security/advisories/new` },
      ],
    },
    {
      title: t('footer.contact'),
      links: [
        { label: SITE.email, href: `mailto:${SITE.email}` },
        { label: 'ahmershah.dev', href: SITE.authorUrl },
      ],
    },
  ];

  return (
    <footer className="relative mt-24 overflow-hidden border-t border-line bg-canvas md:mt-32">
      <Reveal className="shell flex flex-col items-start justify-between gap-10 py-20 md:flex-row md:items-end md:py-28">
        <div className="space-y-5">
          <h2 className="display-lg max-w-[15ch]">
            {t('footer.ctaTitle')} <span className="text-flame">{t('footer.ctaAccent')}</span>
          </h2>
          <p className="max-w-md text-lg text-muted">{t('footer.ctaBody')}</p>
        </div>
        <Magnetic strength={0.25}>
          <Link to="/signup" className="btn btn-primary !px-7 !py-4">
            {t('footer.ctaButton')}
            <span aria-hidden="true" className="btn-arrow">
              &rarr;
            </span>
          </Link>
        </Magnetic>
      </Reveal>

      <div className="shell grid gap-12 border-t border-line py-16 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr_1.1fr]">
        <div className="space-y-5">
          <Link to="/" className="inline-block">
            <Logo className="h-9 w-auto" />
          </Link>
          <p className="max-w-xs text-sm text-muted">{t('footer.tagline')}</p>
          <p className="label">
            {t('footer.hyderabad')} &middot; <span className="tabular-nums">{time}</span>
          </p>
        </div>
        {columns.map((column) => (
          <div key={column.title} className="space-y-4">
            <p className="label !text-ink">{column.title}</p>
            <ul className="space-y-2.5 text-sm">
              {column.links.map((link) => (
                <li key={link.label}>
                  <FooterLink {...('to' in link ? { to: link.to } : { href: link.href })}>
                    {link.label}
                  </FooterLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="space-y-4">
          <p className="label !text-ink">{t('footer.status')}</p>
          <p className="text-sm text-muted">{t('footer.shipped', { count: SHIPPED })}</p>
          <div className="flex gap-1" aria-hidden="true">
            {Array.from({ length: MILESTONES }, (_, index) => (
              <span
                key={index}
                className={`h-0.5 flex-1 rounded-full ${index < SHIPPED ? 'bg-ember' : 'bg-line-strong'}`}
              />
            ))}
          </div>
          <p className="label">
            {t('footer.latest')} &middot;{' '}
            <a href={`${SITE.repo}/releases`} rel="noopener" className="text-ink hover:underline">
              {LATEST}
            </a>
          </p>
        </div>
      </div>

      <GiantWordmark />

      <div className="shell flex flex-wrap items-center justify-between gap-6 border-t border-line py-6">
        <span className="label">
          &copy; {new Date().getFullYear()} {SITE.author} &middot; {t('footer.rights')}
        </span>
        <LanguageSwitcher />
      </div>
    </footer>
  );
}
