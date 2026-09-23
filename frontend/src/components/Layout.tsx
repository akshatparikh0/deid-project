import type { ReactNode } from 'react';
import { useSyncExternalStore } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  getActiveBatchSnapshot,
  getActiveFolderSnapshot,
  getActiveJobSnapshot,
  getQueueCountSnapshot,
  getUploadReadySnapshot,
  subscribeActiveJob,
} from '@/stores/activeJob';
import { paths } from '@/config/paths';
import { getAuthUserSnapshot, logout, subscribeAuth } from '@/lib/auth';
import { routeForJobStatus } from '@/lib/jobRoute';
import { cn } from '@/lib/utils';
import { Toaster } from '@/components/ui/sonner';

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeJob = useSyncExternalStore(subscribeActiveJob, getActiveJobSnapshot);
  const activeFolder = useSyncExternalStore(subscribeActiveJob, getActiveFolderSnapshot);
  const queueCount = useSyncExternalStore(subscribeActiveJob, getQueueCountSnapshot);
  const uploadReadyFolderId = useSyncExternalStore(subscribeActiveJob, getUploadReadySnapshot);
  const activeBatchId = useSyncExternalStore(subscribeActiveJob, getActiveBatchSnapshot);
  const user = useSyncExternalStore(subscribeAuth, getAuthUserSnapshot);

  async function onLogout() {
    await logout();
    navigate(paths.login.getHref(), { replace: true });
  }

  const path = location.pathname;
  const rulesPath = activeFolder ? paths.folderRules.getHref(activeFolder.id) : null;
  const uploadPath =
    activeFolder && uploadReadyFolderId === activeFolder.id ? paths.upload.getHref(activeFolder.id) : null;
  const reviewPath = activeJob ? routeForJobStatus(activeJob.id, activeJob.status) : null;
  const statusPath = activeBatchId != null ? paths.uploadStatus.getHref(activeBatchId) : null;

  const items = [
    {
      num: '01',
      label: 'Document library',
      badge: queueCount != null ? String(queueCount) : '',
      to: paths.queue.getHref(),
      active: path === paths.queue.path || /^\/jobs\/\d+\/audit$/.test(path),
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
      active: path === paths.upload.path,
    },
    {
      num: '04',
      label: 'Status',
      badge: '',
      to: statusPath,
      active: statusPath !== null && path === statusPath,
    },
    {
      num: '05',
      label: 'Review',
      badge: activeJob ? String(activeJob.entityCount) : '',
      to: reviewPath,
      active: reviewPath !== null && (path === reviewPath || /^\/jobs\/\d+\/rules$/.test(path)),
    },
  ];

  return (
    <div className="flex min-h-screen">
      <nav className="bg-nav-bg text-nav-text sticky top-0 flex h-screen w-(--nav-width) flex-none flex-col py-4.5">
        <div className="font-serif text-nav-active-text flex flex-col gap-0.75 px-4.5 pb-5 text-[16px] font-semibold tracking-[-0.01em]">
          Safe Harbor
          <small className="font-mono text-[10px] font-normal tracking-[0.1em] text-[#5c666f]">
            45 CFR §164.514(b)(2)
          </small>
        </div>
        <div className="flex flex-col gap-0.5 px-2.5">
          {items.map((item) => (
            <button
              key={item.num}
              type="button"
              className={cn(
                'text-nav-text flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left font-sans text-[13px] font-normal transition-colors duration-100',
                'not-disabled:hover:bg-white/4 not-disabled:hover:text-nav-active-text',
                'disabled:cursor-not-allowed disabled:opacity-40',
                item.active && 'bg-nav-active-bg text-nav-active-text font-semibold',
              )}
              disabled={!item.to}
              onClick={() => item.to && navigate(item.to)}
            >
              <span className="font-mono text-[11px] opacity-55">{item.num}</span>
              <span className="flex-1">{item.label}</span>
              {item.badge && (
                <span className="rounded-full bg-[#232b33] px-1.5 py-px font-mono text-[10px] text-[#c8ced4]">
                  {item.badge}
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <div className="mx-2.5 flex flex-col gap-1.5 border-t border-[#1d242b] px-2 pt-4">
          <div className="text-[11px] tracking-[0.04em] text-[#5c666f]">Signed in as</div>
          <div className="text-[13px] text-[#d6dbe0]">{user?.name || user?.username}</div>
          <button
            type="button"
            className="mt-0.5 self-start py-0.75 font-sans text-[11.5px] font-medium text-nav-text hover:text-nav-active-text hover:underline"
            onClick={onLogout}
          >
            Log out
          </button>
        </div>
      </nav>
      <main className="min-w-0 flex-1 px-9 pt-7 pb-15">
        <Outlet />
      </main>
      <Toaster />
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="font-serif mb-1 text-[26px]">{title}</h1>
        {subtitle && <p className="text-muted-foreground text-[13.5px]">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}
