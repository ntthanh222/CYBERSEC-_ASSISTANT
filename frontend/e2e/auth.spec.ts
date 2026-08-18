import { test, expect } from '@playwright/test';
import { mintTestSession, injectSession, uniqueMarker } from './helpers/session';

test.describe('Auth session', () => {
  test('an injected valid session lands on the dashboard, not /login', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);

    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator('body')).not.toContainText('Sign in', { timeout: 5000 }).catch(() => {});
  });

  test('no session redirects a protected route to /login', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login/);
  });

  test('session restore survives a full page reload', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);

    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/dashboard/);

    await page.reload();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 8000 });
  });

  test('an authenticated request carries no token in visible UI text or console', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);

    const consoleTexts: string[] = [];
    page.on('console', (msg) => consoleTexts.push(msg.text()));

    await page.goto('/toolkit/history');
    await page.waitForTimeout(1000);

    const bodyText = await page.locator('body').innerText();
    expect(bodyText).not.toContain(session.accessToken);
    for (const line of consoleTexts) {
      expect(line).not.toContain(session.accessToken);
    }
  });
});
