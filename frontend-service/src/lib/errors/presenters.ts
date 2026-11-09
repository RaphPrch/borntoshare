import { humanizeFileServerMessage } from './file-server';
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
  SHARE_HAS_STORAGE_ROOTS: () => t('BornToShare manages folders in this share: remove them from BornToShare first.'),
  STORAGE_ROOT_HAS_ACCESSES: () => t('This storage root still has active accesses or pending requests: revoke or decide them first.'),
  ACCESS_NOT_IN_FORCE: () => t('This access is no longer in force: it cannot be extended.'),
  ACCESS_PERMANENT: () => t('This access has no end date: there is nothing to extend.'),
  FOLDER_WORKER_TIMEOUT: () => t('The worker does not answer: nothing was done on the file server. Check that it is started, then try again.'),
  FOLDER_JOB_STILL_RUNNING: () => t('The worker is still working on it: check the file server before trying again.'),
  FOLDER_NAME_RESERVED: () => t('This name is reserved by Windows'),
  STORAGE_ENDPOINT_DISABLED: () => t('This file server is disabled'),
  FOLDER_OPERATION_FAILED: () => t('The worker could not finish the operation on the file server.'),
  CONFIRM_NAME_MISMATCH: () => t('Type the exact name of the storage root to confirm.'),
  FOLDER_CONTEXT_INCOMPLETE: () => t('The folder, its share or the file server account is missing.'),
  FOLDER_NAME_INVALID: () => t('These characters are refused by Windows: \\ / : * ? " < > |'),
  STORAGE_ROOT_HAS_CHILDREN: () => t('Child storage roots are attached to this storage root: remove them first.')
};

/** Translated message of a known business code, for toasts and inline errors alike. */
export function codeMessage(code: string | null | undefined): string | undefined {
  return code ? CODE_MESSAGES[code]?.() : undefined;
}

const BARE_HTTP = /^(http\s*\d+|request failed|conflict|not found|bad request|forbidden|unauthorized|unprocessable( entity)?|\d{3})\b/i;
const isExplained = (message: unknown): boolean => {
  const text = String(message ?? '').trim();
  return text.length > 8 && !BARE_HTTP.test(text) && !text.startsWith('{') && !text.startsWith('[');
};

export function presentErrorMessage(error: AppError): string {
  if (error.message?.includes('NT_STATUS_')) return humanizeFileServerMessage(error.message);
  const byCode = codeMessage(error.code);
  if (byCode) return byCode;
  // A refusal explained by the server (« Vous ne pouvez pas désactiver votre propre compte. ») says more than the status
  if (error.status && error.status >= 400 && error.status < 500 && error.status !== 401 && isExplained(error.message)) return t(String(error.message));
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
