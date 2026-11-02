const DOTS = ['bg-gold', 'bg-teal', 'bg-coral', 'bg-lavender', 'bg-mint', 'bg-sky'];

export function Marquee({ items }: { items: string[] }) {
  const row = (hidden: boolean) => (
    <ul aria-hidden={hidden || undefined} className="flex shrink-0 items-center">
      {items.map((item, index) => (
        <li
          key={item}
          className="flex items-center gap-6 px-6 font-display text-3xl whitespace-nowrap text-ink/90 md:text-5xl"
        >
          <span className={`size-2.5 rounded-full ${DOTS[index % DOTS.length]}`} />
          {item}
        </li>
      ))}
    </ul>
  );
  return (
    <div className="relative overflow-hidden border-y border-line py-8 [mask-image:linear-gradient(90deg,transparent,black_12%,black_88%,transparent)]">
      <div className="marquee-track">
        {row(false)}
        {row(true)}
      </div>
    </div>
  );
}
