import type { Category } from '@/api/types';

export interface CategoryMeta {
  category: Category;
  label: string;
  color: string;
  cfr: string;
}

// Order matches the canonical table in the API contract / the order the
// /rules/ endpoint returns rows in — mirrors backend documents/categories.py
// exactly (the single source of truth for this taxonomy).
export const CATEGORY_ORDER: Category[] = [
  'patient_name',
  'physician_name',
  'person_name',
  'guarantor_name',
  'facility_name',
  'employer',
  'date_of_birth',
  'date_of_service',
  'other_date',
  'age_over_89',
  'age_89_or_below',
  'street_address',
  'zip_code',
  'phone',
  'fax',
  'email',
  'url',
  'ssn',
  'mrn',
  'member_id',
  'account',
  'payment_card',
  'ip_address',
  'device_id',
  'license',
  'vehicle',
  'biometric',
  'photo',
  'other',
];

const NAMES_CFR = '§164.514(b)(2)(i)(A)';
const GEO_CFR = '§164.514(b)(2)(i)(B)';
const DATES_CFR = '§164.514(b)(2)(i)(C)';

const META: Record<Category, CategoryMeta> = {
  patient_name: { category: 'patient_name', label: 'Patient name', color: '#6A3FA0', cfr: NAMES_CFR },
  physician_name: { category: 'physician_name', label: 'Physician / provider name', color: '#9B6FD1', cfr: NAMES_CFR },
  person_name: { category: 'person_name', label: 'Other person name', color: '#7C4DBC', cfr: NAMES_CFR },
  guarantor_name: { category: 'guarantor_name', label: 'Guarantor / next of kin', color: '#7C4DBC', cfr: NAMES_CFR },
  facility_name: { category: 'facility_name', label: 'Facility / organization', color: '#3A7CA5', cfr: '' },
  employer: { category: 'employer', label: 'Employer', color: '#3A7CA5', cfr: '' },
  date_of_birth: { category: 'date_of_birth', label: 'Date of birth', color: '#B8792D', cfr: DATES_CFR },
  date_of_service: { category: 'date_of_service', label: 'Date of service', color: '#B8792D', cfr: DATES_CFR },
  other_date: { category: 'other_date', label: 'Other date', color: '#B8792D', cfr: DATES_CFR },
  age_over_89: { category: 'age_over_89', label: 'Age above 89', color: '#B8792D', cfr: DATES_CFR },
  age_89_or_below: { category: 'age_89_or_below', label: 'Age 89 or below', color: '#B8792D', cfr: '' },
  street_address: { category: 'street_address', label: 'Street address', color: '#2D6FB8', cfr: GEO_CFR },
  zip_code: { category: 'zip_code', label: 'ZIP code', color: '#2D6FB8', cfr: GEO_CFR },
  phone: { category: 'phone', label: 'Telephone', color: '#1F8A70', cfr: '§164.514(b)(2)(i)(D)' },
  fax: { category: 'fax', label: 'Fax', color: '#1F8A70', cfr: '§164.514(b)(2)(i)(E)' },
  email: { category: 'email', label: 'Email', color: '#1F8A70', cfr: '§164.514(b)(2)(i)(F)' },
  url: { category: 'url', label: 'URL', color: '#2D6FB8', cfr: '§164.514(b)(2)(i)(N)' },
  ssn: { category: 'ssn', label: 'SSN / government ID', color: '#A4291F', cfr: '§164.514(b)(2)(i)(G)' },
  mrn: { category: 'mrn', label: 'Medical record number', color: '#A4291F', cfr: '§164.514(b)(2)(i)(H)' },
  member_id: { category: 'member_id', label: 'Member ID', color: '#A4291F', cfr: '§164.514(b)(2)(i)(I)' },
  account: { category: 'account', label: 'Account number', color: '#8A5A1B', cfr: '§164.514(b)(2)(i)(J)' },
  payment_card: { category: 'payment_card', label: 'Payment card / bank identifier', color: '#A4291F', cfr: '§164.514(b)(2)(i)(R)' },
  ip_address: { category: 'ip_address', label: 'IP address', color: '#2D6FB8', cfr: '§164.514(b)(2)(i)(O)' },
  device_id: { category: 'device_id', label: 'Device identifier', color: '#5B6770', cfr: '§164.514(b)(2)(i)(M)' },
  license: { category: 'license', label: 'Certificate / licence', color: '#8A5A1B', cfr: '§164.514(b)(2)(i)(K)' },
  vehicle: { category: 'vehicle', label: 'Vehicle identifier', color: '#5B6770', cfr: '§164.514(b)(2)(i)(L)' },
  biometric: { category: 'biometric', label: 'Biometric identifier', color: '#7C4DBC', cfr: '§164.514(b)(2)(i)(P)' },
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

