import { expect, test, type Locator, type Page } from '@playwright/test';
import { injectSession, mintTestSession, uniqueMarker } from './helpers/session';

interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

function intersectionArea(a: Box, b: Box): number {
  const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return width * height;
}

async function visibleBoxes(locator: Locator): Promise<Box[]> {
  return locator.evaluateAll((elements) =>
    elements
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        };
      })
      .filter((rect) => rect.width > 1 && rect.height > 1),
  );
}

async function expectNoNodeOverlap(page: Page) {
  let boxes: Box[] = [];
  const nodeLocator = page.locator('[data-testid^="attack-node-"]:not([data-testid^="attack-node-label-"]):visible');
  await expect.poll(async () => {
    boxes = await visibleBoxes(nodeLocator);
    return boxes.length;
  }, {
    timeout: 10_000,
  }).toBeGreaterThanOrEqual(5);
  expect(boxes.length).toBeGreaterThanOrEqual(5);
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      expect(intersectionArea(boxes[i], boxes[j]), `node ${i} overlaps node ${j}`).toBe(0);
    }
  }
}

async function expectLabelsFit(page: Page) {
  // .attack-node-title uses -webkit-line-clamp:2, which intentionally caps
  // clientHeight at two lines while scrollHeight still reports the full
  // (unclamped) content height of any text that wraps to 3+ lines - that's
  // the clamp working as designed (nothing is visibly cut off mid-line, the
  // browser paints exactly two lines and hides the rest), not an overflow
  // bug. Only clientWidth truncation and clamped elements' *own* box height
  // exceeding its line-clamp budget would indicate a real layout defect.
  const overflows = await page.locator('[data-testid^="attack-node-label-"]').evaluateAll((labels) =>
    labels
      .map((label) => {
        const isClamped = getComputedStyle(label).webkitLineClamp !== 'none';
        return {
          text: label.textContent ?? '',
          scrollWidth: label.scrollWidth,
          clientWidth: label.clientWidth,
          scrollHeight: label.scrollHeight,
          clientHeight: label.clientHeight,
          isClamped,
        };
      })
      .filter(
        (label) =>
          label.scrollWidth > label.clientWidth + 1 ||
          (!label.isClamped && label.scrollHeight > label.clientHeight + 2),
      ),
  );
  expect(overflows, `node label overflow: ${JSON.stringify(overflows)}`).toEqual([]);
}

async function expectEdgeLabelsDoNotCoverNodes(page: Page) {
  const result = await page.evaluate(() => {
    const nodeRects = Array.from(document.querySelectorAll('[data-testid^="attack-node-"]'))
      .filter((element) => !element.getAttribute('data-testid')?.startsWith('attack-node-label-'))
      .map((element) => element.getBoundingClientRect());
    const labelRects = Array.from(document.querySelectorAll('.react-flow__edge-textbg')).map((element) => element.getBoundingClientRect());
    return labelRects.flatMap((label, labelIndex) =>
      nodeRects
        .map((node, nodeIndex) => {
          const width = Math.max(0, Math.min(label.right, node.right) - Math.max(label.left, node.left));
          const height = Math.max(0, Math.min(label.bottom, node.bottom) - Math.max(label.top, node.top));
          return { labelIndex, nodeIndex, area: width * height };
        })
        .filter((item) => item.area > 24),
    );
  });
  expect(result, `edge label over node bounds: ${JSON.stringify(result)}`).toEqual([]);
}

async function expectGraphInsideCanvas(page: Page) {
  const canvas = await page.getByTestId('attack-graph-canvas').boundingBox();
  expect(canvas).not.toBeNull();
  if (canvas!.width < 1000) {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    return;
  }
  const boxes = await visibleBoxes(page.locator('[data-testid^="attack-node-"]:not([data-testid^="attack-node-label-"]):visible'));
  const union = boxes.reduce(
    (acc, box) => ({
      left: Math.min(acc.left, box.left),
      top: Math.min(acc.top, box.top),
      right: Math.max(acc.right, box.right),
      bottom: Math.max(acc.bottom, box.bottom),
      width: 0,
      height: 0,
    }),
    { left: Number.POSITIVE_INFINITY, top: Number.POSITIVE_INFINITY, right: 0, bottom: 0, width: 0, height: 0 },
  );
  expect(union.left).toBeGreaterThanOrEqual(canvas!.x - 8);
  expect(union.top).toBeGreaterThanOrEqual(canvas!.y - 8);
  expect(union.right).toBeLessThanOrEqual(canvas!.x + canvas!.width + 8);
  expect(union.bottom).toBeLessThanOrEqual(canvas!.y + canvas!.height + 8);
  expect(union.right - union.left).toBeGreaterThan(canvas!.width * 0.35);
}

test.describe('Attack Graph visual layout regression', () => {
  test('seeded graph auto-layout avoids node and label overlap across CRUD and reload', async ({ page, context, request }) => {
    const session = mintTestSession(`${uniqueMarker('attack-graph')}@example.test`);
    await injectSession(context, session);

    const authHeaders = { Authorization: `Bearer ${session.accessToken}` };
    const nodes = [
      { label: 'External Attacker', node_type: 'attacker', status: 'secure', severity: 'high', ip_address: '198.51.100.42' },
      { label: 'Initial Access via VPN Valid Accounts T1078', node_type: 'asset', status: 'vulnerable', severity: 'critical', ip_address: 'vpn.corp.local' },
      { label: 'Execution on Corp Web 01 with long-but-readable hostname', node_type: 'asset', status: 'compromised', severity: 'high', ip_address: '10.20.30.41' },
      { label: 'Privilege Escalation Database Credential Store', node_type: 'database', status: 'vulnerable', severity: 'high', ip_address: '10.20.40.12' },
      { label: 'T1078 Valid Accounts Initial Access Technique', node_type: 'gateway', status: 'vulnerable', severity: 'medium', ip_address: '' },
      { label: 'Target Incident Customer Data Exposure', node_type: 'target', status: 'compromised', severity: 'critical', ip_address: '' },
    ] as const;

    const created = [];
    for (const node of nodes) {
      const response = await request.post('/api/attack-graph/nodes', {
        headers: authHeaders,
        data: { ...node, position_x: 0, position_y: 0 },
      });
      expect(response.ok()).toBeTruthy();
      created.push(await response.json());
    }

    const edges = [
      [0, 1, 'initial access'],
      [1, 2, 'valid accounts'],
      [2, 3, 'credential access'],
      [3, 5, 'impact path'],
      [2, 4, 'MITRE mapping'],
      [4, 5, 'technique supports incident'],
    ] as const;
    for (const [source, target, label] of edges) {
      const response = await request.post('/api/attack-graph/edges', {
        headers: authHeaders,
        data: {
          source_node_id: created[source].id,
          target_node_id: created[target].id,
          label,
          status: 'active',
        },
      });
      expect(response.ok()).toBeTruthy();
    }

    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto('/attack-graph');
    await expect(page.getByTestId('attack-graph-canvas')).toBeVisible({ timeout: 10_000 });
    await expectNoNodeOverlap(page);
    await expectLabelsFit(page);
    await expectEdgeLabelsDoNotCoverNodes(page);
    await expectGraphInsideCanvas(page);

    await page.getByRole('button', { name: /Tự sắp xếp/i }).click();
    await expectNoNodeOverlap(page);

    const label = `Additional pivot ${Date.now()}`;
    await page.getByPlaceholder('Tên node').fill(label);
    await page.getByPlaceholder('IP / host').fill('10.20.50.77');
    await page.getByRole('button', { name: /^Node$/i }).click();
    await expect(page.locator('[data-testid^="attack-node-label-"]').filter({ hasText: label })).toBeVisible({ timeout: 10_000 });
    await expectNoNodeOverlap(page);
    await expectLabelsFit(page);

    await page.locator('select').nth(2).selectOption(created[1].id);
    await page.locator('select').nth(3).selectOption(created[2].id);
    await page.getByPlaceholder('Tên đường liên kết').fill('parallel verification relation');
    const edgeResponse = page.waitForResponse((response) => response.url().includes('/api/attack-graph/edges') && response.request().method() === 'POST');
    await page.getByRole('button', { name: /Thêm liên kết/i }).click();
    expect((await edgeResponse).ok()).toBeTruthy();
    await expectNoNodeOverlap(page);
    await expectEdgeLabelsDoNotCoverNodes(page);

    await page.reload();
    await expect(page.getByTestId('attack-graph-canvas')).toBeVisible({ timeout: 10_000 });
    await expectNoNodeOverlap(page);

    const seriousErrors = consoleErrors.filter((msg) => !msg.includes('Fast Refresh') && !msg.includes('DevTools'));
    expect(seriousErrors, `Unexpected console errors: ${seriousErrors.join('\n')}`).toEqual([]);
  });
});
