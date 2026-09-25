import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { ApiError, applyRules, getJob, getRules, updateRule } from '@/api/client';
import type { CategoryRule, Job, Mode } from '@/api/types';
import { CategoryDot } from '@/components/CategoryBadge';
import { EmptyState, ErrorBanner, LoadingState } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { paths } from '@/config/paths';
import { categoryLabel, MODE_LABELS } from '@/lib/categories';
import { formatPercent } from '@/lib/format';
import { getDisplayThreshold, setDisplayThreshold } from '@/lib/threshold';
import { cn } from '@/lib/utils';
import { setActiveJob } from '@/stores/activeJob';
import { showToast } from '@/lib/toast';

const THRESHOLD_STEPS = [0.7, 0.8, 0.85, 0.9];
const RULE_MODES: Mode[] = ['redact', 'mask', 'pseudo'];

export function RulesPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const navigate = useNavigate();

  const [job, setJob] = useState<Job | null>(null);
  const [rules, setRules] = useState<CategoryRule[] | null>(null);
  const [threshold, setThreshold] = useState(0.5);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([getJob(jobId), getRules(jobId)])
      .then(([jobRes, rulesRes]) => {
        setJob(jobRes.job);
        setActiveJob(jobRes.job);
        setRules(rulesRes.rules);
        setThreshold(getDisplayThreshold(jobId, jobRes.job.confidence_threshold));
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.detail : 'Failed to load detection rules.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, [jobId]);

  function patchRule(category: CategoryRule['category'], patch: Partial<CategoryRule>) {
    if (!rules || job?.status === 'complete') return;
    const prev = rules;
    setRules(rules.map((r) => (r.category === category ? { ...r, ...patch } : r)));
    setRowError(null);
    updateRule(jobId, category, patch).catch((err: unknown) => {
      setRules(prev); // roll back on failure
      setRowError(err instanceof ApiError ? err.detail : `Failed to update the ${category} rule.`);
    });
  }

  function onThresholdChange(value: number) {
    setThreshold(value);
    setDisplayThreshold(jobId, value);
  }

  async function onApply() {
    setApplying(true);
    setError(null);
    try {
      const { entities: updated } = await applyRules(jobId);
      showToast(`Defaults applied to ${updated.length} entities.`);
      navigate(paths.jobReview.getHref(jobId));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to apply rules.');
      setApplying(false);
    }
  }

  if (loading) return <LoadingState label="Loading detection rules…" />;
  if (error && !rules) return <ErrorBanner message={error} onRetry={load} />;
  if (!rules || !job) return <EmptyState title="Job not found" />;

  const isComplete = job.status === 'complete';
  const totalFound = rules.reduce((n, r) => n + r.found, 0);
  const classCount = rules.filter((r) => r.found > 0).length;

  return (
    <div>
      <div className="mb-6 flex flex-col items-start gap-1.5">
        <div className="flex items-baseline gap-3">
          <h1 className="font-serif text-[26px]">Detection rules</h1>
          <span className="text-muted-foreground font-mono text-xs">
            {job.code} · {job.filename}
          </span>
        </div>
        <p className="text-muted-foreground text-[13.5px]">
          The scan found {totalFound} unique identifiers across {classCount} of the eighteen Safe
          Harbor classes. Confirm the default action for each class, then review the document.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}
      {rowError && <ErrorBanner message={rowError} />}

      {isComplete && (
        <div className="bg-muted text-muted-foreground border-border mb-4.5 flex items-center gap-3 rounded-md border px-3.5 py-3 text-[13px]">
          <Lock className="size-4 shrink-0" aria-hidden="true" />
          <span className="flex-1">
            This document is complete and permanently locked — its source file has been removed, so
            detection rules can no longer be changed.
          </span>
        </div>
      )}

      <Card className="mb-5 flex-row items-center gap-4.5 px-4.5 py-4">
        <div>
          <div className="text-[13.5px] font-semibold">Confidence threshold</div>
          <div className="text-muted-foreground mt-0.5 text-[13.5px]">
            Below this, entities are flagged for review instead of auto-applied.
          </div>
        </div>
        <div className="ml-auto flex shrink-0 gap-1">
          {THRESHOLD_STEPS.map((step) => (
            <Button
              key={step}
              type="button"
              size="sm"
              variant={threshold === step ? 'default' : 'outline'}
              className="rounded-full px-3 text-xs"
              onClick={() => onThresholdChange(step)}
            >
              {formatPercent(step)}
            </Button>
          ))}
        </div>
      </Card>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Identifier class</TableHead>
              <TableHead>Found</TableHead>
              <TableHead>Default action</TableHead>
              <TableHead>Placeholder token</TableHead>
              <TableHead>Enabled</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rules.map((rule) => (
              <TableRow key={rule.category} style={{ opacity: rule.enabled ? (rule.found === 0 ? 0.55 : 1) : 0.45 }}>
                <TableCell>
                  <span className="inline-flex items-center gap-2">
                    <CategoryDot category={rule.category} />
                    {categoryLabel(rule.category)}
                  </span>
                </TableCell>
                <TableCell className={cn('font-mono', rule.found === 0 && 'text-muted-foreground')}>
                  {rule.found || '—'}
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    {RULE_MODES.map((mode) => (
                      <Button
                        key={mode}
                        type="button"
                        size="sm"
                        variant={rule.mode === mode ? 'default' : 'outline'}
                        disabled={!rule.enabled || isComplete}
                        className="h-7 px-2 text-[11px]"
                        onClick={() => patchRule(rule.category, { mode })}
                      >
                        {MODE_LABELS[mode]}
                      </Button>
                    ))}
                  </div>
                </TableCell>
                <TableCell>
                  <Input
                    className="text-status-success w-32 font-mono"
                    value={rule.token}
                    disabled={!rule.enabled || isComplete}
                    onChange={(e) =>
                      setRules(
                        rules.map((r) =>
                          r.category === rule.category ? { ...r, token: e.target.value } : r,
                        ),
                      )
                    }
                    onBlur={(e) => patchRule(rule.category, { token: e.target.value })}
                  />
                </TableCell>
                <TableCell>
                  <Switch
                    checked={rule.enabled}
                    disabled={isComplete}
                    onCheckedChange={() => patchRule(rule.category, { enabled: !rule.enabled })}
                    aria-label={rule.enabled ? 'Disable this class' : 'Enable this class'}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {!isComplete && (
        <div className="mt-4 flex items-center gap-4">
          <p className="text-muted-foreground text-[13.5px]">
            {rules.filter((r) => r.found > 0).length} classes present ·{' '}
            {rules.reduce((n, r) => n + r.found, 0)} entities will be transformed on apply.
          </p>
          <Button disabled={applying} onClick={onApply} className="ml-auto">
            {applying ? 'Applying…' : 'Apply and review →'}
          </Button>
        </div>
      )}
    </div>
  );
}
