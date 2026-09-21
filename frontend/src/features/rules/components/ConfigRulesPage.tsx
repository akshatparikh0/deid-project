import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError, getFolderRules, listFolders, updateFolderRule } from '@/api/client';
import type { Folder, FolderCategoryRule, Mode } from '@/api/types';
import { CategoryDot } from '@/components/CategoryBadge';
import { PageHeader } from '@/components/Layout';
import { EmptyState, ErrorBanner, LoadingState } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
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
      <div className="flex justify-center">
        <div className="w-full max-w-170">
          <PageHeader
            title="Config rules"
            subtitle="Choose which identifier classes to detect and how to transform each, before uploading a document."
          />
          <div className="rounded-xl border bg-card">
            <EmptyState
              title="Choose a patient folder first"
              description="Detection rules are configured per patient folder. Open a patient folder in the document library, then configure its ruleset from there."
              action={
                <Button asChild>
                  <Link to="/queue">Go to document library</Link>
                </Button>
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
      <div className="mb-6 flex flex-col items-start gap-1.5">
        <div className="flex items-baseline gap-3">
          <h1 className="font-serif text-[26px]">Config rules</h1>
          <span className="text-muted-foreground font-mono text-xs">{folderName}</span>
        </div>
        <p className="text-muted-foreground text-[13.5px]">
          Choose which of the eighteen Safe Harbor classes to detect in this folder and how to
          transform each by default. Documents uploaded here start from this ruleset; any single
          entity can still be overridden during review.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}
      {rowError && <ErrorBanner message={rowError} />}

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Identifier class</TableHead>
              <TableHead>Default action</TableHead>
              <TableHead>Placeholder token</TableHead>
              <TableHead>Enabled</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rules.map((rule) => (
              <TableRow key={rule.category} style={{ opacity: rule.enabled ? 1 : 0.45 }}>
                <TableCell>
                  <span className="inline-flex items-center gap-2">
                    <CategoryDot category={rule.category} />
                    {categoryLabel(rule.category)}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    {RULE_MODES.map((mode) => (
                      <Button
                        key={mode}
                        type="button"
                        size="sm"
                        variant={rule.mode === mode ? 'default' : 'outline'}
                        disabled={!rule.enabled}
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
                </TableCell>
                <TableCell>
                  <Switch
                    checked={rule.enabled}
                    onCheckedChange={() => patchRule(rule.category, { enabled: !rule.enabled })}
                    aria-label={rule.enabled ? 'Disable this class' : 'Enable this class'}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="mt-4 flex items-center gap-4">
        <p className="text-muted-foreground text-[13.5px]">
          {enabledCount} of {rules.length} classes enabled for detection.
        </p>
        <Button
          className="ml-auto"
          onClick={() => {
            showToast('Ruleset saved.');
            setUploadReady(folderId);
            navigate(`/upload?folder=${folderId}`);
          }}
        >
          Continue to upload →
        </Button>
      </div>
    </div>
  );
}
