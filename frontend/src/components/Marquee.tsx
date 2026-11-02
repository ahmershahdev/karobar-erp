export function Marquee({ items }: { items: string[] }) {
  const row = (hidden: boolean) => (
    <ul aria-hidden={hidden || undefined} className="flex shrink-0 items-center">
      {items.map((item, index) => (
        <li
          key={item}
          className={`flex items-center gap-8 px-8 font-display text-5xl whitespace-nowrap md:text-8xl ${
            index % 2 ? 'outline-text' : 'text-ink'
          }`}
        >
          {item}
          <span className="text-2xl text-gold md:text-4xl">&#10022;</span>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="relative overflow-hidden border-y border-line py-8 md:py-12">
      <div className="marquee-track">
        {row(false)}
        {row(true)}
      </div>
    </div>
  );
}
