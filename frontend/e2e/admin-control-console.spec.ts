import { test, expect } from '@playwright/test';
import { injectSession, mintTestSession, uniqueMarker } from './helpers/session';

const demoSuperadminPassword = process.env.DEMO_SUPERADMIN_PASSWORD;

async function signInSuperadmin(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.locator('#identifier-input').fill('demo_superadmin');
  await page.locator('#password-input').fill(demoSuperadminPassword!);
  await page.getByRole('button', { name: /THI|ESTABLISH SECURE SESSION/i }).click();
  await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 15_000 });
}

test.describe('Control Console administration', () => {
  test.skip(!demoSuperadminPassword, 'DEMO_SUPERADMIN_PASSWORD not provided to the e2e runner.');

  test('shows the required administration sections without exposing secrets', async ({ page }) => {
    await signInSuperadmin(page);

    for (const label of ['Overview', 'Users & Roles', 'Audit Logs', 'System Health', 'AI & Knowledge', 'Crawler', 'Security Settings']) {
      await expect(page.getByRole('link', { name: label })).toBeVisible();
    }

    await expect(page.getByText('Users', { exact: true })).toBeVisible();
    await expect(page.getByText('Security', { exact: true })).toBeVisible();
    await expect(page.getByText('AI / RAG', { exact: true })).toBeVisible();
    await expect(page.getByText('System', { exact: true })).toBeVisible();

    await page.getByRole('link', { name: 'Security Settings' }).click();
    await expect(page.getByText('Secrets hidden')).toBeVisible();
    const bodyText = await page.locator('body').innerText();
    expect(bodyText).not.toMatch(/sk-[A-Za-z0-9_-]{12,}|api[_ -]?key\s*[:=]\s*\S+|password\s*[:=]\s*\S+/i);
  });

  test('filters TEST users, changes role and activation, and writes audit rows', async ({ page, request }) => {
    const email = `${uniqueMarker('control-console-role')}@example.test`;
    const session = mintTestSession(email);

    const me = await request.get('/api/auth/me', {
      headers: { Authorization: `Bearer ${session.accessToken}` },
    });
    expect(me.ok()).toBeTruthy();

    await signInSuperadmin(page);
    await page.getByRole('link', { name: 'Users & Roles' }).click();
    await expect(page).toHaveURL(/\/admin\/users/);

    await expect(page.getByLabel('Search')).toBeVisible();
    await page.getByLabel('Search').fill(email);
    await page.getByRole('button', { name: 'Apply' }).click();
    await expect(page.getByText('No users match the current filters.')).toBeVisible();

    await page.getByLabel('Hide TEST').uncheck();
    await page.getByRole('button', { name: 'Apply' }).click();
    const userRow = page.locator('tr').filter({ hasText: email });
    await expect(userRow).toBeVisible();
    await expect(page.getByText(/test \/ TEST/i)).toBeVisible();

    await userRow.getByRole('button', { name: new RegExp(`Actions for ${email}`) }).click();
    await page.getByRole('button', { name: 'Details' }).click();
    await expect(page.getByRole('heading', { name: 'User detail' })).toBeVisible();
    await expect(page.getByText(session.userId)).toBeVisible();

    await page.getByRole('button', { name: 'Promote to admin' }).click();
    await expect(page.getByRole('button', { name: 'Demote to user' })).toBeVisible();
    await page.getByRole('button', { name: 'Demote to user' }).click();
    await expect(page.getByRole('button', { name: 'Promote to admin' })).toBeVisible();

    await page.getByRole('button', { name: 'Disable account' }).click();
    await expect(page.getByRole('button', { name: 'Enable account' })).toBeVisible();
    await page.getByRole('button', { name: 'Enable account' }).click();
    await expect(page.getByRole('button', { name: 'Disable account' })).toBeVisible();

    await page.getByRole('button', { name: 'Close user detail' }).click();
    await expect(page.getByRole('heading', { name: 'User detail' })).toBeHidden();
    await page.goto('/admin/audit');
    await page.getByLabel('Target ID').fill(session.userId);
    await page.getByRole('button', { name: 'Apply' }).click();
    await expect(page.locator('tr').filter({ hasText: 'Role changed' }).first()).toBeVisible();
    await expect(page.locator('tr').filter({ hasText: /User activated|User deactivated/ }).first()).toBeVisible();
  });

  test('non-admin users cannot reach the Control Console', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker('control-console-rbac')}@example.test`);
    await injectSession(context, session);

    await page.goto('/admin/overview');
    await expect(page).toHaveURL(/\/access-denied/, { timeout: 10_000 });
  });

  test('Control Console responsive routes avoid horizontal overflow', async ({ page }) => {
    await signInSuperadmin(page);
    for (const path of ['/admin/overview', '/admin/users', '/admin/audit', '/admin/health', '/admin/rag', '/admin/crawler', '/admin/settings']) {
      await page.goto(path);
      await page.waitForTimeout(500);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
      expect(overflow, `${path} has horizontal overflow`).toBe(false);
    }
  });
});
