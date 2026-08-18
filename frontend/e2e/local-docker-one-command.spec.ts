import { test, expect, type Page } from '@playwright/test';
import { execSync } from 'node:child_process';
import { getBackendContainer, waitForEmbeddingReady } from './helpers/session';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';

/**
 * Section XI acceptance journey: everything a real user gets from just
 * `docker compose up -d --build` at the repo root, driven through the real
 * `/login` form - never the test-safe session-injection shortcut every
 * other spec file uses. No .env beyond the seeded DEMO_USER_PASSWORD, no
 * token minting, no migration command, no npm/uvicorn run outside Docker.
 *
 * Originally drove this via the anonymous "Enter Local Mode" button -
 * removed by design once Demo Mode is active (DEMO_SEED_ENABLED or
 * DEMO_REQUIRE_GEMINI auto-disable POST /api/auth/local-session, see
 * backend/config/settings.py::allow_local_mode) so a zero-credential
 * session can never sit alongside the seeded demo accounts it's meant to
 * be replaced by. Signs in as the real, credentialed demo_user account
 * through the actual form instead - still a genuine UI-driven journey,
 * just through the login path every real user now has.
 */
const DEMO_USER_PASSWORD = process.env.DEMO_USER_PASSWORD;

async function enterLocalModeViaUi(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('#identifier-input').fill('demo_user');
  await page.locator('#password-input').fill(DEMO_USER_PASSWORD!);
  await page.getByRole('button', { name: /THIẾT LẬP PHIÊN BẢO MẬT/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 });
}

function uniqueMarker(prefix = 'onecmd'): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

test.describe('Docker one-command acceptance journey', () => {
  test.skip(!DEMO_USER_PASSWORD, 'DEMO_USER_PASSWORD env var not provided to the e2e runner.');

  test('the seeded demo_user account signs in with no hosted auth and no manual setup', async ({ page }) => {
    await enterLocalModeViaUi(page);
    // Scoped to headings, not a bare text regex: on mobile viewports the
    // AppShell nav's own "Dashboard" link label (see resilience.spec.ts's
    // identical mobile-nav comment) is also a text match for "Dashboard"
    // but stays hidden behind the collapsed hamburger menu - a bare
    // getByText().first() can resolve to that hidden nav span before the
    // actual page heading, in DOM order, and fail toBeVisible() for a
    // reason that has nothing to do with whether sign-in worked.
    await expect(
      page.getByRole('heading', { name: /CyberSec Assistant/i }).first(),
    ).toBeVisible();
  });

  test('full journey: upload, RAG answer, citation, security tools, history, conversation persistence', async ({
    page,
  }) => {
    // On a genuinely fresh embedding_cache volume (this test's real
    // condition against a from-scratch `docker compose up -d --build`),
    // the very first document upload also downloads the embedding model
    // from Hugging Face Hub - observed ~84s end-to-end in this environment,
    // not just the usual few-second in-memory model load this project's
    // other specs see against an already-warm cache. Every later upload in
    // this same run is fast (model is now cached in the volume).
    test.setTimeout(180000);
    const marker = uniqueMarker();
    await enterLocalModeViaUi(page);

    // Knowledge Base upload -> READY
    await page.goto('/knowledge-base');
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(
        `Docker one-command acceptance document. The unique marker for this run is ${marker}. This ` +
          `paragraph exists so the document is long enough to chunk and embed meaningfully.`,
      ),
    });
    const row = page.locator('tbody tr', { hasText: `${marker}.txt` });
    await expect(row).toBeVisible({ timeout: 90000 });
    await expect(row.getByText('READY').or(row.getByText('SẴN SÀNG'))).toBeVisible({ timeout: 30000 });

    // 2. RAG AI Answer
    await page.goto('/ai');
    await page.getByRole('button', { name: /Cuộc trò chuyện bảo mật mới/i }).click();
    await page.getByPlaceholder('Hỏi CyberSec Assistant...').fill(`What is the unique marker ${marker}?`);
    await page.getByPlaceholder('Hỏi CyberSec Assistant...').press('Enter');
    await expect(page.getByText(new RegExp(marker)).last()).toBeVisible({ timeout: 30000 });

    // URL Scanner
    await page.goto('/toolkit/url-scanner');
    await page.locator('#url-input').fill('https://example.com');
    await page.getByRole('button', { name: 'QUÉT' }).click();
    await expect(page.getByText(/scanning/i).or(page.getByText(/example\.com/i))).toBeVisible({ timeout: 15000 });

    // Password Checker
    await page.goto('/toolkit/password-checker');
    await page.locator('#pass-checker-input').fill('Sup3r-Secret-Test-Passw0rd!');
    await page.waitForTimeout(1500);
    await expect(page.locator('body')).toBeVisible();

    // CVE Lookup
    await page.goto('/toolkit/cve-lookup');
    await page.locator('#cve-search-input').fill('CVE-2021-44228');
    await page.waitForTimeout(3000);
    await expect(page.locator('body')).toBeVisible();

    // Scan History
    await page.goto('/toolkit/history');
    await expect(page.locator('body')).toBeVisible();

    // Conversation persists across navigation
    await page.goto('/ai');
    await expect(page.getByText(new RegExp(marker)).last()).toBeVisible({ timeout: 10000 });
  });

  test('backend container restart: demo account session and website recover', async ({ page }) => {
    test.setTimeout(120000);
    await enterLocalModeViaUi(page);
    await page.goto('/dashboard');

    const backendContainer = getBackendContainer();
    execSync(`docker restart ${backendContainer}`, { stdio: 'ignore' });
    for (let i = 0; i < 30; i++) {
      try {
        execSync(
          `docker exec ${backendContainer} python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=2)"`,
          { stdio: 'ignore' },
        );
        break;
      } catch {
        await page.waitForTimeout(1000);
      }
    }

    await page.reload();
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.locator('body')).toBeVisible();
    // Leave the shared backend container fully settled (not just bare
    // /health) before this test ends - see waitForEmbeddingReady's own
    // comment for why: the next spec file in this project's serial run
    // would otherwise race the embedding model's post-restart warmup.
    await waitForEmbeddingReady(BASE_URL);

    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    await page.waitForTimeout(1000);
    expect(errors).toHaveLength(0);
  });

  test('no console errors, no network 500s, no horizontal overflow on the core pages', async ({ page }) => {
    await enterLocalModeViaUi(page);

    const consoleErrors: string[] = [];
    page.on('console', (m) => {
      if (m.type() === 'error') consoleErrors.push(m.text());
    });
    const failedResponses: string[] = [];
    page.on('response', (r) => {
      if (r.status() >= 500) failedResponses.push(`${r.status()} ${r.url()}`);
    });

    for (const path of ['/dashboard', '/knowledge-base', '/ai', '/toolkit/url-scanner']) {
      await page.goto(path);
      // Measure scrollWidth only after the page has genuinely settled - a
      // measurement taken mid-layout (webfonts/icons still loading, async
      // widgets still mounting) can transiently read as overflowing even
      // though the final layout does not.
      await page.waitForLoadState('networkidle');
      const hasOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(hasOverflow, `${path} should not overflow horizontally`).toBe(false);
    }

    expect(failedResponses, 'no 5xx responses from any page in this journey').toEqual([]);
    expect(consoleErrors.filter((e) => !e.includes('favicon')), 'no console errors').toEqual([]);
  });
});
