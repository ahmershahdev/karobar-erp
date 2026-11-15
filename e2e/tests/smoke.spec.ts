import { expect, test } from '@playwright/test';

import { DEMO_EMAIL } from '../stack.mjs';
import {
  SCREENS,
  businessPath,
  expectNoSidewaysScroll,
  signIn,
  text,
  useLanguage,
  watch,
} from './helpers';

// Smoke tests: does every screen open, with real data, without an error anywhere. They change
// nothing, so they are also what to run against a deployed server.

test('the server says it is healthy', async ({ request }) => {
  const reply = await request.get('/api/health/');
  expect(reply.status()).toBe(200);
});

for (const path of ['/', '/modules', '/security', '/login', '/signup', '/forgot-password']) {
  test(`the public page ${path} opens`, async ({ page }) => {
    const trouble = watch(page);
    await page.goto(path);
    await expect(page.locator('h1').first()).toBeVisible();
    await expectNoSidewaysScroll(page);
    expect(trouble).toEqual([]);
  });
}

test('an address that does not exist shows the not-found page', async ({ page }) => {
  await page.goto('/no-such-page');
  await expect(page.getByText(text('notFound.title'))).toBeVisible();
});

const WALKS = [
  { language: 'en', business: 'Kiryana' },
  { language: 'en', business: 'Trading' },
  { language: 'ur', business: 'Kiryana' },
  { language: 'ar', business: 'Trading' },
];

for (const { language, business } of WALKS) {
  test(`every screen of the ${business} demo business opens in ${language}`, async ({ page }) => {
    test.setTimeout(10 * 60_000);
    const trouble = watch(page);
    await useLanguage(page, language);
    await signIn(page, DEMO_EMAIL, language);
    const base = await businessPath(page, business);
    const direction = language === 'en' ? 'ltr' : 'rtl';
    const failed: string[] = [];
    for (const screen of SCREENS) {
      const before = trouble.length;
      await page.goto(`${base}/${screen}`);
      await page.waitForLoadState('networkidle');
      const problems: string[] = [];
      if (!new URL(page.url()).pathname.startsWith(`${base}/${screen}`.replace(/\/$/, ''))) {
        problems.push(`sent away to ${page.url()}`);
      }
      if ((await page.locator('html').getAttribute('dir')) !== direction) {
        problems.push(`the page is not ${direction}`);
      }
      if (!(await page.locator('main h1, main h2').first().isVisible())) {
        problems.push('no heading');
      }
      if (await page.getByText(text('signIn.unavailable', language)).first().isVisible()) {
        problems.push('shows "the server could not be reached"');
      }
      const extra = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      if (extra > 1) problems.push(`${extra}px wider than the window`);
      problems.push(...trouble.slice(before).map((entry) => `${entry.kind}: ${entry.detail}`));
      if (problems.length) failed.push(`${screen || 'home'}: ${problems.join('; ')}`);
    }
    expect(failed, failed.join('\n')).toEqual([]);
  });
}

test('every link in the menu is a screen this test walks', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'the menu is laid out for a wide screen');
  await signIn(page, DEMO_EMAIL);
  const base = await businessPath(page, 'Kiryana');
  await page.goto(base);
  await page.waitForLoadState('networkidle');
  const links = await page
    .locator(`a[href^="${base}"]`)
    .evaluateAll((all) => all.map((link) => new URL((link as HTMLAnchorElement).href).pathname));
  const known = new Set(SCREENS.map((screen) => `${base}/${screen}`.replace(/\/$/, '')));
  const unknown = [...new Set(links)].filter((link) => !known.has(link));
  // A new screen belongs in SCREENS, or the walk above would pass without ever opening it.
  expect(unknown).toEqual([]);
});
