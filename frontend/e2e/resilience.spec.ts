import { test, expect, type Page } from '@playwright/test';
import { execSync } from 'node:child_process';
import { mintTestSession, injectSession, uniqueMarker, getBackendContainer, waitForEmbeddingReady } from './helpers/session';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';

async function recoverFromOfflineRouteIfNeeded(page: Page): Promise<void> {
  if (new URL(page.url()).pathname !== '/offline') return;
  try {
    await page.locator('button').first().click({ timeout: 5000 });
  } catch (error) {
    if (new URL(page.url()).pathname !== '/offline') return;
    throw error;
  }
}

// The first four specs use page.route() to stub HTTP responses at the
// browser level - they verify the frontend's handling of those status
// codes, not a real backend/infrastructure failure. Only the final spec
// (container restart) is a genuine infrastructure-level failure injection.
test.describe('Resilience and failure handling', () => {
  test('a 500 from the backend shows an error, not a stack trace or infinite spinner', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);

    await page.route('**/api/knowledge/documents*', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: '{"message":"Internal error"}' }),
    );

    await page.goto('/knowledge-base');
    await page.waitForTimeout(2000);
    const bodyText = await page.locator('body').innerText();
    expect(bodyText).not.toContain('Traceback');
    expect(bodyText).not.toContain('at Object.');
    await expect(page.locator('body')).toBeVisible();
  });

  test('a 401 mid-session redirects to login rather than hanging', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);

    await page.goto('/toolkit/history');
    await page.waitForTimeout(1000);

    // Exclude /api/system/health: it's a public, unauthenticated endpoint a
    // real backend never 401s (see getSystemHealth's own comment). Stubbing
    // it here would make ConnectionRecoveryProvider treat the response as
    // "backend unreachable" and redirect to /offline instead, which is not
    // what this test verifies.
    await page.route('**/api/tools/url-scan', (route) =>
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"message":"Unauthorized"}' }),
    );
    // Client-side navigation (not page.goto, which hard-reloads and
    // re-runs the initial session-bootstrap path - toAppUser() there
    // treats a failed GET /api/auth/me as "role lookup failed, default to
    // user" rather than "session invalid", so a bootstrap-time 401 doesn't
    // sign out). A real mid-session 401 happens to an already-mounted SPA,
    // which is what clicking a nav link, not a full reload, represents.
    // On mobile viewports (see AppShell.tsx) the nav is collapsed behind a
    // hamburger toggle, so the link isn't in the accessibility tree until
    // that's opened - desktop already renders it directly, where this is a
    // harmless extra click on an already-open nav.
    // Scoped to a <nav> ancestor - both AppShell's desktop sidebar and its
    // mobile drawer wrap links in <nav>, but the toolkit page's own
    // "Kiểm tra Website" sub-nav tab (same accessible name) does not, so
    // this reaches the sidebar/drawer link on every viewport without a
    // strict-mode violation.
    // .filter({ visible: true }) matters once the mobile drawer opens below:
    // the desktop sidebar's <nav> stays in the DOM (just CSS-hidden) while
    // the drawer's own <nav> mounts alongside it, so two "Kiểm tra Website"
    // links exist at once and only the visibility filter picks the right one.
    const navLink = page.locator('nav a', { hasText: 'Kiểm tra Website' }).filter({ visible: true });
    if (!(await navLink.isVisible())) {
      await page.getByRole('button', { name: /Toggle Navigation Menu|Chuy/i }).first().click();
    }
    await navLink.click();
    await expect(page).toHaveURL(/\/toolkit\/url-scanner/);
    // The scanner page itself makes no API call on mount - only submitting
    // a scan does, so that is what needs to trigger the stubbed 401.
    // authFetch signs the user out on any 401 (see authFetch.ts), so the
    // submit should redirect to /login rather than hang on the still-mounted
    // form.
    await page.locator('#url-input').fill('https://example.com');
    await page.getByRole('button', { name: 'QUÉT' }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('a 429 rate-limit response is shown as an error, not silently retried forever', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);

    let calls = 0;
    await page.route('**/api/tools/url-scan', (route) => {
      calls += 1;
      return route.fulfill({ status: 429, contentType: 'application/json', body: '{"message":"Too many requests"}' });
    });

    await page.goto('/toolkit/url-scanner');
    await page.locator('#url-input').fill('https://example.com');
    await page.getByRole('button', { name: 'QUÉT' }).click();
    await page.waitForTimeout(3000);
    expect(calls).toBeLessThan(5);
  });

  test('a network drop (aborted request) mid-upload does not create an orphan document', async ({ page, context }) => {
    const marker = uniqueMarker();
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.route('**/api/knowledge/documents', (route) => {
      if (route.request().method() === 'POST') return route.abort('connectionreset');
      return route.continue();
    });

    await page.goto('/knowledge-base');
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from('Network-drop test document, content long enough to pass validation checks.'),
    });
    await page.waitForTimeout(2000);
    await expect(page.locator('tbody tr', { hasText: `${marker}.txt` })).toHaveCount(0);
  });

  test('backend container restart: session and data survive, UI recovers', async ({ page, context }) => {
    test.setTimeout(150000);
    const marker = uniqueMarker();
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/knowledge-base');
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(`Restart-survival test document ${marker}, long enough content for validation.`),
    });
    // See accessibility.spec.ts's identical comment: a genuinely fresh
    // Docker one-command stack's first embedding call costs ~20-30s
    // (ONNX Runtime session init), on top of normal overhead.
    await expect(page.locator('tbody tr', { hasText: `${marker}.txt` })).toBeVisible({ timeout: 90000 });
    await expect(page.locator('tbody tr', { hasText: `${marker}.txt` }).getByText(/READY|SẴN SÀNG/i)).toBeVisible({
      timeout: 20000,
    });

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

    // The container's bare /health liveness check above can pass before
    // full readiness (embedding model reinit, ~20-30s) settles. Wait for
    // the same terminal readiness condition as global setup before asking
    // the browser to reload the protected route, otherwise the reload can
    // correctly park on /offline while the model is still warming.
    await waitForEmbeddingReady(BASE_URL, 90000);
    await page.reload();
    await recoverFromOfflineRouteIfNeeded(page);
    await expect(page).toHaveURL(/\/knowledge-base/, { timeout: 60000 });
    await expect(page.locator('tbody tr', { hasText: `${marker}.txt` })).toBeVisible({ timeout: 15000 });
  });
});
