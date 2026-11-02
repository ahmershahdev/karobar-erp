import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import ar from './locales/ar.json';
import en from './locales/en.json';
import ur from './locales/ur.json';

export const LANGUAGES = [
  { code: 'en', label: 'English', dir: 'ltr' },
  { code: 'ur', label: 'اردو', dir: 'rtl' },
  { code: 'ar', label: 'العربية', dir: 'rtl' },
] as const;

export type LanguageCode = (typeof LANGUAGES)[number]['code'];

// Nastaliq and Kufi are large, so they load only when someone picks Urdu or Arabic.
const fontLoaders: Partial<Record<LanguageCode, () => Promise<unknown>>> = {
  ur: () => import('@fontsource/noto-nastaliq-urdu/400.css'),
  ar: () => import('@fontsource-variable/noto-kufi-arabic'),
};

function applyDocumentLanguage(code: string): void {
  const language = LANGUAGES.find((entry) => entry.code === code) ?? LANGUAGES[0];
  document.documentElement.lang = language.code;
  document.documentElement.dir = language.dir;
  void fontLoaders[language.code]?.();
}

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, ur: { translation: ur }, ar: { translation: ar } },
    fallbackLng: 'en',
    supportedLngs: LANGUAGES.map((entry) => entry.code),
    interpolation: { escapeValue: false },
    detection: { order: ['localStorage', 'navigator'], caches: ['localStorage'] },
    returnObjects: true,
  });

applyDocumentLanguage(i18n.resolvedLanguage ?? 'en');
i18n.on('languageChanged', applyDocumentLanguage);

export default i18n;
