/**
 * Runs once before the whole Desktop E2E suite. The backend now warms the
 * embedding model in the background on its own startup (see
 * backend/main.py's _warmup_embedding_model), but that warmup and the
 * container reporting "healthy" both start around the same time - a suite
 * that starts running immediately can still race a genuinely fresh
 * container's first embedding-touching test against a still-warming model.
 *
 * Rather than let whichever spec happens to run first pay that cost
 * (previously the accessibility spec's alphabetical-first upload test -
 * the actual root cause of this suite's historical flakiness), block here
 * until the backend reports `embedding.status === 'ready'` (or genuinely
 * `failed`, which is also a terminal state a test can proceed against and
 * observe honestly). A bounded wait exists so a truly wedged backend
 * fails *this setup step* loudly instead of hanging forever - it does
 * NOT fall through to running the suite anyway on timeout, since that
 * would silently reintroduce the exact cold-start race this file exists
 * to eliminate.
 */
import type { FullConfig } from '@playwright/test';

const POLL_INTERVAL_MS = 2000;
const MAX_WAIT_MS = 10 * 60 * 1000; // extended wait to handle slower embedding warmup

async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use?.baseURL ?? process.env.E2E_BASE_URL ?? 'http://localhost:3000';
  const backendHealthURL = process.env.E2E_BACKEND_URL ?? 'http://localhost:8000';
  const deadline = Date.now() + MAX_WAIT_MS;

  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      const response = await fetch(`${backendHealthURL}/api/system/health`);
      if (response.ok) {
        const body = await response.json();
        const status = body?.embedding?.status;
        if (status === 'ready' || status === 'failed') {
          console.log(`[global-setup] embedding readiness: ${status} - proceeding with the suite.`);
          return;
        }
        console.log(`[global-setup] embedding readiness: ${status ?? 'unknown'} - waiting...`);
      }
    } catch {
      console.log('[global-setup] backend not reachable yet - waiting...');
    }
    if (Date.now() > deadline) {
      throw new Error(
        `[global-setup] embedding readiness did not reach 'ready'/'failed' within ${MAX_WAIT_MS}ms - ` +
          'refusing to start the suite against a still-warming (or unreachable) backend, since that ' +
          'would just reintroduce the cold-start race this file exists to eliminate.',
      );
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

export default globalSetup;
