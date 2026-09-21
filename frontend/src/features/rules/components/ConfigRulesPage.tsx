import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError, getFolderRules, listFolders, updateFolderRule } from '@/api/client';
import type { Folder, FolderCategoryRule, Mode } from '@/api/types';
import { CategoryDot } from '@/components/CategoryBadge';
import { PageHeader } from '@/components/Layout';
import { EmptyState, ErrorBanner, LoadingState } from '@/components/States';
import { categoryLabel, MODE_LABELS } from '@/lib/categories';
import { isPatientFolder, pathTo } from '@/lib/folders';
import { showToast } from '@/lib/toast';
import { setActiveFolder, setUploadReady } from '@/stores/activeJob';

const RULE_MODES: Mode[] = ['redact', 'mask', 'pseudo'];

export function ConfigRulesPage() {
  const { id } = useParams<{ id: string }>();
  const folderId = Number(id);
  const navigate = useNavigate();

  const [folders, setFolders] = useState<Folder[] | null>(null);
  const [rules, setRules] = useState<FolderCategoryRule[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([listFolders(), getFolderRules(folderId)])
      .then(([folderRes, rulesRes]) => {
        setFolders(folderRes.folders);
        setRules(rulesRes.rules);
        const folder = folderRes.folders.find((f) => f.id === folderId);
        if (folder && isPatientFolder(folderRes.folders, folderId)) setActiveFolder(folder);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.detail : 'Failed to load the detection ruleset.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, [folderId]);

  function patchRule(category: FolderCategoryRule['category'], patch: Partial<FolderCategoryRule>) {
    if (!rules) return;
    const prev = rules;
    setRules(rules.map((r) => (r.category === category ? { ...r, ...patch } : r)));
    setRowError(null);
    updateFolderRule(folderId, category, patch).catch((err: unknown) => {
      setRules(prev); // roll back on failure
      setRowError(err instanceof ApiError ? err.detail : `Failed to update the ${category} rule.`);
    });
  }

  if (loading) return <LoadingState label="Loading detection ruleset…" />;

  if (Number.isNaN(folderId) || (folders && !isPatientFolder(folders, folderId))) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{ width: '100%', maxWidth: 680 }}>
          <PageHeader
            title="Config rules"
            subtitle="Choose which identifier classes to detect and how to transform each, before uploading a document."
          />
          <div className="card">
            <EmptyState
              title="Choose a patient folder first"
              description="Detection rules are configured per patient folder. Open a patient folder in the document library, then configure its ruleset from there."
              action={
                <Link to="/queue" className="btn btn-primary">
                  Go to document library
                </Link>
              }
            />
          </div>
        </div>
      </div>
    );
  }

  if (error && !rules) return <ErrorBanner message={error} onRetry={load} />;
  if (!rules || !folders) return <EmptyState title="Folder not found" />;

  const trail = pathTo(folders, folderId);
  const folderName = trail.length ? trail[trail.length - 1].name : 'Patient folder';
  const enabledCount = rules.filter((r) => r.enabled).length;

  return (
    <div>
      <div className="page-header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 5 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <h1 className="page-title" style={{ margin: 0 }}>
            Config rules
          </h1>
          <span className="mono" style={{ fontSize: 12, color: 'var(--color-text-faint)' }}>
            {folderName}
          </span>
        </div>
        <p className="page-subtitle" style={{ margin: 0 }}>
          Choose which of the eighteen Safe Harbor classes to detect in this folder and how to
          transform each by default. Documents uploaded here start from this ruleset; any single
          entity can still be overridden during review.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}
      {rowError && <ErrorBanner message={rowError} />}

      <div className="card" style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Identifier class</th>
              <th>Default action</th>
              <th>Placeholder token</th>
              <th>Enabled</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.category} style={{ opacity: rule.enabled ? 1 : 0.45 }}>
                <td>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <CategoryDot category={rule.category} />
                    {categoryLabel(rule.category)}
                  </span>
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {RULE_MODES.map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        disabled={!rule.enabled}
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
                    disabled={!rule.enabled}
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

      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
        <p className="page-subtitle" style={{ margin: 0 }}>
          {enabledCount} of {rules.length} classes enabled for detection.
        </p>
        <button
          className="btn btn-primary"
          style={{ marginLeft: 'auto' }}
          onClick={() => {
            showToast('Ruleset saved.');
            setUploadReady(folderId);
            navigate(`/upload?folder=${folderId}`);
          }}
        >
          Continue to upload →
        </button>
      </div>
    </div>
  );
}
