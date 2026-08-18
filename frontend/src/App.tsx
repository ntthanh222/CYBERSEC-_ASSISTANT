import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './features/auth/AuthContext';
import { AppRoutes } from './routes/AppRoutes';
import { ConnectionRecoveryProvider } from './lib/network/ConnectionRecoveryProvider';
import { ErrorBoundary } from './components/ErrorBoundary';

function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <ConnectionRecoveryProvider>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </ConnectionRecoveryProvider>
      </ErrorBoundary>
    </BrowserRouter>
  );
}

export default App;
