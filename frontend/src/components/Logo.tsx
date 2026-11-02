// Two ledger columns that meet in the middle: debits on one side, credits on the other.
export function Logo({ className = 'size-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="logo-a" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--color-gold)" />
          <stop offset="1" stopColor="var(--color-coral)" />
        </linearGradient>
        <linearGradient id="logo-b" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="var(--color-indigo)" />
          <stop offset="1" stopColor="var(--color-turquoise)" />
        </linearGradient>
      </defs>
      <rect x="3" y="4" width="11" height="24" rx="3" fill="url(#logo-a)" />
      <rect x="18" y="4" width="11" height="24" rx="3" fill="url(#logo-b)" />
      <rect x="9" y="14.5" width="14" height="3" rx="1.5" fill="var(--color-cream)" />
    </svg>
  );
}
