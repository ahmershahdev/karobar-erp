import createClient, { type Middleware } from 'openapi-fetch';

import { env } from '../env';
import type { paths } from './schema';

const CSRF_COOKIE = /(?:^|;\s*)(?:__Host-)?kb_csrftoken=([^;]+)/;
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

let activeTenant: string | null = null;

export function setActiveTenant(tenantId: string | null): void {
  activeTenant = tenantId;
}

function csrfToken(): string | null {
  const match = CSRF_COOKIE.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

const sessionHeaders: Middleware = {
  onRequest({ request }) {
    if (UNSAFE_METHODS.has(request.method)) {
      const token = csrfToken();
      if (token) request.headers.set('X-CSRFToken', token);
    }
    if (activeTenant) request.headers.set('X-Tenant', activeTenant);
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: env.apiBaseUrl, credentials: 'same-origin' });
api.use(sessionHeaders);
