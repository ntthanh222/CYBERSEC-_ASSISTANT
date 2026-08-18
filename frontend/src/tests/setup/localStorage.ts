// Node 22+'s own experimental global `localStorage` (a Web Storage API
// implementation backed by a file, controlled by --localstorage-file) can
// shadow jsdom's environment-provided localStorage in some Node/Vitest
// version combinations. Without a valid backing file, every method on that
// global is `undefined` - `localStorage.getItem`/`setItem`/`removeItem` all
// throw "is not a function" the instant application code touches it, even
// though a real browser (and Playwright-driven Chrome, which this app is
// actually tested against for E2E) has a fully functional localStorage.
// Replace it with a small in-memory Storage-compatible polyfill whenever
// the ambient one is missing a real implementation, so unit tests exercise
// the same code paths a real browser would.
if (typeof localStorage === 'undefined' || typeof localStorage.getItem !== 'function') {
  const store = new Map<string, string>();
  const polyfill: Storage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
  Object.defineProperty(globalThis, 'localStorage', {
    value: polyfill,
    writable: true,
    configurable: true,
  });
}

if (typeof ResizeObserver === 'undefined') {
  class ResizeObserverPolyfill {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  Object.defineProperty(globalThis, 'ResizeObserver', {
    value: ResizeObserverPolyfill,
    writable: true,
    configurable: true,
  });
}
