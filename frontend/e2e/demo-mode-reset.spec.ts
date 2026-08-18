import { expect, test } from '@playwright/test';

const demoSuperadminPassword = process.env.DEMO_SUPERADMIN_PASSWORD;

test.describe('Demo Mode reset and restart', () => {
  test.skip(!demoSuperadminPassword, 'DEMO_SUPERADMIN_PASSWORD not provided to the e2e runner.');

  test('start -> reset -> restart -> exit uses real UI and preserves app health', async ({ page }) => {
    const consoleErrors: string[] = [];
    const server5xx: string[] = [];
    const failedDemoApi: string[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('response', (response) => {
      const url = response.url();
      if (response.status() >= 500) {
        server5xx.push(`${response.status()} ${url}`);
      }
      if (url.includes('/api/demo') && response.status() >= 400) {
        failedDemoApi.push(`${response.status()} ${url}`);
      }
    });

    await page.goto('/login');
    await page.locator('#identifier-input').fill('demo_superadmin');
    await page.locator('#password-input').fill(demoSuperadminPassword!);
    await page.getByRole('button', { name: /THI/i }).click();
    await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 15_000 });

    await page.goto('/reports');
    await page.getByRole('button', { name: /Demo Mode/i }).click();

    await page.getByRole('button', { name: /Start Log4Shell demo/i }).click();
    await expect(page.getByText('Asset: corp-web-01 (Demo Seed)')).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText('CVE: CVE-2024-3400')).toBeVisible();

    await page.getByRole('button', { name: /Reset Demo/i }).click();
    await expect(page.getByText(/Reset Demo removed \d+ demo records/)).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText('Asset: corp-web-01 (Demo Seed)')).toHaveCount(0);
    await expect(page.getByText('CVE: CVE-2024-3400')).toHaveCount(0);

    await page.getByRole('button', { name: /Start Log4Shell demo/i }).click();
    await expect(page.getByText('Asset: corp-web-01 (Demo Seed)')).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText('CVE: CVE-2024-3400')).toBeVisible();

    await page.getByRole('button', { name: /Exit Demo/i }).click();
    await expect(page.getByRole('button', { name: /Demo Mode/i })).toBeVisible();
    await expect(page.locator('select').first()).toBeVisible();

    const unexpectedConsoleErrors = consoleErrors.filter(
      (msg) => !msg.includes('Fast Refresh') && !msg.includes('DevTools'),
    );
    expect(failedDemoApi, `Demo API failures: ${failedDemoApi.join('\n')}`).toEqual([]);
    expect(server5xx, `Unexpected server errors: ${server5xx.join('\n')}`).toEqual([]);
    expect(
      unexpectedConsoleErrors,
      `Unexpected console errors: ${unexpectedConsoleErrors.join('\n')}`,
    ).toEqual([]);
  });
});
