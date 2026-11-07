// Free of browser and React imports: vite.config.ts reads this through src/seo/site.ts.

/** Screens for signing in and getting started. They live at the root, outside /app. */
export const AUTH_PATHS = [
  '/login',
  '/signup',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
  '/confirm-email',
  '/accept-invite',
  '/new-business',
] as const;

export type AuthPath = (typeof AUTH_PATHS)[number];

/** True for every page where someone is getting something done, so no intro or transition. */
export function isAppPath(pathname: string): boolean {
  return pathname.startsWith('/app') || AUTH_PATHS.some((path) => pathname.startsWith(path));
}

/** Where a `next` value may send someone. Anything else could be a link to another site. */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || next.includes('//') || next.includes('\\')) return null;
  return next.startsWith('/app') || next.startsWith('/accept-invite') ? next : null;
}
