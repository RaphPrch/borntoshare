import type { BulkDecisionResponse } from '../api/access-requests';

type DecisionErrorSeverity = 'warning' | 'error';

export type AccessRequestDecisionUiError = {
  title: string;
  message: string;
  severity: DecisionErrorSeverity;
  code: string | null;
  permission: 'READ' | 'WRITE' | null;
  hint: string | null;
  storageRootId: number | null;
  actionLabel: string | null;
  actionHref: string | null;
  showInlineNotice: boolean;
  inlinePrimary: string | null;
  inlineSecondary: string | null;
};

type FailedDetail = {
  code?: string | null;
  message?: string | null;
  hint?: string | null;
  storage_root_id?: number | null;
  requested_permission?: string | null;
};

type ItemErrorInput = {
  detail?: FailedDetail | null;
  reason?: string | null;
  fallbackStorageRootId?: number | null;
};

type BulkMapOptions = {
  fallbackStorageRootId?: number | null;
};

const textOrNull = (value: unknown): string | null => {
  if (value === null || value === undefined) return null;
  const out = String(value).trim();
  return out.length > 0 ? out : null;
};

const toIntOrNull = (value: unknown): number | null => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
};

const normalizePermission = (value: unknown): 'READ' | 'WRITE' | null => {
  const raw = textOrNull(value)?.toUpperCase();
  if (!raw) return null;
  if (raw.includes('READ')) return 'READ';
  if (raw.includes('WRITE')) return 'WRITE';
  return null;
};

const extractPermissionFromText = (value: unknown): 'READ' | 'WRITE' | null => {
  const raw = textOrNull(value)?.toUpperCase();
  if (!raw) return null;
  if (raw.includes('PERMISSION READ') || raw.includes(' READ ')) return 'READ';
  if (raw.includes('PERMISSION WRITE') || raw.includes(' WRITE ')) return 'WRITE';
  return null;
};

const storageRootHref = (storageRootId: number | null): string | null =>
  storageRootId && storageRootId > 0 ? `/storage-roots?selected=${storageRootId}` : null;

const mapByCode = (args: {
  code: string | null;
  permission: 'READ' | 'WRITE' | null;
  hint: string | null;
  storageRootId: number | null;
  fallbackMessage: string | null;
}): AccessRequestDecisionUiError => {
  const code = textOrNull(args.code)?.toUpperCase() ?? null;
  const permission = args.permission;
  const hint = args.hint;
  const storageRootId = args.storageRootId;
  const fallbackMessage = args.fallbackMessage;
  const actionHref = storageRootHref(storageRootId);

  if (code === 'GOVERNED_GROUP_NAME_MISSING') {
    return {
      title: 'Decision blocked',
      message: 'No AD group name can be computed for this storage root. Check the naming policy of its zone or endpoint.',
      severity: 'warning',
      code,
      permission,
      hint,
      storageRootId,
      actionLabel: actionHref ? 'Open storage root' : null,
      actionHref,
      showInlineNotice: true,
      inlinePrimary: 'Technical configuration missing: the AD group for this access level cannot be named.',
      inlineSecondary: 'Fix the naming policy (zone, endpoint or storage root), then retry the decision.'
    };
  }

  if (code === 'INVALID_ACCESS_LEVEL' || code === 'INVALID_REQUEST_PERMISSION') {
    return {
      title: 'Decision blocked',
      message: 'The request permission could not be resolved to a supported READ or WRITE access level.',
      severity: 'error',
      code,
      permission,
      hint,
      storageRootId,
      actionLabel: null,
      actionHref: null,
      showInlineNotice: false,
      inlinePrimary: null,
      inlineSecondary: null
    };
  }

  if (code === 'UNSUPPORTED_TARGET_TYPE') {
    return {
      title: 'Decision blocked',
      message: 'This request target type is not supported for this action.',
      severity: 'error',
      code,
      permission,
      hint,
      storageRootId,
      actionLabel: null,
      actionHref: null,
      showInlineNotice: false,
      inlinePrimary: null,
      inlineSecondary: null
    };
  }

  return {
    title: 'Decision failed',
    message: fallbackMessage ?? 'The request could not be applied. Review the request configuration and try again.',
    severity: 'error',
    code,
    permission,
    hint,
    storageRootId,
    actionLabel: null,
    actionHref: null,
    showInlineNotice: false,
    inlinePrimary: null,
    inlineSecondary: null
  };
};

export const mapAccessRequestDecisionError = (input: ItemErrorInput): AccessRequestDecisionUiError => {
  const detail = input.detail ?? null;
  const reason = textOrNull(input.reason);

  const code = textOrNull(detail?.code)?.toUpperCase() ?? null;
  const permission = normalizePermission(detail?.requested_permission) ?? extractPermissionFromText(reason);
  const hint = textOrNull(detail?.hint);
  const storageRootId = toIntOrNull(detail?.storage_root_id) ?? toIntOrNull(input.fallbackStorageRootId);

  return mapByCode({ code, permission, hint, storageRootId, fallbackMessage: reason });
};

export const mapAccessRequestDecisionErrorFromBulk = (
  result: BulkDecisionResponse,
  options?: BulkMapOptions
): AccessRequestDecisionUiError => {
  const firstFailedId = Number(result?.failed_ids?.[0] ?? 0);
  const detail = firstFailedId > 0 ? result?.failed_details?.[firstFailedId] ?? null : null;
  const reason = firstFailedId > 0 ? result?.failed_reasons?.[firstFailedId] ?? null : null;

  return mapAccessRequestDecisionError({
    detail,
    reason,
    fallbackStorageRootId: options?.fallbackStorageRootId ?? null
  });
};
