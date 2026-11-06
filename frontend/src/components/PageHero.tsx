import { Breadcrumbs } from './Breadcrumbs';
import { Reveal } from './Reveal';
import { SplitHeadline } from './SplitHeadline';

interface Props {
  trail: { label: string; to: string }[];
  eyebrow: string;
  title: string;
  accent?: string;
  lead: string;
}

export function PageHero({ trail, eyebrow, title, accent, lead }: Props) {
  return (
    <section className="shell pt-[calc(var(--header-height)+3rem)] pb-16 md:pt-[calc(var(--header-height)+5rem)] md:pb-24">
      <Breadcrumbs trail={trail} />
      <Reveal className="mt-14">
        <p className="label">{eyebrow}</p>
      </Reveal>
      <SplitHeadline
        text={title}
        {...(accent ? { accent } : {})}
        className="display-xl mt-5 max-w-[14ch]"
        delay={100}
      />
      <Reveal delay={350}>
        <p className="mt-8 max-w-xl text-lg text-muted md:text-xl">{lead}</p>
      </Reveal>
    </section>
  );
}
