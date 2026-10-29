import { t } from '$lib/i18n';
import type { AppError } from './types';

// Business codes whose message is worth more than the generic status message
const CODE_MESSAGES: Record<string, () => string> = {
  SNAPSHOT_ALREADY_RUNNING: () => t('A snapshot is already running for this identity source.'),
  SNAPSHOT_DISABLED: () => t('Snapshot inventory is disabled for this identity source.'),
  IDENTITY_SOURCE_NAME_TAKEN: () => t('An identity source with this name already exists.'),
  IDENTITY_SOURCE_DOMAIN_TAKEN: () => t('Another active source already authenticates the users of this domain.'),
  ACCOUNT_NOT_AUTHORIZED: () => t('This account is not authorized in BornToShare'),
  ENDPOINT_HAS_ACCESS_GROUPS: () =>
    t('AD access groups already exist for the storage roots of this file server: its identity source and zone can no longer change.'),
  ENDPOINT_HOST_HAS_ROOTS: () => t('Storage roots use the current host in their path.'),
  STORAGE_ROOT_PATH_TAKEN: () => t('This storage root path is already declared.'),
  STORAGE_ROOT_HOST_MISMATCH: () => t('The path points at another server than the file server of this storage root.'),
  STORAGE_ROOT_PATH_LOCKED: () => t('AD access groups and NTFS permissions are set on this folder: its path cannot change.'),
  STORAGE_ROOT_HAS_ACCESSES: () => t('This storage root still has active accesses or pending requests: revoke or decide them first.')
};

/** Translated message of a known business code, for toasts and inline errors alike. */
export function codeMessage(code: string | null | undefined): string | undefined {
  return code ? CODE_MESSAGES[code]?.() : undefined;
}

export function presentErrorMessage(error: AppError): string {
  const byCode = codeMessage(error.code);
  if (byCode) return byCode;
  if (error.status === 400) return t('Invalid request.');
  if (error.status === 401) return t('Session expired.');
  if (error.status === 403) return t('Action not allowed.');
  if (error.status === 404) return t('Item not found.');
  if (error.status === 409) return t('Item still used.');
  if ((error.status ?? 0) >= 500) return t('Unexpected error.');
  if (error.kind === 'network') return t('Network error.');
  if (error.kind === 'timeout') return t('Request timeout.');
  return error.message;
}

export function presentErrorHint(error: AppError): string | undefined {
  return error.hint;
}
