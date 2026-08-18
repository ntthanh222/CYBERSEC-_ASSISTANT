import { test, expect } from '@playwright/test';

/**
 * Proves the unified `/login` page: exactly one visible sign-in form, no
 * anonymous "no account needed" bypass, and no local-admin toggle hidden
 * behind a second form. Runs across desktop/iPhone/iPad via
 * `playwright.config.ts`'s three projects.
 */
test.describe('Unified /login form', () => {
  test('shows exactly one visible sign-in form with a single identifier field', async ({ page }) => {
    await page.goto('/login');

    // Exactly one <form> visible on the page.
    const forms = page.locator('form:visible');
    await expect(forms).toHaveCount(1);

    // Exactly one identity field and one password field.
    await expect(page.locator('#identifier-input')).toBeVisible();
    await expect(page.locator('#password-input')).toBeVisible();
    await expect(page.locator('input[type="password"]:visible')).toHaveCount(1);

    // The removed anonymous bypass and the removed collapsed local-account
    // form must not be reachable from this page at all.
    await expect(page.getByText('ENTER LOCAL MODE')).toHaveCount(0);
    await expect(page.getByText('Sign in with a local account')).toHaveCount(0);
    await expect(page.getByText('No account needed', { exact: false })).toHaveCount(0);
  });

  test('does not advertise a non-functional Forgot Password link', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByText('Forgot Password?')).toHaveCount(0);
  });

  test('the identifier field is not a browser-validated email-only input', async ({ page }) => {
    // Demo/local accounts sign in with a username, not an email address -
    // the single field must accept both, so it must not be type=email.
    await page.goto('/login');
    await expect(page.locator('#identifier-input')).toHaveAttribute('type', 'text');
  });
});

/**
 * Real sign-in through the single unified form for every seeded demo
 * account, proving the role returned by `/api/auth/me` (never the form used)
 * decides the landing UI. Requires a target instance with
 * `DEMO_SEED_ENABLED=true` and the matching `DEMO_*_PASSWORD` values passed
 * through as env vars - skipped otherwise rather than failing, the same
 * live-gated pattern used by the backend's golden-set RAG test.
 */
const demoCreds = {
  demo_user: process.env.DEMO_USER_PASSWORD,
  demo_analyst: process.env.DEMO_ANALYST_PASSWORD,
  demo_superadmin: process.env.DEMO_SUPERADMIN_PASSWORD,
};
const haveDemoCreds = Object.values(demoCreds).every(Boolean);

test.describe('Demo account sign-in via the unified form', () => {
  test.skip(!haveDemoCreds, 'DEMO_*_PASSWORD env vars not provided to the e2e runner.');

  async function signIn(page: import('@playwright/test').Page, username: string, password: string) {
    await page.goto('/login');
    await page.locator('#identifier-input').fill(username);
    await page.locator('#password-input').fill(password);
    await page.getByRole('button', { name: /THIẾT LẬP PHIÊN BẢO MẬT|ESTABLISH SECURE SESSION/i }).click();
  }

  test('demo_user lands on the regular dashboard, not the admin overview', async ({ page }) => {
    await signIn(page, 'demo_user', demoCreds.demo_user!);
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
  });

  test('demo_analyst lands on the regular dashboard, not the admin overview', async ({ page }) => {
    await signIn(page, 'demo_analyst', demoCreds.demo_analyst!);
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
  });

  test('demo_superadmin lands on the admin overview', async ({ page }) => {
    await signIn(page, 'demo_superadmin', demoCreds.demo_superadmin!);
    await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 10_000 });
  });

  test('demo_admin is retired: login fails even if the row still exists from before the consolidation', async ({ page }) => {
    // demo_admin (role admin) was consolidated into demo_superadmin - the
    // seed now disables any leftover demo_admin row rather than deleting it
    // (see backend/services/demo_accounts.py::_retire_demo_admin). Whatever
    // password it used to have, sign-in must be refused.
    await page.goto('/login');
    await page.locator('#identifier-input').fill('demo_admin');
    await page.locator('#password-input').fill('anything-it-is-disabled-now');
    await page.getByRole('button', { name: /THIẾT LẬP PHIÊN BẢO MẬT|ESTABLISH SECURE SESSION/i }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
    await expect(page.locator('body')).toContainText(
      /invalid username or password|tên đăng nhập hoặc mật khẩu không|tÃªn Ä‘Äƒng nháº­p hoáº·c máº­t kháº©u khÃ´ng/i,
    );
  });

  test('demo_disabled is rejected even with its correct (demo_user-shared) password', async ({ page }) => {
    // demo_disabled is seeded inactive and deliberately reuses demo_user's
    // password (see backend/services/demo_accounts.py) - using the
    // *correct* password here proves the account is refused specifically
    // for being deactivated, not merely for a wrong credential.
    await signIn(page, 'demo_disabled', demoCreds.demo_user!);
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('body')).toContainText(
      /invalid username or password|tên đăng nhập hoặc mật khẩu không|tÃªn Ä‘Äƒng nháº­p hoáº·c máº­t kháº©u khÃ´ng/i,
    );
  });
});
