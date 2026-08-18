import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mintTestSession, injectSession, uniqueMarker, getBackendContainer, waitForEmbeddingReady } from './helpers/session';

function dockerStop(container: string) {
  execFileSync('docker', ['stop', container]);
}
function dockerStart(container: string) {
  execFileSync('docker', ['start', container]);
}

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';

async function waitForBackendHealthy(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE_URL}/api/system/health`);
      if (res.ok) {
        const body = await res.json();
        if (body?.checks?.backend?.status === 'healthy') return;
      }
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('backend did not become healthy in time');
}

test.describe('Offline / network-recovery flow', () => {
  test('/offline is directly reachable, survives reload and back/forward, with full CSS and clean console', async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto('/offline');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(bodyBg).not.toBe(''); // real stylesheet applied, not unstyled white

    await page.goto('/dashboard'); // will redirect to /login (no session) - fine, just building history
    await page.goto('/offline');
    await page.reload();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    // Wait for goBack() to actually settle (the custom router shim in
    // src/vendor/react-router-dom.tsx updates location on the browser's
    // 'popstate' event, asynchronously relative to Playwright's goBack()
    // call) before firing goForward() - otherwise, under load, the second
    // navigation can race the first's popstate handling and land on the
    // wrong history entry for a reason that has nothing to do with what
    // this test verifies.
    await page.goBack();
    await expect(page).not.toHaveURL(/\/offline$/);
    await page.goForward();
    await expect(page).toHaveURL(/\/offline$/);

    expect(consoleErrors).toEqual([]);
  });

  test('a real backend container outage redirects to /offline and auto-recovers back to the prior route, with the session still authenticated', async ({
    page,
    context,
  }) => {
    test.setTimeout(150000);
    const marker = uniqueMarker('phase34-outage');
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/dashboard');
    await expect(page.getByText(/CyberSec Assistant|System Status|Administration/i).first()).toBeVisible({
      timeout: 15000,
    });

    const backendContainer = getBackendContainer();
    dockerStop(backendContainer);
    try {
      await expect(page).toHaveURL(/\/offline$/, { timeout: 30000 });
      await expect(page.getByText(/UNREACHABLE|OFFLINE|Không thể kết nối/i).first()).toBeVisible();
    } finally {
      dockerStart(backendContainer);
    }

    await waitForBackendHealthy(90000);
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 60000 });
    // Session must still be authenticated - no forced logout, no redirect to /login.
    await expect(page).not.toHaveURL(/\/login$/);
    // Bare /health can pass before the embedding model has re-warmed after
    // the stop/start cycle above - leave the shared container fully
    // settled so the next spec file in this project's serial run doesn't
    // race that warmup for a reason unrelated to what it's testing.
    await waitForEmbeddingReady(BASE_URL);
  });

  test('browser-level offline/online is detected and recovers without a backend outage', async ({
    page,
    context,
  }) => {
    const marker = uniqueMarker('phase34-browseroffline');
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/ai');
    await expect(page.locator('textarea')).toBeVisible({ timeout: 15000 });

    await context.setOffline(true);
    await expect(page).toHaveURL(/\/offline$/, { timeout: 15000 });
    await expect(page.getByText(/No Network Connection|OFFLINE|Không có kết nối mạng/i).first()).toBeVisible();

    await context.setOffline(false);
    await expect(page).toHaveURL(/\/ai$/, { timeout: 15000 });
  });

  test('an in-progress chatbot draft survives a network outage and is never auto-sent', async ({
    page,
    context,
  }) => {
    const marker = uniqueMarker('phase34-draft');
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/ai');
    const textarea = page.locator('textarea');
    await expect(textarea).toBeVisible({ timeout: 15000 });
    await textarea.fill(`unsent draft ${marker}`);

    await context.setOffline(true);
    await expect(page).toHaveURL(/\/offline$/, { timeout: 15000 });
    await context.setOffline(false);
    await expect(page).toHaveURL(/\/ai$/, { timeout: 15000 });

    await expect(page.locator('textarea')).toHaveValue(`unsent draft ${marker}`);
    // No message was ever sent - the conversation area must not show it as a message bubble.
    await expect(page.getByText('Không tìm thấy cuộc trò chuyện phù hợp.')).toBeVisible();
  });

  test('a normal 401 is routed to /login, never to /offline', async ({ page }) => {
    // No session injected - an authenticated route should bounce to /login,
    // which is a completely different, pre-existing code path from the
    // network-recovery layer added this phase.
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login$/, { timeout: 10000 });
  });

  // Regression tests for the history corruption fixed in
  // ConnectionRecoveryProvider: a health check that fails once (in practice,
  // one aborted by the browser because the page is navigating away) used to
  // be treated as a real outage, redirecting the outgoing page to /offline
  // and leaving a phantom /offline entry behind that broke back/forward
  // afterwards. These pin the corrected behavior directly rather than only
  // observing it through the flow above.
  test('a single transient health-check failure never redirects to /offline', async ({ page, context }) => {
    // A real session is required: an unauthenticated route bounces to
    // /login, which is exempt from the recovery redirect entirely and so
    // could not detect this regression at all.
    const session = mintTestSession(`${uniqueMarker('transient-probe')}@example.test`);
    await injectSession(context, session);

    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15000 });

    // Fail exactly one health probe, exactly as a navigation-aborted fetch
    // rejects, then let everything succeed again.
    let failed = 0;
    await page.route('**/api/system/health', async (route) => {
      if (failed === 0) {
        failed += 1;
        return route.abort('failed');
      }
      return route.fallback();
    });

    await page.waitForTimeout(6000);
    // One blip must not have moved the user off their page.
    expect(failed).toBe(1);
    await expect(page).not.toHaveURL(/\/offline$/);
  });

  test('a sustained outage still redirects to /offline and leaves history uncorrupted', async ({ page, context }) => {
    const session = mintTestSession(`${uniqueMarker('sustained-outage')}@example.test`);
    await injectSession(context, session);

    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15000 });

    // Every probe fails: this is a real outage and must reach /offline.
    await page.route('**/api/system/health', (route) => route.abort('failed'));
    await expect(page).toHaveURL(/\/offline$/, { timeout: 20000 });

    // The involuntary redirect replaced rather than pushed, so the phantom
    // entry that used to break back/forward is never created: going back
    // lands on whatever preceded /dashboard, never on /offline again.
    await page.unroute('**/api/system/health');
    await page.getByRole('button', { name: /THỬ LẠI KẾT NỐI|THá»¬ Láº I Káº¾T Ná»I|Retry/i }).click();
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 20000 });
    await page.goBack();
    await expect(page).not.toHaveURL(/\/offline$/);
  });

  test('a bfcache restore (pageshow persisted) revalidates instead of showing frozen state', async ({ page }) => {
    await waitForBackendHealthy();
    await waitForEmbeddingReady(BASE_URL);
    await page.goto('/offline');
    await page.goto('/login');
    await page.goBack();
    await expect(page).toHaveURL(/\/offline$/);

    // However the browser served this page (bfcache or a fresh load), the
    // recovery page must be reporting a live result, not whatever it was
    // frozen with - the backend is healthy here, so it must say so.
    await expect(page.getByText('Backend', { exact: false })).toBeVisible({ timeout: 15000 });
    const healthChecks = page.getByText('healthy', { exact: false }).first();
    await expect(healthChecks).toBeVisible({ timeout: 15000 });
  });
});
