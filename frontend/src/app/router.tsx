import type { ReactNode } from 'react';
import { lazy, Suspense, useSyncExternalStore } from 'react';
import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { FullPageLoader } from '@/components/States';
import { paths } from '@/config/paths';
import { getAuthStatusSnapshot, subscribeAuth } from '@/lib/auth';
import { NotFoundPage } from './not-found-page';

const LoginPage = lazy(() =>
  import('@/features/auth/components/LoginPage').then((m) => ({ default: m.LoginPage })),
);
const RegisterPage = lazy(() =>
  import('@/features/auth/components/RegisterPage').then((m) => ({ default: m.RegisterPage })),
);
const QueuePage = lazy(() =>
  import('@/features/queue/components/QueuePage').then((m) => ({ default: m.QueuePage })),
);
const ConfigRulesPage = lazy(() =>
  import('@/features/rules/components/ConfigRulesPage').then((m) => ({ default: m.ConfigRulesPage })),
);
const UploadPage = lazy(() =>
  import('@/features/upload/components/UploadPage').then((m) => ({ default: m.UploadPage })),
);
const StatusPage = lazy(() =>
  import('@/features/upload/components/StatusPage').then((m) => ({ default: m.StatusPage })),
);
const RulesPage = lazy(() =>
  import('@/features/rules/components/RulesPage').then((m) => ({ default: m.RulesPage })),
);
const ReviewPage = lazy(() =>
  import('@/features/review/components/ReviewPage').then((m) => ({ default: m.ReviewPage })),
);
const AuditPage = lazy(() =>
  import('@/features/audit/components/AuditPage').then((m) => ({ default: m.AuditPage })),
);

function RequireAuth({ children }: { children: ReactNode }) {
  const status = useSyncExternalStore(subscribeAuth, getAuthStatusSnapshot);
  const location = useLocation();

  if (status === 'loading') return <FullPageLoader />;
  if (status === 'guest') {
    return <Navigate to={paths.login.getHref()} replace state={{ from: location }} />;
  }
  return <>{children}</>;
}

function withSuspense(node: ReactNode) {
  return <Suspense fallback={<FullPageLoader />}>{node}</Suspense>;
}

export const router = createBrowserRouter([
  { path: paths.login.path, element: withSuspense(<LoginPage />) },
  { path: paths.register.path, element: withSuspense(<RegisterPage />) },
  {
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to={paths.queue.getHref()} replace /> },
      { path: paths.queue.path, element: withSuspense(<QueuePage />) },
      { path: paths.folderRules.path, element: withSuspense(<ConfigRulesPage />) },
      { path: paths.upload.path, element: withSuspense(<UploadPage />) },
      { path: paths.uploadStatus.path, element: withSuspense(<StatusPage />) },
      { path: paths.jobRules.path, element: withSuspense(<RulesPage />) },
      { path: paths.jobReview.path, element: withSuspense(<ReviewPage />) },
      { path: paths.jobAudit.path, element: withSuspense(<AuditPage />) },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
