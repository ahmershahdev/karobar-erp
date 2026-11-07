import { describe, expect, it } from 'vitest';

import { api, setActiveTenant } from './client';

async function sentTenant(headers: Record<string, string> = {}) {
  let tenant: string | null = null;
  const fetch = (request: Request) => {
    tenant = request.headers.get('X-Tenant');
    return Promise.resolve(new Response('{}', { status: 200 }));
  };
  await api.GET('/api/assistant/check/', { baseUrl: 'http://test.local', fetch, headers });
  return tenant;
}

describe('the business sent with a request', () => {
  it('is the selected business by default', async () => {
    setActiveTenant('selected');
    expect(await sentTenant()).toBe('selected');
  });

  it('stays the one a request was bound to after a switch', async () => {
    setActiveTenant('selected');
    expect(await sentTenant({ 'X-Tenant': 'bound' })).toBe('bound');
  });
});
