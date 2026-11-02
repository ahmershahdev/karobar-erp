// Shared by the app and vite.config.ts, so it must stay free of browser and React imports.

export interface PublicRoute {
  path: string;
  name: string;
  title: string;
  description: string;
  changefreq: 'weekly' | 'monthly';
  priority: number;
  summary: string;
}

export const SITE = {
  name: 'Karobar ERP',
  author: 'Syed Ahmer Shah',
  authorUrl: 'https://ahmershah.dev',
  email: 'support@ahmershah.dev',
  repo: 'https://github.com/ahmershahdev/karobar-erp',
  locale: 'en_US',
  themeColor: '#0b0b10',
  ogImage: '/og-image.png',
} as const;

export const PUBLIC_ROUTES = [
  {
    path: '/',
    name: 'Home',
    title: 'Karobar ERP: Stock, Sales, Books and Payroll',
    description:
      'Open-source ERP for shops and distributors: inventory, POS, double-entry accounting, tax reports and payroll in English, Urdu and Arabic.',
    changefreq: 'weekly',
    priority: 1,
    summary:
      'Karobar ERP is a multi-tenant ERP for small shops, wholesalers and distributors. Every sale, purchase and payment posts its own balanced journal entry, stock is updated under row locks, and each business sees only its own data.',
  },
  {
    path: '/modules',
    name: 'Modules',
    title: 'Modules: Inventory, POS, Accounting, HR | Karobar',
    description:
      'Inventory with FIFO valuation, sales and POS, purchasing, double-entry accounting, GST and VAT reports, HR and payroll in one system.',
    changefreq: 'monthly',
    priority: 0.8,
    summary:
      'Inventory (variants, units, warehouses, batches, FIFO and moving average), sales and point of sale, purchasing, accounting (chart of accounts, journal entries, trial balance, profit and loss, balance sheet), sales tax reports, HR and monthly payroll.',
  },
  {
    path: '/security',
    name: 'Security',
    title: 'Security and Data Isolation | Karobar ERP',
    description:
      'How Karobar ERP keeps each business apart, books balanced and stock correct: row locks, audit logs, CSP, rate limits and Argon2 hashing.',
    changefreq: 'monthly',
    priority: 0.7,
    summary:
      'Tenant isolation is enforced by a fail-closed query manager and tested on every endpoint. Sessions use HttpOnly cookies with CSRF protection, passwords are hashed with Argon2id, every endpoint is rate limited, and the frontend runs under a nonce-based Content Security Policy.',
  },
] as const satisfies readonly PublicRoute[];

// The home page FAQ as structured data. Keep it word for word with home.faq in en.json: search
// engines only trust FAQ markup that matches what the page shows. A test checks they agree.
export const HOME_FAQ: readonly { q: string; a: string }[] = [
  {
    q: 'Is Karobar ERP free?',
    a: 'Yes. It is open source under the MIT license. You can run it on your own server at no cost.',
  },
  {
    q: 'Can several businesses share one installation?',
    a: "Yes. Each business has its own books, stock and staff, and the server refuses any request for another business's data.",
  },
  {
    q: 'Does it work in Urdu and Arabic?',
    a: 'Every screen does, with right-to-left layouts. Printed invoices in all three languages arrive with sales.',
  },
  {
    q: "Which countries' taxes are supported?",
    a: 'Tax arrives in milestone M5, starting with Pakistan and then the Gulf. Rates are stored as dated data, never hard-coded.',
  },
  {
    q: 'What happens if I make a mistake in a posted entry?',
    a: 'Posted entries never change. You post a reversal, which keeps a complete and honest audit trail.',
  },
];

export const NOINDEX_PREFIXES = ['/app'] as const;

export function absoluteUrl(siteUrl: string, path: string): string {
  return new URL(path, siteUrl.endsWith('/') ? siteUrl : `${siteUrl}/`).toString();
}
