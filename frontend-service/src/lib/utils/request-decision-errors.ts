import { t } from '$lib/i18n';
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

// Messages are functions: translated when shown
const AD_PROVISIONING_ERRORS: Record<string, { message: () => string; hint?: () => string }> = {
  AD_GROUP_NAME_CONFLICT: {
    message: () => t('A group with this name already exists elsewhere in Active Directory.'),
    hint: () => t('A platform administrator can adopt it for this storage root.')
  },
  AD_ADOPT_TARGET_NOT_FOUND: {
    message: () => t('The group chosen for adoption no longer exists in Active Directory.')
  },
  ZONE_GROUP_OU_MISSING: {
    message: () => t('No organizational unit is set for the groups of this zone.'),
    hint: () => t('Set it in Zones › Provisioning.')
  },
  INVALID_TARGET_OU_DN: {
    message: () => t('The organizational unit of the zone is not a valid LDAP DN.'),
    hint: () => t('Fix it in Zones › Provisioning.')
  },
  AD_TARGET_OU_NOT_FOUND: {
    message: () => t('The organizational unit of the zone does not exist in Active Directory.'),
    hint: () => t('Fix it in Zones › Provisioning.')
  },
  IDENTITY_SOURCE_REQUIRED: {
    message: () => t('The storage endpoint has no Active Directory identity source.')
  },
  AD_PROVISIONING_DISABLED: {
    message: () => t('Managing AD groups is disabled for the identity source of this storage endpoint.'),
    hint: () => t('Enable “Manage AD groups” on the identity source.')
  },
  IDENTITY_SOURCE_INCOMPLETE: {
    message: () => t('The Active Directory identity source is incomplete (host, account, password or base DN).')
  },
  AD_BIND_FAILED: {
    message: () => t('The service account could not sign in to Active Directory.')
  },
  AD_GROUP_CREATE_DENIED: {
    message: () => t('The service account may not create groups in the organizational unit of the zone.'),
    hint: () => t('Delegate “Create group objects” on the organizational unit to the service account.')
  },
  AD_MEMBER_WRITE_DENIED: {
    message: () => t('The service account may not change the members of this group.'),
    hint: () => t('Delegate “Write members” on the group, or on the organizational unit that contains it, to the service account.')
  },
  AD_PERMISSION_DENIED: {
    message: () => t('The service account may not create groups or change members in this organizational unit.'),
    hint: () => t('Delegate “Create group objects” and “Write members” on the organizational unit to the service account.')
  },
  AD_TLS_FAILED: {
    message: () => t('The certificate of the domain controller was refused.'),
    hint: () => t('Check the AD certificate authority given to capsule-runner (LDAP_CA_FILE) and the host name of the identity source.')
  },
  AD_UNREACHABLE: {
    message: () => t('Active Directory did not answer.')
  },
  AD_PRINCIPAL_NOT_FOUND: {
    message: () => t('The requester was not found in Active Directory.')
  },
  AD_GROUP_NAME_INVALID: {
    message: () => t('The naming template produces an invalid group name (64 characters at most, no special characters).')
  },
  AD_JOB_STILL_RUNNING: {
    message: () => t('Active Directory has not answered yet.'),
    hint: () => t('Approve again in a few minutes: nothing is done twice.')
  },
  ACL_APPLY_FAILED: {
    message: () => t('The requester is in the AD group but the NTFS permissions could not be applied.'),
    hint: () => t('Approve again to re-apply them.')
  }
};

/** Translated message of a provisioning error code (log entries, decisions), null when unknown */
export const provisioningErrorMessage = (code: unknown): string | null => {
  const key = textOrNull(code)?.toUpperCase();
  return key && AD_PROVISIONING_ERRORS[key] ? AD_PROVISIONING_ERRORS[key].message() : null;
};

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
      title: t('Decision blocked'),
      message: t('No AD group name can be computed for this storage root. Check the naming policy of its zone or endpoint.'),
      severity: 'warning',
      code,
      permission,
      hint,
      storageRootId,
      actionLabel: actionHref ? t('Open storage root') : null,
      actionHref,
      showInlineNotice: true,
      inlinePrimary: t('Technical configuration missing: the AD group for this access level cannot be named.'),
      inlineSecondary: t('Fix the naming policy (zone, endpoint or storage root), then retry the decision.')
    };
  }

  if (code === 'INVALID_ACCESS_LEVEL' || code === 'INVALID_REQUEST_PERMISSION') {
    return {
      title: t('Decision blocked'),
      message: t('The request permission could not be resolved to a supported READ or WRITE access level.'),
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
      title: t('Decision blocked'),
      message: t('This request target type is not supported for this action.'),
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

  // Provisioning in Active Directory (group of the level, membership, NTFS ACL)
  const provisioning = code ? AD_PROVISIONING_ERRORS[code] : undefined;
  if (provisioning) {
    return {
      title: code === 'AD_JOB_STILL_RUNNING' ? t('Still in progress') : t('Decision blocked'),
      message: provisioning.message(),
      severity: code === 'AD_JOB_STILL_RUNNING' ? 'warning' : 'error',
      code,
      permission,
      hint: provisioning.hint?.() ?? hint,
      storageRootId,
      actionLabel: null,
      actionHref: null,
      showInlineNotice: false,
      inlinePrimary: null,
      inlineSecondary: null
    };
  }

  return {
    title: t('Decision failed'),
    message: fallbackMessage ?? t('The request could not be applied. Review the request configuration and try again.'),
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
