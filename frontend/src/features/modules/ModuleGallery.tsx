import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { Reveal } from '../../components/Reveal';
import { ModuleGlyph } from './catalog';
import { MODULES, type ModuleCopy } from './data';

export function StatusChip({ status, milestone }: { status: string; milestone: string }) {
  const { t } = useTranslation();
  const built = status === 'built';
  return (
    <span className="label inline-flex w-fit items-center gap-2">
      <span
        className={`size-1.5 rounded-full ${built ? 'bg-green' : status === 'next' ? 'bg-ember' : 'bg-line-strong'}`}
      />
      {built ? t('modules.status.built', { milestone }) : t('modules.status.coming', { milestone })}
    </span>
  );
}

// A sheet of ruled cells: each module is one link, and the glyph redraws while it is hovered.
export function ModuleGallery() {
  const { t } = useTranslation();
  const items = t('modules.items', { returnObjects: true }) as ModuleCopy[];
  return (
    <Reveal
      stagger
      className="grid gap-px overflow-hidden rounded-[var(--radius-card)] border border-line bg-line sm:grid-cols-2 lg:grid-cols-4"
    >
      {MODULES.map((meta, index) => {
        const copy = items[index];
        if (!copy) return null;
        return (
          <Link
            key={meta.key}
            to={`/modules#${meta.key}`}
            className="group flex min-h-[19rem] flex-col bg-canvas p-6 transition-colors duration-300 hover:bg-surface md:p-7"
          >
            <StatusChip status={meta.status} milestone={meta.milestone} />
            <ModuleGlyph module={meta.key} className="mt-8 size-14 text-ink" />
            <h3 className="mt-auto pt-8 text-2xl">{copy.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{copy.body}</p>
          </Link>
        );
      })}
    </Reveal>
  );
}
