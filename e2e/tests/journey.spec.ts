import { expect, test } from '@playwright/test';

import { PASSWORD } from '../stack.mjs';
import { lastEmailTo, linkIn, signIn, text, watch } from './helpers';

// What a new shopkeeper does on day one, through the screens only: sign up, confirm the email
// from the link that was sent, create a business and land on its home page.

const email = `owner-${Date.now()}@e2e.test`;
const shop = `Journey Traders ${Date.now() % 100000}`;

test.describe.configure({ mode: 'serial' });

async function fillSignUp(page: import('@playwright/test').Page, name: string): Promise<void> {
  await page.goto('/signup');
  await page.getByLabel(text('auth.fullName')).fill(name);
  await page.getByLabel(text('signIn.email')).fill(email);
  await page.getByLabel(text('signIn.password'), { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: text('auth.signUp'), exact: true }).click();
}

async function fillSignIn(
  page: import('@playwright/test').Page,
  who: string,
  secret: string,
): Promise<void> {
  await page.goto('/login');
  await page.getByLabel(text('signIn.email')).fill(who);
  await page.getByLabel(text('signIn.password'), { exact: true }).fill(secret);
  await page.getByRole('button', { name: text('signIn.submit'), exact: true }).click();
}

test('a new person signs up and is told to check their email', async ({ page }) => {
  const trouble = watch(page);
  await fillSignUp(page, 'Journey Owner');
  await expect(page.getByText(text('auth.checkEmail'))).toBeVisible();
  expect(trouble).toEqual([]);
});

test('signing up twice with the same email looks exactly the same', async ({ page }) => {
  // Otherwise the form would tell a stranger who has an account.
  await fillSignUp(page, 'Someone Else');
  await expect(page.getByText(text('auth.checkEmail'))).toBeVisible();
});

test('before confirming, they cannot create a business', async ({ page }) => {
  await signIn(page, email);
  await page.goto('/new-business');
  await expect(page.getByText(text('workspace.unverified')).first()).toBeVisible();
});

test('the link in the email confirms the address', async ({ page }) => {
  const link = linkIn(lastEmailTo(email, '/verify-email'), '/verify-email');
  await page.goto(link);
  await expect(page.getByText(text('auth.verified'))).toBeVisible();
  // A link with a changed token confirms nothing.
  await page.goto(`${link}x`);
  await expect(page.getByText(text('auth.badLink'))).toBeVisible();
});

test('they create a business and land on its home page', async ({ page }) => {
  const trouble = watch(page);
  await signIn(page, email);
  await page.waitForURL(/new-business/);
  await page.getByLabel(text('workspace.businessName')).fill(shop);
  await page.getByRole('button', { name: text('workspace.create'), exact: true }).click();
  await page.waitForURL(/\/app\/journey-traders/);
  await expect(page.getByRole('combobox').first()).toContainText(shop);
  await page.waitForLoadState('networkidle');
  expect(trouble).toEqual([]);
});

test('a wrong password and an unknown email get the same answer', async ({ page }) => {
  await fillSignIn(page, email, 'not the right password');
  await expect(page.getByText(text('signIn.failed'))).toBeVisible();
  await fillSignIn(page, 'nobody-here@e2e.test', PASSWORD);
  await expect(page.getByText(text('signIn.failed'))).toBeVisible();
});

test('forgot password sends a link that sets a new password', async ({ page }) => {
  await page.goto('/forgot-password');
  await page.getByLabel(text('signIn.email')).fill(email);
  await page.getByRole('button', { name: text('auth.sendLink'), exact: true }).click();
  await expect(page.getByText(text('auth.resetSent'))).toBeVisible();
  await page.goto(linkIn(lastEmailTo(email, '/reset-password'), '/reset-password'));
  const fresh = `${PASSWORD} again`;
  await page.getByLabel(text('auth.newPassword'), { exact: true }).fill(fresh);
  await page.getByRole('button', { name: text('auth.savePassword'), exact: true }).click();
  await expect(page.getByText(text('auth.passwordChanged'))).toBeVisible();
  // The old password no longer signs in; the new one does.
  await fillSignIn(page, email, PASSWORD);
  await expect(page.getByText(text('signIn.failed'))).toBeVisible();
  await fillSignIn(page, email, fresh);
  await page.waitForURL(/\/app\//);
});

test('signing out ends the session', async ({ page }) => {
  await signIn(page, 'boss@e2e.test');
  expect((await page.request.get('/api/tenants/')).status()).toBe(200);
  await page
    .getByRole('button', { name: text('workspace.signOut') })
    .first()
    .click();
  await page.waitForURL(/\/login/);
  expect([401, 403]).toContain((await page.request.get('/api/tenants/')).status());
  await page.goto('/app');
  await page.waitForURL(/\/login/);
});
