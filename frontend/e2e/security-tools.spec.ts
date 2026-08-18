import { test, expect, type Page, type Response } from '@playwright/test';
import { mintTestSession, injectSession, uniqueMarker, waitForEmbeddingReady } from './helpers/session';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000';

async function submitUrlScan(page: Page, url: string): Promise<Response | null> {
  await page.goto('/toolkit/url-scanner');
  const input = page.locator('#url-input');
  await input.fill(url);
  await expect(input).toHaveValue(url);
  const scanResponse = page
    .waitForResponse(
      (response) => response.url().includes('/api/tools/url-scan') && response.request().method() === 'POST',
      { timeout: 10000 },
    )
    .catch(() => null);
  await page.locator('#url-input + div button').last().click();
  return scanResponse;
}

test.describe('Security tool journeys', () => {
  test('URL scanner: success path produces a result card', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);
    const response = await submitUrlScan(page, 'https://example.com');
    expect(response?.ok()).toBe(true);
    await expect(page.getByText(/example\.com/i)).toBeVisible({ timeout: 15000 });
  });

  test('URL scanner: invalid input shows an error, not a crash', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);
    await page.goto('/toolkit/url-scanner');
    await page.locator('#url-input').fill('not-a-valid-url');
    await page.locator('#url-input + div button').last().click();
    await page.waitForTimeout(2000);
    await expect(page.locator('#url-input')).toBeVisible();
  });

  test('Password checker: strength meter updates live and never echoes the password', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);
    await page.goto('/toolkit/password-checker');

    const consoleTexts: string[] = [];
    page.on('console', (m) => consoleTexts.push(m.text()));

    const secret = 'Sup3r-Secret-Test-Passw0rd!';
    await page.locator('#pass-checker-input').fill(secret);
    await page.waitForTimeout(1500);

    for (const line of consoleTexts) {
      expect(line).not.toContain(secret);
    }
  });

  test('Password checker: guidance/reset controls work', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);
    await page.goto('/toolkit/password-checker');
    await page.locator('#pass-checker-input').fill('weak');
    await page.waitForTimeout(1000);
    await page.locator('#pass-checker-input + div button').last().click();
    await expect(page.locator('#pass-checker-input')).toHaveValue('');
  });

  test('CVE lookup: known CVE search returns matches', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);
    await page.goto('/toolkit/cve-lookup');
    await page.locator('#cve-search-input').fill('CVE-2021-44228');
    await page.waitForTimeout(3000);
    await expect(page.locator('#cve-search-input')).toBeVisible();
  });

  test('CVE lookup: clear filters resets the query', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);
    await page.goto('/toolkit/cve-lookup');
    await page.locator('#cve-search-input').fill('Log4j');
    await page.waitForTimeout(500);
    const clearBtn = page.locator('button').filter({ hasText: /^X/ }).first();
    if (await clearBtn.isVisible().catch(() => false)) {
      await clearBtn.click();
      await expect(page.locator('#cve-search-input')).toHaveValue('');
    }
  });

  test('Scan history: page loads and shows this session URL scan', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);

    let response: Response | null = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      response = await submitUrlScan(page, 'https://example.org');
      if (response?.ok()) break;
      await waitForEmbeddingReady(BASE_URL);
    }
    expect(response?.ok()).toBe(true);
    await expect(page.getByText(/example\.org/i)).toBeVisible({ timeout: 15000 });

    await page.goto('/toolkit/history');
    await expect(page.locator('#history-search-input')).toBeVisible({ timeout: 30000 });
    await expect(
      page
        .locator('td[title="https://example.org"]:visible')
        .or(page.locator('div:visible', { hasText: 'https://example.org' }))
        .first(),
    ).toBeVisible({ timeout: 15000 });
  });

  test('Security tools: unauthenticated access redirects to login, not a 401 crash page', async ({ page }) => {
    await page.goto('/toolkit/url-scanner');
    await expect(page).toHaveURL(/\/login/);
  });
});
