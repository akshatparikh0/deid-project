import type { ReactNode } from 'react';
import { useEffect, useSyncExternalStore } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { LoadingState } from '@/components/States';
import { AuditPage } from '@/features/audit/components/AuditPage';
import { LoginPage } from '@/features/auth/components/LoginPage';
import { RegisterPage } from '@/features/auth/components/RegisterPage';
import { QueuePage } from '@/features/queue/components/QueuePage';
import { ReviewPage } from '@/features/review/components/ReviewPage';
import { ConfigRulesPage } from '@/features/rules/components/ConfigRulesPage';
import { RulesPage } from '@/features/rules/components/RulesPage';
import { StatusPage } from '@/features/upload/components/StatusPage';
import { UploadPage } from '@/features/upload/components/UploadPage';
import { bootstrapAuth, getAuthStatusSnapshot, subscribeAuth } from '@/lib/auth';

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
        <Route path="/uploads/:batchId/status" element={<StatusPage />} />
        <Route path="/jobs/:id/rules" element={<RulesPage />} />
        <Route path="/jobs/:id/review" element={<ReviewPage />} />
        <Route path="/jobs/:id/audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/queue" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
