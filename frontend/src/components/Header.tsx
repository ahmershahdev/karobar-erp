import { animate, stagger } from 'animejs';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink, useLocation } from 'react-router';

import { prefersReducedMotion } from '../lib/motion';
import { useLenis } from '../lib/smooth-scroll';
import { SITE } from '../seo/site';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo } from './Logo';

function MobileMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = panel.current;
    if (!open || !element || prefersReducedMotion()) return;
    animate(element, {
      clipPath: ['inset(0 0 100% 0)', 'inset(0 0 0% 0)'],
      duration: 700,
      ease: 'inOutExpo',
    });
    animate(element.querySelectorAll('[data-item]'), {
      translateY: ['110%', '0%'],
      duration: 900,
      delay: stagger(60, { start: 250 }),
      ease: 'outExpo',
    });
  }, [open]);

  if (!open) return null;
  const links = [
    { to: '/', label: t('nav.home') },
    { to: '/modules', label: t('nav.modules') },
    { to: '/security', label: t('nav.security') },
    { to: '/app', label: t('nav.signIn') },
  ];
  return (
    <div
      ref={panel}
      id="mobile-menu"
      className="fixed inset-0 z-[60] flex flex-col bg-black px-[var(--gutter)] pt-[calc(var(--header-height)+2rem)] pb-8 md:hidden"
      data-lenis-prevent
    >
      <nav className="flex-1">
        <ul className="space-y-1">
          {links.map((link, index) => (
            <li key={link.to} className="overflow-hidden border-b border-line">
              <Link
                to={link.to}
                onClick={onClose}
                data-item
                className="flex items-baseline justify-between py-4 font-display text-5xl"
              >
                {link.label}
                <span className="label">0{index + 1}</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex items-center justify-between">
        <LanguageSwitcher />
        <a href={SITE.repo} rel="noopener" className="label hover:text-gold">
          GitHub
        </a>
      </div>
    </div>
  );
}

export function Header() {
  const { t } = useTranslation();
  const location = useLocation();
  const lenis = useLenis();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(location.pathname);

  // Close the menu when the route changes, without an effect that sets state.
  if (open && openedAt !== location.pathname) {
    setOpen(false);
  }

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

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
        className={`fixed inset-x-0 top-0 z-[70] transition-[background-color,backdrop-filter,border-color] duration-500 ${
          scrolled && !open
            ? 'border-b border-line bg-black/55 backdrop-blur-xl'
            : 'border-b border-transparent'
        }`}
      >
        <div className="shell flex h-[var(--header-height)] items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2.5" aria-label="Karobar ERP">
            <Logo className="size-7" />
            <span className="font-display text-2xl leading-none">Karobar</span>
          </Link>
          <nav className="hidden items-center gap-8 md:flex">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `label transition-colors hover:!text-ink ${isActive ? '!text-gold' : ''}`
                }
              >
                {link.label}
              </NavLink>
            ))}
            <a href={SITE.repo} rel="noopener" className="label transition-colors hover:!text-ink">
              GitHub
            </a>
          </nav>
          <div className="flex items-center gap-4">
            <LanguageSwitcher className="hidden lg:flex" />
            <Link
              to="/app"
              className="hidden rounded-full border border-line-strong px-4 py-2 text-sm transition-colors hover:border-gold hover:text-gold sm:inline-block"
            >
              {t('nav.signIn')}
            </Link>
            <button
              type="button"
              className="flex size-10 flex-col items-center justify-center gap-1.5 md:hidden"
              aria-expanded={open}
              aria-controls="mobile-menu"
              aria-label={t('nav.menu')}
              onClick={() => {
                setOpenedAt(location.pathname);
                setOpen(!open);
              }}
            >
              <span
                className={`h-px w-6 bg-cream transition-transform duration-500 ${open ? 'translate-y-[3.5px] rotate-45' : ''}`}
              />
              <span
                className={`h-px w-6 bg-cream transition-transform duration-500 ${open ? '-translate-y-[3.5px] -rotate-45' : ''}`}
              />
            </button>
          </div>
        </div>
      </header>
      <MobileMenu open={open} onClose={() => setOpen(false)} />
    </>
  );
}
