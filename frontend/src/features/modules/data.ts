// The order matches modules.items in the locale files.
export const MODULES = [
  {
    key: 'inventory',
    status: 'built',
    milestone: 'M3',
    color: 'var(--color-turquoise)',
    gradient: 'var(--gradient-lagoon)',
  },
  {
    key: 'sales',
    status: 'next',
    milestone: 'M4',
    color: 'var(--color-ember)',
    gradient: 'var(--gradient-molten)',
  },
  {
    key: 'pos',
    status: 'planned',
    milestone: 'M5',
    color: 'var(--color-pink)',
    gradient: 'var(--gradient-blossom)',
  },
  {
    key: 'purchasing',
    status: 'next',
    milestone: 'M4',
    color: 'var(--color-mint)',
    gradient: 'var(--gradient-orchard)',
  },
  {
    key: 'accounting',
    status: 'built',
    milestone: 'M2',
    color: 'var(--color-lavender)',
    gradient: 'var(--gradient-aurora)',
  },
  {
    key: 'tax',
    status: 'planned',
    milestone: 'M5',
    color: 'var(--color-yellow)',
    gradient: 'var(--gradient-sunrise)',
  },
  {
    key: 'hr',
    status: 'planned',
    milestone: 'M6',
    color: 'var(--color-coral)',
    gradient: 'var(--gradient-dusk)',
  },
  {
    key: 'payroll',
    status: 'planned',
    milestone: 'M6',
    color: 'var(--color-beige)',
    gradient: 'var(--gradient-earth)',
  },
] as const;

export type ModuleKey = (typeof MODULES)[number]['key'];

export interface ModuleCopy {
  title: string;
  body: string;
  points: string[];
  books: string;
}
