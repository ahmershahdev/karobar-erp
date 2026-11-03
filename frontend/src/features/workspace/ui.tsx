import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { usePrivateSeo } from '../../lib/seo';

export function Panel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[var(--radius-card)] border border-line bg-surface/50 p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function PageTitle({
  title,
  subtitle,
  guide,
}: {
  title: string;
  subtitle?: string;
  guide?: string;
}) {
  usePrivateSeo(title);
  return (
    <header className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-4xl">{title}</h1>
        {subtitle && <p className="text-muted">{subtitle}</p>}
      </div>
      {guide && <Guide name={guide} />}
    </header>
  );
}

// Numbered, plain-language steps for the page, written for someone who has never used
// accounting software. Open by default; a click folds it away.
function Guide({ name }: { name: string }) {
  const { t } = useTranslation();
  const steps = t(`guides.${name}`, { returnObjects: true, defaultValue: [] }) as string[];
  if (!Array.isArray(steps) || steps.length === 0) return null;
  return (
    <details open className="group/guide rounded-2xl border border-azure/30 bg-azure/[0.06]">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-3.5 text-sm font-medium [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden="true"
          className="grid size-6 shrink-0 place-items-center rounded-full bg-azure/20 text-xs text-sky"
        >
          ?
        </span>
        {t('guides.title')}
        <span
          aria-hidden="true"
          className="ms-auto text-muted transition-transform duration-300 group-open/guide:rotate-180"
        >
          &#9662;
        </span>
      </summary>
      <ol className="space-y-3 px-5 pb-5">
        {steps.map((step, index) => (
          <li key={step} className="flex gap-3 text-sm leading-relaxed text-ink/85">
            <span className="grid size-6 shrink-0 place-items-center rounded-full border border-ember/50 font-mono text-xs text-ember">
              {index + 1}
            </span>
            <span className="pt-0.5">{step}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}

// One mutation that runs whichever API call it is given, then refreshes the listed queries.
