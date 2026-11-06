// The order matches modules.items in the locale files.
export const MODULES = [
  {
    key: 'inventory',
    status: 'built',
    milestone: 'M3',
  },
  {
    key: 'sales',
    status: 'next',
    milestone: 'M4',
  },
  {
    key: 'pos',
    status: 'planned',
    milestone: 'M5',
  },
  {
    key: 'purchasing',
    status: 'next',
    milestone: 'M4',
  },
  {
    key: 'accounting',
    status: 'built',
    milestone: 'M2',
  },
  {
    key: 'tax',
    status: 'planned',
    milestone: 'M5',
  },
  {
    key: 'hr',
    status: 'planned',
    milestone: 'M6',
  },
  {
    key: 'payroll',
    status: 'planned',
    milestone: 'M6',
  },
] as const;

export type ModuleKey = (typeof MODULES)[number]['key'];

export interface ModuleCopy {
  title: string;
  body: string;
  points: string[];
  books: string;
}
