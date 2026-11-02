import { useTranslation } from 'react-i18next';

import { LANGUAGES } from '../i18n';

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t('nav.language')}
      className="flex rounded-full border border-line p-1"
    >
      {LANGUAGES.map((language) => {
        const active = i18n.resolvedLanguage === language.code;
        return (
          <button
            key={language.code}
            type="button"
            lang={language.code}
            aria-pressed={active}
            onClick={() => void i18n.changeLanguage(language.code)}
            className={`rounded-full px-3 py-1 text-xs transition-colors duration-300 ${
              active ? 'bg-cream text-black' : 'text-muted hover:text-ink'
            }`}
          >
            {language.label}
          </button>
        );
      })}
    </div>
  );
}
