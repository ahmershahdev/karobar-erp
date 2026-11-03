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
    <Reveal stagger className={`space-y-6 ${className}`}>
      <div className="flex items-center gap-4">
        <span className="label !text-ember">[{index}]</span>
        <span className="h-px w-10 bg-line-strong" />
        <span className="label">{eyebrow}</span>
      </div>
      <h2 className="display-lg max-w-[14ch]">{title}</h2>
      {lead && <p className="max-w-xl text-lg text-muted">{lead}</p>}
    </Reveal>
  );
}
