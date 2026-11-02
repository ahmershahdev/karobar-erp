import { useTranslation } from 'react-i18next';

import { Reveal } from '../../components/Reveal';

const GRADIENTS = [
  'var(--gradient-lagoon)',
  'var(--gradient-ledger)',
  'var(--gradient-blossom)',
  'var(--gradient-orchard)',
  'var(--gradient-aurora)',
  'var(--gradient-sunrise)',
  'var(--gradient-dusk)',
  'var(--gradient-earth)',
];

interface Item {
  title: string;
  body: string;
}

export function ModuleGrid({ limit }: { limit?: number }) {
  const { t } = useTranslation();
  const items = (t('modules.items', { returnObjects: true }) as Item[]).slice(0, limit);
  return (
    <Reveal stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item, index) => (
        <article
          key={item.title}
          className="group gradient-border relative overflow-hidden p-6 transition-transform duration-500 ease-[var(--ease-out-expo)] hover:-translate-y-1"
          style={{ ['--gradient' as string]: GRADIENTS[index % GRADIENTS.length] }}
        >
          <div
            aria-hidden="true"
            className="absolute -end-16 -top-16 size-40 rounded-full opacity-30 blur-2xl transition-opacity duration-700 group-hover:opacity-70"
            style={{ background: GRADIENTS[index % GRADIENTS.length] }}
          />
          <p className="font-display text-sm text-muted tabular-nums">
            {String(index + 1).padStart(2, '0')}
          </p>
          <h3 className="mt-10 text-2xl">{item.title}</h3>
          <p className="mt-3 text-sm leading-relaxed text-muted">{item.body}</p>
        </article>
      ))}
    </Reveal>
  );
}
