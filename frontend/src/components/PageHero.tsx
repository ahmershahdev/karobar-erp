import { Breadcrumbs } from './Breadcrumbs';
import { Reveal } from './Reveal';
import { SplitHeadline } from './SplitHeadline';

interface Props {
  trail: { label: string; to: string }[];
  index: string;
  eyebrow: string;
  title: string;
  accent?: string;
  lead: string;
}

export function PageHero({ trail, index, eyebrow, title, accent, lead }: Props) {
  return (
    <section
      data-morph={index === '01' ? '1' : '2'}
      className="shell pt-[calc(var(--header-height)+3rem)] pb-16 md:pt-[calc(var(--header-height)+5rem)] md:pb-24"
    >
      <Breadcrumbs trail={trail} />
      <Reveal className="mt-14 flex items-center gap-4">
        <span className="label !text-ember">[{index}]</span>
        <span className="h-px w-10 bg-line-strong" />
        <span className="label">{eyebrow}</span>
      </Reveal>
      <SplitHeadline
        text={title}
        {...(accent ? { accent } : {})}
        className="display-xl mt-6 max-w-[12ch]"
        delay={150}
      />
      <Reveal delay={500}>
        <p className="mt-10 max-w-xl border-t border-line pt-8 text-lg text-muted">{lead}</p>
      </Reveal>
    </section>
  );
}
