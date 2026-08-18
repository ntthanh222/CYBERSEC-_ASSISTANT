import { test, expect } from '@playwright/test';
import { mintTestSession, injectSession, uniqueMarker } from './helpers/session';
import { buildTextPdf } from './helpers/pdf';

test.describe('Knowledge Base journey', () => {
  test('upload a Vietnamese TXT document, reach READY, and retrieve it by content', async ({ page, context }) => {
    test.setTimeout(120000);
    const marker = uniqueMarker();
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/knowledge-base');
    await expect(page.getByRole('heading', { name: 'Knowledge Base' })).toBeVisible();

    const content = `# Tài liệu kiểm thử ${marker}\n\nĐây là tài liệu tiếng Việt dùng để kiểm thử luồng tải lên và truy xuất của Knowledge Base trong Phase 2.7A. Mã định danh duy nhất của tài liệu này là ${marker}. Hệ thống nên trả lời chính xác câu hỏi liên quan đến mã định danh này.\n\n## Phần bổ sung\n\nĐoạn văn bổ sung để đảm bảo tài liệu đủ dài cho việc chia đoạn (chunking) hoạt động với hơn một đoạn.`;

    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}.md`,
      mimeType: 'text/markdown',
      buffer: Buffer.from(content, 'utf-8'),
    });

    const row = page.locator('tbody tr', { hasText: `${marker}.md` });
    await expect(row).toBeVisible({ timeout: 90000 });
    await expect(row.getByText('READY').or(row.getByText('SẴN SÀNG'))).toBeVisible({ timeout: 20000 });

    const chunkCountText = await row.locator('td').nth(3).innerText();
    expect(Number(chunkCountText)).toBeGreaterThan(0);

    await page.getByPlaceholder('Nhập câu hỏi để xem chatbot sẽ truy xuất được gì...').fill(
      `Mã định danh ${marker} là gì?`,
    );
    await page.getByRole('button', { name: /XEM TRƯỚC/i }).click();
    await expect(page.getByText(new RegExp(marker)).last()).toBeVisible({ timeout: 10000 });
  });

  test('a fake-type upload (binary renamed .txt) is rejected with no phantom row', async ({ page, context }) => {
    const marker = uniqueMarker();
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/knowledge-base');
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}-fake.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x01, 0x02, 0x03]),
    });

    await expect(page.locator('.bg-critical\\/10').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('tbody tr', { hasText: `${marker}-fake.txt` })).toHaveCount(0);
  });

  test('an empty file upload is rejected', async ({ page, context }) => {
    const marker = uniqueMarker();
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/knowledge-base');
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}-empty.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(''),
    });

    await expect(page.locator('.bg-critical\\/10').first()).toBeVisible({ timeout: 10000 });
  });

  test('deleting a document removes it from the list', async ({ page, context }) => {
    test.setTimeout(120000);
    const marker = uniqueMarker();
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/knowledge-base');
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(`Delete-me test document ${marker}. Enough content to pass validation for this journey.`),
    });

    const row = page.locator('tbody tr', { hasText: `${marker}.txt` });
    await expect(row).toBeVisible({ timeout: 90000 });
    await expect(row.getByText('READY').or(row.getByText('SẴN SÀNG'))).toBeVisible({ timeout: 20000 });

    await row.getByTitle('Xóa tài liệu').click();
    await page.getByRole('button', { name: 'XÓA', exact: true }).click();
    await expect(page.locator('tbody tr', { hasText: `${marker}.txt` })).toHaveCount(0, { timeout: 10000 });
  });

  test('a multi-page text-layer PDF uploads, reaches READY, and cites the correct page', async ({ page, context }) => {
    test.setTimeout(120000);
    const marker = uniqueMarker('phase32-pdf');
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);

    await page.goto('/knowledge-base');
    const pdf = buildTextPdf([
      `Page one content, unrelated filler text for chunking purposes.`,
      `Page two content. UNIQUE MARKER ${marker} lives on this page only.`,
      `Page three content, unrelated filler text for chunking purposes.`,
    ]);
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}.pdf`,
      mimeType: 'application/pdf',
      buffer: pdf,
    });

    const row = page.locator('tbody tr', { hasText: `${marker}.pdf` });
    await expect(row).toBeVisible({ timeout: 90000 });
    await expect(row.getByText('READY').or(row.getByText('SẴN SÀNG'))).toBeVisible({ timeout: 20000 });
    const chunkCountText = await row.locator('td').nth(3).innerText();
    expect(Number(chunkCountText)).toBe(3);

    await page.getByPlaceholder('Nhập câu hỏi để xem chatbot sẽ truy xuất được gì...').fill(
      `Where does UNIQUE MARKER ${marker} appear?`,
    );
    await page.getByRole('button', { name: /XEM TRƯỚC/i }).click();
    const resultCard = page.locator('div', { hasText: new RegExp(marker) }).first();
    await expect(resultCard).toBeVisible({ timeout: 10000 });
    // The citation must name the correct page (2), not just the document.
    await expect(page.getByText(`${marker}.pdf · p.2`)).toBeVisible({ timeout: 10000 });
  });

  test('an encrypted PDF is rejected with an honest error, not silently accepted', async ({ page, context }) => {
    const marker = uniqueMarker('phase32-enc');
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);
    await page.goto('/knowledge-base');

    // A well-formed but password-protected PDF (RC4/AESV2 /Encrypt dict) -
    // pypdf must report is_encrypted=True and the service must reject it,
    // not attempt to parse text out of it.
    const encryptedPdf = Buffer.from(
      '%PDF-1.4\n1 0 obj<</Producer(t)>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[4 0 R]>>endobj\n' +
        '3 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n' +
        '4 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n' +
        '5 0 obj<</V 1/R 2/O<0000000000000000000000000000000000000000000000000000000000000000>' +
        '/U<0000000000000000000000000000000000000000000000000000000000000000>/P -4>>endobj\n' +
        'xref\n0 6\n0000000000 65535 f \ntrailer<</Size 6/Root 3 0 R/Encrypt 5 0 R>>\nstartxref\n0\n%%EOF',
      'latin1',
    );
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}.pdf`,
      mimeType: 'application/pdf',
      buffer: encryptedPdf,
    });

    await expect(page.locator('.bg-critical\\/10').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('tbody tr', { hasText: `${marker}.pdf` })).toHaveCount(0);
  });

  test('a path-traversal filename is sanitized to a safe display name, never executed as a path', async ({
    page,
    context,
  }) => {
    test.setTimeout(120000);
    const marker = uniqueMarker('phase32-trav');
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);
    await page.goto('/knowledge-base');

    await page.setInputFiles('#knowledge-upload-input', {
      name: `../../${marker}-escape.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(`Traversal filename test content ${marker}, long enough to pass validation.`),
    });

    const row = page.locator('tbody tr', { hasText: `${marker}-escape.txt` });
    await expect(row).toBeVisible({ timeout: 90000 });
    // The stored/displayed title must never contain the traversal segments.
    await expect(row).not.toContainText('..');
  });

  test('an XSS-payload filename never executes and renders as inert text', async ({ page, context }) => {
    test.setTimeout(120000);
    const marker = uniqueMarker('phase32-xss');
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);
    await page.goto('/knowledge-base');

    let dialogFired = false;
    page.on('dialog', async (dialog) => {
      dialogFired = true;
      await dialog.dismiss();
    });

    await page.setInputFiles('#knowledge-upload-input', {
      name: `<img src=x onerror=alert(1)>-${marker}.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(`XSS filename test content ${marker}, long enough to pass validation.`),
    });

    await expect(page.locator('tbody tr', { hasText: marker })).toBeVisible({ timeout: 90000 });
    expect(dialogFired).toBe(false);
  });

  test('re-uploading identical content under a different name is deduplicated, not duplicated', async ({
    page,
    context,
  }) => {
    test.setTimeout(120000);
    const marker = uniqueMarker('phase32-dup');
    const session = mintTestSession(`${marker}@example.test`);
    await injectSession(context, session);
    await page.goto('/knowledge-base');

    const content = `Duplicate content test ${marker}, long enough to pass validation checks here.`;
    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}-first.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(content),
    });
    // See resilience.spec.ts's identical comment on its own first-upload
    // wait: an embedding call can cost ~20-30s (ONNX Runtime session
    // init) even against an already-warm cache under load, and this is
    // consistently the first upload-visibility wait to run out of margin
    // deep into a full mobile-project suite run - 45s cut it too close.
    await expect(page.locator('tbody tr', { hasText: `${marker}-first.txt` })).toBeVisible({ timeout: 90000 });

    await page.setInputFiles('#knowledge-upload-input', {
      name: `${marker}-second.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(content),
    });
    await page.waitForTimeout(1500);

    // Same content, different filename: must reuse the existing document,
    // never create a second row for it.
    await expect(page.locator('tbody tr', { hasText: `${marker}-second.txt` })).toHaveCount(0);
    await expect(page.locator('tbody tr', { hasText: `${marker}-first.txt` })).toHaveCount(1);
  });

  test('one user cannot see, fetch, or retrieve another user\'s private document', async ({ browser }) => {
    test.setTimeout(120000);
    const markerA = uniqueMarker('phase32-isoA');
    const markerB = uniqueMarker('phase32-isoB');
    const sessionA = mintTestSession(`${markerA}@example.test`);
    const sessionB = mintTestSession(`${markerB}@example.test`);

    const contextA = await browser.newContext();
    await injectSession(contextA, sessionA);
    const pageA = await contextA.newPage();
    await pageA.goto('/knowledge-base');
    await pageA.setInputFiles('#knowledge-upload-input', {
      name: `${markerA}-private.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from(`Private content for user A only, marker ${markerA}, long enough for validation.`),
    });
    await expect(pageA.locator('tbody tr', { hasText: `${markerA}-private.txt` })).toBeVisible({ timeout: 90000 });
    await contextA.close();

    const contextB = await browser.newContext();
    await injectSession(contextB, sessionB);
    const pageB = await contextB.newPage();
    await pageB.goto('/knowledge-base');
    await expect(pageB.locator('tbody tr', { hasText: markerA })).toHaveCount(0);

    await pageB.getByPlaceholder('Nhập câu hỏi để xem chatbot sẽ truy xuất được gì...').fill(
      `Private content for user A only, marker ${markerA}`,
    );
    await pageB.getByRole('button', { name: /XEM TRƯỚC/i }).click();
    await expect(pageB.getByText(new RegExp(markerA))).toHaveCount(0);
    await contextB.close();
  });
});
