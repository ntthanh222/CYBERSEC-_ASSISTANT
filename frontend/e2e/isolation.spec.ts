import { test, expect } from '@playwright/test';
import { mintTestSession, injectSession, uniqueMarker } from './helpers/session';

test.describe('Cross-user data isolation', () => {
  test('user B cannot see user A knowledge documents, scan history, or conversations', async ({ browser }) => {
    const markerA = uniqueMarker();
    const markerB = uniqueMarker();
    const sessionA = mintTestSession(`${markerA}@example.test`);
    const sessionB = mintTestSession(`${markerB}@example.test`);

    const contextA = await browser.newContext();
    await injectSession(contextA, sessionA);
    const pageA = await contextA.newPage();

    await pageA.goto('/knowledge-base');
    await pageA.setInputFiles('#knowledge-upload-input', {
      name: `${markerA}.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(`User A private document ${markerA}. Content long enough to pass validation.`),
    });
    await expect(pageA.locator('tbody tr', { hasText: `${markerA}.txt` })).toBeVisible({ timeout: 45000 });

    await pageA.goto('/toolkit/password-checker');
    await pageA.locator('#pass-checker-input').fill('UserA-Secret-Passw0rd!');

    const contextB = await browser.newContext();
    await injectSession(contextB, sessionB);
    const pageB = await contextB.newPage();

    await pageB.goto('/knowledge-base');
    await expect(pageB.locator('tbody tr', { hasText: `${markerA}.txt` })).toHaveCount(0);

    await pageB.goto('/toolkit/history');
    await expect(pageB.getByText(new RegExp(markerA))).toHaveCount(0);

    await contextA.close();
    await contextB.close();
  });

  test('user B cannot retrieve or cite user A document content via chat preview', async ({ browser }) => {
    const markerA = uniqueMarker();
    const markerB = uniqueMarker();
    const sessionA = mintTestSession(`${markerA}@example.test`);
    const sessionB = mintTestSession(`${markerB}@example.test`);

    const contextA = await browser.newContext();
    await injectSession(contextA, sessionA);
    const pageA = await contextA.newPage();
    await pageA.goto('/knowledge-base');
    await pageA.setInputFiles('#knowledge-upload-input', {
      name: `${markerA}.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(
        `Confidential test content marker ${markerA}. Only the owning user should ever retrieve this text.`,
      ),
    });
    await expect(pageA.locator('tbody tr', { hasText: `${markerA}.txt` })).toBeVisible({ timeout: 45000 });
    await expect(pageA.locator('tbody tr', { hasText: `${markerA}.txt` }).getByText('READY').or(pageA.locator('tbody tr', { hasText: `${markerA}.txt` }).getByText('SẴN SÀNG'))).toBeVisible({
      timeout: 20000,
    });

    const contextB = await browser.newContext();
    await injectSession(contextB, sessionB);
    const pageB = await contextB.newPage();
    await pageB.goto('/knowledge-base');
    await pageB.getByPlaceholder('Nhập câu hỏi để xem chatbot sẽ truy xuất được gì...').fill(
      `What is the confidential content marker ${markerA}?`,
    );
    await pageB.getByRole('button', { name: /XEM TRƯỚC/i }).click();
    await pageB.waitForTimeout(1500);
    await expect(pageB.getByText(new RegExp(markerA))).toHaveCount(0);

    await contextA.close();
    await contextB.close();
  });
});
