import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { SITE } from '../seo/site';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo, Wordmark } from './Logo';
import { Magnetic } from './Magnetic';
import { Reveal } from './Reveal';
import { RollText } from './RollText';

const SHIPPED = 3;
const MILESTONES = 7;
const LATEST = 'v0.3.0';

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

function FooterLink({ to, href, children }: { to?: string; href?: string; children: string }) {
  const className = 'group inline-flex text-ink/75 transition-colors hover:text-ink';
  return to ? (
    <Link to={to} className={className}>
      <RollText>{children}</RollText>
    </Link>
  ) : (
    <a href={href} rel="noopener" className={className}>
      <RollText>{children}</RollText>
    </a>
  );
}

export function Footer() {
  const { t, i18n } = useTranslation();
  const time = useLahoreTime(i18n.resolvedLanguage);

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
    <footer className="relative mt-24 overflow-hidden border-t border-line bg-black md:mt-40">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(45% 55% at 90% 0%, color-mix(in srgb, var(--color-ember) 12%, transparent), transparent 70%), radial-gradient(35% 45% at 0% 100%, color-mix(in srgb, var(--color-azure) 8%, transparent), transparent 70%)',
        }}
      />

      <Reveal className="shell relative grid items-center gap-12 py-20 md:grid-cols-[1fr_auto] md:py-28">
        <div className="space-y-6">
          <span className="label !text-ember">[{t('footer.next')}]</span>
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

      <div className="shell relative grid gap-12 border-t border-line py-16 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr_1.2fr]">
        <div className="space-y-5">
          <Link to="/" className="flex items-center gap-2.5">
            <Logo className="size-8" />
            <Wordmark className="text-2xl" />
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
        {columns.map((column) => (
          <div key={column.title} className="space-y-4">
            <p className="label">{column.title}</p>
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
          <p className="label">{t('footer.status')}</p>
          <div className="space-y-3 rounded-2xl border border-line bg-white/[0.02] p-5">
            <p className="text-sm">{t('footer.shipped', { count: SHIPPED })}</p>
            <div className="flex gap-1" aria-hidden="true">
              {Array.from({ length: MILESTONES }, (_, index) => (
                <span
                  key={index}
                  className={`h-1 flex-1 rounded-full ${index < SHIPPED ? 'bg-ember' : 'bg-line-strong'}`}
                />
              ))}
            </div>
            <p className="label">
              {t('footer.latest')} &middot;{' '}
              <a
                href={`${SITE.repo}/releases`}
                rel="noopener"
                className="!text-ember hover:underline"
              >
                {LATEST}
              </a>
            </p>
          </div>
          <a
            href={SITE.repo}
            rel="noopener"
            data-cursor-stick
            className="inline-flex items-center gap-2 rounded-full border border-line-strong px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember"
          >
            <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
              <path
                d="M8 1.5 9.9 5.4l4.3.6-3.1 3 .7 4.3L8 11.3l-3.8 2 .7-4.3-3.1-3 4.3-.6Z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinejoin="round"
              />
            </svg>
            {t('footer.github')}
          </a>
        </div>
      </div>

      <div className="shell relative flex flex-wrap items-center justify-between gap-6 border-t border-line py-6">
        <span className="label">
          &copy; {new Date().getFullYear()} {SITE.author} &middot; {t('footer.rights')}
        </span>
        <LanguageSwitcher />
      </div>
    </footer>
  );
}
