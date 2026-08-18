import React from 'react';
import { ServerErrorView } from '../features/errors/ServerErrorView';

interface ErrorBoundaryState {
  hasError: boolean;
}

/** Catches a real, unhandled render-time exception anywhere in the tree
 * below it and shows the real 500 page instead of a blank screen or
 * React's own dev overlay. Rendered inside BrowserRouter (see App.tsx) so
 * ServerErrorView's useNavigate still works, but deliberately renders the
 * view directly rather than via a route - a component that just crashed
 * cannot be trusted to still support normal navigation state. */
export class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('Unhandled render error caught by ErrorBoundary', error, info.componentStack);
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      return <ServerErrorView />;
    }
    return this.props.children;
  }
}
