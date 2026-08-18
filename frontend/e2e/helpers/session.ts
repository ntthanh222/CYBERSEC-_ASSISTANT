import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { BrowserContext } from '@playwright/test';

// The compose project directory name (and therefore the container name
// `<project>-backend-1`) varies by checkout - worktrees in particular each
// get their own directory name. Resolve the live container via `docker
// compose ps` from the repo root instead of hardcoding any one checkout's
// name, so this works unmodified on a fresh clone or any worktree.
function resolveBackendContainer(): string {
  if (process.env.E2E_BACKEND_CONTAINER) return process.env.E2E_BACKEND_CONTAINER;
  const repoRoot = fileURLToPath(new URL('../../..', import.meta.url));
  const id = execFileSync('docker', ['compose', 'ps', '-q', 'backend'], {
    cwd: repoRoot,
    encoding: 'utf-8',
  }).trim();
  if (!id) {
    throw new Error(
      '[e2e] could not resolve the running backend container via `docker compose ps -q backend` - ' +
        'is the stack up? Set E2E_BACKEND_CONTAINER to override.',
    );
  }
  return id;
}

export function getBackendContainer(): string {
  return resolveBackendContainer();
}
// The Docker one-command build never has a frontend/.env (that's the whole
// point - see docker-local-one-command work), so VITE_SUPABASE_URL/KEY are
// never baked into the bundle and the real supabase-js client is never
// instantiated. Writing into its expected localStorage key would sit there
// unread. Use the app's own Local Mode session format instead (see
// frontend/src/lib/supabase/authService.ts) - the same storage this
// project's "Enter Local Mode" button itself writes.
const STORAGE_KEY = 'cybersec_local_session';

export interface TestSession {
  userId: string;
  email: string;
  accessToken: string;
  expiresAt: number;
}

function sleepSync(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/**
 * Mints a test-safe, backend-verifiable session by running the repository's
 * own uat_mint_test_session helper inside the real backend container (same
 * legacy-HS256 path proven in backend/tests/test_auth.py). No live GoTrue
 * involved - see PHASE_2_7A_RELEASE_HARDENING_REPORT.md for why.
 */
export function mintTestSession(email: string): TestSession {
  let raw = '';
  let lastError: unknown;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const backendContainer = resolveBackendContainer();
      raw = execFileSync(
        'docker',
        ['exec', backendContainer, 'python', '-m', 'backend.scripts.uat_mint_test_session', '--email', email],
        { encoding: 'utf-8' },
      );
      lastError = null;
      break;
    } catch (error) {
      lastError = error;
      sleepSync(1000);
    }
  }
  if (lastError) throw lastError;
  const parsed = JSON.parse(raw.trim().split('\n').pop()!);
  return {
    userId: parsed.user_id,
    email: parsed.email,
    accessToken: parsed.access_token,
    expiresAt: parsed.expires_at,
  };
}

/**
 * Writes `session` into the browser's localStorage in the app's own Local
 * Mode session shape (see authService.ts's LocalSession), so the app boots
 * already-authenticated without driving the "Enter Local Mode" button or a
 * live GoTrue - same backend-verifiable HS256 token either path produces.
 */
export async function injectSession(context: BrowserContext, session: TestSession): Promise<void> {
  const value = JSON.stringify({
    access_token: session.accessToken,
    expires_at: session.expiresAt,
    user: {
      id: session.userId,
      email: session.email,
      created_at: new Date().toISOString(),
    },
  });
  await context.addInitScript(
    ({ key, val }) => {
      window.localStorage.setItem(key, val);
    },
    { key: STORAGE_KEY, val: value },
  );
}

/**
 * Blocks until the backend reports `embedding.status` as 'ready' or
 * 'failed' (a terminal state either way), the same criterion global-setup.ts
 * uses before the whole suite starts. Every spec that restarts or stops/
 * starts the shared backend container (local-docker-one-command.spec.ts,
 * offline-recovery.spec.ts, resilience.spec.ts) must call this before
 * finishing, not just wait for bare /health - otherwise the NEXT test in
 * this project's serial (workers: 1) run can start while the embedding
 * model is still mid-warmup (~20-30s), see a transient degraded/offline
 * state through no fault of its own, and fail for a reason that has
 * nothing to do with what it's actually testing.
 */
export async function waitForEmbeddingReady(baseURL: string, timeoutMs = 60000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseURL}/api/system/health`);
      if (res.ok) {
        const body = await res.json();
        const status = body?.embedding?.status;
        if (status === 'ready' || status === 'failed') return;
      }
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`[e2e] embedding readiness did not settle within ${timeoutMs}ms after a container restart`);
}

export function uniqueMarker(prefix = 'phase27a'): string {
  return `${prefix}-${crypto.randomUUID().slice(0, 12)}`;
}
