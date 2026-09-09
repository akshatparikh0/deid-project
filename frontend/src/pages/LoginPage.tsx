import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSyncExternalStore } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { ErrorBanner } from '../components/States';
import { getAuthStatusSnapshot, login, subscribeAuth } from '../lib/auth';

export function LoginPage() {
  const status = useSyncExternalStore(subscribeAuth, getAuthStatusSnapshot);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  if (status === 'authenticated') {
    const from = (location.state as { from?: { pathname: string } } | null)?.from;
    return <Navigate to={from?.pathname ?? '/queue'} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      navigate('/queue', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Login failed. Please try again.');
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-brand">
          Safe Harbor
          <small>45 CFR §164.514(b)(2)</small>
        </div>
        <p className="auth-subtitle">Sign in to continue to the de-identification workspace.</p>

        {error && <ErrorBanner message={error} />}

        <form onSubmit={onSubmit}>
          <div className="auth-field">
            <label className="field-label" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              className="text-input"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="auth-field">
            <label className="field-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="text-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={submitting} style={{ width: '100%' }}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="auth-footer">
          Don't have an account? <Link to="/register">Register</Link>
        </div>
      </div>
    </div>
  );
}
