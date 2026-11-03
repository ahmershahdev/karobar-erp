// Two stacked copies of the label: on hover of the nearest `group`, the first rolls up and out
// while the second rolls in from below. Screen readers hear the label once.
export function RollText({ children }: { children: string }) {
  return (
    <span className="relative inline-flex overflow-hidden align-top">
      <span className="block transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:-translate-y-full group-focus-visible:-translate-y-full">
        {children}
      </span>
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-full block text-ember transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:-translate-y-full group-focus-visible:-translate-y-full"
      >
        {children}
      </span>
    </span>
  );
}
