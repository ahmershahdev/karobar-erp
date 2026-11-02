import type { ReactNode } from 'react';

import { Reveal } from './Reveal';

interface Props {
  eyebrow: string;
  title: ReactNode;
  lead?: string;
  gradient?: string;
}

export function SectionHeading({
  eyebrow,
  title,
  lead,
  gradient = 'var(--gradient-ledger)',
}: Props) {
  return (
    <Reveal stagger className="max-w-3xl space-y-5">
      <p className="text-xs font-medium tracking-[0.25em] text-gold uppercase">{eyebrow}</p>
      <h2 className="text-4xl leading-[1.05] md:text-6xl">
        <span className="text-gradient" style={{ ['--gradient' as string]: gradient }}>
          {title}
        </span>
      </h2>
      {lead && <p className="text-lg text-muted">{lead}</p>}
    </Reveal>
  );
}
