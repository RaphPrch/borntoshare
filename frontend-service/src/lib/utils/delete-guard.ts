type ErrorLike = {
  status?: unknown;
  message?: unknown;
  code?: unknown;
  details?: unknown;
};

const DEPENDENCY_DELETE_MARKERS = [
  'attached',
  'associated',
  'cannot be deleted',
  'constraint',
  'declared storage roots',
  'dependent',
  'dependency',
  'foreign key',
  'in use',
  'linked',
  'referenced',
  'still attached',
  'still referenced'
];

const asRecord = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
};

const collectText = (value: unknown, depth = 0): string => {
  if (depth > 3 || value === null || value === undefined) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => collectText(item, depth + 1)).join(' ');
  }

  const record = asRecord(value);
  if (!record) return '';

  return [
    record.message,
    record.detail,
    record.error,
    record.code,
    record.error_code,
    record.hint
  ]
    .map((item) => collectText(item, depth + 1))
    .join(' ');
};

export const deleteErrorStatus = (error: unknown): number => {
  const record = asRecord(error) as ErrorLike | null;
  const status = Number(record?.status ?? 0);
  return Number.isFinite(status) ? status : 0;
};

export const isDependencyDeleteError = (error: unknown): boolean => {
  if (deleteErrorStatus(error) === 409) return true;

  const record = asRecord(error) as ErrorLike | null;
  const haystack = [record?.message, record?.code, record?.details, error]
    .map((item) => collectText(item))
    .join(' ')
    .toLowerCase();

  return DEPENDENCY_DELETE_MARKERS.some((marker) => haystack.includes(marker));
};

export const dependencyDeleteMessage = (
  entityLabel: string,
  relatedLabel = 'related records'
): string => `This ${entityLabel} cannot be deleted while ${relatedLabel} are still attached.`;

export const dependencyCountDeleteMessage = (
  entityLabel: string,
  count: number,
  relatedSingular: string,
  relatedPlural = `${relatedSingular}s`
): string => {
  const safeCount = Math.max(0, Number.isFinite(count) ? Number(count) : 0);
  const related = safeCount === 1 ? relatedSingular : relatedPlural;
  const verb = safeCount === 1 ? 'is' : 'are';
  return `This ${entityLabel} cannot be deleted while ${safeCount} ${related} ${verb} still attached.`;
};
