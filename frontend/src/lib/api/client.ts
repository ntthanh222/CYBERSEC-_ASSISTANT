import { authFetch } from '../supabase/authFetch';

/**
 * Base URL for the FastAPI backend. Defaults to empty ("same origin"),
 * matching production: nginx.conf reverse-proxies /api/ to the backend
 * container, and the page's CSP (connect-src 'self') only allows same-
 * origin requests - a cross-origin default here would make every API call
 * silently CSP-blocked whenever a deployment's frontend/.env doesn't
 * explicitly override it (frontend/.env is gitignored, so a production
 * build easily has none). Set VITE_API_BASE_URL for local `npm run dev`
 * against a bare backend on a different port - see frontend/.env.example.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export class ApiError extends Error {
  status: number;
  errorCode?: string;

  constructor(status: number, message: string, errorCode?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.errorCode = errorCode;
  }
}

/**
 * A transport-level failure - the request never reached the server (or its
 * response never arrived), as opposed to `ApiError`, which means the server
 * *did* answer, just with a non-2xx status. Only this class of failure
 * should ever trigger the network-recovery UI - a normal 4xx is proof the
 * backend is reachable and must never be treated as an outage.
 */
export class NetworkUnavailableError extends Error {
  constructor(cause?: unknown) {
    super('The server could not be reached.');
    this.name = 'NetworkUnavailableError';
    if (cause instanceof Error) this.cause = cause;
  }
}

type NetworkFailureListener = () => void;
const networkFailureListeners = new Set<NetworkFailureListener>();

/** Subscribe to "a request just failed at the transport level" events, so
 * the recovery UI can react immediately instead of waiting for its next
 * poll tick. Returns an unsubscribe function. */
export function onNetworkFailure(listener: NetworkFailureListener): () => void {
  networkFailureListeners.add(listener);
  return () => networkFailureListeners.delete(listener);
}

function notifyNetworkFailure(): void {
  networkFailureListeners.forEach((listener) => listener());
}

async function parseErrorBody(response: Response): Promise<{ message: string; errorCode?: string }> {
  try {
    const body = await response.json();
    if (body && typeof body.message === 'string') {
      return { message: body.message, errorCode: body.error };
    }
  } catch {
    // Body wasn't JSON - fall through to the generic message.
  }
  return { message: `Request failed with status ${response.status}` };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await authFetch(`${API_BASE_URL}${path}`, init);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      throw cause;
    }
    // A missing/rejected session is a distinct, expected case (routed to
    // /login by existing auth handling) - never mask it as a network
    // outage. Anything else thrown here is `fetch()` itself failing at the
    // transport level (connection refused, DNS failure, CORS block,
    // offline) - a real HTTP error response (4xx/5xx) resolves normally
    // and is handled below instead.
    if (cause instanceof Error && cause.name === 'UnauthenticatedError') {
      throw cause;
    }
    notifyNetworkFailure();
    throw new NetworkUnavailableError(cause);
  }

  if (!response.ok) {
    const { message, errorCode } = await parseErrorBody(response);
    throw new ApiError(response.status, message, errorCode);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function apiGet<T>(path: string, init: RequestInit = {}): Promise<T> {
  return request<T>(path, { ...init, method: 'GET' });
}

export function apiPost<T>(path: string, body?: unknown, init: RequestInit = {}): Promise<T> {
  return request<T>(path, {
    ...init,
    method: 'POST',
    headers: body !== undefined ? { ...init.headers, 'Content-Type': 'application/json' } : init.headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiDelete<T = void>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/** POST a multipart/form-data body (file upload). Never sets Content-Type
 * itself - the browser must set it (with the correct boundary) from the
 * FormData object. */
export function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', body: form });
}
