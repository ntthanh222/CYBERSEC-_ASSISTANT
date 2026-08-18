import { test, expect, type Page } from '@playwright/test';

const demoSuperadminPassword = process.env.DEMO_SUPERADMIN_PASSWORD;
const demoUserPassword = process.env.DEMO_USER_PASSWORD;
const haveDemoCreds = Boolean(demoSuperadminPassword && demoUserPassword);

async function signIn(page: Page, username: string, password: string): Promise<void> {
  await page.goto('/login');
  await page.locator('#identifier-input').fill(username);
  await page.locator('#password-input').fill(password);
  await page.locator('form button[type="submit"]').click();
}

test.describe('Classroom demo rehearsal — simplified product', () => {
  test.skip(!haveDemoCreds, 'DEMO_SUPERADMIN_PASSWORD/DEMO_USER_PASSWORD not provided to the e2e runner.');

  test('login -> dashboard -> website check -> SSRF block -> password -> CVE -> AI -> news -> history -> control console', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    // 1. Login as super admin — the account this rehearsal exercises the
    // admin-only Control Console with.
    await signIn(page, 'demo_superadmin', demoSuperadminPassword!);
    await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 10_000 });

    // 2. Dashboard — simplified surface, no SOC-flavored placeholder content.
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'CyberSec Assistant' })).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('body')).not.toContainText('Frontend Presentation Mock View');

    // 3. Kiểm tra Website — real scan against a public domain.
    await page.goto('/toolkit/url-scanner');
    await expect(page.getByRole('heading', { name: 'Kiểm tra Website' })).toBeVisible({ timeout: 10_000 });
    const urlInput = page.locator('#url-input');
    await urlInput.fill('https://example.com');
    await page.getByRole('button', { name: 'QUÉT' }).click();
    await expect(page.getByText('example.com', { exact: false })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('Điểm rủi ro', { exact: false })).toBeVisible();

    // 4. SSRF protection — cloud metadata address must be blocked, not
    // silently requested by the backend. The scanner swaps the input form
    // for the result card after a scan, so clear it first to get the
    // input back.
    await page.getByRole('button', { name: 'Xóa kết quả' }).click();
    await urlInput.fill('http://169.254.169.254');
    await page.getByRole('button', { name: 'QUÉT' }).click();
    await expect(
      page.getByText(/không thể|đã chặn|chặn/i).first(),
    ).toBeVisible({ timeout: 20_000 });

    // 5. Kiểm tra Mật khẩu — weak input scores low, no password ever leaves
    // as anything other than the /api/tools/password-strength POST body.
    await page.goto('/toolkit/password-checker');
    await expect(page.getByRole('heading', { name: 'Kiểm tra Mật khẩu' })).toBeVisible({ timeout: 10_000 });
    const passwordInput = page.locator('#pass-checker-input');
    await passwordInput.fill('123456');
    await expect(page.getByText(/rất yếu|yếu/i).first()).toBeVisible({ timeout: 10_000 });

    // 6. Tra cứu CVE — real NVD-backed lookup via the Log4Shell shortcut.
    await page.goto('/toolkit/cve-lookup');
    await expect(page.getByRole('heading', { name: 'Tra cứu CVE' })).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: 'Log4Shell' }).click();
    await expect(page.getByText('CVE-2021-44228').first()).toBeVisible({ timeout: 20_000 });

    // 7. AI Assistant — general cybersecurity Q&A, real backend response.
    await page.goto('/ai');
    const composer = page.getByPlaceholder('Hỏi CyberSec Assistant...');
    await composer.fill('SQL Injection là gì và cách phòng chống?');
    await composer.press('Enter');
    await expect(page.getByText(/sql injection/i).first()).toBeVisible({ timeout: 30_000 });

    // 8. Tin tức Bảo mật — read-first feed, no manual-create form on the
    // normal user-facing page (that moved to Control Console → Crawler).
    await page.goto('/news');
    await expect(page.getByRole('heading', { name: 'Tin tức Bảo mật' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByPlaceholder('Tiêu đề bài viết')).toHaveCount(0);
    await expect(page.getByLabel('Tìm kiếm tin tức')).toBeVisible();

    // 9. Lịch sử Kiểm tra — the website/CVE lookups above must be recorded,
    // and the password check above must NOT appear anywhere in it. The view
    // renders both a desktop table and a mobile card list for the same
    // rows (only one visible per breakpoint) - filter to the visible match
    // so this doesn't depend on viewport width.
    await page.goto('/toolkit/history');
    await expect(page.getByRole('heading', { name: 'Lịch sử Kiểm tra' })).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText('example.com', { exact: false }).filter({ visible: true }).first(),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('body')).not.toContainText('123456');

    // 10. Control Console — admin-only, still gated.
    await page.goto('/admin/overview');
    await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 10_000 });

    const seriousErrors = consoleErrors.filter(
      (msg) =>
        !msg.includes('Fast Refresh') &&
        !msg.includes('DevTools') &&
        // The browser logs the SSRF-blocked scan's 400 response as a resource
        // load failure — that is the backend correctly rejecting a metadata
        // address, not an application bug.
        !msg.includes('400 (Bad Request)'),
    );
    expect(seriousErrors, `Unexpected console errors during rehearsal: ${seriousErrors.join('\n')}`).toEqual([]);

    // 11. RBAC — a disabled account must still be denied login outright.
    await signIn(page, 'demo_disabled', demoUserPassword!);
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('normal user cannot reach Control Console', async ({ page }) => {
    test.skip(!demoUserPassword, 'DEMO_USER_PASSWORD not provided to the e2e runner.');
    await signIn(page, 'demo_user', demoUserPassword!);
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
    await page.goto('/admin/overview');
    await expect(page).toHaveURL(/\/access-denied/, { timeout: 10_000 });
  });

  // ToolkitLayout previously rendered its own tab row for Website/Password/
  // CVE/History that duplicated the AppShell sidebar - each toolkit page
  // showed the same four links twice. This asserts the DOM, not just a
  // screenshot: exactly one "Kiểm tra Mật khẩu" link should exist anywhere
  // on a toolkit page (the sidebar's), never a second row inside <main>.
  test('toolkit pages have no duplicate inner navigation', async ({ page }) => {
    test.skip(!demoUserPassword, 'DEMO_USER_PASSWORD not provided to the e2e runner.');
    await signIn(page, 'demo_user', demoUserPassword!);
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });

    for (const [path, linkName] of [
      ['/toolkit/url-scanner', 'Kiểm tra Website'],
      ['/toolkit/password-checker', 'Kiểm tra Mật khẩu'],
      ['/toolkit/cve-lookup', 'Tra cứu CVE'],
      ['/toolkit/history', 'Lịch sử Kiểm tra'],
    ] as const) {
      await page.goto(path);
      // On narrow viewports the sidebar is a hamburger-triggered drawer that
      // doesn't exist in the DOM at all until opened (see AppShell.tsx) - on
      // desktop/tablet it's already visible, but render/hydration after
      // goto() is not instant (especially under sustained suite load), so a
      // single synchronous count() right after navigation can race a sidebar
      // that hasn't painted yet. Give the toggle-button fallback path a real
      // wait instead of assuming absence means "must be a drawer".
      let navLink = page.locator('nav a', { hasText: linkName }).filter({ visible: true });
      const toggleButton = page.getByRole('button', { name: /Toggle Navigation Menu|Chuy/i }).first();
      await expect(navLink.or(toggleButton)).toBeVisible({ timeout: 10_000 });
      if ((await navLink.count()) === 0) {
        await toggleButton.click();
        navLink = page.locator('nav a', { hasText: linkName }).filter({ visible: true });
      }
      await expect(navLink).toHaveCount(1);
      // The content area (<main>) must never contain its own nav landmark
      // duplicating the sidebar's links.
      await expect(page.locator('main nav')).toHaveCount(0);
    }
  });

  // Manual news-create form: admin-only, both in the UI and enforced by the
  // backend if a normal user calls the API directly.
  test('manual news create form is admin-only, backend enforces it', async ({ page, request }) => {
    test.skip(!haveDemoCreds, 'DEMO_SUPERADMIN_PASSWORD/DEMO_USER_PASSWORD not provided to the e2e runner.');

    await signIn(page, 'demo_user', demoUserPassword!);
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
    await page.goto('/news');
    await expect(page.getByPlaceholder('Tiêu đề bài viết')).toHaveCount(0);
    await expect(page.getByText('Quản lý nguồn tin')).toHaveCount(0);

    const token = await page.evaluate(() => {
      const raw = localStorage.getItem('cybersec_local_session');
      return raw ? JSON.parse(raw).access_token : null;
    });
    expect(token).toBeTruthy();
    const denied = await request.post('/api/news', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title: 'Should be rejected',
        summary: 'Attempted direct API call by a non-admin.',
        url: 'https://example.com/should-not-be-created',
        source: 'e2e-test',
        published_at: new Date().toISOString(),
      },
    });
    expect(denied.status()).toBe(403);

    await signIn(page, 'demo_superadmin', demoSuperadminPassword!);
    await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 10_000 });
    await page.goto('/admin/crawler');
    await expect(page.getByPlaceholder('Tiêu đề bài viết')).toBeVisible({ timeout: 10_000 });
  });
});
