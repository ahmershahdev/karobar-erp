import type { ReactNode } from 'react';

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

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  usePrivateSeo(title);
  return (
    <header className="space-y-1">
      <h1 className="text-4xl">{title}</h1>
      {subtitle && <p className="text-muted">{subtitle}</p>}
    </header>
  );
}

// One mutation that runs whichever API call it is given, then refreshes the listed queries.
