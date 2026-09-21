import type { Mode } from '@/api/types';
import { MODE_LABELS } from '@/lib/categories';

export function ModePill({ mode }: { mode: Mode }) {
  return <span className={`mode-pill mode-pill-${mode}`}>{MODE_LABELS[mode]}</span>;
}
