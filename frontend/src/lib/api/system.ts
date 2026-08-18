import { apiGet, NetworkUnavailableError } from './client';

export type DependencyStatus = 'healthy' | 'degraded' | 'unavailable' | 'unknown';

export interface DependencyCheck {
  status: DependencyStatus;
  latency_ms: number | null;
}

export interface SystemHealthResponse {
  status: DependencyStatus;
  timestamp: string;
  request_id: string | null;
  checks: {
    backend: DependencyCheck;
    database: DependencyCheck;
    redis: DependencyCheck;
    migration: DependencyCheck;
    pgvector: DependencyCheck;
    local_auth_secret: DependencyCheck;
  };
  embedding: {
    status: 'not_started' | 'warming' | 'ready' | 'failed';
    elapsed_seconds: number | null;
    error: string | null;
  };
}

/**
 * `/api/system/health` is a public, unauthenticated readiness endpoint (see
 * `useEmbeddingReadiness`, which already calls it via a raw `fetch` for the
 * same reason) - it must work before login, and even with no session at
 * all, so the connection-recovery layer can tell the difference between
 * "not logged in" and "backend unreachable." Going through `apiGet` (which
 * requires a token via `authFetch`) would make every check fail with an
 * auth error whenever there's no session, misreporting a healthy backend
 * as unreachable.
 */
export async function getSystemHealth(signal?: AbortSignal): Promise<SystemHealthResponse> {
  let response: Response;
  try {
    response = await fetch('/api/system/health', { signal });
  } catch (cause) {
    throw new NetworkUnavailableError(cause);
  }
  if (!response.ok) {
    throw new NetworkUnavailableError(new Error(`health check returned ${response.status}`));
  }
  return (await response.json()) as SystemHealthResponse;
}

export interface AiHealthResponse {
  status: 'healthy' | 'degraded';
  provider: string;
  provider_configured: boolean;
  fallback_provider: string;
  rag_ready: boolean;
  rag_documents: number;
  detail: string;
}

export function getAiHealth(): Promise<AiHealthResponse> {
  return apiGet<AiHealthResponse>('/api/system/ai-health');
}
