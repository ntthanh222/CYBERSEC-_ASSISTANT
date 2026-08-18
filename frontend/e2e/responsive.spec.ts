import { test, expect } from '@playwright/test';
import { mintTestSession, injectSession, uniqueMarker } from './helpers/session';

const PAGES = ['/dashboard', '/ai', '/knowledge-base', '/toolkit/url-scanner', '/toolkit/password-checker', '/toolkit/cve-lookup', '/toolkit/history', '/news'];

test.describe('Responsive layout', () => {
  for (const path of PAGES) {
    test(`${path}: no horizontal overflow, no severe console errors`, async ({ page, context }) => {
      const session = mintTestSession(`${uniqueMarker()}@example.test`);
      await injectSession(context, session);

      const severeErrors: string[] = [];
      page.on('pageerror', (e) => severeErrors.push(e.message));

      await page.goto(path);
      await page.waitForTimeout(1500);

      const overflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth + 1;
      });
      expect(overflow, `${path} has horizontal overflow`).toBe(false);
      expect(severeErrors, `${path} threw uncaught errors: ${severeErrors.join('; ')}`).toHaveLength(0);
    });
  }
});

test.describe('Mobile composer reachability', () => {
  // scrollWidth-based overflow checks above pass even when a control is
  // pushed outside the viewport by a sibling that clips via
  // overflow-x-hidden, since that never grows document scrollWidth. This
  // caught two real bugs: (1) on first load at a mobile width, the AI
  // Assistant's conversation-history sidebar defaulted open (fixed 256px,
  // no responsive collapse) and pushed the chat panel off-screen; (2) the
  // chat panel and its composer textarea were flex items without
  // `min-width: 0`, so per the CSS Flexbox spec's automatic minimum size
  // rule they refused to shrink below their content's intrinsic width even
  // after the sidebar was fixed - both silently clipped by overflow-x-hidden
  // rather than ever showing as a scrollbar.
  test('a first-time mobile visit to /ai keeps the message composer on-screen', async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 }); // iPhone 14 Pro Max class width
    const session = mintTestSession(`${uniqueMarker()}@example.test`);
    await injectSession(context, session);

    await page.goto('/ai');
    await page.waitForTimeout(1500);

    const composer = page.getByPlaceholder('Hỏi CyberSec Assistant...');
    await expect(composer).toBeVisible();
    const box = await composer.boundingBox();
    expect(box, 'composer input has no bounding box').not.toBeNull();
    const viewport = page.viewportSize();
    expect(viewport).not.toBeNull();
    if (box && viewport) {
      expect(box.x, 'composer input starts outside the viewport').toBeGreaterThanOrEqual(0);
      expect(
        box.x + box.width,
        'composer input extends past the right edge of the viewport',
      ).toBeLessThanOrEqual(viewport.width + 1);
    }
  });
});
