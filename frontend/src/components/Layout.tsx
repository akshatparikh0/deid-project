import type { ReactNode } from 'react';
import { useSyncExternalStore } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { getActiveJobSnapshot, getQueueCountSnapshot, subscribeActiveJob } from '../lib/activeJob';
import { Toast } from './Toast';

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeJob = useSyncExternalStore(subscribeActiveJob, getActiveJobSnapshot);
  const queueCount = useSyncExternalStore(subscribeActiveJob, getQueueCountSnapshot);

  const path = location.pathname;
  const rulesPath = activeJob ? `/jobs/${activeJob.id}/rules` : null;
  const reviewPath = activeJob ? `/jobs/${activeJob.id}/review` : null;

  const items = [
    { num: '01', label: 'Upload file', badge: '', to: '/upload', active: path === '/upload' },
    {
      num: '02',
      label: 'Rules',
      badge: activeJob ? String(activeJob.classCount) : '',
      to: rulesPath,
      active: rulesPath !== null && path === rulesPath,
    },
    {
      num: '03',
      label: 'Review',
      badge: activeJob ? String(activeJob.entityCount) : '',
      to: reviewPath,
      active: reviewPath !== null && path === reviewPath,
    },
    {
      num: '04',
      label: 'Document library',
      badge: queueCount != null ? String(queueCount) : '',
      to: '/queue',
      active: path === '/queue' || /^\/jobs\/\d+\/audit$/.test(path),
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
          <div className="nav-footer-name">R. Okonkwo</div>
          <div className="nav-footer-role">Privacy Officer</div>
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
