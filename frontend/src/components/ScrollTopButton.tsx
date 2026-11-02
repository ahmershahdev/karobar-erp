import { useTranslation } from 'react-i18next';

import { useScroll } from '../lib/scroll';
import { scrollToTop, useLenis } from '../lib/smooth-scroll';

// Floats in the corner once the reader is a screen down, so getting back to the top never means
// scrolling to the footer first. The ring fills with reading progress.
export function ScrollTopButton() {
  const { t } = useTranslation();
  const lenis = useLenis();
  const { y, progress } = useScroll();
  const shown = y > window.innerHeight * 0.8;
  const circumference = 2 * Math.PI * 22;

  return (
    <button
      type="button"
      onClick={() => {
        if (lenis) lenis.scrollTo(0, { duration: 1.4, lock: true, force: true });
        else scrollToTop(null);
      }}
      aria-label={t('footer.top')}
      tabIndex={shown ? 0 : -1}
      data-cursor-stick
      className={`group fixed end-5 bottom-5 z-[60] flex size-14 items-center justify-center rounded-full bg-black/70 backdrop-blur-md transition-[opacity,transform] duration-500 ease-[var(--ease-out-expo)] md:end-8 md:bottom-8 ${
        shown ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-6 opacity-0'
      }`}
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
      <svg
        viewBox="0 0 16 16"
        className="relative size-4 transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:-translate-y-0.5"
        aria-hidden="true"
      >
        <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    </button>
  );
}
