import type { ReactNode } from 'react';

// One simple picture per screen, so people who read slowly can find their way by shape.
const PATHS: Record<string, ReactNode> = {
  overview: <path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z" />,
  account: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c.6-4.4 3.8-7 8-7s7.4 2.6 8 7" />
    </>
  ),
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
  counter: <path d="M3 10h18v9H3zM6 10V5h12v5M8 14h3M8 16.5h3M15 14v2.5" />,
  dashboard: <path d="M4 20V10M10 20V4M16 20v-7M21 20H3" />,
  suppliers: (
    <>
      <path d="M2.5 7h11v10h-11zM13.5 10h4l4 4v3h-8z" />
      <circle cx="7" cy="18" r="2" />
      <circle cx="17" cy="18" r="2" />
    </>
  ),
  orders: <path d="M9 4h6v3H9zM7 5.5H5v15.5h14V5.5h-2M8.5 12h7M8.5 16h7" />,
  receipts: <path d="m12 8 8 3.5v7L12 22l-8-3.5v-7zM12 2v7M9 6l3 3 3-3" />,
  bills: <path d="M6 3h9l4 4v14H6zM15 3v4h4M9 12h7M9 16h7" />,
  gift: <path d="M4 11h16v10H4zM3 7h18v4H3zM12 7v14M12 7c-1.5-3-5-3-5 0M12 7c1.5-3 5-3 5 0" />,
  shield: <path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6zM9 12l2 2 4-4" />,
  payments: (
    <>
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6 9.5v5M18 9.5v5" />
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
