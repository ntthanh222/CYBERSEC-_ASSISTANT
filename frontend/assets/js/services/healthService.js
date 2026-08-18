const SYSTEM_HEALTH_ENDPOINT = "/api/system/health";
const DEFAULT_TIMEOUT_MS = 8000;

export class HealthRequestError extends Error {
  constructor(message, { cause } = {}) {
    super(message);
    this.name = "HealthRequestError";
    if (cause) {
      this.cause = cause;
    }
  }
}

/**
 * Fetches real system health data from the backend. Never fabricates a
 * healthy/degraded result: any transport failure, timeout or non-2xx
 * response is surfaced as a rejected promise so the UI can render a
 * distinct error state instead of stale or fake status.
 */
export async function fetchSystemHealth(fetchImpl, { timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetchImpl(SYSTEM_HEALTH_ENDPOINT, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new HealthRequestError(`system health request failed with status ${response.status}`);
    }

    const payload = await response.json();
    if (!payload || typeof payload.status !== "string" || typeof payload.checks !== "object") {
      throw new HealthRequestError("system health response has an unexpected shape");
    }
    return payload;
  } catch (error) {
    if (error instanceof HealthRequestError) {
      throw error;
    }
    if (error && error.name === "AbortError") {
      throw new HealthRequestError("system health request timed out", { cause: error });
    }
    throw new HealthRequestError("system health request failed", { cause: error });
  } finally {
    clearTimeout(timer);
  }
}
