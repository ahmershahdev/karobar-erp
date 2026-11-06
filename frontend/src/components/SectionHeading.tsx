import type { ReactNode } from 'react';

import { Reveal } from './Reveal';

interface Props {
  index: string;
  eyebrow: string;
  title: ReactNode;
  lead?: string;
  className?: string;
}

export function SectionHeading({ index, eyebrow, title, lead, className = '' }: Props) {
  return (
    <Reveal stagger className={`space-y-5 ${className}`}>
      <p className="label flex items-center gap-3">
        <span className="text-ember tabular-nums">{index}</span>
        {eyebrow}
      </p>
      <h2 className="display-lg max-w-[16ch]">{title}</h2>
      {lead && <p className="max-w-xl text-lg text-muted">{lead}</p>}
    </Reveal>
  );
}
