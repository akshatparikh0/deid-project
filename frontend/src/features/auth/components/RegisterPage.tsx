import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSyncExternalStore } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { ApiError } from '@/api/client';
import { ErrorBanner } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { paths } from '@/config/paths';
import { getAuthStatusSnapshot, register, subscribeAuth } from '@/lib/auth';

export function RegisterPage() {
  const status = useSyncExternalStore(subscribeAuth, getAuthStatusSnapshot);
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  if (status === 'authenticated') {
    return <Navigate to={paths.queue.getHref()} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register(name, username, password);
      navigate(paths.queue.getHref(), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Registration failed. Please try again.');
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
              Create an account to start de-identifying documents.
            </p>
          </div>
        </CardHeader>

        <CardContent className="px-0">
          {error && <ErrorBanner message={error} />}

          <form onSubmit={onSubmit}>
            <div className="mb-3.5">
              <Label htmlFor="name" className="text-muted-foreground mb-1.5 text-xs font-semibold">
                Full name
              </Label>
              <Input
                id="name"
                type="text"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
              />
            </div>
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
              />
            </div>
            <div className="mb-3.5">
              <Label htmlFor="password" className="text-muted-foreground mb-1.5 text-xs font-semibold">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? 'Creating account…' : 'Create account'}
            </Button>
          </form>

          <div className="text-muted-foreground mt-5 text-center text-[12.5px]">
            Already have an account? <Link to={paths.login.getHref()}>Sign in</Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
