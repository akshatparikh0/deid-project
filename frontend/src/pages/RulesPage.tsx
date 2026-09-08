import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError, applyRules, getJob, getRules, reopenJob, updateRule } from '../api/client';
import type { CategoryRule, Job, Mode } from '../api/types';
import { CategoryDot } from '../components/CategoryBadge';
import { EmptyState, ErrorBanner, LoadingState } from '../components/States';
import { setActiveJob } from '../lib/activeJob';
import { categoryLabel, MODE_LABELS } from '../lib/categories';
import { formatPercent } from '../lib/format';
import { getDisplayThreshold, setDisplayThreshold } from '../lib/threshold';
import { showToast } from '../lib/toast';

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
  const [reopening, setReopening] = useState(false);

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
      navigate(`/jobs/${jobId}/review`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to apply rules.');
      setApplying(false);
    }
  }

  async function onReopen() {
    setReopening(true);
    setError(null);
    try {
      await reopenJob(jobId);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to reopen this document.');
      setReopening(false);
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
      <div className="page-header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 5 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <h1 className="page-title" style={{ margin: 0 }}>
            Detection rules
          </h1>
          <span className="mono" style={{ fontSize: 12, color: 'var(--color-text-faint)' }}>
            {job.code} · {job.filename}
          </span>
        </div>
        <p className="page-subtitle" style={{ margin: 0 }}>
          The scan found {totalFound} unique identifiers across {classCount} of the eighteen Safe
          Harbor classes. Confirm the default action for each class, then review the document.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}
      {rowError && <ErrorBanner message={rowError} />}

      {isComplete && (
        <div className="notice-banner">
          <span aria-hidden="true">🔒</span>
          <span style={{ flex: 1 }}>
            This document is complete, so detection rules are locked. Reopen it to change them.
          </span>
          <button className="btn btn-sm" disabled={reopening} onClick={onReopen}>
            {reopening ? 'Reopening…' : 'Reopen to edit'}
          </button>
        </div>
      )}

      <div
        className="card"
        style={{
          display: 'flex',
          gap: 18,
          alignItems: 'center',
          padding: '16px 18px',
          marginBottom: 20,
        }}
      >
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 600 }}>Confidence threshold</div>
          <div className="page-subtitle" style={{ marginTop: 2 }}>
            Below this, entities are flagged for review instead of auto-applied.
          </div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4, flexShrink: 0 }}>
          {THRESHOLD_STEPS.map((step) => (
            <button
              key={step}
              type="button"
              className={`chip${threshold === step ? ' chip-active' : ''}`}
              onClick={() => onThresholdChange(step)}
            >
              {formatPercent(step)}
            </button>
          ))}
        </div>
      </div>

      <div className="card" style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Identifier class</th>
              <th>Found</th>
              <th>Default action</th>
              <th>Placeholder token</th>
              <th>Enabled</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.category} style={{ opacity: rule.enabled ? (rule.found === 0 ? 0.55 : 1) : 0.45 }}>
                <td>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <CategoryDot category={rule.category} />
                    {categoryLabel(rule.category)}
                  </span>
                </td>
                <td className="mono" style={{ color: rule.found === 0 ? 'var(--color-text-faint)' : undefined }}>
                  {rule.found || '—'}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {RULE_MODES.map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        disabled={!rule.enabled || isComplete}
                        className={`seg-btn-solid${rule.mode === mode ? ' seg-btn-solid-active' : ''}`}
                        style={{ padding: '4px 9px', fontSize: 11 }}
                        onClick={() => patchRule(rule.category, { mode })}
                      >
                        {MODE_LABELS[mode]}
                      </button>
                    ))}
                  </div>
                </td>
                <td>
                  <input
                    className="text-input mono"
                    style={{ width: 130, color: 'var(--color-success)' }}
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
                </td>
                <td>
                  <button
                    type="button"
                    className={`switch${rule.enabled ? ' switch-on' : ''}`}
                    disabled={isComplete}
                    onClick={() => patchRule(rule.category, { enabled: !rule.enabled })}
                    aria-label={rule.enabled ? 'Disable this class' : 'Enable this class'}
                  >
                    <span className="switch-knob" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!isComplete && (
        <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
          <p className="page-subtitle" style={{ margin: 0 }}>
            {rules.filter((r) => r.found > 0).length} classes present ·{' '}
            {rules.reduce((n, r) => n + r.found, 0)} entities will be transformed on apply.
          </p>
          <button className="btn btn-primary" disabled={applying} onClick={onApply} style={{ marginLeft: 'auto' }}>
            {applying ? 'Applying…' : 'Apply and review →'}
          </button>
        </div>
      )}
    </div>
  );
}
