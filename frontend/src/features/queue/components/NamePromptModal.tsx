import { useState } from 'react';
import { ApiError } from '@/api/client';
import { ErrorBanner } from '@/components/States';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

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
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-105">
        <DialogHeader>
          <DialogTitle className="font-serif text-[19px]">{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="name-prompt-input">{label}</Label>
          <Input
            id="name-prompt-input"
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
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? 'Saving…' : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
