import React, {
  createContext,
  isValidElement,
  useContext,
  useEffect,
  useMemo,
  useState
} from 'react';

type NavigateTarget = string | number;
type Params = Record<string, string>;

interface LocationState {
  pathname: string;
  search: string;
  hash: string;
}

interface RouterContextValue {
  location: LocationState;
  navigate: (to: NavigateTarget, options?: { replace?: boolean }) => void;
}

const RouterContext = createContext<RouterContextValue | null>(null);
const ParamsContext = createContext<Params>({});

const currentBrowserLocation = (): LocationState => ({
  pathname: window.location.pathname || '/',
  search: window.location.search || '',
  hash: window.location.hash || ''
});

const splitTarget = (target: string): LocationState => {
  const url = new URL(target, 'http://local.test');
  return {
    pathname: url.pathname || '/',
    search: url.search,
    hash: url.hash
  };
};

const pathWithSuffix = (location: LocationState) =>
  `${location.pathname}${location.search}${location.hash}`;

const normalizePath = (path: string) => {
  if (!path || path === '/') return '/';
  return path.endsWith('/') ? path.slice(0, -1) : path;
};

const matchRoute = (pattern: string | undefined, pathname: string): Params | null => {
  if (!pattern) return null;
  if (pattern === '*') return {};

  const normalizedPattern = normalizePath(pattern);
  const normalizedPathname = normalizePath(pathname);
  const patternParts = normalizedPattern.split('/').filter(Boolean);
  const pathParts = normalizedPathname.split('/').filter(Boolean);

  if (patternParts.length !== pathParts.length) {
    return null;
  }

  const params: Params = {};
  for (let index = 0; index < patternParts.length; index += 1) {
    const patternPart = patternParts[index];
    const pathPart = pathParts[index];

    if (patternPart.startsWith(':')) {
      params[patternPart.slice(1)] = decodeURIComponent(pathPart);
      continue;
    }

    if (patternPart !== pathPart) {
      return null;
    }
  }

  return params;
};

export const BrowserRouter: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [location, setLocation] = useState<LocationState>(() => currentBrowserLocation());

  useEffect(() => {
    const handlePopState = () => setLocation(currentBrowserLocation());
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const value = useMemo<RouterContextValue>(() => ({
    location,
    navigate: (to, options) => {
      if (typeof to === 'number') {
        window.history.go(to);
        setLocation(currentBrowserLocation());
        return;
      }

      const nextLocation = splitTarget(to);
      const nextPath = pathWithSuffix(nextLocation);
      if (options?.replace) {
        window.history.replaceState(null, '', nextPath);
      } else {
        window.history.pushState(null, '', nextPath);
      }
      setLocation(nextLocation);
    }
  }), [location]);

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
};

export const MemoryRouter: React.FC<{
  children: React.ReactNode;
  initialEntries?: string[];
}> = ({ children, initialEntries = ['/'] }) => {
  const [entries, setEntries] = useState(() => initialEntries.map(splitTarget));
  const [index, setIndex] = useState(0);
  const location = entries[index] ?? splitTarget('/');

  const value = useMemo<RouterContextValue>(() => ({
    location,
    navigate: (to, options) => {
      if (typeof to === 'number') {
        setIndex(current => Math.min(Math.max(current + to, 0), entries.length - 1));
        return;
      }

      const nextLocation = splitTarget(to);
      setEntries(current => {
        if (options?.replace) {
          const next = [...current];
          next[index] = nextLocation;
          return next;
        }
        return [...current.slice(0, index + 1), nextLocation];
      });
      if (!options?.replace) {
        setIndex(current => current + 1);
      }
    }
  }), [entries.length, index, location]);

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
};

export const Route: React.FC<{ path?: string; element: React.ReactNode }> = () => null;

export const Routes: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { location } = useRouterContext();
  const routes = React.Children.toArray(children);

  for (const child of routes) {
    if (!isValidElement<{ path?: string; element?: React.ReactNode }>(child)) {
      continue;
    }

    const params = matchRoute(child.props.path, location.pathname);
    if (params) {
      return (
        <ParamsContext.Provider value={params}>
          {child.props.element}
        </ParamsContext.Provider>
      );
    }
  }

  return null;
};

export const Navigate: React.FC<{ to: string; replace?: boolean }> = ({ to, replace = false }) => {
  const navigate = useNavigate();

  useEffect(() => {
    navigate(to, { replace });
  }, [navigate, replace, to]);

  return null;
};

export const Link = React.forwardRef<
  HTMLAnchorElement,
  React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string; replace?: boolean }
>(({ to, replace, onClick, ...props }, ref) => {
  const navigate = useNavigate();

  return (
    <a
      {...props}
      href={to}
      ref={ref}
      onClick={event => {
        onClick?.(event);
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.altKey ||
          event.ctrlKey ||
          event.shiftKey
        ) {
          return;
        }

        event.preventDefault();
        navigate(to, { replace });
      }}
    />
  );
});

Link.displayName = 'Link';

export const useLocation = () => useRouterContext().location;

export const useNavigate = () => useRouterContext().navigate;

export const useParams = <T extends Params = Params>() => useContext(ParamsContext) as T;

const useRouterContext = () => {
  const context = useContext(RouterContext);
  if (!context) {
    throw new Error('Router context is missing');
  }
  return context;
};
