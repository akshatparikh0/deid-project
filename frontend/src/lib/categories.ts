import type { Category } from '@/api/types';

export interface CategoryMeta {
  category: Category;
  label: string;
  color: string;
  cfr: string;
}

// Order matches the canonical table in the API contract / the order the
// /rules/ endpoint returns rows in.
export const CATEGORY_ORDER: Category[] = [
  'patient_name',
  'physician_name',
  'name',
  'facility',
  'geo',
  'date',
  'phone',
  'fax',
  'email',
  'ssn',
  'mrn',
  'plan',
  'account',
  'license',
  'vehicle',
  'device',
  'url',
  'ip',
  'biometric',
  'photo',
  'other',
];

const META: Record<Category, CategoryMeta> = {
  patient_name: {
    category: 'patient_name',
    label: 'Patient name',
    color: '#6A3FA0',
    cfr: '§164.514(b)(2)(i)(A)',
  },
  physician_name: {
    category: 'physician_name',
    label: 'Physician / provider name',
    color: '#9B6FD1',
    cfr: '§164.514(b)(2)(i)(A)',
  },
  name: { category: 'name', label: 'Other person name', color: '#7C4DBC', cfr: '§164.514(b)(2)(i)(A)' },
  facility: { category: 'facility', label: 'Facility / organization', color: '#3A7CA5', cfr: '' },
  geo: { category: 'geo', label: 'Geographic', color: '#2D6FB8', cfr: '§164.514(b)(2)(i)(B)' },
  date: { category: 'date', label: 'Date', color: '#B8792D', cfr: '§164.514(b)(2)(i)(C)' },
  phone: { category: 'phone', label: 'Telephone', color: '#1F8A70', cfr: '§164.514(b)(2)(i)(D)' },
  fax: { category: 'fax', label: 'Fax', color: '#1F8A70', cfr: '§164.514(b)(2)(i)(E)' },
  email: { category: 'email', label: 'Email', color: '#1F8A70', cfr: '§164.514(b)(2)(i)(F)' },
  ssn: { category: 'ssn', label: 'SSN', color: '#A4291F', cfr: '§164.514(b)(2)(i)(G)' },
  mrn: { category: 'mrn', label: 'Medical record no.', color: '#A4291F', cfr: '§164.514(b)(2)(i)(H)' },
  plan: { category: 'plan', label: 'Health plan no.', color: '#A4291F', cfr: '§164.514(b)(2)(i)(I)' },
  account: { category: 'account', label: 'Account no.', color: '#8A5A1B', cfr: '§164.514(b)(2)(i)(J)' },
  license: {
    category: 'license',
    label: 'Certificate / licence',
    color: '#8A5A1B',
    cfr: '§164.514(b)(2)(i)(K)',
  },
  vehicle: {
    category: 'vehicle',
    label: 'Vehicle identifier',
    color: '#5B6770',
    cfr: '§164.514(b)(2)(i)(L)',
  },
  device: {
    category: 'device',
    label: 'Device identifier',
    color: '#5B6770',
    cfr: '§164.514(b)(2)(i)(M)',
  },
  url: { category: 'url', label: 'URL', color: '#2D6FB8', cfr: '§164.514(b)(2)(i)(N)' },
  ip: { category: 'ip', label: 'IP address', color: '#2D6FB8', cfr: '§164.514(b)(2)(i)(O)' },
  biometric: { category: 'biometric', label: 'Biometric', color: '#7C4DBC', cfr: '§164.514(b)(2)(i)(P)' },
  photo: { category: 'photo', label: 'Full-face image', color: '#7C4DBC', cfr: '§164.514(b)(2)(i)(Q)' },
  other: { category: 'other', label: 'Other identifier', color: '#5B6770', cfr: '§164.514(b)(2)(i)(R)' },
};

export function categoryMeta(category: Category): CategoryMeta {
  return META[category];
}

export function categoryLabel(category: Category): string {
  return META[category]?.label ?? category;
}

export function categoryColor(category: Category): string {
  return META[category]?.color ?? '#5B6770';
}

export function categoryCfr(category: Category): string {
  return META[category]?.cfr ?? '';
}

export const MODE_LABELS: Record<import('../api/types').Mode, string> = {
  redact: 'Redact',
  mask: 'Mask',
  pseudo: 'Pseudonymize',
  keep: 'Keep',
};

export const MODES: import('../api/types').Mode[] = ['redact', 'mask', 'pseudo', 'keep'];

export const MODE_NOTES: Record<import('../api/types').Mode, string> = {
  redact:
    'A black bar is burned over the value. Nothing recoverable remains in the output PDF or its text layer.',
  mask: 'The value is replaced by a placeholder token. Document structure and readability are preserved.',
  pseudo:
    'A consistent surrogate replaces the value everywhere it appears in this document. The mapping is retained so the set can be re-identified under a separate authorization.',
  keep: 'Value is released as-is. Requires a documented justification; the document no longer meets Safe Harbor.',
};

