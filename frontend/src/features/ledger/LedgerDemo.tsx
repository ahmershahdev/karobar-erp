import { animate } from 'animejs';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { prefersReducedMotion } from '../../lib/motion';

// 12 cartons at 1,250 with 18% sales tax, costing 800 each. Debits and credits both total 27,300.
const ENTRY: { debit: number; credit: number }[] = [
  { debit: 17700, credit: 0 },
  { debit: 0, credit: 15000 },
  { debit: 0, credit: 2700 },
  { debit: 9600, credit: 0 },
  { debit: 0, credit: 9600 },
];
const TOTAL = 27300;

export function LedgerDemo() {
  const { t, i18n } = useTranslation();
  const rows = t('ledger.rows', { returnObjects: true }) as string[];
  const tableRef = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(() => (prefersReducedMotion() ? 1 : 0));
  const format = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumFractionDigits: 0 });

  useEffect(() => {
    const table = tableRef.current;
    if (!table || prefersReducedMotion()) return;
    const state = { value: 0 };
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        observer.disconnect();
        animate(state, {
          value: 1,
          duration: 2400,
          ease: 'outExpo',
          onUpdate: () => setProgress(state.value),
        });
      },
      { threshold: 0.4 },
    );
    observer.observe(table);
    return () => observer.disconnect();
  }, []);

  const cell = (amount: number) => (amount ? format.format(Math.round(amount * progress)) : '');
  const balanced = progress > 0.999;

  return (
    <div ref={tableRef} className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-5 py-4 md:px-7">
        <span className="label">JV-000142</span>
        <span className={`label transition-colors duration-700 ${balanced ? '!text-mint' : ''}`}>
          {balanced ? t('ledger.balanced') : t('ledger.posting')}
        </span>
      </div>
      <table className="w-full font-mono text-[0.8rem] tabular-nums md:text-sm">
        <thead>
          <tr className="label">
            <th className="px-5 py-3 text-start font-normal md:px-7">{t('ledger.account')}</th>
            <th className="px-3 py-3 text-end font-normal">{t('ledger.debit')}</th>
            <th className="px-5 py-3 text-end font-normal md:px-7">{t('ledger.credit')}</th>
          </tr>
        </thead>
        <tbody>
          {ENTRY.map((line, index) => (
            <tr key={rows[index] ?? index} className="border-t border-line">
              <td
                className={`px-5 py-3.5 font-sans text-sm md:px-7 ${line.credit ? 'ps-9 text-muted md:ps-12' : ''}`}
              >
                {rows[index]}
              </td>
              <td className="px-3 py-3.5 text-end">{cell(line.debit)}</td>
              <td className="px-5 py-3.5 text-end md:px-7">{cell(line.credit)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-ember/40 text-base text-ember md:text-lg">
            <td className="px-5 py-4 font-sans md:px-7">{t('ledger.total')}</td>
            <td className="px-3 py-4 text-end">{cell(TOTAL)}</td>
            <td className="px-5 py-4 text-end md:px-7">{cell(TOTAL)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
