import { animate, stagger } from 'animejs';
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink, useLocation } from 'react-router';

import { prefersReducedMotion } from '../lib/motion';
import { useScroll } from '../lib/scroll';
import { useLenis } from '../lib/smooth-scroll';
import { SITE } from '../seo/site';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo } from './Logo';
import { RollText } from './RollText';

function MobileMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = panel.current;
    if (!open || !element || prefersReducedMotion()) return;
    animate(element, {
      clipPath: ['circle(0% at 92% 4%)', 'circle(150% at 92% 4%)'],
      duration: 900,
      ease: 'inOutExpo',
    });
    animate(element.querySelectorAll('[data-item]'), {
      translateY: ['110%', '0%'],
      rotate: ['3deg', '0deg'],
      duration: 1000,
      delay: stagger(70, { start: 300 }),
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
      className="fixed inset-0 z-[65] flex flex-col overflow-y-auto overscroll-contain bg-black px-[var(--gutter)] pt-28 pb-8 md:hidden"
      data-lenis-prevent
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            'radial-gradient(70% 50% at 100% 0%, rgb(216 178 106 / 0.18), transparent 70%), radial-gradient(60% 40% at 0% 100%, rgb(116 98 201 / 0.14), transparent 70%)',
        }}
      />
      <span className="label mb-6">{t('nav.menu')}</span>
      <nav className="flex-1">
        <ul>
          {links.map((link, index) => (
            <li key={link.to} className="overflow-hidden border-b border-line">
              <Link
                to={link.to}
                onClick={onClose}
                data-item
                className="flex items-baseline justify-between py-5 font-display text-5xl"
              >
                {link.label}
                <span className="label !text-gold">0{index + 1}</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="space-y-6">
        <a href={`mailto:${SITE.email}`} className="block text-lg text-gold">
          {SITE.email}
        </a>
        <div className="flex items-center justify-between">
          <LanguageSwitcher />
          <a href={SITE.repo} rel="noopener" className="label hover:!text-gold">
            GitHub
          </a>
        </div>
      </div>
    </div>
  );
}

interface Indicator {
  left: number;
  width: number;
  visible: boolean;
}

export function Header() {
  const { t } = useTranslation();
  const location = useLocation();
  const lenis = useLenis();
  const { y, progress, direction } = useScroll();
  const [open, setOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(location.pathname);
  const [indicator, setIndicator] = useState<Indicator>({ left: 0, width: 0, visible: false });
  const navRef = useRef<HTMLElement>(null);

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

  const moveIndicator = (event: ReactPointerEvent<HTMLElement>) => {
    const nav = navRef.current?.getBoundingClientRect();
    const rect = event.currentTarget.getBoundingClientRect();
    if (!nav) return;
    setIndicator({ left: rect.left - nav.left, width: rect.width, visible: true });
  };

  // Out of the way while reading down the page; back as soon as the reader scrolls up.
  const hidden = !open && direction === 'down' && y > 160;

  const links = [
    { to: '/modules', label: t('nav.modules') },
    { to: '/security', label: t('nav.security') },
  ];

  return (
    <>
      <header
        className={`fixed inset-x-0 top-3 z-[70] px-[var(--gutter)] transition-transform duration-700 ease-[var(--ease-out-expo)] md:top-5 ${
          hidden ? '-translate-y-[150%] has-[:focus-visible]:translate-y-0' : 'translate-y-0'
        }`}
      >
        <div
          className={`relative mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 rounded-full border ps-4 pe-2 transition-[background-color,border-color,box-shadow] duration-500 ${
            y > 24 || open
              ? 'border-line bg-black/60 shadow-[0_20px_60px_-20px_rgb(0_0_0/0.8)] backdrop-blur-xl'
              : 'border-transparent bg-transparent'
          }`}
        >
          <Link to="/" className="group flex items-center gap-2.5" aria-label="Karobar ERP">
            <Logo className="size-7 transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:rotate-[180deg]" />
            <span className="font-display text-2xl leading-none">Karobar</span>
            <span className="label hidden !text-[0.6rem] lg:inline">v0.2</span>
          </Link>

          <nav
            ref={navRef}
            className="relative hidden items-center md:flex"
            onPointerLeave={() => setIndicator((current) => ({ ...current, visible: false }))}
          >
            <span
              aria-hidden="true"
              className="absolute top-1/2 h-9 -translate-y-1/2 rounded-full border border-line bg-white/[0.04] transition-[left,width,opacity] duration-500 ease-[var(--ease-out-expo)]"
              style={{
                left: indicator.left,
                width: indicator.width,
                opacity: indicator.visible ? 1 : 0,
              }}
            />
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                onPointerEnter={moveIndicator}
                className={({ isActive }) =>
                  `group relative px-4 py-2 font-mono text-[0.7rem] tracking-[0.14em] uppercase ${
                    isActive ? 'text-gold' : 'text-ink/75'
                  }`
                }
              >
                <RollText>{link.label}</RollText>
              </NavLink>
            ))}
            <a
              href={SITE.repo}
              rel="noopener"
              onPointerEnter={moveIndicator}
              className="group relative px-4 py-2 font-mono text-[0.7rem] tracking-[0.14em] text-ink/75 uppercase"
            >
              <RollText>GitHub</RollText>
            </a>
          </nav>

          <div className="flex items-center gap-3">
            <LanguageSwitcher className="hidden lg:flex" />
            <Link
              to="/app"
              data-cursor={t('cursor.open')}
              className="group hidden items-center gap-2 overflow-hidden rounded-full py-2.5 ps-5 pe-2.5 text-sm font-medium text-black sm:inline-flex"
              style={{ background: 'var(--gradient-molten)' }}
            >
              <RollText>{t('nav.signIn')}</RollText>
              <span className="relative flex size-6 items-center justify-center overflow-hidden rounded-full bg-black/85 text-cream">
                <span className="transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:translate-x-6 rtl:rotate-180 rtl:group-hover:-translate-x-6">
                  &rarr;
                </span>
                <span className="absolute -translate-x-6 transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:translate-x-0 rtl:translate-x-6 rtl:rotate-180">
                  &rarr;
                </span>
              </span>
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
                className={`h-px w-4 bg-cream transition-transform duration-500 ${open ? 'translate-y-[3.5px] rotate-45' : ''}`}
              />
              <span
                className={`h-px w-4 bg-cream transition-transform duration-500 ${open ? '-translate-y-[3.5px] -rotate-45' : ''}`}
              />
            </button>
          </div>

          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-8 -bottom-px h-px origin-left rtl:origin-right"
            style={{
              background: 'var(--gradient-molten)',
              transform: `scaleX(${progress})`,
              opacity: y > 24 ? 1 : 0,
            }}
          />
        </div>
      </header>
      <MobileMenu open={open} onClose={() => setOpen(false)} />
    </>
  );
}
