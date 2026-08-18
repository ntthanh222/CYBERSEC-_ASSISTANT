import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { getSystemHealth } from '../api/system';
import type { SystemHealthResponse } from '../api/system';
import { onNetworkFailure } from '../api/client';

export type ConnectionStatus =
  | 'online'
  | 'checking'
  | 'offline'
  | 'backend_unreachable'
  | 'degraded'
  | 'recovering'
  | 'restored';

export interface ConnectionState {
  status: ConnectionStatus;
  checks: SystemHealthResponse['checks'] | null;
  embedding: SystemHealthResponse['embedding'] | null;
  lastCheckedAt: number | null;
  checkNow: () => void;
}

const ConnectionRecoveryContext = createContext<ConnectionState | null>(null);

export function useBackendAvailability(): ConnectionState {
  const ctx = useContext(ConnectionRecoveryContext);
  if (!ctx) {
    throw new Error('useBackendAvailability must be used within a ConnectionRecoveryProvider');
  }
  return ctx;
}

const RETURN_PATH_KEY = 'cybersec_offline_return_path';
// Routes that either don't depend on a live backend for anything meaningful,
// or already have their own honest handling of a missing connection - never
// auto-redirect away from these into the recovery page.
// /admin/login and /admin/setup are gone (redirected into /login - see
// AppRoutes.tsx), so they no longer need their own exemption entries.
const EXEMPT_PREFIXES = ['/offline', '/login', '/register'];

const MIN_POLL_MS = 4000;
const MAX_POLL_MS = 20000;
//: Gap before the confirming second probe (see the catch block in `check`).
//: Long enough that a page genuinely unloading has finished doing so, short
//: enough that a real outage still surfaces the recovery page promptly.
const CONFIRM_RETRY_MS = 400;

function isExempt(pathname: string): boolean {
  return EXEMPT_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Centralizes "can we currently reach a working backend" for the whole app.
 * Distinguishes a hard browser-offline signal, a transport-level failure
 * (backend unreachable), and a degraded-but-reachable backend (a specific
 * dependency like the database is unhealthy) from an ordinary API error
 * response - only the first three ever redirect to /offline, and only when
 * the current route isn't exempt. Never touches auth/session state.
 *
 * The mount effect below intentionally has an empty dependency array (it
 * must only ever attach one set of listeners/timers for the component's
 * whole lifetime), so every value it reads at event time is threaded
 * through a ref updated on every render, never a value closed over at
 * mount. `navigate`/`location` in particular must never be read from a
 * stale closure - this project's router (`src/vendor/react-router-dom.tsx`,
 * a lightweight in-house shim, not the npm package) recreates `navigate`
 * on every location change, and calling a stale instance for a `replace`
 * navigation resolves against a stale history index.
 */
export const ConnectionRecoveryProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const locationRef = useRef(location);
  locationRef.current = location;

  const [state, setState] = useState<Omit<ConnectionState, 'checkNow'>>({
    status: 'checking',
    checks: null,
    embedding: null,
    lastCheckedAt: null,
  });

  const pollDelayRef = useRef(MIN_POLL_MS);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancelledRef = useRef(false);
  const wasUnreachableRef = useRef(false);
  const checkNowRef = useRef<() => void>(() => undefined);
  // A health check that is still in flight when the page starts unloading
  // (a link click, a browser back/forward, any full navigation) has its
  // fetch aborted by the browser. That abort is NOT evidence the backend is
  // down, and must never be allowed to run redirectToOffline() - doing so
  // pushes a bogus /offline entry onto the history stack of the page being
  // left behind, which then silently corrupts the user's back/forward
  // history (a later Back lands on /offline instead of the page they were
  // actually on). Tracked explicitly rather than inferred from the error,
  // since a genuine transport failure and an abort both surface as the same
  // NetworkUnavailableError.
  const inFlightAbortRef = useRef<AbortController | null>(null);
  const unloadingRef = useRef(false);
  // Guards against ever having two concurrent check()->scheduleNext() chains
  // alive at once (e.g. a manual checkNow() firing while the passive
  // timer-driven check is still awaiting its response) - without this, each
  // chain independently re-arms its own timer, so polling frequency could
  // silently double every time a manual trigger overlaps an in-flight check.
  const checkInFlightRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;
    // If this mount is starting out already parked at /offline with a
    // stored return path, that combination only happens via an automatic
    // redirect (see redirectToOffline below) - never from a user typing the
    // URL, since that path leaves RETURN_PATH_KEY unset. A full page reload
    // while already on /offline (e.g. triggered by this same provider's own
    // background poll finishing a redirect before an external reload lands)
    // otherwise resets this ref to false on the fresh mount, so a
    // same-render healthy check would report plain 'online' instead of
    // 'restored' and skip restoreFromOffline() below - stranding the user
    // on /offline forever despite the backend already being healthy.
    wasUnreachableRef.current =
      locationRef.current.pathname === '/offline' && sessionStorage.getItem(RETURN_PATH_KEY) !== null;

    const redirectToOffline = () => {
      // Never mutate history on a page that is already going away - see
      // unloadingRef above.
      if (unloadingRef.current || cancelledRef.current) return;
      const path = locationRef.current.pathname;
      if (path === '/offline' || isExempt(path)) return;
      sessionStorage.setItem(RETURN_PATH_KEY, `${path}${locationRef.current.search}`);
      // `replace`, never a push: this redirect is involuntary (the user did
      // not ask to go to /offline), and restoreFromOffline below already
      // replaces back to the stored path once the backend recovers - so the
      // pair leaves the history stack exactly as it found it. Pushing here
      // instead injected a phantom /offline entry that outlived the outage,
      // so a later Back from an unrelated page landed on the recovery page
      // rather than where the user actually came from.
      navigateRef.current('/offline', { replace: true });
    };

    const restoreFromOffline = () => {
      if (locationRef.current.pathname !== '/offline') return;
      const returnPath = sessionStorage.getItem(RETURN_PATH_KEY);
      if (!returnPath) return; // arrived by typing the URL directly - leave the user in control
      sessionStorage.removeItem(RETURN_PATH_KEY);
      navigateRef.current(returnPath, { replace: true });
    };

    const check = async () => {
      if (!navigator.onLine) {
        if (cancelledRef.current) return;
        wasUnreachableRef.current = true;
        setState({ status: 'offline', checks: null, embedding: null, lastCheckedAt: Date.now() });
        redirectToOffline();
        pollDelayRef.current = MIN_POLL_MS;
        return;
      }

      const controller = new AbortController();
      inFlightAbortRef.current = controller;
      try {
        const health = await getSystemHealth(controller.signal);
        if (cancelledRef.current) return;
        const backendUp = health.checks.backend.status === 'healthy';
        const databaseUp = health.checks.database.status === 'healthy';
        const criticallyUnreachable = !backendUp || !databaseUp;

        if (criticallyUnreachable) {
          wasUnreachableRef.current = true;
          setState({
            status: !backendUp ? 'backend_unreachable' : 'degraded',
            checks: health.checks,
            embedding: health.embedding,
            lastCheckedAt: Date.now(),
          });
          redirectToOffline();
          pollDelayRef.current = MIN_POLL_MS;
        } else {
          const isFullyHealthy = health.status === 'healthy';
          const nextStatus = wasUnreachableRef.current ? 'restored' : isFullyHealthy ? 'online' : 'degraded';
          setState({
            status: nextStatus,
            checks: health.checks,
            embedding: health.embedding,
            lastCheckedAt: Date.now(),
          });
          if (wasUnreachableRef.current) {
            wasUnreachableRef.current = false;
            restoreFromOffline();
          }
          pollDelayRef.current = Math.min(pollDelayRef.current * 1.5, MAX_POLL_MS);
        }
      } catch {
        if (cancelledRef.current) return;
        // An aborted request says nothing about the backend's health - it
        // means this page is being torn down (or the provider unmounted)
        // mid-check. Reporting it as an outage would both flash a false
        // recovery page and corrupt history via redirectToOffline().
        if (controller.signal.aborted || unloadingRef.current) return;

        // One failed probe is not proof of an outage. A fetch aborted by the
        // browser because the page is navigating away rejects exactly like a
        // real transport failure, and cannot be told apart from one at this
        // layer (the browser aborts the underlying request without touching
        // our own AbortController, so signal.aborted stays false). Treating
        // that single rejection as "backend unreachable" redirected the
        // outgoing page to /offline, leaving a phantom /offline entry that
        // corrupted browser back/forward afterwards. Confirm with a second
        // probe before declaring an outage: a navigation-aborted check never
        // reproduces, a genuine outage always does.
        await new Promise((resolve) => setTimeout(resolve, CONFIRM_RETRY_MS));
        if (cancelledRef.current || unloadingRef.current) return;
        const confirmController = new AbortController();
        inFlightAbortRef.current = confirmController;
        try {
          await getSystemHealth(confirmController.signal);
          // Recovered on the retry: it was a blip, not an outage. Leave the
          // status alone and let the next scheduled poll report properly.
          pollDelayRef.current = MIN_POLL_MS;
          return;
        } catch {
          if (cancelledRef.current || unloadingRef.current) return;
          if (confirmController.signal.aborted) return;
        }

        wasUnreachableRef.current = true;
        setState({ status: 'backend_unreachable', checks: null, embedding: null, lastCheckedAt: Date.now() });
        redirectToOffline();
        pollDelayRef.current = MIN_POLL_MS;
      } finally {
        if (inFlightAbortRef.current === controller) inFlightAbortRef.current = null;
      }
    };

    const scheduleNext = () => {
      if (cancelledRef.current || unloadingRef.current) return;
      timerRef.current = setTimeout(runCheckAndSchedule, pollDelayRef.current);
    };

    // The single entry point for every check, whether timer-driven or
    // manually triggered (Retry, the 'online' event, a failed request
    // elsewhere via onNetworkFailure). `checkInFlightRef` makes this a
    // mutex: if a check is already running, this call is a no-op and the
    // in-flight one's own scheduleNext() (below) re-arms the next poll when
    // it finishes - so there is only ever one live check()->scheduleNext()
    // chain, never two running concurrently.
    const runCheckAndSchedule = async () => {
      if (checkInFlightRef.current) return;
      checkInFlightRef.current = true;
      try {
        await check();
      } finally {
        checkInFlightRef.current = false;
      }
      scheduleNext();
    };

    const checkNow = () => {
      pollDelayRef.current = MIN_POLL_MS;
      if (checkInFlightRef.current) return;
      if (timerRef.current) clearTimeout(timerRef.current);
      void runCheckAndSchedule();
    };
    checkNowRef.current = checkNow;

    void runCheckAndSchedule();

    const handleOnline = () => checkNow();
    const handleOffline = () => {
      wasUnreachableRef.current = true;
      setState({ status: 'offline', checks: null, embedding: null, lastCheckedAt: Date.now() });
      redirectToOffline();
    };
    // pagehide/pageshow rather than unload: 'unload' is never fired for a
    // page entering the back/forward cache (and registering it disqualifies
    // the page from bfcache entirely in WebKit/Safari), which is exactly
    // the navigation path this guard exists for.
    const handlePageHide = () => {
      unloadingRef.current = true;
      inFlightAbortRef.current?.abort();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // A page restored from bfcache resumes with whatever connection state it
    // was frozen with, and its poll timer was cleared on the way out - so
    // revalidate immediately instead of showing stale "healthy"/"offline"
    // state from before the freeze.
    const handlePageShow = (event: PageTransitionEvent) => {
      unloadingRef.current = false;
      if (!event.persisted) return;
      checkNow();
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    window.addEventListener('pagehide', handlePageHide);
    window.addEventListener('pageshow', handlePageShow);
    const unsubscribeNetworkFailure = onNetworkFailure(() => checkNow());

    return () => {
      cancelledRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      inFlightAbortRef.current?.abort();
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('pagehide', handlePageHide);
      window.removeEventListener('pageshow', handlePageShow);
      unsubscribeNetworkFailure();
    };
  }, []);

  return (
    <ConnectionRecoveryContext.Provider
      value={{ ...state, checkNow: () => checkNowRef.current() }}
    >
      {children}
    </ConnectionRecoveryContext.Provider>
  );
};
