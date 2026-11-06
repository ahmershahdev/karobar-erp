import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink, useLocation } from 'react-router';

import { useSignedIn } from '../features/auth/session';
import { useScroll } from '../lib/scroll';
import { useLenis } from '../lib/smooth-scroll';
import { SITE } from '../seo/site';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo } from './Logo';
import { RollText } from './RollText';

function MobileMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const signedIn = useSignedIn();
  if (!open) return null;
  const links = [
    { to: '/', label: t('nav.home') },
    { to: '/modules', label: t('nav.modules') },
    { to: '/security', label: t('nav.security') },
    signedIn ? { to: '/app', label: t('nav.openApp') } : { to: '/login', label: t('nav.signIn') },
  ];
  return (
    <div
      id="mobile-menu"
      className="fixed inset-0 z-[65] flex flex-col overflow-y-auto overscroll-contain bg-canvas px-[var(--gutter)] pt-[calc(var(--header-height)+1.5rem)] pb-8 md:hidden"
      data-lenis-prevent
    >
      <nav className="flex-1">
        <ul className="border-t border-line">
          {links.map((link) => (
            <li key={link.to} className="border-b border-line">
              <Link
                to={link.to}
                onClick={onClose}
                className="flex items-center justify-between py-5 font-display text-3xl tracking-[-0.03em]"
              >
                {link.label}
                <span aria-hidden="true" className="text-xl text-muted rtl:rotate-180">
                  &rarr;
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="space-y-5 pt-8">
        <a href={`mailto:${SITE.email}`} className="block text-muted">
          {SITE.email}
        </a>
        <div className="flex items-center justify-between">
          <LanguageSwitcher />
          <a href={SITE.repo} rel="noopener" className="label">
            GitHub
          </a>
        </div>
      </div>
    </div>
  );
}

const NAV_LINK = 'group relative px-3.5 py-2 text-sm transition-colors';

export function Header() {
  const { t } = useTranslation();
  const location = useLocation();
  const lenis = useLenis();
  const signedIn = useSignedIn();
  const { y } = useScroll();
  const [open, setOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(location.pathname);

  // Close the menu when the route changes, without an effect that sets state.
  if (open && openedAt !== location.pathname) {
    setOpen(false);
  }

  useEffect(() => {
    if (open) lenis?.stop();
    else lenis?.start();
  }, [open, lenis]);

  // The menu and its toggle disappear at 768px; close it there, or scrolling would stay locked
  // with no way to reopen the toggle. Escape closes it too.
  useEffect(() => {
    if (!open) return;
    const wide = window.matchMedia('(min-width: 768px)');
    const close = () => {
      if (wide.matches) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    wide.addEventListener('change', close);
    window.addEventListener('keydown', onKey);
    return () => {
      wide.removeEventListener('change', close);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const links = [
    { to: '/modules', label: t('nav.modules') },
    { to: '/security', label: t('nav.security') },
  ];

  return (
    <>
      <header
        className={`fixed inset-x-0 top-0 z-[70] border-b transition-[background-color,border-color] duration-300 ${
          y > 8 || open
            ? 'border-line bg-canvas/85 backdrop-blur-xl'
            : 'border-transparent bg-transparent'
        }`}
      >
        <div className="shell flex h-[var(--header-height)] items-center justify-between gap-4">
          <Link to="/" className="shrink-0">
            <Logo className="h-6 w-auto sm:h-8 md:h-9" />
          </Link>

          <nav className="hidden items-center md:flex">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `${NAV_LINK} ${isActive ? 'text-ink' : 'text-muted hover:text-ink'}`
                }
              >
                <RollText tone="inherit">{link.label}</RollText>
              </NavLink>
            ))}
            <a href={SITE.repo} rel="noopener" className={`${NAV_LINK} text-muted hover:text-ink`}>
              <RollText tone="inherit">GitHub</RollText>
            </a>
          </nav>

          <div className="flex items-center gap-2 sm:gap-4">
            <LanguageSwitcher className="max-[359px]:hidden" />
            <Link
              to={signedIn ? '/app' : '/login'}
              className="btn btn-primary hidden !py-2.5 !text-sm sm:inline-flex"
            >
              {signedIn ? t('nav.openApp') : t('nav.signIn')}
            </Link>
            <button
              type="button"
              className="flex size-10 flex-col items-center justify-center gap-1.5 rounded-full border border-line md:hidden"
              aria-expanded={open}
              aria-controls="mobile-menu"
              aria-label={t('nav.menu')}
              onClick={() => {
                setOpenedAt(location.pathname);
                setOpen(!open);
              }}
            >
              <span
                className={`h-px w-4 bg-ink transition-transform duration-300 ${open ? 'translate-y-[3.5px] rotate-45' : ''}`}
              />
              <span
                className={`h-px w-4 bg-ink transition-transform duration-300 ${open ? '-translate-y-[3.5px] -rotate-45' : ''}`}
              />
            </button>
          </div>
        </div>
      </header>
      <MobileMenu open={open} onClose={() => setOpen(false)} />
    </>
  );
}
