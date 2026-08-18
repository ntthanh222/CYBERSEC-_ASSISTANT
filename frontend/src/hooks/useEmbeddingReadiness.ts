import { useEffect, useRef, useState } from 'react';

export type EmbeddingReadinessStatus = 'not_started' | 'warming' | 'ready' | 'failed' | 'unknown';

export interface EmbeddingReadiness {
  status: EmbeddingReadinessStatus;
  elapsedSeconds: number | null;
}

const POLL_INTERVAL_MS = 3000;
// Bounded: stop polling automatically after this long so a genuinely wedged
// backend degrades to "unknown" instead of polling forever - matches the
// "retry phải có giới hạn" requirement. The model itself has been observed
// taking up to ~90s cold; this leaves real margin above that.
const MAX_POLL_MS = 5 * 60 * 1000;

/**
 * Polls `/api/system/health`'s `embedding` field so the UI can show a clear
 * "AI model initializing" state instead of letting a slow first
 * upload/chat request look like a hang. This is a public infra endpoint -
 * no auth required, and it must work even before Local Mode sign-in so
 * headers stay minimal on purpose.
 */
export function useEmbeddingReadiness(): EmbeddingReadiness {
  const [state, setState] = useState<EmbeddingReadiness>({ status: 'not_started', elapsedSeconds: null });
  const startedAtRef = useRef(Date.now());

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      if (cancelled) return;
      if (Date.now() - startedAtRef.current > MAX_POLL_MS) {
        setState((prev) => (prev.status === 'ready' ? prev : { status: 'unknown', elapsedSeconds: prev.elapsedSeconds }));
        return;
      }
      try {
        const response = await fetch('/api/system/health');
        if (!response.ok) throw new Error('non-200');
        const body = await response.json();
        const embedding = body?.embedding;
        if (cancelled) return;
        const status: EmbeddingReadinessStatus = embedding?.status ?? 'unknown';
        setState({ status, elapsedSeconds: embedding?.elapsed_seconds ?? null });
        if (status === 'ready' || status === 'failed') return; // stop polling
      } catch {
        if (cancelled) return;
        setState((prev) => ({ status: prev.status === 'not_started' ? 'unknown' : prev.status, elapsedSeconds: prev.elapsedSeconds }));
      }
      if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return state;
}
