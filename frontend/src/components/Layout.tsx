import type { ReactNode } from 'react';
import { useSyncExternalStore } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  getActiveFolderSnapshot,
  getActiveJobSnapshot,
  getQueueCountSnapshot,
  getUploadReadySnapshot,
  subscribeActiveJob,
} from '../lib/activeJob';
import { getAuthUserSnapshot, logout, subscribeAuth } from '../lib/auth';
import { routeForJobStatus } from '../lib/jobRoute';
import { Toast } from './Toast';

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeJob = useSyncExternalStore(subscribeActiveJob, getActiveJobSnapshot);
  const activeFolder = useSyncExternalStore(subscribeActiveJob, getActiveFolderSnapshot);
  const queueCount = useSyncExternalStore(subscribeActiveJob, getQueueCountSnapshot);
  const uploadReadyFolderId = useSyncExternalStore(subscribeActiveJob, getUploadReadySnapshot);
  const user = useSyncExternalStore(subscribeAuth, getAuthUserSnapshot);

  async function onLogout() {
    await logout();
    navigate('/login', { replace: true });
  }

  const path = location.pathname;
  const rulesPath = activeFolder ? `/folders/${activeFolder.id}/rules` : null;
  const uploadPath =
    activeFolder && uploadReadyFolderId === activeFolder.id ? `/upload?folder=${activeFolder.id}` : null;
  const reviewPath = activeJob ? routeForJobStatus(activeJob.id, activeJob.status) : null;

  const items = [
    {
      num: '01',
      label: 'Document library',
      badge: queueCount != null ? String(queueCount) : '',
      to: '/queue',
      active: path === '/queue' || /^\/jobs\/\d+\/audit$/.test(path),
    },
    {
      num: '02',
      label: 'Config Rules',
      badge: '',
      to: rulesPath,
      active: rulesPath !== null && path === rulesPath,
    },
    {
      num: '03',
      label: 'Upload File',
      badge: '',
      to: uploadPath,
      active: path === '/upload',
    },
    {
      num: '04',
      label: 'Review',
      badge: activeJob ? String(activeJob.entityCount) : '',
      to: reviewPath,
      active: reviewPath !== null && (path === reviewPath || /^\/jobs\/\d+\/rules$/.test(path)),
    },
  ];

  return (
    <div className="app-shell">
      <nav className="nav-rail">
        <div className="nav-brand">
          Safe Harbor
          <small>45 CFR §164.514(b)(2)</small>
        </div>
        <div className="nav-list">
          {items.map((item) => (
            <button
              key={item.num}
              type="button"
              className={`nav-item${item.active ? ' nav-item-active' : ''}`}
              disabled={!item.to}
              onClick={() => item.to && navigate(item.to)}
            >
              <span className="nav-item-num">{item.num}</span>
              <span className="nav-item-label">{item.label}</span>
              {item.badge && <span className="nav-item-badge">{item.badge}</span>}
            </button>
          ))}
        </div>
        <div className="nav-spacer" />
        <div className="nav-footer">
          <div className="nav-footer-label">Signed in as</div>
          <div className="nav-footer-name">{user?.name || user?.username}</div>
          <button type="button" className="nav-logout-btn" onClick={onLogout}>
            Log out
          </button>
        </div>
      </nav>
      <main className="app-main">
        <Outlet />
      </main>
      <Toast />
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>{actions}</div>}
    </div>
  );
}
