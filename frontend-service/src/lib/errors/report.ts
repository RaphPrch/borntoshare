import { codeMessage } from './presenters';
import { t } from '$lib/i18n';
import { logAppError } from '../logging/logger';
import { toAppError } from './normalize';
import { notifyError } from './notify';
import type { AppError } from './types';

const GENERIC_ERROR_MESSAGES = new Set(['Unexpected error', 'Backend error', 'Network error', 'Request timeout']);

/** True for transport-level messages that say nothing about what failed. */
export function isGenericErrorMessage(message: string | null | undefined): boolean {
  const text = String(message ?? '').trim();
  // Messages are translated when created: compare in both forms
  return !text || GENERIC_ERROR_MESSAGES.has(text) || [...GENERIC_ERROR_MESSAGES].some((m) => t(m) === text);
}

/** Normalizes and logs a UI failure; generic transport messages are replaced by `fallback`. */
export function toUiAppError(
  error: unknown,
  fallback: string,
  source: AppError['source'] = 'ui',
  context?: Record<string, unknown>
): AppError {
  const normalized = toAppError(error, { source });
  const known = codeMessage(normalized.code);
  const appError = known
    ? { ...normalized, message: known }
    : isGenericErrorMessage(normalized.message)
      ? { ...normalized, message: fallback }
      : normalized;
  logAppError(appError, context);
  return appError;
}

/** Logs and toasts a UI action failure, then returns the message to show inline. */
export function reportUiError(error: unknown, fallback: string, action: string): string {
  const appError = toUiAppError(error, fallback, 'ui', { action });
  notifyError(appError);
  return appError.message;
}
