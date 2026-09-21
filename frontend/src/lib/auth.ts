import { getAuthToken, getMe, login as apiLogin, logout as apiLogout, register as apiRegister, setAuthToken } from '@/api/client';
import type { AuthUser } from '@/api/types';

export type AuthStatus = 'loading' | 'authenticated' | 'guest';

let status: AuthStatus = getAuthToken() ? 'loading' : 'guest';
let user: AuthUser | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function subscribeAuth(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getAuthStatusSnapshot(): AuthStatus {
  return status;
}

export function getAuthUserSnapshot(): AuthUser | null {
  return user;
}

/** Resolves a persisted token (from a previous session) to a user, or clears it if it's stale. */
export async function bootstrapAuth(): Promise<void> {
  if (!getAuthToken()) {
    status = 'guest';
    emit();
    return;
  }
  try {
    const res = await getMe();
    user = res.user;
    status = 'authenticated';
  } catch {
    setAuthToken(null);
    user = null;
    status = 'guest';
  }
  emit();
}

export async function login(username: string, password: string): Promise<void> {
  const res = await apiLogin({ username, password });
  setAuthToken(res.token);
  user = res.user;
  status = 'authenticated';
  emit();
}

export async function register(name: string, username: string, password: string): Promise<void> {
  const res = await apiRegister({ name, username, password });
  setAuthToken(res.token);
  user = res.user;
  status = 'authenticated';
  emit();
}

export async function logout(): Promise<void> {
  try {
    await apiLogout();
  } catch {
    // token may already be invalid server-side — clear local state regardless
  }
  setAuthToken(null);
  user = null;
  status = 'guest';
  emit();
}

// A request that comes back 401 (token revoked/expired) drops local state so
// the route guard redirects to /login instead of leaving a dead session.
window.addEventListener('auth:unauthorized', () => {
  user = null;
  status = 'guest';
  emit();
});
