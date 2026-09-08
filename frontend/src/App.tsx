import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { AuditPage } from './pages/AuditPage';
import { QueuePage } from './pages/QueuePage';
import { ReviewPage } from './pages/ReviewPage';
import { RulesPage } from './pages/RulesPage';
import { UploadPage } from './pages/UploadPage';

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/queue" replace />} />
        <Route path="/queue" element={<QueuePage />} />
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
