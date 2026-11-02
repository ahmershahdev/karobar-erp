import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { useScroll } from '../lib/scroll';
import { scrollToTop, useLenis } from '../lib/smooth-scroll';
import { SITE } from '../seo/site';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo } from './Logo';
import { Magnetic } from './Magnetic';
import { Reveal } from './Reveal';
import { RollText } from './RollText';

function useLahoreTime(locale: string | undefined): string {
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

function BackToTop() {
  const { t } = useTranslation();
  const lenis = useLenis();
  const { progress } = useScroll();
  const circumference = 2 * Math.PI * 22;
  return (
    <button
      type="button"
      onClick={() => {
        if (lenis) lenis.scrollTo(0, { duration: 1.6 });
        else scrollToTop(null);
      }}
      className="group relative flex size-14 items-center justify-center"
      aria-label={t('footer.top')}
      data-cursor={t('footer.topShort')}
    >
      <svg viewBox="0 0 48 48" className="absolute inset-0 -rotate-90" aria-hidden="true">
        <circle
          cx="24"
          cy="24"
          r="22"
          fill="none"
          stroke="var(--color-line-strong)"
          strokeWidth="1"
        />
        <circle
          cx="24"
          cy="24"
          r="22"
          fill="none"
          stroke="var(--color-gold)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
        />
      </svg>
      <span className="transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:-translate-y-1">
        &uarr;
      </span>
    </button>
  );
}

function FooterLink({ to, href, children }: { to?: string; href?: string; children: string }) {
  const className = 'group inline-flex text-ink/80 hover:text-ink';
  if (to) {
    return (
      <Link to={to} className={className}>
        <RollText>{children}</RollText>
      </Link>
    );
  }
  return (
    <a href={href} rel="noopener" className={className}>
      <RollText>{children}</RollText>
    </a>
  );
}

export function Footer() {
  const { t, i18n } = useTranslation();
  const time = useLahoreTime(i18n.resolvedLanguage);

  return (
    <footer className="relative mt-24 overflow-hidden bg-black md:mt-40">
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-px"
        style={{ background: 'var(--gradient-molten)' }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background: 'radial-gradient(50% 60% at 85% 0%, rgb(216 178 106 / 0.1), transparent 70%)',
        }}
      />

      <Reveal className="shell relative grid items-center gap-12 py-20 md:grid-cols-[1fr_auto] md:py-28">
        <div className="space-y-6">
          <span className="label !text-gold">[{t('footer.next')}]</span>
          <h2 className="display-lg max-w-[13ch]">
            {t('footer.ctaTitle')} <em className="text-gradient">{t('footer.ctaAccent')}</em>
          </h2>
          <p className="max-w-md text-muted">{t('footer.ctaBody')}</p>
        </div>
        <Magnetic strength={0.4}>
          <Link
            to="/app/sign-up"
            data-cursor={t('cursor.open')}
            className="group relative flex size-40 items-center justify-center overflow-hidden rounded-full text-center font-medium text-black md:size-48"
            style={{ background: 'var(--gradient-molten)' }}
          >
            <span className="absolute inset-0 origin-bottom scale-y-0 rounded-full bg-cream transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:scale-y-100" />
            <span className="relative max-w-[8ch] leading-tight">{t('footer.ctaButton')}</span>
          </Link>
        </Magnetic>
      </Reveal>

      <div className="shell relative grid gap-12 border-t border-line py-16 sm:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr_1fr]">
        <div className="space-y-5">
          <Link to="/" className="flex items-center gap-2.5">
            <Logo className="size-8" />
            <span className="font-display text-3xl">Karobar</span>
          </Link>
          <p className="max-w-xs text-sm text-muted">{t('footer.tagline')}</p>
          <div className="flex items-center gap-3">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-mint opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-mint" />
            </span>
            <span className="label">
              {t('footer.lahore')} &middot; <span className="tabular-nums">{time}</span>
            </span>
          </div>
        </div>
        <div className="space-y-4">
          <p className="label">{t('footer.explore')}</p>
          <ul className="space-y-2.5">
            <li>
              <FooterLink to="/">{t('nav.home')}</FooterLink>
            </li>
            <li>
              <FooterLink to="/modules">{t('nav.modules')}</FooterLink>
            </li>
            <li>
              <FooterLink to="/security">{t('nav.security')}</FooterLink>
            </li>
            <li>
              <FooterLink to="/app">{t('nav.signIn')}</FooterLink>
            </li>
          </ul>
        </div>
        <div className="space-y-4">
          <p className="label">{t('footer.project')}</p>
          <ul className="space-y-2.5">
            <li>
              <FooterLink href={SITE.repo}>{t('nav.source')}</FooterLink>
            </li>
            <li>
              <FooterLink href={`${SITE.repo}/wiki`}>{t('footer.wiki')}</FooterLink>
            </li>
            <li>
              <FooterLink href={`${SITE.repo}/releases`}>{t('footer.releases')}</FooterLink>
            </li>
            <li>
              <FooterLink href={`${SITE.repo}/blob/main/SECURITY.md`}>
                {t('footer.report')}
              </FooterLink>
            </li>
          </ul>
        </div>
        <div className="space-y-4">
          <p className="label">{t('footer.contact')}</p>
          <ul className="space-y-2.5">
            <li>
              <FooterLink href={`mailto:${SITE.email}`}>{SITE.email}</FooterLink>
            </li>
            <li>
              <FooterLink href={SITE.authorUrl}>ahmershah.dev</FooterLink>
            </li>
          </ul>
        </div>
      </div>

      <div className="shell relative flex flex-wrap items-center justify-between gap-6 border-t border-line py-6">
        <span className="label">
          &copy; {new Date().getFullYear()} {SITE.author} &middot; {t('footer.rights')}
        </span>
        <LanguageSwitcher />
        <BackToTop />
      </div>
    </footer>
  );
}
