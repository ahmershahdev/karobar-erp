import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { Logo } from '../../components/Logo';
import { prefersReducedMotion } from '../../lib/motion';
import { LedgerDemo } from '../ledger/LedgerDemo';

// A quiet picture of the app itself: its sidebar, and the journal entry from the ledger demo
// posting live. It settles from slightly small to full size as it scrolls into place.
export function ProductWindow() {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element || prefersReducedMotion()) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const top = element.parentElement?.getBoundingClientRect().top ?? 0;
      const progress = Math.min(1, Math.max(0, 1 - (top - 120) / (window.innerHeight * 0.7)));
      element.style.transform = `scale(${0.94 + 0.06 * progress})`;
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  const nav = [
    { label: t('workspace.overview') },
    { label: t('acc.journal'), active: true },
    { label: t('acc.chart') },
    { label: t('acc.trialBalance') },
    { label: t('inv.products') },
    { label: t('inv.onHandTitle') },
  ];

  return (
    <div>
      <div
        ref={ref}
        className="grid origin-top overflow-hidden rounded-[var(--radius-card)] border border-line bg-canvas shadow-[var(--shadow-float)] will-change-transform md:grid-cols-[14rem_1fr]"
      >
        <aside aria-hidden="true" className="hidden border-e border-line p-5 md:block">
          <Logo variant="mark" className="h-7 w-auto" />
          <ul className="mt-7 space-y-1 text-sm">
            {nav.map((item) => (
              <li
                key={item.label}
                className={`rounded-lg px-3 py-2 ${item.active ? 'bg-raised text-ink' : 'text-muted'}`}
              >
                {item.label}
              </li>
            ))}
          </ul>
        </aside>
        <div className="min-w-0 bg-surface p-4 md:p-8">
          <p className="mb-5 text-xl font-medium tracking-[-0.02em]">{t('acc.journal')}</p>
          <LedgerDemo />
        </div>
      </div>
    </div>
  );
}
