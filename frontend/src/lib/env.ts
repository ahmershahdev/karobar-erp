// The only module that reads import.meta.env. Everything else imports from here.

function required(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} is not set; see frontend/.env.example`);
  return value;
}

export const env = {
  siteUrl: required('VITE_SITE_URL', import.meta.env.VITE_SITE_URL as string | undefined),
  // Empty means same origin, which is how production runs: nginx serves the app and proxies /api.
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '',
} as const;

export const isProduction = import.meta.env.PROD;
