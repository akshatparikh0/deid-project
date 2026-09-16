import type { ReactNode } from 'react';
import { useEffect, useSyncExternalStore } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Layout } from './components/Layout';
import { LoadingState } from './components/States';
import { bootstrapAuth, getAuthStatusSnapshot, subscribeAuth } from './lib/auth';
import { AuditPage } from './pages/AuditPage';
import { ConfigRulesPage } from './pages/ConfigRulesPage';
import { LoginPage } from './pages/LoginPage';
import { QueuePage } from './pages/QueuePage';
import { RegisterPage } from './pages/RegisterPage';
import { ReviewPage } from './pages/ReviewPage';
import { RulesPage } from './pages/RulesPage';
import { UploadPage } from './pages/UploadPage';

function RequireAuth({ children }: { children: ReactNode }) {
  const status = useSyncExternalStore(subscribeAuth, getAuthStatusSnapshot);
  const location = useLocation();

  if (status === 'loading') {
    return (
      <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center' }}>
        <LoadingState label="Loading…" />
      </div>
    );
  }
  if (status === 'guest') {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}

function App() {
  useEffect(() => {
    bootstrapAuth();
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Navigate to="/queue" replace />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/folders/:id/rules" element={<ConfigRulesPage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/jobs/:id/rules" element={<RulesPage />} />
        <Route path="/jobs/:id/review" element={<ReviewPage />} />
        <Route path="/jobs/:id/audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/queue" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
