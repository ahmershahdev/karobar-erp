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
  const tableRef = useRef<HTMLTableElement>(null);
  const [progress, setProgress] = useState(prefersReducedMotion() ? 1 : 0);
  const format = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumFractionDigits: 0 });

  useEffect(() => {
    const table = tableRef.current;
    if (!table || prefersReducedMotion()) return;
    const state = { value: 0 };
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry?.isIntersecting) return;
      observer.disconnect();
      animate(state, {
        value: 1,
        duration: 2200,
        ease: 'outExpo',
        onUpdate: () => setProgress(state.value),
      });
    });
    observer.observe(table);
    return () => observer.disconnect();
  }, []);

  const cell = (amount: number) => (amount ? format.format(Math.round(amount * progress)) : '');

  return (
    <div
      className="gradient-border overflow-hidden p-1"
      style={{ ['--gradient' as string]: 'var(--gradient-ledger)' }}
    >
      <table ref={tableRef} className="w-full text-start text-sm tabular-nums md:text-base">
        <thead className="text-xs tracking-widest text-muted uppercase">
          <tr>
            <th className="px-5 py-4 text-start font-medium">{t('ledger.account')}</th>
            <th className="px-5 py-4 text-end font-medium">{t('ledger.debit')}</th>
            <th className="px-5 py-4 text-end font-medium">{t('ledger.credit')}</th>
          </tr>
        </thead>
        <tbody>
          {ENTRY.map((line, index) => (
            <tr key={rows[index] ?? index} className="border-t border-line">
              <td className={`px-5 py-4 ${line.credit ? 'ps-10 text-muted' : ''}`}>
                {rows[index]}
              </td>
              <td className="px-5 py-4 text-end">{cell(line.debit)}</td>
              <td className="px-5 py-4 text-end">{cell(line.credit)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-gold/40 font-display text-lg">
            <td className="px-5 py-5">{t('ledger.total')}</td>
            <td className="px-5 py-5 text-end text-gold">{cell(TOTAL)}</td>
            <td className="px-5 py-5 text-end text-gold">{cell(TOTAL)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
