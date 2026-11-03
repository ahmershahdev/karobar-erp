// Two stacked copies of the label: on hover of the nearest `group`, the first rolls up and out
// while the second rolls in from below. Screen readers hear the label once.
// `inherit` keeps the label's own colour, for labels on filled buttons where the accent colour
// would vanish into the background.
export function RollText({
  children,
  tone = 'accent',
}: {
  children: string;
  tone?: 'accent' | 'inherit';
}) {
  return (
    <span className="relative inline-flex overflow-hidden align-top">
      <span className="block transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:-translate-y-full group-focus-visible:-translate-y-full">
        {children}
      </span>
      <span
        aria-hidden="true"
        className={`absolute inset-x-0 top-full block ${tone === 'accent' ? 'text-ember' : ''} transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:-translate-y-full group-focus-visible:-translate-y-full`}
      >
        {children}
      </span>
    </span>
  );
}
