import { useSyncExternalStore } from 'react';
import { getToastSnapshot, subscribeToast } from '../lib/toast';

export function Toast() {
  const message = useSyncExternalStore(subscribeToast, getToastSnapshot);
  if (!message) return null;
  return <div className="toast">{message}</div>;
}
