import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink } from 'react-router';

import { LanguageSwitcher } from './LanguageSwitcher';
import { Logo } from './Logo';

export function Header() {
  const { t } = useTranslation();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const links = [
    { to: '/modules', label: t('nav.modules') },
    { to: '/security', label: t('nav.security') },
  ];

  return (
    <header
      className={`fixed inset-x-0 top-0 z-40 transition-[background-color,backdrop-filter,border-color] duration-500 ${
        scrolled
          ? 'border-b border-line bg-black/60 backdrop-blur-xl'
          : 'border-b border-transparent'
      }`}
    >
      <div className="mx-auto flex h-[var(--header-height)] max-w-7xl items-center justify-between gap-4 px-4 md:px-8">
        <Link to="/" className="flex items-center gap-3 font-display text-lg tracking-tight">
          <Logo />
          <span>Karobar</span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm md:flex">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `relative py-1 transition-colors after:absolute after:inset-x-0 after:-bottom-0.5 after:h-px after:origin-left after:scale-x-0 after:bg-gold after:transition-transform after:duration-500 hover:after:scale-x-100 ${
                  isActive ? 'text-ink after:scale-x-100' : 'text-muted hover:text-ink'
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <div className="hidden sm:block">
            <LanguageSwitcher />
          </div>
          <Link
            to="/app"
            className="rounded-full bg-cream px-4 py-2 text-sm font-medium text-black transition-transform duration-300 hover:-translate-y-0.5"
          >
            {t('nav.signIn')}
          </Link>
        </div>
      </div>
    </header>
  );
}
