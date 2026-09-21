import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSyncExternalStore } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '@/api/client';
import { ErrorBanner } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getAuthStatusSnapshot, login, subscribeAuth } from '@/lib/auth';

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
    <div className="bg-background flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-[380px] p-7">
        <CardHeader className="px-0">
          <div>
            <div className="font-serif text-foreground text-xl font-semibold">
              Safe Harbor
              <small className="font-mono text-muted-foreground mt-1.5 block text-[10px] font-normal tracking-[0.1em]">
                45 CFR §164.514(b)(2)
              </small>
            </div>
            <p className="text-muted-foreground mt-2 mb-0 text-[13px]">
              Sign in to continue to the de-identification workspace.
            </p>
          </div>
        </CardHeader>

        <CardContent className="px-0">
          {error && <ErrorBanner message={error} />}

          <form onSubmit={onSubmit}>
            <div className="mb-3.5">
              <Label htmlFor="username" className="text-muted-foreground mb-1.5 text-xs font-semibold">
                Username
              </Label>
              <Input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="mb-3.5">
              <Label htmlFor="password" className="text-muted-foreground mb-1.5 text-xs font-semibold">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>

          <div className="text-muted-foreground mt-5 text-center text-[12.5px]">
            Don't have an account? <Link to="/register">Register</Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
