import { expect, test, type Page } from '@playwright/test';

import { API_PORT, DEMO_EMAIL } from '../stack.mjs';
import { businessPath, signIn } from './helpers';

// The rules in docs/security.md, checked from outside against a running server.

interface Membership {
  tenant_id: string;
  tenant_name: string;
}

async function tenantId(page: Page, name: string): Promise<string> {
  const rows = (await (await page.request.get('/api/tenants/')).json()) as Membership[];
  const row = rows.find((entry) => entry.tenant_name.includes(name));
  if (!row) throw new Error(`no business named ${name}`);
  return row.tenant_id;
}

/** Headers for a change made the way the app makes it: the business, the CSRF token, the page. */
async function changing(page: Page, tenant?: string): Promise<Record<string, string>> {
  const cookies = await page.context().cookies();
  const token = cookies.find((cookie) => cookie.name.endsWith('kb_csrftoken'))?.value ?? '';
  return {
    'X-CSRFToken': token,
    Referer: page.url(),
    ...(tenant ? { 'X-Tenant': tenant } : {}),
  };
}

test('nothing private answers without signing in', async ({ request }) => {
  for (const path of [
    '/api/tenants/',
    '/api/accounts/me/',
    '/api/sales/invoices/',
    '/api/reports/dashboard/',
    '/api/audit/',
    '/api/assistant/messages/',
    '/api/payroll/runs/',
  ]) {
    const reply = await request.get(path);
    expect([401, 403], path).toContain(reply.status());
  }
});

test('the app screens send a stranger to sign in', async ({ page }) => {
  await page.goto('/app/any-business/sales/invoices');
  await page.waitForURL(/\/login/);
});

test('the session cookie cannot be read by scripts and the headers are set', async ({ page }) => {
  await signIn(page, 'boss@e2e.test');
  const cookies = await page.context().cookies();
  const session = cookies.find((cookie) => cookie.name.endsWith('kb_session'));
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe('Lax');
  expect(await page.evaluate(() => document.cookie)).not.toContain('kb_session');
  // Nothing about the session is kept where a script could read it.
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(stored).not.toMatch(/token|session|password/i);

  const headers = (await page.request.get('/api/tenants/')).headers();
  expect(headers['x-content-type-options']).toBe('nosniff');
  expect(headers['x-frame-options']).toBe('DENY');
  expect(headers['cache-control']).toContain('no-store');
  expect(headers['content-security-policy']).toContain("frame-ancestors 'none'");
  expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin');
});

test('a change without the CSRF token is refused', async ({ page }) => {
  await signIn(page, 'boss@e2e.test');
  const tenant = await tenantId(page, 'Seeded Shop');
  const bare = await page.request.post('/api/sales/customers/', {
    data: { code: 'NOTOKEN', name: 'No Token Customer' },
    headers: { 'X-Tenant': tenant },
  });
  expect(bare.status()).toBe(403);
  const withToken = await page.request.post('/api/sales/customers/', {
    data: { code: `TOK${Date.now()}`, name: 'Token Customer' },
    headers: await changing(page, tenant),
  });
  expect(withToken.status()).toBe(201);
});

test('one business never sees another', async ({ browser, page }) => {
  const other = await browser.newContext();
  const rivalPage = await other.newPage();
  await signIn(rivalPage, 'rival@e2e.test');
  const rival = await tenantId(rivalPage, 'Rival Shop');
  const made = await rivalPage.request.post('/api/sales/customers/', {
    data: { code: `RIV${Date.now()}`, name: 'Rival Secret Customer' },
    headers: await changing(rivalPage, rival),
  });
  expect(made.status()).toBe(201);
  const secret = ((await made.json()) as { id: number }).id;
  await other.close();

  await signIn(page, 'boss@e2e.test');
  const mine = await tenantId(page, 'Seeded Shop');
  // Asking for the rival business by its id is "not found", the same as an id that never was.
  for (const path of ['/api/sales/customers/', '/api/reports/dashboard/', '/api/members/']) {
    const reply = await page.request.get(path, {
      headers: { 'X-Tenant': rival },
    });
    expect(reply.status(), path).toBe(404);
  }
  const unknown = '00000000-0000-4000-8000-000000000000';
  const never = await page.request.get('/api/sales/customers/', {
    headers: { 'X-Tenant': unknown },
  });
  expect(never.status()).toBe(404);
  // And the rival row is not found from inside my own business either.
  const row = await page.request.get(`/api/sales/customers/${secret}/`, {
    headers: { 'X-Tenant': mine },
  });
  expect(row.status()).toBe(404);
  const list = await page.request.get('/api/sales/customers/', {
    headers: { 'X-Tenant': mine },
  });
  expect(await list.text()).not.toContain('Rival Secret Customer');
});

test('a cashier only reaches what the role allows', async ({ page }) => {
  await signIn(page, 'cashier@e2e.test');
  const tenant = await tenantId(page, 'Seeded Shop');
  const headers = { 'X-Tenant': tenant };
  for (const path of [
    '/api/reports/dashboard/',
    '/api/reports/profit-loss/',
    '/api/accounting/entries/',
    '/api/members/',
    '/api/roles/',
    '/api/audit/',
    '/api/payroll/runs/',
    '/api/hr/employees/',
    '/api/purchasing/bills/',
  ]) {
    expect((await page.request.get(path, { headers })).status(), path).toBe(403);
  }
  expect((await page.request.get('/api/pos/products/', { headers })).status()).toBe(200);
  // The menu shows the counter and none of the screens the role may not open.
  const base = await businessPath(page, 'Seeded Shop');
  await page.goto(base);
  await page.waitForLoadState('networkidle');
  await expect(page.locator(`nav a[href="${base}/counter"]`)).toHaveCount(1);
  for (const hidden of ['reports/dashboard', 'accounting/journal', 'members', 'hr/payroll']) {
    await expect(page.locator(`nav a[href="${base}/${hidden}"]`)).toHaveCount(0);
  }
});

test('text typed into a name is shown as text, never run', async ({ page }) => {
  await signIn(page, 'boss@e2e.test');
  const tenant = await tenantId(page, 'Seeded Shop');
  const name = '<img src=x onerror="window.__ran=1"> =HYPERLINK("http://x")';
  const made = await page.request.post('/api/sales/customers/', {
    data: { code: `XSS${Date.now()}`, name },
    headers: await changing(page, tenant),
  });
  expect(made.status()).toBe(201);
  await page.goto(`${await businessPath(page, 'Seeded Shop')}/sales/customers`);
  await expect(page.getByText(name).first()).toBeVisible();
  expect(await page.evaluate(() => (window as { __ran?: number }).__ran)).toBeUndefined();
});

test('a search that looks like SQL is only a search', async ({ page }) => {
  await signIn(page, 'boss@e2e.test');
  const headers = { 'X-Tenant': await tenantId(page, 'Seeded Shop') };
  const reply = await page.request.get('/api/sales/customers/', {
    headers,
    params: {
      search: "' OR 1=1 -- ",
      ordering: 'id; DROP TABLE sales_customer',
    },
  });
  expect([200, 400]).toContain(reply.status());
  expect((await page.request.get('/api/sales/customers/', { headers })).status()).toBe(200);
});

test('a body larger than the limit is refused', async ({ page, playwright }) => {
  await signIn(page, 'boss@e2e.test');
  const tenant = await tenantId(page, 'Seeded Shop');
  const cookies = await page.context().cookies();
  // Straight to the API on its own connection: the server stops reading part-way, and the
  // dev proxy would hand that broken connection to the next test.
  const direct = await playwright.request.newContext({
    baseURL: `http://127.0.0.1:${API_PORT}`,
  });
  const reply = await direct.post('/api/sales/customers/', {
    data: { code: 'BIG', name: 'x'.repeat(3 * 1024 * 1024) },
    headers: {
      ...(await changing(page, tenant)),
      Cookie: cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; '),
      Connection: 'close',
    },
  });
  expect(reply.status()).toBe(413);
  await direct.dispose();
});

test('the shared demo account cannot change itself or reach outside the demo', async ({ page }) => {
  await signIn(page, DEMO_EMAIL);
  const headers = await changing(page);
  const business = await page.request.post('/api/tenants/', {
    data: { name: 'Not Allowed', base_currency: 'PKR', locale: 'en' },
    headers,
  });
  expect(business.status()).toBe(403);
  expect(((await business.json()) as { code: string }).code).toBe('demo_account');
  const password = await page.request.post('/api/accounts/password/', {
    data: { current_password: 'x', new_password: 'another long password here' },
    headers,
  });
  expect(password.status()).toBe(403);
});

test('errors never show how the server is built', async ({ page }) => {
  await signIn(page, 'boss@e2e.test');
  const tenant = await tenantId(page, 'Seeded Shop');
  const reply = await page.request.post('/api/sales/customers/', {
    data: '{"name": ',
    headers: {
      ...(await changing(page, tenant)),
      'Content-Type': 'application/json',
    },
  });
  expect(reply.status()).toBe(400);
  expect(await reply.text()).not.toMatch(/Traceback|django|mysql|File "/i);
  const missing = await page.request.get('/api/no-such-thing/');
  expect(missing.status()).toBe(404);
  expect(await missing.text()).not.toMatch(/Traceback|urlpatterns|DEBUG/);
});
