import { useState } from 'react';
import { ApiError } from '@/api/client';
import { ErrorBanner } from '@/components/States';

export function NamePromptModal({
  title,
  label,
  initialValue = '',
  confirmLabel = 'Save',
  onSubmit,
  onClose,
}: {
  title: string;
  label: string;
  initialValue?: string;
  confirmLabel?: string;
  onSubmit: (name: string) => Promise<void>;
  onClose: () => void;
}) {
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    const trimmed = value.trim();
    if (!trimmed) {
      setError('This field cannot be blank.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(trimmed);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Something went wrong. Please try again.');
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" style={{ maxWidth: 400 }} onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">{title}</h2>
        <div className="auth-field" style={{ marginTop: 14 }}>
          <label className="field-label" htmlFor="name-prompt-input">
            {label}
          </label>
          <input
            id="name-prompt-input"
            className="text-input"
            type="text"
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submit();
            }}
          />
        </div>
        {error && <ErrorBanner message={error} />}
        <div className="modal-actions">
          <button className="btn" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? 'Saving…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
