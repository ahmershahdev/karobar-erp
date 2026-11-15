import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { expect, type Page } from '@playwright/test';

import { PASSWORD, frontend, mailDir } from '../stack.mjs';

type Words = { [key: string]: string | Words };

function words(language: string): Words {
  const file = join(frontend, 'src', 'i18n', 'locales', `${language}.json`);
  return JSON.parse(readFileSync(file, 'utf8')) as Words;
}

/** The app's own text, so a reworded button doesn't break a test that isn't about wording. */
export function text(key: string, language = 'en'): string {
  let found: string | Words | undefined = words(language);
  for (const part of key.split('.')) {
    found = typeof found === 'object' ? found[part] : undefined;
  }
  if (typeof found !== 'string') throw new Error(`no text for ${key} in ${language}`);
  return found;
}

/** Every screen inside a business, as in frontend/src/app/AppRoutes.tsx. */
export const SCREENS = [
  '',
  'account',
  'counter',
  'members',
  'bill-design',
  'roles',
  'audit',
  'sales/invoices',
  'sales/receipts',
  'sales/customers',
  'sales/orders',
  'sales/returns',
  'sales/owed-to-me',
  'reports/dashboard',
  'reports/profit-loss',
  'reports/balance-sheet',
  'reports/cash-flow',
  'reports/sales-tax',
  'accounting/journal',
  'accounting/chart',
  'accounting/trial-balance',
  'accounting/ledger',
  'accounting/periods',
  'accounting/tax-rates',
  'inventory/products',
  'inventory/entries',
  'inventory/on-hand',
  'inventory/alerts',
  'inventory/setup',
  'purchasing/suppliers',
  'purchasing/orders',
  'purchasing/receipts',
  'purchasing/bills',
  'purchasing/payments',
  'purchasing/owed-by-me',
  'hr/employees',
  'hr/departments',
  'hr/salary-structures',
  'hr/leave',
  'hr/attendance',
  'hr/holidays',
  'hr/payroll',
  'hr/tax-slabs',
  'hr/contributions',
  'hr/end-of-service',
] as const;

export interface Trouble {
  kind: 'console' | 'crash' | 'server' | 'request';
  detail: string;
}

/** Collects what a person would never see but a bug leaves behind: errors in the console,
 * crashed scripts, and API calls the server failed or refused. `allow` lists refusals a test
 * expects, as "STATUS path-fragment". */
export function watch(page: Page, allow: string[] = []): Trouble[] {
  const found: Trouble[] = [];
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const detail = message.text();
    // The browser logs every failed request here too; those are judged below, with their status.
    if (detail.startsWith('Failed to load resource')) return;
    found.push({ kind: 'console', detail });
  });
  page.on('pageerror', (error) => found.push({ kind: 'crash', detail: error.message }));
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith('/api/') || response.status() < 400) return;
    const line = `${response.status()} ${response.request().method()} ${url.pathname}`;
    if (
      allow.some(
        (entry) =>
          line.startsWith(entry.split(' ')[0] ?? '') && line.includes(entry.split(' ')[1] ?? ''),
      )
    ) {
      return;
    }
    found.push({
      kind: response.status() >= 500 ? 'server' : 'request',
      detail: line,
    });
  });
  return found;
}

export async function useLanguage(page: Page, language: string): Promise<void> {
  await page.addInitScript((code) => {
    window.localStorage.setItem('i18nextLng', code);
  }, language);
}

export async function signIn(page: Page, email: string, language = 'en'): Promise<void> {
  await page.goto('/login');
  await page.getByLabel(text('signIn.email', language)).fill(email);
  await page.getByLabel(text('signIn.password', language), { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: text('signIn.submit', language), exact: true }).click();
  await page.waitForURL(/\/(app|new-business)/);
}

/** The address of a business the signed-in person belongs to, by its name. */
export async function businessPath(page: Page, name: string): Promise<string> {
  const reply = await page.request.get('/api/tenants/');
  expect(reply.ok()).toBe(true);
  const rows = (await reply.json()) as {
    tenant_name: string;
    tenant_slug: string;
  }[];
  const row = rows.find((entry) => entry.tenant_name.includes(name));
  if (!row) throw new Error(`no business named ${name} in ${rows.map((r) => r.tenant_name)}`);
  return `/app/${row.tenant_slug}`;
}

/** The page is no wider than the window. In Urdu and Arabic a stray offset shows up here. */
export async function expectNoSidewaysScroll(page: Page): Promise<void> {
  const extra = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(extra, `the page is ${extra}px wider than the window`).toBeLessThanOrEqual(1);
}

/** The newest email sent to an address that mentions `about` (a link path, say), from the files
 * the server writes instead of sending. */
export function lastEmailTo(address: string, about = ''): string {
  const files = readdirSync(mailDir)
    .map((name) => join(mailDir, name))
    .sort();
  for (const file of files.reverse()) {
    // Long lines are wrapped with "=" at the end, and "=" itself is written as "=3D".
    const body = readFileSync(file, 'utf8')
      .replace(/=\r?\n/g, '')
      .replaceAll('=3D', '=');
    if (body.includes(`To: ${address}`) && body.includes(about)) return body;
  }
  throw new Error(`no email to ${address}`);
}

export function linkIn(email: string, path: string): string {
  const match = new RegExp(`https?://[^\\s"<>]*${path}[^\\s"<>]*`).exec(email);
  if (!match) throw new Error(`no ${path} link in the email`);
  const url = new URL(match[0]);
  return url.pathname + url.search;
}
