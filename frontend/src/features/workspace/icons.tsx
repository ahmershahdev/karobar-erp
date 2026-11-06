import type { ReactNode } from 'react';

// One simple picture per screen, so people who read slowly can find their way by shape.
const PATHS: Record<string, ReactNode> = {
  overview: <path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z" />,
  members: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.5-4 3-6 6.5-6s6 2 6.5 6M16 5a3.5 3.5 0 0 1 0 6.5M18 14c2 .7 3.2 2.6 3.5 6" />
    </>
  ),
  roles: <path d="M12 3 5 6v5c0 5 3 8 7 10 4-2 7-5 7-10V6zM9 12l2 2 4-4" />,
  audit: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  journal: (
    <path d="M6 3h12a1 1 0 0 1 1 1v17l-3.5-2-3.5 2-3.5-2L5 21V4a1 1 0 0 1 1-1zM9 8h6M9 12h6" />
  ),
  chart: <path d="M4 5h6v6H4zM14 5h6v6h-6zM4 15h6v5H4zM14 15h6v5h-6z" />,
  'trial-balance': <path d="M12 4v16M7 20h10M5 7h14M5 7l-3 7h6zM19 7l-3 7h6z" />,
  ledger: <path d="M5 3h12a2 2 0 0 1 2 2v16H7a2 2 0 0 1-2-2zM5 18a2 2 0 0 1 2-2h12M9 7h6" />,
  periods: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </>
  ),
  products: <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9" />,
  entries: <path d="M7 4v14M7 18l-3.5-3.5M7 18l3.5-3.5M17 20V6M17 6l-3.5 3.5M17 6l3.5 3.5" />,
  'on-hand': <path d="M3 10 12 4l9 6v10H3zM8 20v-6h8v6M8 17h8" />,
  alerts: <path d="M12 4 2.5 20h19zM12 10v5M12 17.5v.5" />,
  setup: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" />
    </>
  ),
};

export function ScreenIcon({ name, className = 'size-5' }: { name: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`shrink-0 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  );
}
