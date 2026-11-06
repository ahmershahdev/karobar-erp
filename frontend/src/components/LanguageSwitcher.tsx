import { useTranslation } from 'react-i18next';

import { LANGUAGES } from '../i18n';

export function LanguageSwitcher({ className = '' }: { className?: string }) {
  const { t, i18n } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t('nav.language')}
      className={`flex items-center gap-1 ${className}`}
    >
      {LANGUAGES.map((language, index) => {
        const active = i18n.resolvedLanguage === language.code;
        return (
          <span key={language.code} className="flex items-center gap-1">
            {index > 0 && <span className="text-muted/40">/</span>}
            <button
              type="button"
              lang={language.code}
              aria-pressed={active}
              onClick={() => void i18n.changeLanguage(language.code)}
              className={`px-1.5 py-1.5 text-sm transition-colors duration-300 ${
                active ? 'font-medium text-ink' : 'text-muted hover:text-ink'
              } `}
            >
              {language.code === 'en' ? 'En' : language.label}
            </button>
          </span>
        );
      })}
    </div>
  );
}
