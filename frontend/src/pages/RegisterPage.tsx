import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSyncExternalStore } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { ErrorBanner } from '../components/States';
import { getAuthStatusSnapshot, register, subscribeAuth } from '../lib/auth';

export function RegisterPage() {
  const status = useSyncExternalStore(subscribeAuth, getAuthStatusSnapshot);
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  if (status === 'authenticated') {
    return <Navigate to="/queue" replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register(name, username, password);
      navigate('/queue', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Registration failed. Please try again.');
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
        <p className="auth-subtitle">Create an account to start de-identifying documents.</p>

        {error && <ErrorBanner message={error} />}

        <form onSubmit={onSubmit}>
          <div className="auth-field">
            <label className="field-label" htmlFor="name">
              Full name
            </label>
            <input
              id="name"
              className="text-input"
              type="text"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>
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
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={submitting} style={{ width: '100%' }}>
            {submitting ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <div className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </div>
      </div>
    </div>
  );
}
