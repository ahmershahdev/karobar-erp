import type { ReactNode } from 'react';

import { Logo } from '../../components/Logo';
import { usePrivateSeo } from '../../lib/seo';

export function AuthCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  usePrivateSeo(title);
  return (
    <section className="flex min-h-[100svh] items-center justify-center px-4 py-28">
      <div className="w-full max-w-md space-y-6">
        <div className="gradient-border space-y-6 p-8">
          <div className="flex items-center gap-3">
            <Logo className="size-9" />
            <h1 className="text-3xl">{title}</h1>
          </div>
          {children}
        </div>
        {footer && <div className="text-center text-sm text-muted">{footer}</div>}
      </div>
    </section>
  );
}
